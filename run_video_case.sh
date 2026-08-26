#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE="${1:-list}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)_${CASE}}"
RESULT_ROOT="${RESULT_ROOT:-${ROOT}/results/${RUN_ID}}"
CPUS="${CPUS:-2}"
MEMORY="${MEMORY:-4g}"
CPUSET="${CPUSET:-0,1}"
TIMEOUT="${TIMEOUT:-2400}"

# Global state for cleanup trap
CPU_PID=""
MONITOR_PID=""
OPENCLAW_TEMP=""
RUN_DIR=""
CONTAINER_NAME=""

cleanup() {
    local rc=$?
    # Stop monitors
    if [ -n "${CPU_PID}" ]; then kill "${CPU_PID}" 2>/dev/null || true; fi
    if [ -n "${MONITOR_PID}" ]; then kill "${MONITOR_PID}" 2>/dev/null || true; fi
    wait "${CPU_PID}" "${MONITOR_PID}" 2>/dev/null || true
    # Cleanup temp .openclaw
    if [ -n "${OPENCLAW_TEMP}" ] && [ -d "${OPENCLAW_TEMP}" ]; then rm -rf "${OPENCLAW_TEMP}" 2>/dev/null || true; fi
    # Stop container if still running
    if [ -n "${CONTAINER_NAME}" ]; then docker stop "${CONTAINER_NAME}" 2>/dev/null || true; fi
    return $rc
}
trap cleanup EXIT

list_cases() {
    cat <<'EOF'
generate  SUB-NET-VIDEO-GEN-01  Agentic Multi-shot Video Generation (VideoClaw)
edit      SUB-CPU-VIDEO-EDIT-01 Agentic Material-based Video Editing (OpenStoryline)
EOF
}

if [[ "${CASE}" == list ]]; then list_cases; exit 0; fi
if [[ ! -f "${ROOT}/config.env" ]]; then
    echo '[ERROR] config.env not found' >&2; exit 2
fi
set -a; source "${ROOT}/config.env"; set +a

case "${CASE}" in
    generate)
        CASE_ID="SUB-NET-VIDEO-GEN-01"; DIR="10_video_generate"
        IMAGE="${IMAGE_GEN:-video-bench-gen:1.0}"; ENTRYPOINT="entrypoints/gen_entrypoint.sh" ;;
    edit)
        CASE_ID="SUB-CPU-VIDEO-EDIT-01"; DIR="11_video_edit"
        IMAGE="${IMAGE_EDIT:-video-bench-edit:1.0}"; ENTRYPOINT="entrypoints/edit_entrypoint.sh" ;;
    *) list_cases; exit 2 ;;
esac

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
    echo "[ERROR] Image ${IMAGE} not found" >&2; exit 3
fi

RUN_DIR="${RESULT_ROOT}/${CASE_ID}"
mkdir -p "${RUN_DIR}"
CONTAINER_NAME="video_bench_${CASE_ID}_${RUN_ID}"

echo "[INFO] case=${CASE_ID} image=${IMAGE}"
echo "[INFO] run_dir=${RUN_DIR}"

# Resource monitors
python3 "${ROOT}/container_cpu.py" --container-name "${CONTAINER_NAME}" --interval 1 --output-dir "${RUN_DIR}" &
CPU_PID=$!
python3 "${ROOT}/docker_resource_monitor.py" --container-name "${CONTAINER_NAME}" --interval 3 --output-dir "${RUN_DIR}" &
MONITOR_PID=$!

# Isolation: copy base config to temp dir per run
OPENCLAW_TEMP="${RUN_DIR}/.openclaw_tmp"
rm -rf "${OPENCLAW_TEMP}"
mkdir -p "${OPENCLAW_TEMP}"
cp -a /root/.openclaw/* "${OPENCLAW_TEMP}/" 2>/dev/null || true
rm -rf "${OPENCLAW_TEMP}/agents/main/sessions/" 2>/dev/null || true

# Agent container — NO hidden GT mounted, NO verifier inside, isolated .openclaw
# #2 fix: --env-file doesn't expand ${VAR}; pass keys explicitly after source
set +e
docker run --rm \
    --name "${CONTAINER_NAME}" \
    --cpus="${CPUS}" --memory="${MEMORY}" --cpuset-cpus="${CPUSET}" \
    --env-file "${ROOT}/config.env" \
    -e DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY}" \
    -e DASHSCOPE_API_KEY="${DASHSCOPE_API_KEY}" \
    -e LLM_API_KEY="${LLM_API_KEY}" \
    -e VLM_API_KEY="${VLM_API_KEY}" \
    -e PYTHONPATH=/opt/openstoryline:/opt/openstoryline/src \
    -v /opt/openclaw:/opt/openclaw:ro \
    -v "${OPENCLAW_TEMP}:/root/.openclaw" \
    -v "${ROOT}/skills:/root/.openclaw/skills:ro" \
    -v "${ROOT}/adapters/openstoryline:/workspace/adapters:ro" \
    -v "${ROOT}/cases/${DIR}/task.prompt:/workspace/task.prompt:ro" \
    -v "${ROOT}/cases/${DIR}/fixtures:/workspace/fixtures:ro" \
    -v "${ROOT}/${ENTRYPOINT}:/entrypoint.sh:ro" \
    -v "${RUN_DIR}:/workspace/output" \
    "${IMAGE}" bash /entrypoint.sh 2>&1 | tee "${RUN_DIR}/container.log"
DOCKER_RC=${PIPESTATUS[0]:-1}
set -e

echo "${DOCKER_RC}" > "${RUN_DIR}/exit_code.txt"

# #5 fix: auto-generate run metadata
python3 -c "
import json, subprocess, hashlib
from pathlib import Path

# Get Docker image ID
r = subprocess.run(['docker', 'inspect', '--format', '{{.Id}}', '${IMAGE}'], capture_output=True, text=True)
image_id = r.stdout.strip() if r.returncode == 0 else 'unknown'

# Get OpenClaw version
r2 = subprocess.run(['openclaw', '--version'], capture_output=True, text=True)
openclaw_version = r2.stdout.strip() if r2.returncode == 0 else 'unknown'

# Fixture SHA
fixture_dir = Path('${ROOT}/cases/${DIR}/fixtures')
fixture_sha = hashlib.sha256()
for f in sorted(fixture_dir.rglob('*')):
    if f.is_file():
        fixture_sha.update(f.read_bytes())
        fixture_sha.update(str(f).encode())

# Skill SHA
skill_sha = hashlib.sha256()
skill_dir = Path('${ROOT}/skills')
for f in sorted(skill_dir.rglob('SKILL.md')):
    skill_sha.update(f.read_bytes())

metadata = {
    'benchmark_git_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, cwd='${ROOT}').stdout.strip(),
    'docker_image_tag': '${IMAGE}',
    'docker_image_id': image_id,
    'openclaw_version': openclaw_version,
    'agent_model': 'deepseek/deepseek-v4-flash',
    'cpus': '${CPUS}',
    'memory': '${MEMORY}',
    'cpuset': '${CPUSET}',
    'case_id': '${CASE_ID}',
    'fixture_sha256': fixture_sha.hexdigest()[:16] + '...',
    'skill_sha256': skill_sha.hexdigest()[:16] + '...',
}
Path('${RUN_DIR}/run_metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
" 2>/dev/null || true

# Host-side verifier (#1: always runs, even on docker failure)
echo "[INFO] running verifier on host..."
if [[ "${CASE}" == "edit" ]]; then
    GT_PATH="${ROOT}/verifier/hidden/edit_ground_truth.json"
    MANIFEST_PATH="${ROOT}/cases/${DIR}/fixtures/source_manifest.json"
    if [ -f "${GT_PATH}" ]; then
        set +e
        python3 "${ROOT}/cases/${DIR}/verify_video_${CASE}.py" \
            --output-dir "${RUN_DIR}" \
            --constraints "${ROOT}/cases/${DIR}/fixtures/expected_constraints.json" \
            --result-dir "${RUN_DIR}" \
            --ground-truth "${GT_PATH}" \
            --fixture-manifest "${MANIFEST_PATH}" 2>&1
        VERIFIER_RC=$?
        set -e
    else
        echo "[ERROR] hidden GT not found" >&2; echo "VERIFIER_ERROR" > "${RUN_DIR}/verifier_status.txt"; VERIFIER_RC=1
    fi
else
    set +e
    python3 "${ROOT}/cases/${DIR}/verify_video_${CASE}.py" \
        --output-dir "${RUN_DIR}" \
        --constraints "${ROOT}/cases/${DIR}/fixtures/expected_constraints.json" \
        --result-dir "${RUN_DIR}" 2>&1
    VERIFIER_RC=$?
    set -e
fi
if [ ${VERIFIER_RC} -ne 0 ]; then
    echo "[WARN] verifier rc=${VERIFIER_RC}" >&2
    echo "VERIFIER_FAIL" > "${RUN_DIR}/verifier_status.txt"
else
    echo "VERIFIER_OK" > "${RUN_DIR}/verifier_status.txt"
fi

# Summarize
set +e
python3 "${ROOT}/summarize_run.py" --run-dir "${RUN_DIR}" --case-id "${CASE_ID}" 2>&1
set -e

echo "[INFO] result=${RUN_DIR}"
