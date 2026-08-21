#!/usr/bin/env python3
"""generate_voiceover adapter — wraps GenerateVoiceoverNode. E7: 配音 (conditional)."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _adapter_base import run_adapter, parse_json_arg


def main():
    parser = argparse.ArgumentParser(description="generate_voiceover: TTS voiceover from script text")
    parser.add_argument("--script", required=True, help="JSON output from generate_script")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    script_data = parse_json_arg(args.script)

    inputs = {
        "generate_script": script_data,
        "user_request": "",
    }

    from open_storyline.nodes.core_nodes.generate_voiceover import GenerateVoiceoverNode
    sys.exit(run_adapter("generate_voiceover", lambda s: GenerateVoiceoverNode(s), "process", inputs, args.output_dir))


if __name__ == "__main__":
    main()
