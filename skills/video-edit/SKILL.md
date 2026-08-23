---
name: video-edit
description: "Use this skill when the user wants to edit, assemble, or reorganize existing video footage into a coherent final video. This means: loading source media files, detecting shot boundaries, transcribing audio (ASR), understanding clip content visually, filtering and grouping clips, generating narration scripts, selecting background music, planning a timeline, and rendering the final video. The deliverable must be a video file (final.mp4) plus intermediate artifacts. Do NOT trigger for generating video from scratch — use video-generate for that."
license: Apache-2.0
metadata:
  source: "benchmark-owned (mapped to OpenStoryline frozen implementations)"
  upstream_repository: "https://github.com/FireRedTeam/FireRed-OpenStoryline"
  upstream_commit: "local-snapshot"
  upstream_skill: false
  version: "1.0"
---

# Video Editing Skill

## Overview

This skill enables an agent to produce a coherent final video from existing source materials by orchestrating a set of video editing CLI tools. Each tool wraps a frozen upstream implementation from OpenStoryline's core nodes.

**The agent is the sole decision-maker.** This skill defines available capabilities and their interfaces; it does not prescribe a fixed execution order. The agent must decide which tools to call and in what sequence based on the task, available materials, and intermediate results.

## Available Tools

All tools are located at `/opt/video-tools/` and are executed as CLI commands. Each tool accepts JSON input and produces JSON output. See `source_mapping.json` for the exact upstream module, symbol, and commit each tool wraps.

### 1. inspect_media
Load and index input media files. Extracts video/image metadata (duration, resolution, fps, audio presence).
```
python3 /opt/video-tools/inspect_media.py --inputs '<json>' --output-dir '<dir>'
```
**Upstream**: `open_storyline.nodes.core_nodes.LoadMediaNode`

### 2. split_shots
Detect shot boundaries in video files using TransNetV2. Splits long videos into individual shot clips via ffmpeg stream copy.
```
python3 /opt/video-tools/split_shots.py --media '<json>' --output-dir '<dir>'
```
**Upstream**: `open_storyline.nodes.core_nodes.SplitShotsNode`

### 3. transcribe
Perform ASR (automatic speech recognition) on video clips using funasr (paraformer-zh). Extracts audio, transcribes, and returns text with timestamps.
```
python3 /opt/video-tools/transcribe.py --clips '<json>' --output-dir '<dir>'
```
**Upstream**: `open_storyline.nodes.core_nodes.LocalASRNode`

### 4. understand_clips
Analyze clips visually using a VLM (vision-language model). Generates content descriptions for each clip.
```
python3 /opt/video-tools/understand_clips.py --clips '<json>' --media '<json>' --output-dir '<dir>'
```
**Upstream**: `open_storyline.nodes.core_nodes.UnderstandClipsNode`

### 5. filter_clips
Filter clips based on their descriptions and user requirements. Selects which clips to keep.
```
python3 /opt/video-tools/filter_clips.py --clip-captions '<json>' --clips '<json>' --user-request '<text>' --output-dir '<dir>'
```
**Upstream**: `open_storyline.nodes.core_nodes.FilterClipsNode`

### 6. group_clips
Group filtered clips into narrative segments based on content similarity and user requirements.
```
python3 /opt/video-tools/group_clips.py --filter-result '<json>' --user-request '<text>' --output-dir '<dir>'
```
**Upstream**: `open_storyline.nodes.core_nodes.GroupClipsNode`

### 7. generate_script
Generate video narration script/copy and subtitles from grouped clips and their descriptions.
```
python3 /opt/video-tools/generate_script.py --groups '<json>' --clips '<json>' --captions '<json>' --user-request '<text>' --output-dir '<dir>'
```
**Upstream**: `open_storyline.nodes.core_nodes.GenerateScriptNode`

### 8. generate_voiceover (conditional)
Generate TTS voiceover audio from the script text. Uses external TTS API.
```
python3 /opt/video-tools/generate_voiceover.py --script '<json>' --output-dir '<dir>'
```
**Upstream**: `open_storyline.nodes.core_nodes.GenerateVoiceoverNode`

### 9. select_bgm
Select background music from the local BGM library based on user requirements and clip content. Uses librosa for audio feature matching.
```
python3 /opt/video-tools/select_bgm.py --user-request '<text>' --output-dir '<dir>'
```
**Upstream**: `open_storyline.nodes.core_nodes.SelectBGMNode`

### 10. plan_timeline
Plan the final video timeline: arrange clips, align subtitles, sync audio/BGM, enforce duration constraints.
```
python3 /opt/video-tools/plan_timeline.py --groups '<json>' --clips '<json>' --script '<json>' --bgm '<json>' --output-dir '<dir>'
```
**Upstream**: `open_storyline.nodes.core_nodes.PlanTimelineNode`

### 11. render_video
Render the final video from the planned timeline using moviepy + ffmpeg. Produces final.mp4.
```
python3 /opt/video-tools/render_video.py --timeline '<json>' --output-dir '<dir>'
```
**Upstream**: `open_storyline.nodes.core_nodes.RenderVideoNode`

## Key Rules

1. **Agent decides the order**: This skill does not prescribe E1→E2→E3. The agent must choose which tools to call based on the task and intermediate results.
2. **Preserve intermediate artifacts**: Every tool's JSON output must be saved to `/workspace/output/`.
3. **Use real tools, not pass-through**: Some upstream nodes have a `default_process` that skips real computation. The CLI adapters always call the real `process()` method. The verifier checks actual output.
4. **VLM and LLM configuration**: The OpenStoryline config.toml `[llm]` points to DeepSeek (OpenAI-compatible), `[vlm]` points to qwen-vl-max via DashScope. L2 judge also uses qwen-vl-max.
5. **CPU-only**: TransNetV2 runs on CPU by upstream default config. Do not attempt to use GPU.
6. **Do not install packages or download data during the task**
7. **Do not merely describe the work**: create and verify actual files

## Output Requirements

The following files must be written to `/workspace/output/`:
- `final.mp4` — the final rendered video
- `media_inventory.json` — result of inspect_media
- `shot_segments.json` — result of split_shots (must show real segmentation)
- `asr_transcript.json` — result of transcribe
- `clip_captions.json` — result of understand_clips
- `selection_and_groups.json` — result of filter_clips + group_clips
- `script.json` — result of generate_script
- `timeline.json` — result of plan_timeline (must include source provenance)
