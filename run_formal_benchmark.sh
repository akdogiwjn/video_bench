#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/home/lcq/video_agent/video_bench"
source "${ROOT}/config.env"
export DASHSCOPE_API_KEY DEEPSEEK_API_KEY LLM_API_KEY VLM_API_KEY

RESULTS_DIR="${ROOT}/results/formal_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${RESULTS_DIR}"

run_case() {
    local case_type=$1
    local run_num=$2
    local total=$3
    local run_dir="${RESULTS_DIR}/${case_type^^}_${run_num}"
    
    echo "====== ${case_type^^} ${run_num}/${total} $(date) ======"
    
    RUN_ID="formal_${case_type}_${run_num}" \
    RESULT_ROOT="${RESULTS_DIR}" \
    "${ROOT}/run_video_case.sh" "${case_type}" 2>&1 | tee "${run_dir}/formal.log" || true
    
    # L2 judge
    if [ -f "${run_dir}/final.mp4" ]; then
        BRIEF_FLAG=""
        if [ "${case_type}" == "generate" ]; then
            BRIEF_FLAG="--brief ${ROOT}/cases/10_video_generate/fixtures/creative_brief.json"
        fi
        python3 "${ROOT}/l2_judge.py" \
            --video "${run_dir}/final.mp4" \
            --rubric "${ROOT}/evidence/judge_rubric_${case_type}.json" \
            --output "${run_dir}/l2_judge_result.json" \
            --case-id "SUB-NET-VIDEO-${case_type^^}-01" \
            --api-key "${DASHSCOPE_API_KEY}" \
            ${BRIEF_FLAG} 2>&1 | tee "${run_dir}/l2_judge.log" || true
    fi
    echo "====== ${case_type^^} ${run_num} DONE $(date) ======"
}

# GEN ×2
run_case generate 1 2
run_case generate 2 2

# EDIT ×3
run_case edit 1 3
run_case edit 2 3
run_case edit 3 3

# Summary
python3 -c "
import json
from pathlib import Path
r = Path('${RESULTS_DIR}')
runs = []
for d in sorted(r.iterdir()):
    if not d.is_dir(): continue
    bv = json.loads((d/'business_verification.json').read_text()) if (d/'business_verification.json').exists() else {}
    l2 = json.loads((d/'l2_judge_result.json').read_text()) if (d/'l2_judge_result.json').exists() else {}
    tw = json.loads((d/'task_window.json').read_text()) if (d/'task_window.json').exists() else {}
    rs = json.loads((d/'run_summary.json').read_text()) if (d/'run_summary.json').exists() else {}
    runs.append({
        'run': d.name,
        'hard_pass': bv.get('hard_pass', False),
        'l0': bv.get('L0_pass', False),
        'l1': bv.get('L1_pass', False),
        'l2_score': l2.get('semantic_score'),
        'task_wall_s': tw.get('duration_seconds'),
        'task_cpu_time_s': rs.get('cpu_summary', {}).get('task_cpu_time_seconds'),
        'task_peak_mem_bytes': rs.get('resource_summary', {}).get('task_peak_memory_bytes'),
        'task_net_rx': rs.get('resource_summary', {}).get('task_net_rx_bytes'),
    })

gen = [r for r in runs if 'GEN' in r['run']]
edit = [r for r in runs if 'EDIT' in r['run']]
gen_scores = [r['l2_score'] for r in gen if r['l2_score'] is not None]
edit_scores = [r['l2_score'] for r in edit if r['l2_score'] is not None]

def stats(run_list, scores):
    # #33: denominator = actual run count, not L2-available count
    # #34: report median as primary, mean as secondary
    n_runs = len(run_list)
    n_pass = sum(1 for r in run_list if r['hard_pass'])
    if not scores:
        return {'count': n_runs, 'success_rate': f'{n_pass}/{n_runs}', 'l2_available': 0}
    s = sorted(scores)
    n = len(s)
    return {
        'count': n_runs,
        'success_rate': f'{n_pass}/{n_runs}',
        'l2_available': n,
        'l2_missing': n_runs - n,
        'l2_median': s[n//2],
        'l2_min': min(s),
        'l2_max': max(s),
        'l2_mean': round(sum(s)/n, 4),
        'l2_scores': scores,
    }

summary = {
    'runs': runs,
    'gen': stats(gen, gen_scores),
    'edit': stats(edit, edit_scores),
}
(r/'benchmark_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
print(json.dumps(summary, indent=2, ensure_ascii=False))
"
echo "BENCHMARK COMPLETE $(date)"
