# 外部评审意见 V7

> 日期：2026-08-25
> 5 个剩余问题，前 2 个 P0

## #1 SRT 自动生成违反 benchmark integrity (P0)
- entrypoint 在 task_window 后自动从 timeline 生成 final.srt → harness 帮 Agent 补产物
- 修：删除自动生成；Skill 告诉 Agent 字幕可作 sidecar final.srt 或 subtitle stream 交付

## #2 smoke evidence commit 不匹配 (P0)
- smoke_edit_v4.json 记录 commit=ebc94d5，但 SRT 逻辑在 186787a 才加入
- 修：代码全部修完 → commit → checkout → 跑 smoke → 记录正确 commit

## #3 BGM gate 仍不能严格证明 BGM 进了 final (P1)
- has_bgm from timeline + audio_not_silent，但 final 可能只有 talking-head 人声
- 修：加 render_video_result provenance 链（timeline → render → final）

## #4 shot_segmentation_executed 不能证明 TransNetV2 真跑过 (P1)
- Agent 自己写 JSON 也能满足
- 修：adapter 输出 execution evidence JSON（tool/symbol/method/device/status）

## #5 GEN freshness 判断用 -newer task.prompt 有污染风险 (P1)
- task.prompt mtime 是宿主文件时间，非 run 开始时间
- 修：touch run marker + find -newer marker
