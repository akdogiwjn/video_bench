#!/usr/bin/env python3
"""transcribe adapter — wraps LocalASRNode. E3: ASR/音频理解."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _adapter_base import run_adapter, parse_json_arg


def main():
    parser = argparse.ArgumentParser(description="transcribe: ASR on video clips using funasr")
    parser.add_argument("--clips", required=True, help="JSON output from split_shots ({clips: [...]})")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    clips_data = parse_json_arg(args.clips)
    clips = clips_data.get("clips", clips_data) if isinstance(clips_data, dict) else clips_data

    inputs = {"split_shots": {"clips": clips}}

    from open_storyline.nodes.core_nodes.asr_node import LocalASRNode
    sys.exit(run_adapter("transcribe", lambda s: LocalASRNode(s), "process", inputs, args.output_dir))


if __name__ == "__main__":
    main()
