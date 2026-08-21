#!/usr/bin/env bash
set -Eeuo pipefail

CASE_ID="SUB-CPU-VIDEO-EDIT-01"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-/workspace}"
OUTPUT_DIR="${OUTPUT_DIR:-${WORKSPACE_ROOT}/output}"
OPENSTORYLINE_REPO="${OPENSTORYLINE_REPO:-/opt/openstoryline}"
ADAPTER_DIR="${ADAPTER_DIR:-/opt/video-tools}"
CONFIG_FILE="${OPENSTORYLINE_REPO}/config.toml"

source /tmp/prepare_common.sh 2>/dev/null || true

rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"

systemctl stop docker >/dev/null 2>&1 || service docker stop >/dev/null 2>&1 || true
pkill -f "jupyter|chromium|chrome|playwright" >/dev/null 2>&1 || true

test -d "${OPENSTORYLINE_REPO}/src/open_storyline" || { echo "[ERROR] OpenStoryline src not found" >&2; exit 1; }
test -f "${CONFIG_FILE}" || { echo "[ERROR] config.toml not found" >&2; exit 1; }

for tool in inspect_media split_shots transcribe understand_clips filter_clips group_clips generate_script select_bgm plan_timeline render_video; do
    test -x "${ADAPTER_DIR}/${tool}.py" || { echo "[ERROR] adapter ${tool}.py not found or not executable" >&2; exit 1; }
done

command -v ffmpeg >/dev/null 2>&1 || { echo "[ERROR] ffmpeg not found" >&2; exit 1; }
command -v ffprobe >/dev/null 2>&1 || { echo "[ERROR] ffprobe not found" >&2; exit 1; }

python3 - <<'PY'
import importlib.util
missing = []
for name in ("torch", "numpy", "av", "moviepy", "funasr", "librosa", "faiss", "sentence_transformers", "PIL", "pydantic", "tomllib"):
    if name == "tomllib":
        try:
            import tomllib
        except ImportError:
            try:
                import tomli
            except ImportError:
                missing.append("tomllib/tomli")
    elif importlib.util.find_spec(name) is None:
        missing.append(name)
if missing:
    raise SystemExit("Missing required Python packages: " + ", ".join(missing))
PY

test -f "${OPENSTORYLINE_REPO}/.storyline/models/transnetv2-pytorch-weights.pth" || { echo "[ERROR] TransNetV2 weights not found" >&2; exit 1; }

if [ -f "${CONFIG_FILE}" ]; then
    if [ -n "${LLM_API_KEY:-}" ]; then
        python3 "${OPENSTORYLINE_REPO}/scripts/update_config.py" --config "${CONFIG_FILE}" --set "llm.api_key=${LLM_API_KEY}" || true
    fi
    if [ -n "${LLM_MODEL:-}" ]; then
        python3 "${OPENSTORYLINE_REPO}/scripts/update_config.py" --config "${CONFIG_FILE}" --set "llm.model=${LLM_MODEL}" || true
    fi
    if [ -n "${LLM_BASE_URL:-}" ]; then
        python3 "${OPENSTORYLINE_REPO}/scripts/update_config.py" --config "${CONFIG_FILE}" --set "llm.base_url=${LLM_BASE_URL}" || true
    fi
    if [ -n "${VLM_API_KEY:-}" ]; then
        python3 "${OPENSTORYLINE_REPO}/scripts/update_config.py" --config "${CONFIG_FILE}" --set "vlm.api_key=${VLM_API_KEY}" || true
    fi
    if [ -n "${VLM_MODEL:-}" ]; then
        python3 "${OPENSTORYLINE_REPO}/scripts/update_config.py" --config "${CONFIG_FILE}" --set "vlm.model=${VLM_MODEL}" || true
    fi
    if [ -n "${VLM_BASE_URL:-}" ]; then
        python3 "${OPENSTORYLINE_REPO}/scripts/update_config.py" --config "${CONFIG_FILE}" --set "vlm.base_url=${VLM_BASE_URL}" || true
    fi
fi

FIXTURE_DIR="${WORKSPACE_ROOT}/fixtures/media"
if [ -d "${FIXTURE_DIR}" ]; then
    find "${FIXTURE_DIR}" -type f \( -name "*.mp4" -o -name "*.mov" -o -name "*.jpg" -o -name "*.png" \) | head -20
else
    echo "[WARN] fixture media directory not found at ${FIXTURE_DIR}" >&2
fi

cp -f /workspace/fixtures/expected_constraints.json "${OUTPUT_DIR}/expected_constraints.json"

echo "[INFO] EDIT prepare complete"
echo "[INFO] output_dir=${OUTPUT_DIR}"
echo "[INFO] openstoryline=${OPENSTORYLINE_REPO}"
echo "[INFO] adapters=${ADAPTER_DIR}"
