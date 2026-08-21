#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/home/lcq/video_agent/video_bench"
RESULTS_DIR="${ROOT}/results/formal_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${RESULTS_DIR}"

source "${ROOT}/config.env"
export DASHSCOPE_API_KEY DEEPSEEK_API_KEY LLM_API_KEY VLM_API_KEY

run_gen() {
    local run_num=$1
    local run_dir="${RESULTS_DIR}/GEN_${run_num}"
    mkdir -p "${run_dir}"
    
    echo "====== GEN RUN ${run_num}/2 $(date) ======"
    
    docker run --rm \
      --name "gen_formal_${run_num}" \
      --cpus=2 --memory=4g \
      -e DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY}" \
      -e DASHSCOPE_API_KEY="${DASHSCOPE_API_KEY}" \
      -v /opt/openclaw:/opt/openclaw:ro \
      -v /root/.openclaw:/root/.openclaw \
      -v "${ROOT}/skills:/root/.openclaw/skills:ro" \
      -v "${ROOT}/cases/10_video_generate/task.prompt:/workspace/task.prompt:ro" \
      -v "${ROOT}/cases/10_video_generate/fixtures:/workspace/fixtures:ro" \
      -v "${ROOT}/cases/10_video_generate/verify_video_generate.py:/workspace/verify.py:ro" \
      -v /tmp/gen_smoke_entrypoint.sh:/entrypoint.sh:ro \
      -v "${run_dir}:/workspace/output" \
      video-bench-gen:1.0 \
      bash /entrypoint.sh 2>&1 | tee "${run_dir}/container.log"
    
    # Compress for L2 if needed
    if [ -f "${run_dir}/final.mp4" ]; then
        SIZE=$(stat -c%s "${run_dir}/final.mp4" 2>/dev/null || echo 0)
        if [ "${SIZE}" -gt 10000000 ]; then
            ffmpeg -y -i "${run_dir}/final.mp4" -b:v 500k -s 360x640 -c:a copy "${run_dir}/final_small.mp4" 2>/dev/null
        else
            cp "${run_dir}/final.mp4" "${run_dir}/final_small.mp4" 2>/dev/null || true
        fi
        # L2 judge
        python3 "${ROOT}/l2_judge.py" \
          --video "${run_dir}/final_small.mp4" \
          --rubric "${ROOT}/evidence/judge_rubric_gen.json" \
          --output "${run_dir}/l2_judge_result.json" \
          --case-id SUB-NET-VIDEO-GEN-01 \
          --api-key "${DASHSCOPE_API_KEY}" 2>&1 | tee "${run_dir}/l2_judge.log"
    fi
    
    echo "====== GEN RUN ${run_num} DONE $(date) ======"
}

run_edit() {
    local run_num=$1
    local run_dir="${RESULTS_DIR}/EDIT_${run_num}"
    mkdir -p "${run_dir}"
    
    echo "====== EDIT RUN ${run_num}/3 $(date) ======"
    
    docker run --rm \
      --name "edit_formal_${run_num}" \
      --cpus=2 --memory=4g \
      -e LLM_API_KEY="${LLM_API_KEY}" \
      -e VLM_API_KEY="${VLM_API_KEY}" \
      -e PYTHONPATH=/opt/openstoryline:/opt/openstoryline/src \
      -v /opt/openclaw:/opt/openclaw:ro \
      -v /root/.openclaw:/root/.openclaw \
      -v "${ROOT}/skills:/root/.openclaw/skills:ro" \
      -v "${ROOT}/adapters/openstoryline:/workspace/adapters:ro" \
      -v "${ROOT}/cases/11_video_edit/task.prompt:/workspace/task.prompt:ro" \
      -v "${ROOT}/cases/11_video_edit/fixtures:/workspace/fixtures:ro" \
      -v "${ROOT}/cases/11_video_edit/verify_video_edit.py:/workspace/verify.py:ro" \
      -v "${ROOT}/verifier/hidden:/workspace/verifier_hidden:ro" \
      -v /tmp/edit_smoke_v4.sh:/entrypoint.sh:ro \
      -v "${run_dir}:/workspace/output" \
      video-bench-edit:1.0 \
      bash /entrypoint.sh 2>&1 | tee "${run_dir}/container.log"
    
    # L2 judge
    if [ -f "${run_dir}/final.mp4" ]; then
        python3 "${ROOT}/l2_judge.py" \
          --video "${run_dir}/final.mp4" \
          --rubric "${ROOT}/evidence/judge_rubric_edit.json" \
          --output "${run_dir}/l2_judge_result.json" \
          --case-id SUB-CPU-VIDEO-EDIT-01 \
          --api-key "${DASHSCOPE_API_KEY}" 2>&1 | tee "${run_dir}/l2_judge.log"
    fi
    
    echo "====== EDIT RUN ${run_num} DONE $(date) ======"
}

# Run all formal runs
echo "BENCHMARK START $(date)"
echo "Results: ${RESULTS_DIR}"

run_gen 1
run_gen 2
run_edit 1
run_edit 2
run_edit 3

# Generate summary
echo "GENERATING SUMMARY..."
python3 -c "
import json, os
from pathlib import Path

results_dir = Path('${RESULTS_DIR}')
summary = {'runs': []}

for run_dir in sorted(results_dir.iterdir()):
    if not run_dir.is_dir():
        continue
    run_name = run_dir.name
    
    # Load verification
    bv_path = run_dir / 'business_verification.json'
    bv = json.loads(bv_path.read_text()) if bv_path.exists() else {}
    
    # Load task window
    tw_path = run_dir / 'task_window.json'
    tw = json.loads(tw_path.read_text()) if tw_path.exists() else {}
    
    # Load L2
    l2_path = run_dir / 'l2_judge_result.json'
    l2 = json.loads(l2_path.read_text()) if l2_path.exists() else {}
    
    # Check final.mp4
    final_path = run_dir / 'final.mp4'
    
    summary['runs'].append({
        'run': run_name,
        'hard_pass': bv.get('hard_pass', False),
        'l0_pass': bv.get('L0_pass', False),
        'l1_pass': bv.get('L1_pass', False),
        'l2_semantic_score': l2.get('semantic_score', None),
        'l2_scores': l2.get('scores', {}),
        'duration_seconds': tw.get('duration_seconds', None),
        'final_mp4_exists': final_path.exists(),
        'final_mp4_size_mb': round(final_path.stat().st_size / 1024 / 1024, 1) if final_path.exists() else 0,
    })

# Compute stats
gen_scores = [r['l2_semantic_score'] for r in summary['runs'] if r['l2_semantic_score'] and 'GEN' in r['run']]
edit_scores = [r['l2_semantic_score'] for r in summary['runs'] if r['l2_semantic_score'] and 'EDIT' in r['run']]

summary['gen'] = {
    'count': len(gen_scores),
    'scores': gen_scores,
    'mean': round(sum(gen_scores)/len(gen_scores), 4) if gen_scores else None,
    'success_rate': f'{sum(1 for r in summary[\"runs\"] if \"GEN\" in r[\"run\"] and r[\"hard_pass\"])}/{len(gen_scores)}',
}
summary['edit'] = {
    'count': len(edit_scores),
    'scores': edit_scores,
    'mean': round(sum(edit_scores)/len(edit_scores), 4) if edit_scores else None,
    'success_rate': f'{sum(1 for r in summary[\"runs\"] if \"EDIT\" in r[\"run\"] and r[\"hard_pass\"])}/{len(edit_scores)}',
}

output = results_dir / 'benchmark_summary.json'
output.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
print(json.dumps(summary, indent=2, ensure_ascii=False))
"

echo "BENCHMARK COMPLETE $(date)"
echo "Results: ${RESULTS_DIR}"
