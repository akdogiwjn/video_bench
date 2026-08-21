# SUB-NET-VIDEO-GEN-01: Agentic Multi-shot Video Generation

## 用例说明

从创意 brief 出发，由 OpenClaw 自主完成剧本、角色/场景规划、分镜、参考视觉资产、多镜头视频生成和最终合成。

- **Skill**: VideoClaw (frozen commit `1324b36`)
- **模型**: deepseek/deepseek-v4-flash
- **目标时长**: 30-45 秒
- **比例**: 9:16
- **最少镜头数**: 4
- **最少场景数**: 2

## 执行

```bash
./run_video_case.sh generate
```

## 产物

| 文件 | 说明 |
|------|------|
| final.mp4 | 最终成片 |
| script.json | 剧本 |
| storyboard.json | 分镜 |
| reference_images/ | 参考图 |
| video_clips/ | 视频片段 |
| business_verification.json | 验收结果 |

## 验收

- L0: 中间产物存在 + video_clips ≥ 4
- L1: ffprobe 时长 [30,45]s + 720p+ + 音视频流
- L2: qwen-vl-max rubric (brief_adherence/narrative/consistency/continuity/audio)
