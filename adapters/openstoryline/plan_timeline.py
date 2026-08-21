#!/usr/bin/env python3
"""plan_timeline adapter — wraps PlanTimelineNode. E8: 时间线规划."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _adapter_base import run_adapter, parse_json_arg


def main():
    parser = argparse.ArgumentParser(description="plan_timeline: plan final video timeline with clips, subtitles, audio")
    parser.add_argument("--groups", required=True, help="JSON output from group_clips")
    parser.add_argument("--clips", required=True, help="JSON output from split_shots")
    parser.add_argument("--script", required=True, help="JSON output from generate_script")
    parser.add_argument("--bgm", required=True, help="JSON output from select_bgm")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    groups_data = parse_json_arg(args.groups)
    clips_data = parse_json_arg(args.clips)
    script_data = parse_json_arg(args.script)
    bgm_data = parse_json_arg(args.bgm)

    inputs = {
        "group_clips": groups_data,
        "split_shots": clips_data,
        "generate_script": script_data,
        "select_bgm": bgm_data,
        "user_request": "",
    }

    from open_storyline.nodes.core_nodes.plan_timeline import PlanTimelineNode
    sys.exit(run_adapter("plan_timeline", lambda s: PlanTimelineNode(s), "process", inputs, args.output_dir))


if __name__ == "__main__":
    main()
