# 外部评审意见 V6

> 日期：2026-08-23
> 6 个剩余问题，前 3 个 P0

## #1 audio_not_silent 没生效 (P0)
- silencedetect d=60 太长（GEN 只有 30-45s），且有 audio_streams 就 True 兜底
- 修：d=1, silence_ratio = sum(silence_duration)/final_duration, <0.95 才 PASS

## #2 BGM 不能证明进了 final (P0)
- has_bgm from timeline OR bgm_valid from bgm.json + audio_not_silent
- 但 final 可能只有 talking-head 原声
- 修：hard gate 只认 timeline bgm track AND final 非静音

## #3 字幕 timeline 规划了就 PASS (P0)
- subtitle_in_timeline = True 就 PASS，但 final 可能没字幕
- 修：hard gate 只认 subtitle stream OR valid final.srt；timeline 移到 L0

## #4 real_shot_segmentation 没真正修 (P1)
- 仍然叫 real_shot_segmentation，逻辑没变
- 修：改名 shot_segmentation_executed，验证 segments 存在 + 多 source 多 clip

## #5 agent exit code 没保存 (P1)
- entrypoint 仍 || true，没写 agent_exit_code.txt
- 修：set +e + AGENT_RC=$? + 写文件 + set -e

## #6 最新 commit 没有 smoke evidence
- 0c8a8f0 没有 tested_runs
- 修：重跑 GEN+EDIT smoke v4
