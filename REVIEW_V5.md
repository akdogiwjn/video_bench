# 外部评审意见 V5 (9.2/10)

> 日期：2026-08-23
> 7 个剩余问题，前 4 个 P0

## #1 runner 异常退出清理 (P0)
- set -e + pipefail 下 docker run pipeline 失败会跳过 verifier/cleanup
- 修：set +e 包裹 docker run + trap cleanup EXIT + 保存 agent_exit_code.txt

## #2 budget 缺失默认 True (P0)
- overall_pass = hard_pass AND bp.get("budget_pass", True) → 缺失报告时默认通过
- 修：budget_pass = bp.get("budget_pass") is True
- 删 max_retry_per_stage（未 enforce 的约束不声明）

## #3 EDIT brief 3→4 B-roll (P0)
- brief 写 3 B-roll，manifest 实际 4
- 修：brief 改成 4 B-roll + validator 检查 talking_head/broll/image 数量

## #4 L2 material_selection 不可观测 (P0/P1)
- judge 没看到原始素材，无法判断"选择质量"
- 修：改成 content_relevance_and_variety（只看 final video 能判的维度）

## #5 BGM/字幕/音频 hard gate 偏松 (P1)
- BGM 只需 bgm.json 存在就 PASS，不需进 final
- 字幕只需 timeline 有 subtitle track
- 音频只检查 stream exists，不检查是否静音
- 修：BGM 需 final 有非静音音频 + silencedetect + 字幕明确 sidecar/burn-in

## #6 shot segmentation 无法证明是 TransNet 真实 boundary (P1)
- max_shot_duration=30s 会强制切分，不能证明 TransNet 检出了真实边界
- 修：改为 shot_segmentation_executed + adapter 输出 execution evidence

## #7 GEN ×2 median bug (P1)
- s[n//2] 对偶数个样本取的是上半而非真正中位数
- 修：用 statistics.median
