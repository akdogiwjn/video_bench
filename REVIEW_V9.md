# 外部评审意见 V9

> 日期：2026-08-25
> 8 个问题，前 5 个 P0

## P0:
#1: runner set +e/trap 回归（docker pipeline 前 set +e 丢失）
#2: docker --env-file ${VAR} 仍没 -e 显式传 LLM/VLM key
#3: formal runner rubric 路径 `${case_type}` → judge_rubric_generate.json（不存在）
#4: budget_pass + performance_valid 没进 formal overall_pass
#5: task_window 缺失/损坏时仍 fail-open

## P1:
#6: median 仍用 s[n//2]（GEN×2 偶数样本 bug）
#7: formal summary 仍缺 avg_cpu/peak_mem/net/disk
#8: validator 没接入 formal runner 第一行
