#!/usr/bin/env python3
"""SUB-CPU-VIDEO-EDIT-01 verifier: L0 + L1 layers for agentic material-based video editing.

Fixes:
- #25: 9:16 aspect ratio check (not just short_side >= 720)
- #26: BGM verification (from select_bgm_result or timeline)
- #27: Subtitle verification (SRT non-empty + format check)
- #28: Timeline verifier (source_ref valid, start < end, duration alignment, min sources)
"""
from __future__ import annotations

import argparse
import json
import re
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


def check_aspect_ratio(w: int, h: int) -> dict:
    if w == 0 or h == 0:
        return {"passed": False, "error": "zero dimensions"}
    ratio = w / h
    target = 9 / 16
    tolerance = 0.05
    is_portrait = h > w
    passed = is_portrait and abs(ratio - target) <= tolerance
    return {"width": w, "height": h, "ratio": round(ratio, 4), "target": round(target, 4), "passed": passed}


def is_valid_srt(path: Path) -> bool:
    """Check that SRT file is non-empty and has valid SRT format."""
    if not path.exists() or path.stat().st_size < 10:
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
        # SRT format: index, timestamp range, text — repeated
        # Check for at least one timestamp pattern
        return bool(re.search(r"\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}", content))
    except OSError:
        return False


def check_l0(output_dir: Path) -> dict:
    checks = {}
    for name in ["media_inventory.json", "shot_segments.json", "asr_transcript.json",
                 "clip_captions.json", "selection_and_groups.json", "script.json", "timeline.json"]:
        path = output_dir / name
        data = load_json_safe(path)
        checks[name] = {
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else 0,
            "valid_json": data is not None,
            "passed": data is not None,
        }

    # Real shot segmentation check (#12 fix): at least one source has >=2 segments
    seg_data = load_json_safe(output_dir / "shot_segments.json")
    real_split = False
    if seg_data is not None:
        segments = seg_data if isinstance(seg_data, list) else seg_data.get("clips", seg_data.get("segments", []))
        if isinstance(segments, list):
            # Group by media_id
            by_source = {}
            for seg in segments:
                sr = seg.get("source_ref", {}) if isinstance(seg, dict) else {}
                mid = sr.get("media_id", "unknown")
                by_source.setdefault(mid, []).append(seg)
            # At least one source has >=2 segments with internal boundaries
            for mid, segs in by_source.items():
                if len(segs) >= 2:
                    real_split = True
                    break
    checks["real_shot_segmentation"] = {"verified": real_split, "passed": real_split}

    final = output_dir / "final.mp4"
    checks["final_render"] = {
        "exists": final.exists(),
        "bytes": final.stat().st_size if final.exists() else 0,
        "passed": final.exists() and final.stat().st_size > 51200,
    }
    return checks


def check_timeline(output_dir: Path, constraints: dict, ground_truth: dict, final_duration: float) -> dict:
    """Enhanced timeline verification (#28)."""
    checks = {}
    tl_data = load_json_safe(output_dir / "timeline.json")
    
    if tl_data is None:
        checks["timeline_exists"] = {"passed": False}
        checks["timeline_valid"] = {"passed": False}
        checks["multiple_sources"] = {"passed": False, "source_count": 0}
        checks["distractor_excluded"] = {"passed": True, "uses_distractor": False}
        checks["bgm_present"] = {"passed": False}
        return checks

    # Build provenance mapping (#13 fix): fixture asset_id → openstoryline media_id
    asset_to_media = {}
    inv_data = load_json_safe(output_dir / "media_inventory.json")
    if inv_data is not None:
        inv_list = inv_data if isinstance(inv_data, list) else inv_data.get("media", inv_data.get("result", {}).get("media", []))
        if isinstance(inv_list, list):
            for m in inv_list:
                if isinstance(m, dict):
                    mid = m.get("media_id", "")
                    orig_path = m.get("orig_path", "")
                    # Map fixture filename → media_id
                    if orig_path:
                        asset_to_media[orig_path] = mid

    # Check timeline using provenance mapping
    clips = tl_data if isinstance(tl_data, list) else tl_data.get("clips", tl_data.get("segments", []))
    if not isinstance(clips, list):
        clips = []

    checks["timeline_exists"] = {"passed": True}

    valid_clips = 0
    source_files = set()
    distractor_ids = set(ground_truth.get("distractor_asset_ids", []))
    uses_distractor = False
    has_bgm = False
    negative_ts = False

    for clip in clips:
        if not isinstance(clip, dict):
            continue
        sr = clip.get("source_ref", {})
        media_id = sr.get("media_id", "")
        orig_path = clip.get("orig_path", "")
        s = sr.get("start")
        e = sr.get("end")

        if s is not None and e is not None:
            if s < 0 or e < 0:
                negative_ts = True
            elif e > s:
                valid_clips += 1

        if media_id:
            source_files.add(media_id)
            # Check if this media_id maps to a distractor via provenance
            for asset_id, mid in asset_to_media.items():
                if mid == media_id and asset_id in distractor_ids:
                    uses_distractor = True

        # BGM check (#14 fix): only count explicit bgm, not any audio
        if clip.get("kind") == "bgm" or clip.get("type") == "bgm" or \
           "bgm" in str(clip.get("path", "")).lower() or \
           "bgm" in str(clip.get("source", "")).lower():
            has_bgm = True

    # Also check select_bgm_result (#14)
    bgm_data = load_json_safe(output_dir / "select_bgm_result.json")
    bgm_valid = False
    if bgm_data is not None:
        bgm = bgm_data.get("bgm", bgm_data.get("result", {}).get("bgm", {}))
        if isinstance(bgm, dict) and bgm.get("path"):
            bgm_valid = True
        elif isinstance(bgm, str) and bgm:
            bgm_valid = True

    checks["timeline_valid"] = {
        "clip_count": len(clips),
        "valid_clips": valid_clips,
        "has_negative_timestamps": negative_ts,
        "passed": valid_clips > 0 and not negative_ts,
    }

    min_sources = constraints.get("min_source_files_used", 3)
    checks["multiple_sources"] = {
        "source_count": len(source_files),
        "min_required": min_sources,
        "passed": len(source_files) >= min_sources,
    }

    checks["distractor_excluded"] = {
        "distractor_ids": list(distractor_ids),
        "uses_distractor": uses_distractor,
        "provenance_mapping": len(asset_to_media) > 0,
        "passed": not uses_distractor,
    }

    checks["bgm_present"] = {
        "found_in_timeline": has_bgm,
        "found_in_bgm_result": bgm_valid,
        "passed": has_bgm or bgm_valid,
    }

    # Timeline duration vs final duration alignment
    tl_duration = 0
    for clip in clips:
        if isinstance(clip, dict):
            sr = clip.get("source_ref", {})
            s = sr.get("start", 0) or 0
            e = sr.get("end", 0) or 0
            if e > s:
                tl_duration += (e - s)
    if final_duration > 0 and tl_duration > 0:
        diff_pct = abs(tl_duration / 1000 - final_duration) / final_duration
        checks["timeline_duration_alignment"] = {
            "timeline_duration_s": round(tl_duration / 1000, 1),
            "final_duration_s": round(final_duration, 1),
            "diff_pct": round(diff_pct * 100, 1),
            "passed": diff_pct < 0.3,  # within 30%
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
        "actual": round(duration, 1), "min": min_dur, "max": max_dur,
        "passed": min_dur <= duration <= max_dur,
    }
    checks["video_stream"] = {"exists": len(video_streams) > 0, "passed": len(video_streams) > 0}
    checks["audio_stream"] = {"exists": len(audio_streams) > 0, "passed": len(audio_streams) > 0}

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

    # Subtitle verification (#27): SRT must be non-empty and valid format
    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
    srt_paths = [output_dir / "final.srt", output_dir / "subtitles.srt"]
    srt_valid = any(is_valid_srt(p) for p in srt_paths)
    checks["subtitle"] = {
        "stream_exists": len(subtitle_streams) > 0,
        "srt_valid": srt_valid,
        "passed": len(subtitle_streams) > 0 or srt_valid,
    }

    # Timeline + BGM + distractor checks (#26, #28)
    checks.update(check_timeline(output_dir, constraints, ground_truth, duration))

    checks["file_size"] = {"bytes": final.stat().st_size, "passed": final.stat().st_size > 51200}
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
    l0_pass = all(l0.get(n, {}).get("passed", False) for n in l0_required) and \
              l0.get("real_shot_segmentation", {}).get("passed", False) and \
              l0.get("final_render", {}).get("passed", False)
    l1_pass = all(c.get("passed", False) for c in l1.values()) if l1 else False

    result = {
        "case_id": "SUB-CPU-VIDEO-EDIT-01",
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
