#!/usr/bin/env python3
"""understand_clips adapter — wraps UnderstandClipsNode. E4: 视觉/多模态内容理解.

Fix #11: upstream UnderstandClipsNode expects inputs["media"] to be a dict
keyed by media_id (e.g. {"media_0001": {...}}), not {"media": {"media": [...]}}.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _adapter_base import run_adapter, parse_json_arg


def main():
    parser = argparse.ArgumentParser(description="understand_clips: VLM analysis of clip content")
    parser.add_argument("--clips", required=True, help="JSON output from split_shots ({clips: [...]})")
    parser.add_argument("--media", required=True, help="JSON output from inspect_media ({media: [...]})")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    clips_data = parse_json_arg(args.clips)
    clips = clips_data.get("clips", clips_data) if isinstance(clips_data, dict) else clips_data

    media_data = parse_json_arg(args.media)
    media_list = media_data.get("media", media_data) if isinstance(media_data, dict) else media_data

    # Build media dict keyed by media_id (upstream expects this)
    media_dict = {}
    if isinstance(media_list, list):
        for m in media_list:
            mid = m.get("media_id", "")
            if mid:
                media_dict[mid] = m
    elif isinstance(media_list, dict) and "media" in media_list:
        for m in media_list["media"]:
            mid = m.get("media_id", "")
            if mid:
                media_dict[mid] = m

    inputs = {
        "split_shots": {"clips": clips},
        "media": media_dict,  # upstream does: load_media = inputs["media"]; media_item = load_media.get(media_id)
        "user_request": "",
    }

    from open_storyline.nodes.core_nodes.understand_clips import UnderstandClipsNode
    sys.exit(run_adapter("understand_clips", lambda s: UnderstandClipsNode(s), "process", inputs, args.output_dir))


if __name__ == "__main__":
    main()
