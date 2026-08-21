#!/usr/bin/env python3
"""select_bgm adapter — wraps SelectBGMNode. E7b: BGM 选择."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _adapter_base import run_adapter, parse_json_arg


def main():
    parser = argparse.ArgumentParser(description="select_bgm: select background music from local library")
    parser.add_argument("--user-request", required=True, help="user editing brief text")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    inputs = {
        "user_request": args.user_request,
        "filter_include": {},
        "filter_exclude": {},
    }

    from open_storyline.nodes.core_nodes.select_bgm import SelectBGMNode
    sys.exit(run_adapter("select_bgm", lambda s: SelectBGMNode(s), "process", inputs, args.output_dir))


if __name__ == "__main__":
    main()
