#!/usr/bin/env python3
"""split_shots adapter — wraps SplitShotsNode. E2: 镜头切分/素材结构化."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _adapter_base import run_adapter, parse_json_arg


def main():
    parser = argparse.ArgumentParser(description="split_shots: detect shot boundaries using TransNetV2")
    parser.add_argument("--media", required=True, help="JSON output from inspect_media ({media: [...]})")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-shot-duration", type=int, default=1000, help="min shot duration in ms")
    parser.add_argument("--max-shot-duration", type=int, default=30000, help="max shot duration in ms")
    args = parser.parse_args()

    media_data = parse_json_arg(args.media)
    media_list = media_data.get("media", media_data) if isinstance(media_data, dict) else media_data

    inputs = {
        "load_media": {"media": media_list},
        "min_shot_duration": args.min_shot_duration,
        "max_shot_duration": args.max_shot_duration,
    }

    from open_storyline.nodes.core_nodes.split_shots import SplitShotsNode
    sys.exit(run_adapter("split_shots", lambda s: SplitShotsNode(s), "process", inputs, args.output_dir))


if __name__ == "__main__":
    main()
