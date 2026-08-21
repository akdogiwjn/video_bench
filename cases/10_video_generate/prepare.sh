#!/usr/bin/env bash
set -Eeuo pipefail

CASE_ID="SUB-NET-VIDEO-GEN-01"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-/workspace}"
OUTPUT_DIR="${OUTPUT_DIR:-${WORKSPACE_ROOT}/output}"
VIDEOCLAW_REPO="${VIDEOCLAW_REPO:-/opt/videoclaw}"
CONFIG_FILE="${VIDEOCLAW_REPO}/backend/config.yaml"

source /tmp/prepare_common.sh 2>/dev/null || true

rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"

systemctl stop docker >/dev/null 2>&1 || service docker stop >/dev/null 2>&1 || true
pkill -f "jupyter|chromium|chrome|playwright" >/dev/null 2>&1 || true

test -f "${VIDEOCLAW_REPO}/video-claw/SKILL.md" || { echo "[ERROR] VideoClaw SKILL.md not found at ${VIDEOCLAW_REPO}" >&2; exit 1; }
test -f "${VIDEOCLAW_REPO}/backend/api_server.py" || { echo "[ERROR] VideoClaw backend not found" >&2; exit 1; }

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[ERROR] ffmpeg not found" >&2
    exit 1
fi

if [ -f "${CONFIG_FILE}" ]; then
    if [ -n "${DASHSCOPE_API_KEY:-}" ]; then
        sed -i "s/api_key:.*/api_key: ${DASHSCOPE_API_KEY}/" "${CONFIG_FILE}" || true
    fi
    if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
        sed -i "s|api_key:.*deepseek|api_key: ${DEEPSEEK_API_KEY}|" "${CONFIG_FILE}" || true
    fi
else
    echo "[ERROR] VideoClaw config.yaml not found at ${CONFIG_FILE}" >&2
    exit 1
fi

if [ -n "${DASHSCOPE_API_KEY:-}" ]; then
    if ! curl -sf --max-time 10 "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation" >/dev/null 2>&1; then
        echo "[WARN] DashScope API not reachable, generation may fail" >&2
    fi
fi

cp -f /workspace/fixtures/creative_brief.json "${OUTPUT_DIR}/creative_brief.json"
cp -f /workspace/fixtures/expected_constraints.json "${OUTPUT_DIR}/expected_constraints.json"

echo "[INFO] GEN prepare complete"
echo "[INFO] output_dir=${OUTPUT_DIR}"
echo "[INFO] config=${CONFIG_FILE}"
