#!/usr/bin/env python3
"""render_video adapter — wraps RenderVideoNode. E9: 渲染与成片检查."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _adapter_base import run_adapter, parse_json_arg


def main():
    parser = argparse.ArgumentParser(description="render_video: render final video from timeline using moviepy+ffmpeg")
    parser.add_argument("--timeline", required=True, help="JSON output from plan_timeline")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    timeline_data = parse_json_arg(args.timeline)

    inputs = {
        "plan_timeline": timeline_data,
        "user_request": "",
    }

    from open_storyline.nodes.core_nodes.render_video import RenderVideoNode
    sys.exit(run_adapter("render_video", lambda s: RenderVideoNode(s), "process", inputs, args.output_dir))


if __name__ == "__main__":
    main()
