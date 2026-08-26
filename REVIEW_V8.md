# 外部评审意见 V8

> 日期：2026-08-25
> 8 个剩余问题

## #1 summarize fail-open (P0)
- task window 无采样时 fallback 到全量 → 应 fail-closed: PERF_DATA_INVALID

## #2 config.env ${VAR} Docker --env-file 不展开 (P0)
- Docker --env-file 不支持 ${VAR} interpolation → 容器内得到字面值
- 修: runner source 后 -e 显式传四个 key

## #3 budget 计数不可靠 → 降为辅助指标 (P1)
- grep 日志文本计数不准 → overall_pass 先不 gate budget

## #4 GEN final.mp4 选择不严谨 (P1)
- largest MP4 → 记录 selection_method + 优先 Agent 自己放的 final.mp4

## #5 run_metadata.json 自动生成 (P1)
- git commit + docker image ID + openclaw version + fixture sha + skill sha

## #6 模型权重 SHA256 (P2)
- transnetv2 weight sha256 记入 evidence

## #7 formal summary 补全资源指标 (P1)
- 带 avg_cpu/peak_mem/net_rx/tx/disk_read/write

## #8 prepare.sh 语义 + task_start/end_epoch 清理 (P2)
- prepare.sh 标注为 standalone validation
- 删 summarize 中不存在的 task_start/end_epoch.txt 读取
