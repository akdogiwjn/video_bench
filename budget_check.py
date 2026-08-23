#!/usr/bin/env python3
"""Parse OpenClaw stderr.log to count API calls and check against budget.

Usage:
  python3 budget_check.py --stderr-log output/openclaw_agent.stderr.log \
    --budget evidence/api_pricing_snapshot.json --output output/budget_report.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def parse_container_log(log_path: Path) -> dict:
    """Parse container.log for VideoClaw backend API calls (image/video generation)."""
    if not log_path.exists():
        return {"image": 0, "video": 0}
    content = log_path.read_text(encoding="utf-8", errors="replace")
    image_calls = content.count("image-synthesis") + content.count("t2i")
    video_calls = content.count("video_generation") + content.count("generate-video")
    return {"image": image_calls, "video": video_calls}


def parse_api_calls(stderr_path: Path) -> dict:
    """Count API calls from OpenClaw provider-transport-fetch log lines."""
    if not stderr_path.exists():
        return {"llm": 0, "image": 0, "video": 0, "tts": 0, "total": 0}

    content = stderr_path.read_text(encoding="utf-8", errors="replace")

    # Pattern: [provider-transport-fetch] [model-fetch] response provider=deepseek ... status=200
    # Also check for dashscope image/video generation calls
    llm_calls = len(re.findall(r"\[model-fetch\] response provider=deepseek.*?status=200", content))
    
    # Image generation calls (from VideoClaw backend, not in OpenClaw log)
    # These would appear in container.log, not stderr
    image_calls = content.count("image-synthesis") + content.count("t2i")
    
    # Video generation calls
    video_calls = content.count("video-synthesis") + content.count("i2v") + content.count("text2video")
    
    # TTS calls
    tts_calls = content.count("tts") + content.count("voiceover") + content.count("edge_tts")
    
    total = llm_calls + image_calls + video_calls + tts_calls
    
    return {
        "llm": llm_calls,
        "image": image_calls,
        "video": video_calls,
        "tts": tts_calls,
        "total": total,
    }


def check_budget(calls: dict, budget: dict) -> dict:
    """Check if API call counts exceed budget."""
    results = {}
    exceeded = False

    budget_map = {
        "llm": budget.get("max_llm_calls"),
        "image": budget.get("max_image_api_calls"),
        "video": budget.get("max_video_api_calls"),
        "tts": budget.get("max_tts_api_calls"),
    }

    for call_type, count in calls.items():
        if call_type == "total":
            continue
        limit = budget_map.get(call_type)
        if limit is not None and count > limit:
            results[call_type] = {"count": count, "limit": limit, "exceeded": True}
            exceeded = True
        elif limit is not None:
            results[call_type] = {"count": count, "limit": limit, "exceeded": False}
        else:
            results[call_type] = {"count": count, "limit": None, "exceeded": False}

    return {
        "call_counts": calls,
        "budget_check": results,
        "budget_exceeded": exceeded,
        "status": "BUDGET_EXCEEDED" if exceeded else "OK",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stderr-log", required=True)
    parser.add_argument("--budget", required=True, help="Path to api_pricing_snapshot.json")
    parser.add_argument("--case-type", required=True, choices=["generate", "edit"], help="Select GEN or EDIT budget")
    parser.add_argument("--container-log", default="", help="Path to container.log for GEN API calls")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    calls = parse_api_calls(Path(args.stderr_log))

    # For GEN, also parse container.log for image/video API calls
    if args.case_type == "generate" and args.container_log:
        container_calls = parse_container_log(Path(args.container_log))
        calls["image"] = calls.get("image", 0) + container_calls.get("image", 0)
        calls["video"] = calls.get("video", 0) + container_calls.get("video", 0)

    with open(args.budget) as f:
        pricing = json.load(f)
    budget = pricing.get("budget_freeze", {}).get(args.case_type, {})

    report = check_budget(calls, budget)

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(1 if report["budget_exceeded"] else 0)


if __name__ == "__main__":
    main()
