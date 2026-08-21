---
name: video-generate
description: "Use this skill when the user wants to generate a complete multi-shot video from a creative brief. This means: turning an idea into a structured script, designing characters and scenes, planning a storyboard, generating reference images or keyframes, producing individual video clips, organizing audio, and assembling a final rendered video. The deliverable must be a video file (final.mp4) plus intermediate artifacts. Do NOT trigger for editing existing video footage — use video-edit for that."
license: MIT
metadata:
  source: "https://github.com/HITsz-TMG/VideoClaw"
  commit: "1324b36"
  upstream_skill: true
  version: "1.0"
---

# Video Generation Skill

## Overview

This skill enables an agent to produce a complete narrative video from a creative brief by orchestrating the VideoClaw backend service. The backend runs locally at `http://127.0.0.1:8000` and provides a 6-stage generation pipeline.

## Prerequisites

- VideoClaw backend must be running at `http://127.0.0.1:8000`
- ffmpeg must be available in PATH
- API keys for LLM (DeepSeek), Image generation (DashScope/Wan/Seedream), and Video generation (DashScope/Seedance/Kling) must be configured in `backend/config.yaml`

## Available Capabilities

The following capabilities are provided through the VideoClaw backend API. The agent should select and orchestrate these autonomously based on the creative brief — do not follow a fixed script.

### 1. Script Planning
- Create a structured script/storyboard from a creative brief
- Define episodes, scenes, and narrative arc
- **API**: `POST /api/project/{session_id}/artifact/script_generation`

### 2. Character & Scene Design
- Design visual characters and environments
- Define style, appearance, and scene descriptions
- **API**: `POST /api/project/{session_id}/artifact/character_design`

### 3. Storyboard Planning
- Break the script into individual shots
- Define shot composition, camera, and transition per shot
- **API**: `POST /api/project/{session_id}/artifact/storyboard`

### 4. Reference Image Generation
- Generate reference images or keyframes for each shot
- Uses external image generation API (DashScope/Wan)
- **API**: `POST /api/project/{session_id}/artifact/reference_generation`

### 5. Video Clip Generation
- Generate individual video clips from reference images
- Uses external video generation API (Seedance/Kling/Wan)
- **API**: `POST /api/project/{session_id}/artifact/video_generation`

### 6. Post-production Assembly
- Assemble clips with audio into a final video
- Add transitions, music, voiceover as needed
- Uses ffmpeg locally
- **API**: `POST /api/project/{session_id}/artifact/post_production`

### 7. Audio Layer (conditional)
- Generate TTS voiceover from script
- Select or generate background music
- TTS provider: minimax or bytedance
- **API**: `POST /api/project/{session_id}/artifact/audio` (if needed)

## Key Rules

1. **Check backend health first**: `curl -sf http://127.0.0.1:8000/api/health`
2. **Model IDs must be dynamically obtained** from the backend API, never hardcoded
3. **Preserve intermediate artifacts**: script, storyboard, reference images, and video clips must be saved to the output directory
4. **Aspect ratio and resolution** must match the brief requirements
5. **Cross-shot consistency**: if the brief requires a recurring subject, ensure character consistency across shots
6. **Do not install packages or download data during the task**
7. **Do not merely describe the work**: create and verify actual files

## Workflow Reference

For detailed API documentation, see the VideoClaw references directory:
- `references/workflow/` — 6-stage workflow API
- `references/sandbox/` — single-shot tools
- `references/init_project/` — project initialization

## Output Requirements

The following files must be written to `/workspace/output/`:
- `final.mp4` — the final rendered video
- `script.json` — the generated script
- `storyboard.json` — the storyboard with shot breakdown
- `reference_images/` — directory of reference images
- `video_clips/` — directory of individual video clips
