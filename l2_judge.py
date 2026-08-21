#!/usr/bin/env python3
"""L2 Semantic Judge: uses qwen-vl-max via DashScope to score final video output.

Fixes applied:
- #29: Judge receives creative brief / task brief alongside rubric
- #30: Generates evaluation copy (compressed) for large videos instead of file://
- #31: Validates JSON schema (all dimensions present, 0-4 integers)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

DASHSCOPE_VLM_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
JUDGE_MODEL = "qwen-vl-max"
MAX_VIDEO_SIZE_BYTES = 15 * 1024 * 1024
EVAL_TARGET_WIDTH = 360
EVAL_TARGET_BITRATE = "300k"
MAX_RETRIES = 3


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rubric_sha256(rubric: dict) -> str:
    return hashlib.sha256(json.dumps(rubric, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def generate_evaluation_copy(video_path: str, output_dir: Path) -> str:
    """Generate a compressed evaluation copy for the judge. Does NOT modify the original."""
    src = Path(video_path)
    size = src.stat().st_size
    if size <= MAX_VIDEO_SIZE_BYTES:
        return str(src)
    eval_path = output_dir / "eval_copy.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"scale={EVAL_TARGET_WIDTH}:-2",
        "-b:v", EVAL_TARGET_BITRATE, "-c:a", "copy",
        str(eval_path),
    ], capture_output=True, timeout=120)
    return str(eval_path) if eval_path.exists() else str(src)


def encode_video_for_api(video_path: str) -> dict:
    path = Path(video_path)
    size = path.stat().st_size
    if size > MAX_VIDEO_SIZE_BYTES:
        # Should not reach here if evaluation copy was generated
        return {"type": "text", "text": f"[video too large: {size} bytes]"}
    with open(video_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{data}"}}


def load_brief(brief_path: str | None, case_id: str) -> str:
    """Load creative brief or task brief for the judge."""
    if brief_path and Path(brief_path).exists():
        brief = load_json(brief_path)
        return f"Creative brief:\n{json.dumps(brief, indent=2, ensure_ascii=False)[:2000]}"
    return f"No brief provided for {case_id}."


def build_judge_prompt(rubric: dict, case_id: str, brief_text: str) -> str:
    dims = rubric.get("dimensions", [])
    dim_descriptions = []
    for d in dims:
        anchors = d.get("anchors", {})
        anchor_text = "\n".join(f"    {k}: {v}" for k, v in sorted(anchors.items()))
        dim_descriptions.append(f"  {d['name']} (0-4): {d['description']}\n{anchor_text}")
    dims_block = "\n".join(dim_descriptions)
    dim_names = [d["name"] for d in dims]
    return f"""You are an expert video quality judge for benchmark case {case_id}.

{brief_text}

You will watch a final video and score it on {len(dims)} dimensions, each 0-4.

Dimensions:
{dims_block}

Instructions:
- Watch the entire video carefully.
- Score each dimension 0-4 based on the anchors.
- Be strict and consistent.
- Return ONLY a JSON object with exactly these keys and integer values 0-4:
{json.dumps({name: "<0-4 integer>" for name in dim_names}, indent=2)}
- Do not include any text outside the JSON."""


def validate_scores(scores: dict, rubric: dict) -> list[str]:
    """Validate that scores match the rubric schema."""
    errors = []
    dim_names = [d["name"] for d in rubric.get("dimensions", [])]
    for name in dim_names:
        if name not in scores:
            errors.append(f"missing dimension: {name}")
            continue
        val = scores[name]
        if not isinstance(val, int):
            try:
                val = int(val)
                scores[name] = val
            except (ValueError, TypeError):
                errors.append(f"{name}: not an integer ({val})")
                continue
        if val < 0 or val > 4:
            errors.append(f"{name}: out of range 0-4 ({val})")
    for key in scores:
        if key not in dim_names:
            errors.append(f"unknown dimension: {key}")
    return errors


def call_judge(api_key: str, model: str, video_path: str, prompt: str) -> dict:
    video_content = encode_video_for_api(video_path)
    messages = [
        {"role": "system", "content": [{"type": "text", "text": "You are a strict video quality judge. Return only JSON."}]},
        {"role": "user", "content": [video_content, {"type": "text", "text": prompt}]},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(DASHSCOPE_VLM_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                scores = json.loads(content) if isinstance(content, str) else content
                return {
                    "scores": scores,
                    "returned_model_version": data.get("model", model),
                    "response_id": data.get("id", ""),
                    "attempt": attempt,
                }
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as e:
            if attempt == MAX_RETRIES:
                return {"error": str(e), "attempt": attempt, "scores": {}}
            time.sleep(3)
    return {"error": "max retries", "scores": {}}


def main():
    parser = argparse.ArgumentParser(description="L2 semantic judge using qwen-vl-max")
    parser.add_argument("--video", required=True)
    parser.add_argument("--rubric", required=True)
    parser.add_argument("--brief", default="", help="Path to creative_brief.json or task brief")
    parser.add_argument("--output", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--api-key", default=os.environ.get("DASHSCOPE_API_KEY", ""))
    args = parser.parse_args()

    if not args.api_key:
        print("[ERROR] DASHSCOPE_API_KEY not set", file=sys.stderr)
        sys.exit(2)

    rubric = load_json(args.rubric)
    brief_text = load_brief(args.brief if args.brief else None, args.case_id)
    prompt = build_judge_prompt(rubric, args.case_id, brief_text)
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    rubric_hash = rubric_sha256(rubric)

    # Generate evaluation copy if needed
    output_path = Path(args.output)
    eval_video = generate_evaluation_copy(args.video, output_path.parent)

    print(f"[INFO] L2 judge: model={JUDGE_MODEL}, video={args.video}")
    print(f"[INFO] eval_video={eval_video}, brief={'yes' if args.brief else 'no'}")

    judge_result = call_judge(args.api_key, JUDGE_MODEL, eval_video, prompt)
    scores = judge_result.get("scores", {})

    # Validate schema
    schema_errors = validate_scores(scores, rubric)
    if schema_errors:
        print(f"[WARN] schema validation errors: {schema_errors}", file=sys.stderr)

    dim_names = [d["name"] for d in rubric.get("dimensions", [])]
    total = sum(int(scores.get(n, 0)) for n in dim_names)
    max_possible = len(dim_names) * 4
    semantic_score = round(total / max_possible, 4) if max_possible else 0

    result = {
        "case_id": args.case_id,
        "requested_model": JUDGE_MODEL,
        "returned_model_version": judge_result.get("returned_model_version", ""),
        "response_id": judge_result.get("response_id", ""),
        "temperature": 0,
        "rubric_sha256": rubric_hash,
        "judge_prompt_sha256": prompt_hash,
        "brief_provided": bool(args.brief),
        "schema_errors": schema_errors,
        "attempt": judge_result.get("attempt", 0),
        "scores": scores,
        "semantic_score": semantic_score,
        "max_possible": max_possible,
        "raw_error": judge_result.get("error"),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
