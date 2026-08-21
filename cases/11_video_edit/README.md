# SUB-CPU-VIDEO-EDIT-01: Agentic Material-based Video Editing

## 用例说明

从 4-8 分钟异构已有素材出发，由 OpenClaw 自主完成素材结构化、镜头切分、ASR、多模态理解、内容筛选、叙事组织、时间线规划和最终渲染。

- **Skill**: benchmark-owned video-edit Skill (CLI adapters → OpenStoryline frozen core)
- **模型**: deepseek/deepseek-v4-flash (LLM) + qwen-vl-max (VLM)
- **目标时长**: 55-65 秒
- **比例**: 9:16
- **字幕**: 必须
- **BGM**: 必须

## 执行

```bash
./run_video_case.sh edit
```

## 产物

| 文件 | 说明 |
|------|------|
| final.mp4 | 最终成片 |
| media_inventory.json | 素材索引 |
| shot_segments.json | 镜头切分结果（必须真实 TransNetV2 执行） |
| asr_transcript.json | ASR 转录 |
| clip_captions.json | VLM 理解结果 |
| selection_and_groups.json | 筛选和分组 |
| script.json | 文案 |
| timeline.json | 时间线（含 source provenance） |
| business_verification.json | 验收结果 |

## 验收

- L0: 所有中间产物存在 + real_shot_segmentation 验证（非 pass-through）
- L1: ffprobe 时长 [55,65]s + 720p+ + 多源引用 + 字幕 + 干扰素材排除
- L2: qwen-vl-max rubric (brief/narrative/selection/continuity/audio_subtitle)

## 架构

OpenClaw 是唯一 agent。通过 11 个 CLI adapter 调用 OpenStoryline 冻结核心实现。Adapter 只做适配不做决策。详见 `adapters/openstoryline/source_mapping.json`。
