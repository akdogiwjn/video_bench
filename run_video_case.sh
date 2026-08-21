#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE="${1:-list}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)_${CASE}}"
RESULT_ROOT="${RESULT_ROOT:-${ROOT}/results/${RUN_ID}}"
CPUS="${CPUS:-2}"
MEMORY="${MEMORY:-4g}"
CPUSET="${CPUSET:-0,1}"
KEEP_CONTAINER="${KEEP_CONTAINER:-0}"

list_cases() {
    cat <<'EOF'
generate  SUB-NET-VIDEO-GEN-01  Agentic Multi-shot Video Generation (VideoClaw)
edit      SUB-CPU-VIDEO-EDIT-01 Agentic Material-based Video Editing (OpenStoryline)
EOF
}

if [[ "${CASE}" == list ]]; then list_cases; exit 0; fi
if [[ ! -f "${ROOT}/config.env" ]]; then
    echo "[ERROR] config.env not found. Copy config.env.example and fill in API keys." >&2
    exit 2
fi
set -a
source "${ROOT}/config.env"
set +a

case "${CASE}" in
    generate)
        CASE_ID="SUB-NET-VIDEO-GEN-01"
        DIR="10_video_generate"
        IMAGE="${IMAGE_GEN:-video-bench-gen:1.0}"
        TIMEOUT=1800
        ;;
    edit)
        CASE_ID="SUB-CPU-VIDEO-EDIT-01"
        DIR="11_video_edit"
        IMAGE="${IMAGE_EDIT:-video-bench-edit:1.0}"
        TIMEOUT=1800
        ;;
    *) list_cases; exit 2 ;;
esac

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
    if [[ "${CASE}" == "generate" ]]; then DF="videoclaw.Dockerfile"; else DF="openstoryline.Dockerfile"; fi
    echo "[ERROR] Docker image ${IMAGE} not found. Build it first:" >&2
    echo "[ERROR]   docker build -t ${IMAGE} -f ${ROOT}/image_build/${DF} ${ROOT}/.." >&2
    exit 3
fi

RUN_DIR="${RESULT_ROOT}/${CASE_ID}"
mkdir -p "${RUN_DIR}"

CONTAINER_NAME="video_bench_${CASE_ID}_${RUN_ID}"

echo "[INFO] case=${CASE_ID} image=${IMAGE} cpus=${CPUS} memory=${MEMORY} cpuset=${CPUSET}"
echo "[INFO] run_dir=${RUN_DIR}"
echo "[INFO] container=${CONTAINER_NAME}"

echo "[INFO] starting resource monitors"
python3 "${ROOT}/container_cpu.py" \
    --container-name "${CONTAINER_NAME}" \
    --interval 1 \
    --output-dir "${RUN_DIR}" &
CPU_PID=$!
echo $CPU_PID > "${RUN_DIR}/container_cpu.pid"

python3 "${ROOT}/docker_resource_monitor.py" \
    --container-name "${CONTAINER_NAME}" \
    --interval 3 \
    --output-dir "${RUN_DIR}" &
MONITOR_PID=$!
echo $MONITOR_PID > "${RUN_DIR}/docker_resource_monitor.pid"

START_EPOCH=$(date +%s.%N)
echo "${START_EPOCH}" > "${RUN_DIR}/task_start_epoch.txt"

echo "[INFO] starting workload container"
docker run --rm \
    --name "${CONTAINER_NAME}" \
    --cpus="${CPUS}" \
    --memory="${MEMORY}" \
    --cpuset-cpus="${CPUSET}" \
    --env-file "${ROOT}/config.env" \
    -v "${ROOT}:/workspace" \
    -v "${ROOT}/cases/${DIR}/fixtures:/workspace/fixtures:ro" \
    -v "/opt/openclaw:/opt/openclaw:ro" \
    -v "/root/.openclaw:/root/.openclaw" \
    -v "${ROOT}/skills:/root/.openclaw/skills:ro" \
    -v "${ROOT}/cases/${DIR}/task.prompt:/workspace/task.prompt:ro" \
    -v "${ROOT}/cases/${DIR}/prepare.sh:/workspace/prepare.sh:ro" \
    -v "${ROOT}/cases/${DIR}/verify_video_${CASE}.py:/workspace/verify.py:ro" \
    -v "${ROOT}/entrypoint.sh:/workspace/entrypoint.sh:ro" \
    -v "${ROOT}/verifier/hidden:/workspace/verifier/hidden:ro" \
    "${IMAGE}" \
    bash /workspace/entrypoint.sh "${CASE_ID}" "${TIMEOUT}" \
    2>&1 | tee "${RUN_DIR}/container.log"

RC=${PIPESTATUS[0]:-1}
END_EPOCH=$(date +%s.%N)
echo "${END_EPOCH}" > "${RUN_DIR}/task_end_epoch.txt"

echo "[INFO] stopping resource monitors"
kill "${CPU_PID}" 2>/dev/null || true
kill "${MONITOR_PID}" 2>/dev/null || true
wait "${CPU_PID}" 2>/dev/null || true
wait "${MONITOR_PID}" 2>/dev/null || true

if [ "${KEEP_CONTAINER}" != "1" ]; then
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
fi

cp -rf "${ROOT}/cases/${DIR}/fixtures/../" "${RUN_DIR}/" 2>/dev/null || true
if docker inspect "${CONTAINER_NAME}" >/dev/null 2>&1 && [ "${KEEP_CONTAINER}" = "1" ]; then
    docker cp "${CONTAINER_NAME}:/workspace/output" "${RUN_DIR}/vm_output" 2>/dev/null || true
fi

echo "${RC}" > "${RUN_DIR}/exit_code.txt"

python3 "${ROOT}/summarize_run.py" --run-dir "${RUN_DIR}" --case-id "${CASE_ID}" || true

echo "[INFO] result=${RUN_DIR}"
echo "[INFO] exit_code=${RC}"
