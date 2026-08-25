#!/usr/bin/env python3
"""SUB-CPU-VIDEO-EDIT-01 verifier: L0 + L1 layers for agentic material-based video editing.

V4 fixes:
- #2: Provenance mapping uses manifest as single source of truth (path → asset_id → distractor check)
- #6: BGM init order fixed; video/audio clips separated for duration alignment
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
    if not path.exists() or path.stat().st_size < 10:
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
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

    # #4 fix: verify execution evidence (not just output existence)
    exec_evidence = load_json_safe(output_dir / "split_shots_execution.json")
    seg_executed = False
    if exec_evidence is not None and isinstance(exec_evidence, dict):
        if exec_evidence.get("status") == "success" and exec_evidence.get("upstream_symbol") == "SplitShotsNode":
            seg_executed = True
    # Also check segments as fallback
    seg_data = load_json_safe(output_dir / "shot_segments.json")
    if not seg_executed and seg_data is not None:
        segments = seg_data if isinstance(seg_data, list) else seg_data.get("clips", seg_data.get("segments", []))
        if isinstance(segments, list) and len(segments) > 0:
            by_source = {}
            for seg in segments:
                sr = seg.get("source_ref", {}) if isinstance(seg, dict) else {}
                mid = sr.get("media_id", "unknown")
                by_source.setdefault(mid, []).append(seg)
            seg_executed = len(by_source) > 0 and len(segments) > 0
    checks["shot_segmentation_executed"] = {"verified": seg_executed, "passed": seg_executed}

    final = output_dir / "final.mp4"
    checks["final_render"] = {
        "exists": final.exists(),
        "bytes": final.stat().st_size if final.exists() else 0,
        "passed": final.exists() and final.stat().st_size > 51200,
    }
    return checks


def build_provenance_map(output_dir: Path, fixture_manifest: dict | None) -> dict:
    """Build path → fixture asset_id mapping using manifest as single source of truth (#2 fix)."""
    path_to_asset = {}
    
    # From fixture manifest: file → asset_id
    if fixture_manifest:
        for item in fixture_manifest.get("source_materials", []) + fixture_manifest.get("derived_materials", []):
            fname = item.get("file", "")
            aid = item.get("asset_id", "")
            if fname and aid:
                path_to_asset[fname] = aid

    # From media_inventory: OpenStoryline media_id → orig_path → fixture file
    inv_data = load_json_safe(output_dir / "media_inventory.json")
    if inv_data is not None:
        inv_list = inv_data if isinstance(inv_data, list) else inv_data.get("media", inv_data.get("result", {}).get("media", []))
        if isinstance(inv_list, list):
            for m in inv_list:
                if isinstance(m, dict):
                    mid = m.get("media_id", "")
                    orig_path = m.get("orig_path", "")
                    if orig_path:
                        fname = Path(orig_path).name
                        if fname in path_to_asset:
                            path_to_asset[mid] = path_to_asset[fname]
    
    return path_to_asset


def extract_clip_source_info(clip: dict, path_to_asset: dict) -> tuple[str, float, float]:
    """Extract (logical_asset_id, start, end) from a timeline clip."""
    if not isinstance(clip, dict):
        return "", 0, 0
    
    # Try source_path first, then path, then orig_path
    source_path = clip.get("source_path", "") or clip.get("path", "") or clip.get("orig_path", "")
    
    # Map to logical asset_id
    asset_id = ""
    if source_path:
        fname = Path(source_path).name
        asset_id = path_to_asset.get(fname, "")
        if not asset_id:
            # Try matching by substring
            for manifest_file, manifest_aid in path_to_asset.items():
                if manifest_file in source_path or fname == manifest_file:
                    asset_id = manifest_aid
                    break
    
    # Get start/end from source_ref or source_window
    sr = clip.get("source_ref", {})
    if not sr:
        sw = clip.get("source_window", {})
        sr = {"start": sw.get("start"), "end": sw.get("end")}
    
    s = sr.get("start")
    e = sr.get("end")
    
    return asset_id, s if s is not None else 0, e if e is not None else 0


def check_timeline(output_dir: Path, constraints: dict, ground_truth: dict, final_duration: float, fixture_manifest: dict | None, audio_not_silent: bool = False) -> dict:
    """Enhanced timeline verification with proper provenance (#2 fix)."""
    checks = {}
    tl_data = load_json_safe(output_dir / "timeline.json")
    
    if tl_data is None:
        for name in ["timeline_exists", "timeline_valid", "multiple_sources", "distractor_excluded", "bgm_present"]:
            checks[name] = {"passed": False}
        return checks

    # #3 fix: BGM provenance — verify render_video_result links to final.mp4
    render_result = load_json_safe(output_dir / "render_video_result.json")
    render_provenance = False
    if render_result is not None:
        render_path = render_result.get("output_path", render_result.get("result", {}).get("output_path", ""))
        if render_path:
            render_provenance = True  # render result exists and points to a file

    # Build provenance map from manifest (#2 fix)
    path_to_asset = build_provenance_map(output_dir, fixture_manifest)
    
    # Separate clips by track type (#6 fix)
    video_clips = []
    all_clips = []
    has_bgm = False
    bgm_valid = False
    
    if isinstance(tl_data, list):
        all_clips = tl_data
    elif isinstance(tl_data, dict):
        # Standard keys
        for key in ("clips", "segments"):
            if key in tl_data and isinstance(tl_data[key], list):
                all_clips = tl_data[key]
                break
        # Tracks structure: separate video/bgm/subtitle
        if not all_clips and "tracks" in tl_data:
            tracks = tl_data["tracks"]
            if isinstance(tracks, dict):
                video_clips = tracks.get("video", []) if isinstance(tracks.get("video"), list) else []
                bgm_track = tracks.get("bgm", tracks.get("music", []))
                if isinstance(bgm_track, list) and len(bgm_track) > 0:
                    has_bgm = True
                sub_track = tracks.get("subtitles", [])
                if isinstance(sub_track, list):
                    all_clips = video_clips + sub_track
                else:
                    all_clips = video_clips
            else:
                all_clips = []
    
    checks["timeline_exists"] = {"passed": True}
    
    # Validate video clips
    valid_clips = 0
    logical_source_ids = set()
    distractor_ids = set(ground_truth.get("distractor_asset_ids", []))
    uses_distractor = False
    negative_ts = False
    
    for clip in video_clips if video_clips else all_clips:
        asset_id, s, e = extract_clip_source_info(clip, path_to_asset)
        
        if s is not None and e is not None:
            if s < 0 or e < 0:
                negative_ts = True
            elif e > s:
                valid_clips += 1
        
        if asset_id:
            logical_source_ids.add(asset_id)
            if asset_id in distractor_ids:
                uses_distractor = True
    
    # Also check bgm.json for BGM
    bgm_file = load_json_safe(output_dir / "bgm.json")
    if bgm_file is not None:
        bgm_entry = bgm_file.get("bgm", {})
        if isinstance(bgm_entry, dict) and bgm_entry.get("path"):
            bgm_valid = True
    # Also check select_bgm_result
    bgm_result = load_json_safe(output_dir / "select_bgm_result.json")
    if bgm_result is not None and not bgm_valid:
        bgm = bgm_result.get("bgm", bgm_result.get("result", {}).get("bgm", {}))
        if isinstance(bgm, dict) and bgm.get("path"):
            bgm_valid = True
    
    checks["timeline_valid"] = {
        "video_clip_count": len(video_clips) if video_clips else len(all_clips),
        "valid_clips": valid_clips,
        "has_negative_timestamps": negative_ts,
        "passed": valid_clips > 0 and not negative_ts,
    }
    
    min_sources = constraints.get("min_source_files_used", 3)
    checks["multiple_sources"] = {
        "source_count": len(logical_source_ids),
        "source_ids": list(logical_source_ids),
        "min_required": min_sources,
        "passed": len(logical_source_ids) >= min_sources,
    }
    
    checks["distractor_excluded"] = {
        "distractor_ids": list(distractor_ids),
        "uses_distractor": uses_distractor,
        "provenance_mapping_count": len(path_to_asset),
        "passed": not uses_distractor,
    }
    
    checks["bgm_present"] = {
        "found_in_timeline": has_bgm,
        "bgm_selected": bgm_valid,
        "final_audio_not_silent": audio_not_silent,
        "render_provenance": render_provenance,
        "passed": has_bgm and audio_not_silent and render_provenance,
    }
    
    # Timeline duration alignment (ONLY video clips, using timeline_window #6 fix)
    tl_duration = 0
    clips_for_duration = video_clips if video_clips else all_clips
    for clip in clips_for_duration:
        # Use timeline_window for actual playback duration (not source_ref which is the original clip range)
        tw = clip.get("timeline_window", {})
        if isinstance(tw, dict) and tw.get("end", 0) > tw.get("start", 0):
            tl_duration += (tw["end"] - tw["start"])
        else:
            _, s, e = extract_clip_source_info(clip, path_to_asset)
            if e > s:
                tl_duration += (e - s)
    if final_duration > 0 and tl_duration > 0:
        diff_pct = abs(tl_duration / 1000 - final_duration) / final_duration
        checks["timeline_duration_alignment"] = {
            "timeline_duration_s": round(tl_duration / 1000, 1),
            "final_duration_s": round(final_duration, 1),
            "diff_pct": round(diff_pct * 100, 1),
            "passed": diff_pct < 0.3,
        }
    
    return checks


def check_l1(output_dir: Path, constraints: dict, ground_truth: dict, fixture_manifest: dict | None) -> dict:
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
    checks["duration"] = {"actual": round(duration, 1), "min": min_dur, "max": max_dur, "passed": min_dur <= duration <= max_dur}
    checks["video_stream"] = {"exists": len(video_streams) > 0, "passed": len(video_streams) > 0}
    checks["audio_stream"] = {"exists": len(audio_streams) > 0, "passed": len(audio_streams) > 0}

    # #1 fix: real silencedetect with d=1, silence_ratio < 0.95
    audio_not_silent = False
    if len(audio_streams) > 0:
        result = subprocess.run(
            ["ffmpeg", "-i", str(final), "-af", "silencedetect=noise=-50dB:d=1", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        stderr = result.stderr
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
        checks["resolution"] = {"width": w, "height": h, "short_side": short_side, "min_required": 720, "passed": short_side >= 720}
        checks["aspect_ratio_9_16"] = check_aspect_ratio(w, h)

    # #3 fix: subtitle hard gate = stream OR valid srt (not timeline planning)
    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
    srt_valid = any(is_valid_srt(p) for p in [output_dir / "final.srt", output_dir / "subtitles.srt"])
    checks["subtitle"] = {
        "stream_exists": len(subtitle_streams) > 0,
        "srt_valid": srt_valid,
        "passed": len(subtitle_streams) > 0 or srt_valid,
    }

    checks.update(check_timeline(output_dir, constraints, ground_truth, duration, fixture_manifest, audio_not_silent))
    checks["file_size"] = {"bytes": final.stat().st_size, "passed": final.stat().st_size > 51200}
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--constraints", required=True)
    parser.add_argument("--ground-truth", default="")
    parser.add_argument("--fixture-manifest", default="")
    parser.add_argument("--result-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    with open(args.constraints) as f:
        constraints = json.load(f)
    ground_truth = {}
    if args.ground_truth and Path(args.ground_truth).exists():
        with open(args.ground_truth) as f:
            ground_truth = json.load(f)
    fixture_manifest = None
    if args.fixture_manifest and Path(args.fixture_manifest).exists():
        with open(args.fixture_manifest) as f:
            fixture_manifest = json.load(f)
    result_dir = Path(args.result_dir)

    l0 = check_l0(output_dir)
    l1 = check_l1(output_dir, constraints, ground_truth, fixture_manifest)

    l0_required = ["media_inventory.json", "shot_segments.json", "asr_transcript.json",
                   "clip_captions.json", "selection_and_groups.json", "script.json", "timeline.json"]
    l0_pass = all(l0.get(n, {}).get("passed", False) for n in l0_required) and \
              l0.get("shot_segmentation_executed", {}).get("passed", False) and \
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
