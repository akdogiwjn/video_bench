#!/usr/bin/env python3
"""SUB-CPU-VIDEO-EDIT-01 verifier: L0 + L1 layers for agentic material-based video editing."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_ffprobe(video_path: str) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    return json.loads(result.stdout)


def check_l0(output_dir: Path) -> dict:
    checks = {}
    for name in [
        "media_inventory.json", "shot_segments.json", "asr_transcript.json",
        "clip_captions.json", "selection_and_groups.json", "script.json", "timeline.json"
    ]:
        path = output_dir / name
        checks[name] = {
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else 0,
            "has_content": path.exists() and path.stat().st_size > 10,
        }

    seg_path = output_dir / "shot_segments.json"
    real_split = False
    if seg_path.exists():
        try:
            seg_data = json.loads(seg_path.read_text())
            segments = seg_data if isinstance(seg_data, list) else seg_data.get("clips", seg_data.get("segments", []))
            if isinstance(segments, list) and len(segments) > 1:
                start_times = set()
                for seg in segments:
                    sr = seg.get("source_ref", {}) if isinstance(seg, dict) else {}
                    s = sr.get("start")
                    e = sr.get("end")
                    if s is not None and e is not None and e != sr.get("duration"):
                        start_times.add(s)
                real_split = len(start_times) > 0
        except (json.JSONDecodeError, TypeError):
            pass
    checks["real_shot_segmentation"] = {
        "verified": real_split,
        "passed": real_split,
    }

    final = output_dir / "final.mp4"
    checks["final_render"] = {
        "exists": final.exists(),
        "bytes": final.stat().st_size if final.exists() else 0,
    }
    return checks


def check_l1(output_dir: Path, constraints: dict, ground_truth: dict) -> dict:
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
    min_dur, max_dur = constraints.get("duration_range_seconds", [55, 65])
    checks["duration"] = {
        "actual": round(duration, 1),
        "min": min_dur,
        "max": max_dur,
        "passed": min_dur <= duration <= max_dur,
    }
    checks["video_stream"] = {
        "exists": len(video_streams) > 0,
        "passed": len(video_streams) > 0,
    }
    checks["audio_stream"] = {
        "exists": len(audio_streams) > 0,
        "passed": len(audio_streams) > 0,
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

    timeline_path = output_dir / "timeline.json"
    checks["timeline_valid"] = {
        "exists": timeline_path.exists(),
        "passed": False,
    }
    if timeline_path.exists():
        try:
            tl = json.loads(timeline_path.read_text())
            clips_in_timeline = tl if isinstance(tl, list) else tl.get("clips", tl.get("segments", []))
            if isinstance(clips_in_timeline, list) and len(clips_in_timeline) > 0:
                source_ids = set()
                for clip in clips_in_timeline:
                    sr = clip.get("source_ref", {}) if isinstance(clip, dict) else {}
                    media_id = sr.get("media_id", "")
                    if media_id:
                        source_ids.add(media_id)
                min_sources = constraints.get("min_source_files_used", 3)
                checks["multiple_sources"] = {
                    "source_count": len(source_ids),
                    "min_required": min_sources,
                    "passed": len(source_ids) >= min_sources,
                }
                checks["timeline_valid"]["passed"] = True
        except (json.JSONDecodeError, TypeError):
            pass

    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
    srt_exists = (output_dir / "final.srt").exists() or (output_dir / "subtitles.srt").exists()
    checks["subtitle"] = {
        "stream_exists": len(subtitle_streams) > 0,
        "srt_exists": srt_exists,
        "passed": len(subtitle_streams) > 0 or srt_exists,
    }

    if ground_truth:
        distractor_ids = set(ground_truth.get("distractor_asset_ids", []))
        timeline_path = output_dir / "timeline.json"
        uses_distractor = False
        if timeline_path.exists():
            try:
                tl = json.loads(timeline_path.read_text())
                clips_in_timeline = tl if isinstance(tl, list) else tl.get("clips", tl.get("segments", []))
                if isinstance(clips_in_timeline, list):
                    for clip in clips_in_timeline:
                        sr = clip.get("source_ref", {}) if isinstance(clip, dict) else {}
                        media_id = sr.get("media_id", "")
                        if media_id in distractor_ids:
                            uses_distractor = True
                            break
            except (json.JSONDecodeError, TypeError):
                pass
        checks["distractor_excluded"] = {
            "distractor_ids": list(distractor_ids),
            "uses_distractor": uses_distractor,
            "passed": not uses_distractor,
        }

    checks["file_size"] = {
        "bytes": final.stat().st_size,
        "passed": final.stat().st_size > 51200,
    }
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--constraints", required=True)
    parser.add_argument("--ground-truth", default="")
    parser.add_argument("--result-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    with open(args.constraints) as f:
        constraints = json.load(f)
    ground_truth = {}
    if args.ground_truth and Path(args.ground_truth).exists():
        with open(args.ground_truth) as f:
            ground_truth = json.load(f)
    result_dir = Path(args.result_dir)

    l0 = check_l0(output_dir)
    l1 = check_l1(output_dir, constraints, ground_truth)

    l0_required = ["media_inventory.json", "shot_segments.json", "asr_transcript.json",
                   "clip_captions.json", "selection_and_groups.json", "script.json", "timeline.json"]
    l0_pass = all(l0.get(n, {}).get("has_content", False) for n in l0_required) and \
              l0.get("real_shot_segmentation", {}).get("passed", False) and \
              l0.get("final_render", {}).get("exists", False)
    l1_pass = all(c.get("passed", False) for c in l1.values()) if l1 else False

    result = {
        "case_id": "SUB-CPU-VIDEO-EDIT-01",
        "L0_process": l0,
        "L0_pass": l0_pass,
        "L1_deterministic": l1,
        "L1_pass": l1_pass,
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
