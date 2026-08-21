#!/usr/bin/env python3
"""generate_script adapter — wraps GenerateScriptNode. E6: 叙事/文案组织."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _adapter_base import run_adapter, parse_json_arg


def main():
    parser = argparse.ArgumentParser(description="generate_script: generate video narration script and subtitles")
    parser.add_argument("--groups", required=True, help="JSON output from group_clips ({groups: [...]})")
    parser.add_argument("--clips", required=True, help="JSON output from split_shots ({clips: [...]})")
    parser.add_argument("--captions", required=True, help="JSON output from understand_clips ({clip_captions: [...]})")
    parser.add_argument("--user-request", required=True, help="user editing brief text")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    groups_data = parse_json_arg(args.groups)
    groups = groups_data.get("groups", groups_data) if isinstance(groups_data, dict) else groups_data

    clips_data = parse_json_arg(args.clips)
    clips = clips_data.get("clips", clips_data) if isinstance(clips_data, dict) else clips_data

    captions_data = parse_json_arg(args.captions)
    clip_captions = captions_data.get("clip_captions", captions_data) if isinstance(captions_data, dict) else captions_data

    inputs = {
        "split_shots": {"clips": clips},
        "understand_clips": {"clip_captions": clip_captions, "overall": ""},
        "group_clips": {"groups": groups},
        "user_request": args.user_request,
    }

    from open_storyline.nodes.core_nodes.generate_script import GenerateScriptNode
    sys.exit(run_adapter("generate_script", lambda s: GenerateScriptNode(s), "process", inputs, args.output_dir))


if __name__ == "__main__":
    main()
