#!/usr/bin/env python3
"""Shared helpers for OpenStoryline CLI adapters. Adapter only adapts; it does not decide.

Fixes:
- #10: RealLLMClient replaces StubLLMClient — calls DeepSeek/qwen-vl-max via OpenAI-compatible API
- #11: understand_clips input structure matches upstream (inputs["media"] is a dict keyed by media_id)
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
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
class RealLLMClient:
    """Real LLM client that calls OpenAI-compatible API (DeepSeek / qwen-vl-max).

    Implements the LLMClient protocol: async complete(system_prompt, user_prompt, media, ...)
    """
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    vlm_model: str = ""
    vlm_base_url: str = ""
    vlm_api_key: str = ""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    async def complete(
        self,
        *,
        system_prompt: str | None = None,
        user_prompt: str = "",
        media: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        top_p: float = 0.9,
        max_tokens: int = 2048,
        model_preferences: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        stop_sequences: list[str] | None = None,
    ) -> str:
        from openai import AsyncOpenAI

        is_vlm = media is not None and len(media) > 0
        if is_vlm:
            model = self.vlm_model or "qwen-vl-max"
            base_url = self.vlm_base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            api_key = self.vlm_api_key
        else:
            model = self.llm_model or "deepseek-chat"
            base_url = self.llm_base_url or "https://api.deepseek.com/v1"
            api_key = self.llm_api_key

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if is_vlm:
            content = [{"type": "text", "text": user_prompt}]
            for m in media:
                path = m.get("path", "")
                if path:
                    import base64
                    with open(path, "rb") as f:
                        img_data = base64.b64encode(f.read()).decode("ascii")
                    content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user_prompt})

        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop_sequences,
        )
        return resp.choices[0].message.content or ""


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


def make_node_state(session_id: str = "adapter_session", artifact_id: str = "adapter_artifact", lang: str = "zh"):
    from open_storyline.nodes.node_state import NodeState
    
    settings = load_settings()
    summary = StubNodeSummary()

    llm = RealLLMClient(
        llm_model=getattr(settings.llm, "model", "deepseek-chat"),
        llm_base_url=getattr(settings.llm, "base_url", "https://api.deepseek.com/v1"),
        llm_api_key=getattr(settings.llm, "api_key", ""),
        vlm_model=getattr(settings.vlm, "model", "qwen-vl-max"),
        vlm_base_url=getattr(settings.vlm, "base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        vlm_api_key=getattr(settings.vlm, "api_key", ""),
    )

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

        # #4 fix: write execution evidence
        evidence = {
            "tool": adapter_name,
            "method": process_fn_name,
            "status": "success",
            "result_file": str(result_path),
        }
        # Add upstream symbol info if available
        if hasattr(node, 'meta'):
            evidence["upstream_symbol"] = type(node).__name__
            evidence["upstream_node_id"] = getattr(node.meta, 'node_id', '')
        # Record device for CPU workload evidence (SplitShotsNode → TransNetV2 → device)
        if hasattr(node, 'server_cfg'):
            cfg = node.server_cfg
            if hasattr(cfg, 'split_shots') and hasattr(cfg.split_shots, 'transnet_device'):
                evidence["device"] = cfg.split_shots.transnet_device
        evidence_path = output_path / f"{adapter_name}_execution.json"
        evidence_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")

        print(json.dumps({"status": "success", "result_file": str(result_path), "result": result}, indent=2, ensure_ascii=False, default=str))
        return 0
    except Exception as e:
        error_info = {"status": "error", "error": str(e), "traceback": traceback.format_exc()}
        error_path = output_path / f"{adapter_name}_error.json"
        error_path.write_text(json.dumps(error_info, indent=2, ensure_ascii=False), encoding="utf-8")
        # Still write execution evidence with error status
        evidence = {"tool": adapter_name, "method": process_fn_name, "status": "error", "error": str(e)[:200]}
        evidence_path = output_path / f"{adapter_name}_execution.json"
        evidence_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(error_info, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1


def parse_json_arg(value: str) -> Any:
    if not value:
        return {}
    if value.startswith("@"):
        with open(value[1:], "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(value)
