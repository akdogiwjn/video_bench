# Tested Run Records

This directory contains de-identified test records proving that specific git commits + image versions + fixtures have been actually tested.

Each JSON file records:
- `git_commit`: the benchmark repo commit SHA
- `image_gen` / `image_edit`: Docker image tag
- `agent` / `agent_model` / `vlm_model`: agent and model versions
- `fixture_version`: which fixture version was used
- `hard_pass` / `l0_pass` / `l1_pass`: verification results
- `l2_score` / `l2_scores`: VLM judge results
- `task_wall_time_s`: actual agent execution time
- `tool_calls` / `tool_failures`: agent behavior stats

No API keys, no file paths, no raw logs — only structured summary data.

## Verified Runs

| File | Case | Commit | hard_pass | L2 | Wall time |
|------|------|--------|-----------|-----|-----------|
| smoke_gen.json | GEN | c30a52b | False (12s < 30s) | 0.60 | 1171s |
| smoke_edit.json | EDIT | c30a52b | True | 0.95 | 2089s |
