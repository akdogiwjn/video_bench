#!/usr/bin/env python3
"""inspect_media adapter — wraps LoadMediaNode. E1: 素材加载与盘点."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _adapter_base import run_adapter, parse_json_arg, load_settings

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "openstoryline" / "src"))
sys.path.insert(0, str(load_settings.__module__.rsplit(".", 1)[0] and "/opt/openstoryline/src" or "/opt/openstoryline/src"))


def main():
    parser = argparse.ArgumentParser(description="inspect_media: load and index input media files")
    parser.add_argument("--inputs", required=True, help="JSON array of {path, orig_path}")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    raw_inputs = parse_json_arg(args.inputs)
    if isinstance(raw_inputs, list):
        media_inputs = []
        for i, item in enumerate(raw_inputs, 1):
            media_inputs.append({
                "path": item.get("path", item.get("orig_path", "")),
                "orig_path": item.get("orig_path", item.get("path", "")),
                "orig_md5": item.get("orig_md5", ""),
            })
    else:
        media_inputs = [raw_inputs]

    inputs = {"inputs": media_inputs, "user_request": "", "user_request_llm_input": ""}

    from open_storyline.nodes.core_nodes.load_media import LoadMediaNode
    sys.exit(run_adapter("inspect_media", lambda s: LoadMediaNode(s), "process", inputs, args.output_dir))


if __name__ == "__main__":
    main()
