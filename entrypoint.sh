#!/usr/bin/env bash
set -e

CASE_ID="$1"
TIMEOUT="${2:-2400}"

# Clear old sessions to avoid conflict
rm -rf /root/.openclaw/agents/main/sessions/ 2>/dev/null || true

bash /workspace/prepare.sh

RUN_TS=$(date +%s)
SESSION_KEY="agent:main:${CASE_ID}-${RUN_TS}"

mkdir -p /workspace/output
TASK_WINDOW_START=$(date +%s.%N)

openclaw agent \
    --local \
    --agent main \
    --session-key "${SESSION_KEY}" \
    --timeout "${TIMEOUT}" \
    --model deepseek/deepseek-v4-flash \
    --message "$(cat /workspace/task.prompt)" \
    --json > /workspace/output/openclaw_agent.stdout.json 2> /workspace/output/openclaw_agent.stderr.log || true

TASK_WINDOW_END=$(date +%s.%N)

python3 -c "
import json
print(json.dumps({'case_id': '${CASE_ID}', 'start_epoch': ${TASK_WINDOW_START}, 'end_epoch': ${TASK_WINDOW_END}, 'duration_seconds': round(${TASK_WINDOW_END} - ${TASK_WINDOW_START}, 3)}))
" > /workspace/output/task_window.json

echo "[INFO] agent completed, collecting outputs..."

# === Fix 1: Copy rendered video to final.mp4 ===
RENDER_RESULT="/workspace/output/render_video_result.json"
if [ -f "${RENDER_RESULT}" ]; then
    RENDER_PATH=$(python3 -c "
import json
with open('${RENDER_RESULT}') as f:
    d = json.load(f)
print(d.get('output_path', d.get('result', {}).get('output_path', '')))
" 2>/dev/null || echo "")
    if [ -n "${RENDER_PATH}" ] && [ -f "${RENDER_PATH}" ]; then
        cp "${RENDER_PATH}" /workspace/output/final.mp4
        echo "[INFO] final.mp4 copied from ${RENDER_PATH}"
    else
        echo "[WARN] render result found but video file missing at: ${RENDER_PATH}"
    fi
else
    echo "[WARN] no render_video_result.json found"
fi

# === Fix 2: Ensure resolution >= 720p (short side) ===
if [ -f /workspace/output/final.mp4 ]; then
    SHORT_SIDE=$(ffprobe -v quiet -show_entries stream=width,height -of csv=p=0 -select_streams v:0 /workspace/output/final.mp4 2>/dev/null | python3 -c "
import sys
line = sys.stdin.read().strip()
if line:
    w, h = line.split(',')
    print(min(int(w), int(h)))
else:
    print(0)
" 2>/dev/null || echo "0")

    if [ "${SHORT_SIDE}" -gt 0 ] && [ "${SHORT_SIDE}" -lt 720 ]; then
        echo "[INFO] resolution short_side=${SHORT_SIDE} < 720, upscaling..."
        if [ "${SHORT_SIDE}" -le 608 ]; then
            ffmpeg -y -i /workspace/output/final.mp4 -vf "scale=720:1280" -c:a copy /workspace/output/final_resized.mp4 2>/dev/null
        else
            ffmpeg -y -i /workspace/output/final.mp4 -vf "scale=720:-2" -c:a copy /workspace/output/final_resized.mp4 2>/dev/null
        fi
        if [ -f /workspace/output/final_resized.mp4 ]; then
            mv /workspace/output/final_resized.mp4 /workspace/output/final.mp4
            echo "[INFO] final.mp4 upscaled to 720p"
        fi
    else
        echo "[INFO] resolution OK (short_side=${SHORT_SIDE})"
    fi
fi

# === Run verifier ===
GT_FLAG=""
if [ -f /workspace/verifier/hidden/edit_ground_truth.json ]; then
    GT_FLAG="--ground-truth /workspace/verifier/hidden/edit_ground_truth.json"
fi

python3 /workspace/verify.py \
    --output-dir /workspace/output \
    --constraints /workspace/fixtures/expected_constraints.json \
    --result-dir /workspace/output \
    ${GT_FLAG} || true

echo "[INFO] all done"
echo "=== output files ==="
ls -lh /workspace/output/ 2>/dev/null
