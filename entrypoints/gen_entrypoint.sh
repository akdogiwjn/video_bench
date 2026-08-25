#!/usr/bin/env bash
set -e

CASE_ID="SUB-NET-VIDEO-GEN-01"
TIMEOUT="${TIMEOUT:-2400}"

rm -rf /root/.openclaw/agents/main/sessions/ 2>/dev/null || true

# 1. Configure VideoClaw backend
cd /opt/videoclaw/backend
python3 -c "
import yaml, os
with open('config.yaml') as f:
    cfg = yaml.safe_load(f)
dk = os.environ.get('DEEPSEEK_API_KEY', '')
ds = os.environ.get('DASHSCOPE_API_KEY', '')
if dk:
    cfg['api_providers']['deepseek']['api_key'] = dk
    cfg['api_providers']['deepseek']['base_url'] = 'https://api.deepseek.com/v1'
if ds:
    cfg['api_providers']['dashscope']['api_key'] = ds
cfg['models']['llm'] = 'deepseek-chat'
cfg['server']['host'] = '0.0.0.0'
with open('config.yaml', 'w') as f:
    yaml.dump(cfg, f, allow_unicode=True)
print('[INFO] config.yaml injected')
"

# 2. Start backend in background
python3 api_server.py &
BACKEND_PID=$!
for i in $(seq 1 30); do
    curl -sf http://localhost:8000/api/health >/dev/null 2>&1 && break
    sleep 2
done
curl -sf http://localhost:8000/api/health >/dev/null 2>&1 || { echo "[ERROR] backend not healthy"; kill ${BACKEND_PID}; exit 1; }
echo "[INFO] backend healthy"

# 3. Run agent
mkdir -p /workspace/output
RUN_TS=$(date +%s)
SESSION_KEY="agent:main:${CASE_ID}-${RUN_TS}"

TASK_WINDOW_START=$(date +%s.%N)
set +e
openclaw agent --local --agent main --session-key "${SESSION_KEY}" --timeout "${TIMEOUT}" --model deepseek/deepseek-v4-flash --message "$(cat /workspace/task.prompt)" --json > /workspace/output/openclaw_agent.stdout.json 2> /workspace/output/openclaw_agent.stderr.log
AGENT_RC=$?
set -e
echo "${AGENT_RC}" > /workspace/output/agent_exit_code.txt
TASK_WINDOW_END=$(date +%s.%N)

python3 -c "import json; print(json.dumps({'case_id':'${CASE_ID}','start_epoch':${TASK_WINDOW_START},'end_epoch':${TASK_WINDOW_END},'duration_seconds':round(${TASK_WINDOW_END}-${TASK_WINDOW_START},3)}))" > /workspace/output/task_window.json
echo "[INFO] agent completed"

# 4. Collect outputs (canonicalization only — NO re-encoding, NO upscale)
find /opt/videoclaw/backend/code/result -name "*.mp4" -newer /workspace/task.prompt 2>/dev/null | while read f; do
    cp "$f" /workspace/output/ 2>/dev/null || true
done

# Copy script and storyboard from backend result directories
find /opt/videoclaw/backend/code/result -name "script*" -name "*.json" -newer /workspace/task.prompt 2>/dev/null | head -1 | while read f; do cp "$f" /workspace/output/script.json 2>/dev/null; done
find /opt/videoclaw/backend/code/result -name "storyboard*" -name "*.json" -newer /workspace/task.prompt 2>/dev/null | head -1 | while read f; do cp "$f" /workspace/output/storyboard.json 2>/dev/null; done
# Also try session-specific script/storyboard dirs
find /opt/videoclaw/backend/code/result/script -name "*.json" -newer /workspace/task.prompt 2>/dev/null | head -1 | while read f; do cp "$f" /workspace/output/script.json 2>/dev/null; done
find /opt/videoclaw/backend/code/result/storyboard -name "*.json" -newer /workspace/task.prompt 2>/dev/null | head -1 | while read f; do cp "$f" /workspace/output/storyboard.json 2>/dev/null; done

mkdir -p /workspace/output/reference_images /workspace/output/video_clips
find /opt/videoclaw/backend/code/result/image -name "*.png" -newer /workspace/task.prompt 2>/dev/null | head -10 | while read f; do cp "$f" /workspace/output/reference_images/ 2>/dev/null; done
find /opt/videoclaw/backend/code/result/video -name "*.mp4" -newer /workspace/task.prompt 2>/dev/null | head -10 | while read f; do cp "$f" /workspace/output/video_clips/ 2>/dev/null; done
FINAL_MP4=$(find /opt/videoclaw/backend/code/result -name "*.mp4" -newer /workspace/task.prompt -exec ls -S {} + 2>/dev/null | head -1)
[ -n "${FINAL_MP4}" ] && [ -f "${FINAL_MP4}" ] && cp "${FINAL_MP4}" /workspace/output/final.mp4
echo "[INFO] outputs collected"

kill ${BACKEND_PID} 2>/dev/null || true
