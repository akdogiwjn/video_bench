#!/usr/bin/env python3
"""Parse OpenClaw stderr.log + container.log to count API calls and check against budget.

Status: advisory only. Budget results are reported but NOT included in overall_pass
until RealLLMClient adds explicit api_calls.jsonl instrumentation for reliable counting.

Fixes:
- case_type "generate" maps to budget key "gen"
- VLM calls counted
- EDIT budget field names matched (max_tts_calls vs max_tts_api_calls)
- budget_pass reported in formal summary (advisory, not hard gate)
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
        return {"llm": 0, "vlm": 0, "image": 0, "video": 0, "tts": 0, "total": 0}

    content = stderr_path.read_text(encoding="utf-8", errors="replace")

    # LLM calls: deepseek model-fetch responses
    llm_calls = len(re.findall(r"\[model-fetch\] response provider=deepseek.*?status=200", content))

    # VLM calls: look for qwen-vl or VLM-related API calls
    vlm_calls = len(re.findall(r"qwen-vl|vlm.*complete|VLM", content, re.IGNORECASE))

    # Image generation
    image_calls = content.count("image-synthesis") + content.count("t2i")

    # Video generation
    video_calls = content.count("video-synthesis") + content.count("i2v") + content.count("text2video")

    # TTS calls
    tts_calls = content.count("edge_tts") + content.count("tts") + content.count("voiceover")

    total = llm_calls + vlm_calls + image_calls + video_calls + tts_calls

    return {
        "llm": llm_calls,
        "vlm": vlm_calls,
        "image": image_calls,
        "video": video_calls,
        "tts": tts_calls,
        "total": total,
    }


def check_budget(calls: dict, budget: dict) -> dict:
    """Check if API call counts exceed budget. Handles all field name variants."""
    results = {}
    exceeded = False

    # Field name mapping: our key → possible budget JSON keys
    field_map = {
        "llm": ["max_llm_calls"],
        "vlm": ["max_vlm_calls"],
        "image": ["max_image_api_calls", "max_image_calls"],
        "video": ["max_video_api_calls", "max_video_calls"],
        "tts": ["max_tts_api_calls", "max_tts_calls"],
    }

    for call_type, count in calls.items():
        if call_type == "total":
            continue

        possible_keys = field_map.get(call_type, [])
        limit = None
        for key in possible_keys:
            if key in budget:
                limit = budget[key]
                break

        if limit is not None and count > limit:
            results[call_type] = {"count": count, "limit": limit, "exceeded": True}
            exceeded = True
        elif limit is not None:
            results[call_type] = {"count": count, "limit": limit, "exceeded": False}
        else:
            results[call_type] = {"count": count, "limit": None, "exceeded": False, "note": "no budget defined"}

    return {
        "call_counts": calls,
        "budget_check": results,
        "budget_exceeded": exceeded,
        "budget_pass": not exceeded,
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

    # #4a fix: map "generate" → "gen" key in budget_freeze
    budget_key = "gen" if args.case_type == "generate" else "edit"
    budget = pricing.get("budget_freeze", {}).get(budget_key, {})

    report = check_budget(calls, budget)

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(1 if report["budget_exceeded"] else 0)


if __name__ == "__main__":
    main()
