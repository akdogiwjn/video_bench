#!/usr/bin/env python3
"""L2 Semantic Judge: uses qwen-vl-max via DashScope to score final video output.

Runs AFTER task_window end. Judge API cost does NOT count toward workload metrics.
Each formal run gets exactly 1 judge. Retry only on HTTP failure / timeout / JSON parse failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import base64
from pathlib import Path

import httpx


DASHSCOPE_VLM_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
JUDGE_MODEL = "qwen-vl-max"
MAX_VIDEO_SIZE_BYTES = 20 * 1024 * 1024
MAX_RETRIES = 3


def load_rubric(rubric_path: str) -> dict:
    with open(rubric_path, encoding="utf-8") as f:
        return json.load(f)


def rubric_sha256(rubric: dict) -> str:
    return hashlib.sha256(json.dumps(rubric, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def build_judge_prompt(rubric: dict, case_id: str) -> str:
    dims = rubric.get("dimensions", [])
    dim_descriptions = []
    for d in dims:
        anchors = d.get("anchors", {})
        anchor_text = "\n".join(f"    {k}: {v}" for k, v in sorted(anchors.items()))
        dim_descriptions.append(
            f"  {d['name']} (0-4): {d['description']}\n{anchor_text}"
        )
    dims_block = "\n".join(dim_descriptions)
    return f"""You are an expert video quality judge for benchmark case {case_id}.

You will watch a final video and score it on {len(dims)} dimensions, each 0-4.

Dimensions:
{dims_block}

Instructions:
- Watch the entire video carefully.
- For each dimension, assign a score from 0 to 4 based on the anchors.
- Be strict and consistent.
- Return ONLY a JSON object with the dimension names as keys and integer scores as values.
- Do not include any text outside the JSON.

Return format:
{{
{chr(10).join(f'  "{d["name"]}": <0-4 integer>' for d in dims)}
}}"""


def encode_video_for_api(video_path: str) -> dict:
    path = Path(video_path)
    size = path.stat().st_size
    if size > MAX_VIDEO_SIZE_BYTES:
        return {"type": "video_url", "video_url": {"url": f"file://{video_path}"}}
    with open(video_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{data}"}}


def call_judge(api_key: str, model: str, video_path: str, prompt: str) -> dict:
    video_content = encode_video_for_api(video_path)
    messages = [
        {
            "role": "system",
            "content": [{"type": "text", "text": "You are a strict video quality judge. Return only JSON."}],
        },
        {
            "role": "user",
            "content": [
                video_content,
                {"type": "text", "text": prompt},
            ],
        },
    ]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(DASHSCOPE_VLM_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if isinstance(content, str):
                    scores = json.loads(content)
                else:
                    scores = content
                result = {
                    "scores": scores,
                    "returned_model_version": data.get("model", model),
                    "response_id": data.get("id", ""),
                    "api_version": "v1",
                    "temperature": 0,
                    "attempt": attempt,
                }
                return result
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as e:
            if attempt == MAX_RETRIES:
                return {"error": str(e), "attempt": attempt, "scores": {}}
            time.sleep(3)
    return {"error": "max retries exceeded", "scores": {}}


def main():
    parser = argparse.ArgumentParser(description="L2 semantic judge using qwen-vl-max")
    parser.add_argument("--video", required=True, help="Path to final.mp4")
    parser.add_argument("--rubric", required=True, help="Path to judge rubric JSON")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--api-key", default=os.environ.get("DASHSCOPE_API_KEY", ""))
    args = parser.parse_args()

    if not args.api_key:
        print("[ERROR] DASHSCOPE_API_KEY not set", file=sys.stderr)
        sys.exit(2)

    rubric = load_rubric(args.rubric)
    prompt = build_judge_prompt(rubric, args.case_id)
    rubric_hash = rubric_sha256(rubric)
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()

    print(f"[INFO] L2 judge: model={JUDGE_MODEL}, video={args.video}")
    print(f"[INFO] rubric_sha256={rubric_hash}")
    print(f"[INFO] prompt_sha256={prompt_hash}")

    judge_result = call_judge(args.api_key, JUDGE_MODEL, args.video, prompt)

    scores = judge_result.get("scores", {})
    dim_names = [d["name"] for d in rubric.get("dimensions", [])]
    total = 0
    for name in dim_names:
        score = scores.get(name, 0)
        if isinstance(score, str):
            try:
                score = int(score)
            except ValueError:
                score = 0
        total += score

    max_possible = len(dim_names) * 4
    semantic_score = round(total / max_possible, 4) if max_possible else 0

    result = {
        "case_id": args.case_id,
        "requested_model": JUDGE_MODEL,
        "returned_model_version": judge_result.get("returned_model_version", ""),
        "response_id": judge_result.get("response_id", ""),
        "api_version": judge_result.get("api_version", "v1"),
        "temperature": 0,
        "rubric_sha256": rubric_hash,
        "judge_prompt_sha256": prompt_hash,
        "attempt": judge_result.get("attempt", 0),
        "scores": scores,
        "semantic_score": semantic_score,
        "max_possible": max_possible,
        "raw_error": judge_result.get("error"),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
