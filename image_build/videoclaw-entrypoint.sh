#!/usr/bin/env bash
set -e

CONFIG="/opt/videoclaw/backend/config.yaml"

python3 -c "
import yaml, os
with open('${CONFIG}') as f:
    cfg = yaml.safe_load(f)

dk = os.environ.get('DEEPSEEK_API_KEY', '')
ds = os.environ.get('DASHSCOPE_API_KEY', '')
if dk:
    cfg['api_providers']['deepseek']['api_key'] = dk
    cfg['api_providers']['deepseek']['base_url'] = 'https://api.deepseek.com/v1'
if ds:
    cfg['api_providers']['dashscope']['api_key'] = ds

llm_model = os.environ.get('LLM_MODEL', 'deepseek-chat')
cfg['models']['llm'] = llm_model

with open('${CONFIG}', 'w') as f:
    yaml.dump(cfg, f, allow_unicode=True)
print('[INFO] config.yaml injected from env')
"

exec python3 /opt/videoclaw/backend/api_server.py
