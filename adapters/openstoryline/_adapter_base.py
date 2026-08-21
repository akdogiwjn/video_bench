#!/usr/bin/env python3
"""Shared helpers for OpenStoryline CLI adapters. Adapter only adapts; it does not decide."""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from dataclasses import dataclass
from typing import Any

OPENSTORYLINE_REPO = Path(os.environ.get("OPENSTORYLINE_REPO", "/opt/openstoryline"))
CONFIG_PATH = OPENSTORYLINE_REPO / "config.toml"


def load_settings():
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    from open_storyline.config import Settings

    with open(CONFIG_PATH, "rb") as f:
        config_data = tomllib.load(f)

    return Settings.model_validate(config_data, context={"config_dir": str(OPENSTORYLINE_REPO)})


@dataclass
class StubNodeSummary:
    messages: list = None

    def __post_init__(self):
        self.messages = []

    def info_for_user(self, msg, **kwargs):
        self.messages.append({"level": "info_user", "msg": msg})
        print(f"[INFO] {msg}", file=sys.stderr)

    def info_for_llm(self, msg):
        self.messages.append({"level": "info_llm", "msg": msg})

    def add_warning(self, msg, **kwargs):
        self.messages.append({"level": "warning", "msg": msg})
        print(f"[WARN] {msg}", file=sys.stderr)

    def add_error(self, msg, **kwargs):
        self.messages.append({"level": "error", "msg": msg})
        print(f"[ERROR] {msg}", file=sys.stderr)

    def debug_for_dev(self, msg):
        self.messages.append({"level": "debug", "msg": msg})

    def get_summary(self, artifact_id):
        return {"messages": self.messages, "artifact_id": artifact_id}


@dataclass
class StubLLMClient:
    config: Any = None

    async def sample(self, system_prompt: str, user_prompt: str, **kwargs):
        raise RuntimeError(
            "StubLLMClient.sample() called. Ensure config.toml has valid [llm] and [vlm] sections "
            "with model, base_url, and api_key configured."
        )


def make_node_state(session_id: str = "adapter_session", artifact_id: str = "adapter_artifact", lang: str = "zh"):
    from open_storyline.nodes.node_state import NodeState
    summary = StubNodeSummary()
    llm = StubLLMClient()
    return NodeState(
        session_id=session_id,
        artifact_id=artifact_id,
        lang=lang,
        node_summary=summary,
        llm=llm,
        mcp_ctx=None,
    )


def run_adapter(adapter_name: str, node_factory, process_fn_name: str, inputs: dict, output_dir: str):
    import asyncio

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    settings = load_settings()
    node = node_factory(settings)
    node_state = make_node_state(artifact_id=adapter_name)

    try:
        result = asyncio.run(getattr(node, process_fn_name)(node_state, inputs))
        result_path = output_path / f"{adapter_name}_result.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(json.dumps({"status": "success", "result_file": str(result_path), "result": result}, indent=2, ensure_ascii=False, default=str))
        return 0
    except Exception as e:
        error_info = {"status": "error", "error": str(e), "traceback": traceback.format_exc()}
        error_path = output_path / f"{adapter_name}_error.json"
        error_path.write_text(json.dumps(error_info, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(error_info, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1


def parse_json_arg(value: str) -> Any:
    if not value:
        return {}
    if value.startswith("@"):
        with open(value[1:], "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(value)
