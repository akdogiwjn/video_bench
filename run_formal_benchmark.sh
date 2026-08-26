#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/home/lcq/video_agent/video_bench"
source "${ROOT}/config.env"
export DASHSCOPE_API_KEY DEEPSEEK_API_KEY LLM_API_KEY VLM_API_KEY

# #5 fix: validate before running
echo "[INFO] Running benchmark spec validation..."
python3 "${ROOT}/validate_benchmark_spec.py" || { echo "[ERROR] Benchmark spec validation failed. Aborting." >&2; exit 1; }

RESULTS_DIR="${ROOT}/results/formal_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${RESULTS_DIR}"

run_case() {
    local case_type=$1
    local run_num=$2
    local total=$3
    local case_id
    local run_name

    # Hardcoded CASE_ID — never construct from case_type string (#3 fix)
    if [[ "${case_type}" == "generate" ]]; then
        case_id="SUB-NET-VIDEO-GEN-01"
        rubric_file="${ROOT}/evidence/judge_rubric_gen.json"
        brief_file="${ROOT}/cases/10_video_generate/fixtures/creative_brief.json"
    else
        case_id="SUB-CPU-VIDEO-EDIT-01"
        rubric_file="${ROOT}/evidence/judge_rubric_edit.json"
        brief_file="${ROOT}/cases/11_video_edit/fixtures/edit_brief.json"
    fi

    run_name="${case_type^^}_${run_num}"
    local run_root="${RESULTS_DIR}/${run_name}"
    mkdir -p "${run_root}"

    echo "====== ${run_name}/${total} $(date) ======"

    # Per-run independent RESULT_ROOT (#2 fix)
    RUN_ID="formal_${run_name}" \
    RESULT_ROOT="${run_root}" \
    TIMEOUT=2400 \
    "${ROOT}/run_video_case.sh" "${case_type}" 2>&1 | tee "${run_root}/formal.log" || true

    # L2 judge — find final.mp4 in the actual output dir
    local output_dir="${run_root}/${case_id}"
    if [ -f "${output_dir}/final.mp4" ]; then
        python3 "${ROOT}/l2_judge.py" \
            --video "${output_dir}/final.mp4" \
            --rubric "${rubric_file}" \
            --output "${output_dir}/l2_judge_result.json" \
            --case-id "${case_id}" \
            --api-key "${DASHSCOPE_API_KEY}" \
            --brief "${brief_file}" 2>&1 | tee "${output_dir}/l2_judge.log" || true
    fi

    # Budget check (#16: distinguish GEN/EDIT, GEN also reads container.log)
    local output_dir="${run_root}/${case_id}"
    if [ -f "${output_dir}/openclaw_agent.stderr.log" ]; then
        local container_log_flag=""
        [ -f "${output_dir}/container.log" ] && container_log_flag="--container-log ${output_dir}/container.log"
        python3 "${ROOT}/budget_check.py" \
            --stderr-log "${output_dir}/openclaw_agent.stderr.log" \
            --budget "${ROOT}/evidence/api_pricing_snapshot.json" \
            --case-type "${case_type}" \
            ${container_log_flag} \
            --output "${output_dir}/budget_report.json" 2>&1 | tee "${output_dir}/budget_check.log" || true
    fi

    echo "====== ${run_name} DONE $(date) ======"
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
    # Find case output dir inside
    for case_dir in d.iterdir():
        if not case_dir.is_dir(): continue
        bv_path = case_dir / 'business_verification.json'
        l2_path = case_dir / 'l2_judge_result.json'
        tw_path = case_dir / 'task_window.json'
        rs_path = case_dir / 'run_summary.json'
        bv = json.loads(bv_path.read_text()) if bv_path.exists() else {}
        l2 = json.loads(l2_path.read_text()) if l2_path.exists() else {}
        tw = json.loads(tw_path.read_text()) if tw_path.exists() else {}
        rs = json.loads(rs_path.read_text()) if rs_path.exists() else {}
        bp_path = case_dir / 'budget_report.json'
        bp = json.loads(bp_path.read_text()) if bp_path.exists() else {}
        runs.append({
            'run': d.name,
            'case_id': case_dir.name,
            'hard_pass': bv.get('hard_pass', False),
            'budget_pass': bp.get('budget_pass') is True,
            'performance_valid': rs.get('performance_valid', False),
            'overall_pass': bv.get('hard_pass', False) and (bp.get('budget_pass') is True) and rs.get('performance_valid', False),
            'l0': bv.get('L0_pass', False),
            'l1': bv.get('L1_pass', False),
            'l2_score': l2.get('semantic_score'),
            'task_wall_s': tw.get('duration_seconds'),
            'task_cpu_time_s': rs.get('cpu_summary', {}).get('task_cpu_time_seconds'),
            'avg_cpu_percent': rs.get('cpu_summary', {}).get('task_avg_cpu_percent'),
            'peak_memory_bytes': rs.get('resource_summary', {}).get('task_peak_memory_bytes'),
            'net_rx_bytes': rs.get('resource_summary', {}).get('task_net_rx_bytes'),
            'net_tx_bytes': rs.get('resource_summary', {}).get('task_net_tx_bytes'),
            'disk_read_bytes': rs.get('resource_summary', {}).get('task_disk_read_bytes'),
            'disk_write_bytes': rs.get('resource_summary', {}).get('task_disk_write_bytes'),
            'performance_valid': rs.get('performance_valid', False),
        })

gen = [r for r in runs if 'GEN' in r['run']]
edit = [r for r in runs if 'EDIT' in r['run']]
gen_scores = [r['l2_score'] for r in gen if r['l2_score'] is not None]
edit_scores = [r['l2_score'] for r in edit if r['l2_score'] is not None]

def stats(run_list, scores):
    from statistics import median
    n_runs = len(run_list)
    n_pass = sum(1 for r in run_list if r.get('overall_pass'))
    n_hard = sum(1 for r in run_list if r.get('hard_pass'))
    n_budget = sum(1 for r in run_list if r.get('budget_pass') is True)
    if not scores:
        return {'count': n_runs, 'overall_pass_rate': f'{n_pass}/{n_runs}', 'hard_pass_rate': f'{n_hard}/{n_runs}', 'budget_pass_rate': f'{n_budget}/{n_runs}', 'l2_available': 0}
    s = sorted(scores)
    n = len(s)
    return {
        'count': n_runs,
        'overall_pass_rate': f'{n_pass}/{n_runs}',
        'hard_pass_rate': f'{n_hard}/{n_runs}',
        'budget_pass_rate': f'{n_budget}/{n_runs}',
        'l2_available': n,
        'l2_missing': n_runs - n,
        'l2_median': round(median(s), 4),
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
