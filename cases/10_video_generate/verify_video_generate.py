#!/usr/bin/env python3
"""SUB-NET-VIDEO-GEN-01 verifier: L0 + L1 layers for agentic multi-shot video generation.

Fixes:
- #24: L0 validates JSON content (script has scenes, storyboard has shots, ref count in gate)
- #25: L1 checks 9:16 aspect ratio (not just short_side >= 720)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run_ffprobe(video_path: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", video_path],
        capture_output=True, text=True,
    )
    return json.loads(result.stdout) if result.returncode == 0 else {}


def load_json_safe(path: Path) -> dict | list | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def check_l0(output_dir: Path) -> dict:
    checks = {}

    # script.json: must be valid JSON with content (scenes/story/episodes)
    # Handles both flat and nested structures (VideoClaw wraps in {"stage":..., "artifact":...})
    script_data = load_json_safe(output_dir / "script.json")
    script_valid = False
    if script_data is not None:
        # Deep search for script content keys at any nesting level
        def find_script_content(obj, depth=0):
            if depth > 5:
                return False
            if isinstance(obj, dict):
                keys_lower = {k.lower() for k in obj.keys()}
                if any(k in keys_lower for k in ("scenes", "story", "episodes", "logline", "title", "characters", "script")):
                    # Must have at least one non-trivial value
                    for k in ("scenes", "story", "episodes", "logline", "title", "characters"):
                        for actual_key in obj.keys():
                            if actual_key.lower() == k and obj[actual_key]:
                                return True
                for v in obj.values():
                    if find_script_content(v, depth + 1):
                        return True
            elif isinstance(obj, list) and len(obj) > 0:
                return find_script_content(obj[0], depth + 1)
            return False
        script_valid = find_script_content(script_data)
    checks["script_json"] = {
        "exists": (output_dir / "script.json").exists(),
        "valid_content": script_valid,
        "passed": script_valid,
    }

    # storyboard.json: must be valid JSON with >= 4 shots
    sb_data = load_json_safe(output_dir / "storyboard.json")
    shot_count = 0
    sb_valid = False
    if sb_data is not None:
        shots = []
        if isinstance(sb_data, list):
            shots = sb_data
        elif isinstance(sb_data, dict):
            # Deep search: collect ALL "shots" lists at any nesting level
            def find_all_shots(obj):
                result = []
                if isinstance(obj, dict):
                    if "shots" in obj and isinstance(obj["shots"], list):
                        result.extend(obj["shots"])
                    for v in obj.values():
                        result.extend(find_all_shots(v))
                elif isinstance(obj, list):
                    for item in obj:
                        result.extend(find_all_shots(item))
                return result
            shots = find_all_shots(sb_data)
        shot_count = len(shots)
        sb_valid = shot_count >= 4
    checks["storyboard_json"] = {
        "exists": (output_dir / "storyboard.json").exists(),
        "shot_count": shot_count,
        "passed": sb_valid,
    }

    # reference_images: count >= 2 and count is part of gate
    ref_dir = output_dir / "reference_images"
    ref_files = [f for f in ref_dir.glob("*") if f.is_file()] if ref_dir.exists() else []
    checks["reference_images"] = {
        "exists": ref_dir.exists(),
        "count": len(ref_files),
        "passed": len(ref_files) >= 2,
    }

    # video_clips: count >= 4
    clips_dir = output_dir / "video_clips"
    clip_files = [f for f in clips_dir.glob("*") if f.suffix in (".mp4", ".mov", ".avi", ".mkv", ".webm")] if clips_dir.exists() else []
    checks["video_clips"] = {
        "exists": clips_dir.exists(),
        "count": len(clip_files),
        "passed": len(clip_files) >= 4,
    }

    # final render
    final = output_dir / "final.mp4"
    checks["final_render"] = {
        "exists": final.exists(),
        "bytes": final.stat().st_size if final.exists() else 0,
        "passed": final.exists() and final.stat().st_size > 10240,
    }
    return checks


def check_aspect_ratio(w: int, h: int) -> dict:
    """Check if aspect ratio is approximately 9:16 (0.5625)."""
    if w == 0 or h == 0:
        return {"passed": False, "error": "zero dimensions"}
    ratio = w / h
    target = 9 / 16  # 0.5625
    tolerance = 0.05  # allow 0.5125 - 0.6125
    is_portrait = h > w
    passed = is_portrait and abs(ratio - target) <= tolerance
    return {
        "width": w, "height": h,
        "ratio": round(ratio, 4),
        "target": round(target, 4),
        "is_portrait": is_portrait,
        "passed": passed,
    }


def check_l1(output_dir: Path, constraints: dict) -> dict:
    final = output_dir / "final.mp4"
    checks = {}
    if not final.exists():
        checks["final_mp4"] = {"exists": False, "passed": False}
        return checks

    probe = run_ffprobe(str(final))
    fmt = probe.get("format", {})
    streams = probe.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    duration = float(fmt.get("duration", 0))
    min_dur, max_dur = constraints.get("duration_range_seconds", [30, 45])
    checks["duration"] = {
        "actual": round(duration, 1), "min": min_dur, "max": max_dur,
        "passed": min_dur <= duration <= max_dur,
    }
    checks["video_stream"] = {"exists": len(video_streams) > 0, "passed": len(video_streams) > 0}
    checks["audio_stream"] = {"exists": len(audio_streams) > 0, "passed": len(audio_streams) > 0}
    # #1 fix: real silencedetect with d=1, silence_ratio < 0.95
    audio_not_silent = False
    if len(audio_streams) > 0:
        import subprocess as sp
        result = sp.run(
            ["ffmpeg", "-i", str(final), "-af", "silencedetect=noise=-50dB:d=1", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        stderr = result.stderr
        import re
        silences = re.findall(r"silence_duration: ([\d.]+)", stderr)
        total_silence = sum(float(s) for s in silences) if silences else 0
        silence_ratio = total_silence / duration if duration > 0 else 1.0
        audio_not_silent = silence_ratio < 0.95
        checks["audio_not_silent"] = {
            "total_silence_s": round(total_silence, 2),
            "silence_ratio": round(silence_ratio, 3),
            "passed": audio_not_silent,
        }

    if video_streams:
        vs = video_streams[0]
        w = int(vs.get("width", 0))
        h = int(vs.get("height", 0))
        short_side = min(w, h)
        min_res = constraints.get("min_resolution_short_side", 720)
        checks["resolution"] = {
            "width": w, "height": h, "short_side": short_side,
            "min_required": min_res, "passed": short_side >= min_res,
        }
        checks["aspect_ratio_9_16"] = check_aspect_ratio(w, h)

    checks["file_size"] = {"bytes": final.stat().st_size, "passed": final.stat().st_size > 10240}
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--constraints", required=True)
    parser.add_argument("--result-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    with open(args.constraints) as f:
        constraints = json.load(f)
    result_dir = Path(args.result_dir)

    l0 = check_l0(output_dir)
    l1 = check_l1(output_dir, constraints)

    # L0: all checks must pass (including content validation and counts)
    l0_pass = all(c.get("passed", False) for c in l0.values())
    l1_pass = all(c.get("passed", False) for c in l1.values()) if l1 else False

    result = {
        "case_id": "SUB-NET-VIDEO-GEN-01",
        "L0_process": l0, "L0_pass": l0_pass,
        "L1_deterministic": l1, "L1_pass": l1_pass,
        "hard_pass": l0_pass and l1_pass,
        "L2_pending": True,
    }
    out_path = result_dir / "business_verification.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["hard_pass"] else 1)


if __name__ == "__main__":
    main()
