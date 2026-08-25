#!/usr/bin/env bash
set -e

CASE_ID="SUB-CPU-VIDEO-EDIT-01"
TIMEOUT="${TIMEOUT:-2400}"

rm -rf /root/.openclaw/agents/main/sessions/ 2>/dev/null || true

# 1. Configure config.toml
cd /opt/openstoryline
sed -i '/^\[llm\]$/,/^\[/ s|model = ".*"|model = "deepseek-chat"|' config.toml
sed -i '/^\[llm\]$/,/^\[/ s|base_url = ".*"|base_url = "https://api.deepseek.com/v1"|' config.toml
sed -i '/^\[llm\]$/,/^\[/ s|api_key = ".*"|api_key = "'"$LLM_API_KEY"'"|' config.toml
sed -i '/^\[vlm\]$/,/^\[/ s|model = ".*"|model = "qwen-vl-max"|' config.toml
sed -i '/^\[vlm\]$/,/^\[/ s|base_url = ".*"|base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"|' config.toml
sed -i '/^\[vlm\]$/,/^\[/ s|api_key = ".*"|api_key = "'"$VLM_API_KEY"'"|' config.toml
sed -i 's|transnet_device = ".*"|transnet_device = "cpu"|' config.toml
echo "[INFO] config.toml configured"

# 2. Copy adapters to /opt/video-tools
cp /workspace/adapters/*.py /opt/video-tools/ 2>/dev/null || true
cp /workspace/adapters/_adapter_base.py /opt/video-tools/ 2>/dev/null || true
chmod +x /opt/video-tools/*.py 2>/dev/null || true
echo "[INFO] adapters ready"

# 3. Run agent
export PYTHONPATH=/opt/openstoryline:/opt/openstoryline/src
mkdir -p /workspace/output
touch /tmp/video_bench_run_start.marker
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
MARKER="/tmp/video_bench_run_start.marker"
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
        # Record canonicalization provenance
        python3 -c "
import hashlib, json
from pathlib import Path
src = Path('${RENDER_PATH}')
dst = Path('/workspace/output/final.mp4')
src_sha = hashlib.sha256(src.read_bytes()).hexdigest()
dst_sha = hashlib.sha256(dst.read_bytes()).hexdigest()
prov = {
    'source': str(src),
    'destination': str(dst),
    'source_sha256': src_sha,
    'final_sha256': dst_sha,
    'sha256_match': src_sha == dst_sha,
    'canonicalization_only': True,
}
Path('/workspace/output/render_provenance.json').write_text(json.dumps(prov, indent=2))
print(f'[INFO] final.mp4 copied, sha256_match={src_sha == dst_sha}')
" 2>/dev/null
        echo "[INFO] final.mp4 copied"
    else
        FOUND=$(find /opt/openstoryline/.storyline -name "output_*.mp4" -newer "${MARKER}" 2>/dev/null | head -1)
        [ -n "${FOUND}" ] && cp "${FOUND}" /workspace/output/final.mp4 && echo "[INFO] final.mp4 found via search"
    fi
fi
echo "[INFO] outputs collected"
