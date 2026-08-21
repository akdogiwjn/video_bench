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
        CASE_ID="SUB-NET-VIDEO-GEN-01"
        DIR="10_video_generate"
        IMAGE="${IMAGE_GEN:-video-bench-gen:1.0}"
        ENTRYPOINT="entrypoints/gen_entrypoint.sh"
        ;;
    edit)
        CASE_ID="SUB-CPU-VIDEO-EDIT-01"
        DIR="11_video_edit"
        IMAGE="${IMAGE_EDIT:-video-bench-edit:1.0}"
        ENTRYPOINT="entrypoints/edit_entrypoint.sh"
        ;;
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

# Resource monitors (started before container, stopped after)
python3 "${ROOT}/container_cpu.py" --container-name "${CONTAINER_NAME}" --interval 1 --output-dir "${RUN_DIR}" &
CPU_PID=$!
python3 "${ROOT}/docker_resource_monitor.py" --container-name "${CONTAINER_NAME}" --interval 3 --output-dir "${RUN_DIR}" &
MONITOR_PID=$!

# Agent container — NO hidden GT mounted, NO verifier inside
docker run --rm \
    --name "${CONTAINER_NAME}" \
    --cpus="${CPUS}" --memory="${MEMORY}" --cpuset-cpus="${CPUSET}" \
    --env-file "${ROOT}/config.env" \
    -e PYTHONPATH=/opt/openstoryline:/opt/openstoryline/src \
    -v /opt/openclaw:/opt/openclaw:ro \
    -v /root/.openclaw:/root/.openclaw \
    -v "${ROOT}/skills:/root/.openclaw/skills:ro" \
    -v "${ROOT}/adapters/openstoryline:/workspace/adapters:ro" \
    -v "${ROOT}/cases/${DIR}/task.prompt:/workspace/task.prompt:ro" \
    -v "${ROOT}/cases/${DIR}/fixtures:/workspace/fixtures:ro" \
    -v "${ROOT}/${ENTRYPOINT}:/entrypoint.sh:ro" \
    -v "${RUN_DIR}:/workspace/output" \
    "${IMAGE}" bash /entrypoint.sh 2>&1 | tee "${RUN_DIR}/container.log"

RC=${PIPESTATUS[0]:-1}

# Stop monitors
kill "${CPU_PID}" "${MONITOR_PID}" 2>/dev/null || true
wait "${CPU_PID}" "${MONITOR_PID}" 2>/dev/null || true

# Host-side verifier (has access to hidden GT)
echo "[INFO] running verifier on host..."
GT_FLAG=""
GT_PATH="${ROOT}/verifier/hidden/edit_ground_truth.json"
[ -f "${GT_PATH}" ] && GT_FLAG="--ground-truth ${GT_PATH}"

python3 "${ROOT}/cases/${DIR}/verify_video_${CASE}.py" \
    --output-dir "${RUN_DIR}" \
    --constraints "${ROOT}/cases/${DIR}/fixtures/expected_constraints.json" \
    --result-dir "${RUN_DIR}" \
    ${GT_FLAG} 2>&1 || true

echo "${RC}" > "${RUN_DIR}/exit_code.txt"

# Summarize (with task_window filtering)
python3 "${ROOT}/summarize_run.py" --run-dir "${RUN_DIR}" --case-id "${CASE_ID}" || true

echo "[INFO] result=${RUN_DIR}"
