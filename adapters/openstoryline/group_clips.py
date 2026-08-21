#!/usr/bin/env python3
"""group_clips adapter — wraps GroupClipsNode. E5b: 片段分组."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _adapter_base import run_adapter, parse_json_arg


def main():
    parser = argparse.ArgumentParser(description="group_clips: group filtered clips into narrative segments")
    parser.add_argument("--filter-result", required=True, help="JSON output from filter_clips")
    parser.add_argument("--user-request", required=True, help="user editing brief text")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    filter_data = parse_json_arg(args.filter_result)

    inputs = {
        "filter_clips": filter_data,
        "user_request": args.user_request,
    }

    from open_storyline.nodes.core_nodes.group_clips import GroupClipsNode
    sys.exit(run_adapter("group_clips", lambda s: GroupClipsNode(s), "process", inputs, args.output_dir))


if __name__ == "__main__":
    main()
