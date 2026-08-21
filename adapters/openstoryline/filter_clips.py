#!/usr/bin/env python3
"""filter_clips adapter — wraps FilterClipsNode. E5: 内容筛选与素材选择."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _adapter_base import run_adapter, parse_json_arg


def main():
    parser = argparse.ArgumentParser(description="filter_clips: filter clips based on descriptions and user requirements")
    parser.add_argument("--clip-captions", required=True, help="JSON output from understand_clips ({clip_captions: [...]})")
    parser.add_argument("--clips", required=True, help="JSON output from split_shots ({clips: [...]})")
    parser.add_argument("--user-request", required=True, help="user editing brief text")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    captions_data = parse_json_arg(args.clip_captions)
    clip_captions = captions_data.get("clip_captions", captions_data) if isinstance(captions_data, dict) else captions_data

    clips_data = parse_json_arg(args.clips)
    clips = clips_data.get("clips", clips_data) if isinstance(clips_data, dict) else clips_data

    inputs = {
        "understand_clips": {"clip_captions": clip_captions},
        "split_shots": {"clips": clips},
        "user_request": args.user_request,
    }

    from open_storyline.nodes.core_nodes.filter_clips import FilterClipsNode
    sys.exit(run_adapter("filter_clips", lambda s: FilterClipsNode(s), "process", inputs, args.output_dir))


if __name__ == "__main__":
    main()
