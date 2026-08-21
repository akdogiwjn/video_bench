# 外部评审意见

> 来源：第三方评审，2026-08-21
> 状态：待逐条分析

---

## 一、构建目标是否实现

### 1. "先抽共性，再选实现"——已实现，仓库最强的一部分

README 已明确方法论：benchmark/research → 多开源项目交叉分析 → 重复操作 → 共性 workload → 真实开源实现 → OpenClaw + Skill → independent verifier。

evidence/common_operations.md 落实了来源。GEN 从 VideoWeaver/VideoClaw/ViMax/vox-director 抽 G1-G8；EDIT 从 AgenticVBench/OpenStoryline/Crayotter/CutClaw/video-use 抽 E1-E9。

G1-G8 是 benchmark abstraction，不等于 VideoClaw 固定 8 阶段。这一句很重要，说明不是拿单一仓库倒推 workload。

**结论：保留，不需要大改。**

### 2. 两个 workload 都是 OpenClaw 作为唯一 Agent——已对齐

README 明确：两类负载均使用 OpenClaw 作为唯一任务规划与工具编排 Agent。候选比较明确否掉了双层 Agent。EDIT 改成 OpenClaw + benchmark Skill + OpenStoryline core。

**结论：不要再改回 MCP/双层 Agent。**

### 3. Prompt 设计是对的

GEN prompt 要求 30-45s、≥4 shot、≥2 场景、跨镜头主体一致、≥720p、有音频、保留中间产物，最后只说"读取 Skill，自主规划完成任务"。没有固定调用序列。

EDIT prompt 同样不固定 E1-E9 顺序。保持住了"测 Agent 编排，而不是脚本回放"。

**结论：已做好。**

---

## 二、最大业务问题：EDIT fixture 不代表真实剪辑 workload

### 4. 当前 fixture 主体是 DashScope 生成的图片 → ffmpeg 冻结成 60s 静态视频

造成三个问题：
- E2 镜头切分没有真正被测到（静态视频无真实 shot boundary，max=30s 机械拆分被误判为 PASS）
- E3 ASR 没有被认真触发（无语音素材）
- E4/E5 难度太低（只有 4 个静态主题视频 + 1 图片）

### 5. 建议 EDIT fixture V2 升级

不推倒架构，只换 fixture：
- 总时长 5-6 分钟
- 2 个 talking-head 视频（45-90s，含语音，有自然 cut）
- 4-6 个动态 B-roll（10-40s/段）
- 1-2 张图片
- 4 类 distractor
- 至少 8-12 个 source candidates

### 6. 隐藏 Ground Truth 不一致

GT 写 source_001~006 但 manifest 只有 source_001~005。GT 的 narrative hint 写 talking_head intro → conclusion 但 fixture 根本没有 talking-head。

---

## 三、Skill 冻结未完成

### 7. case_index.json 自己暴露了状态

GEN: skill_frozen=false, skill_md_sha256=PLACEHOLDER
EDIT: upstream_commit="", upstream_frozen=false, adapter SHA256 全是 PLACEHOLDER

README 写"冻结的 VideoClaw/冻结的 OpenStoryline"比真实状态超前。应写"候选冻结版本"或完成冻结再改回来。

---

## 四、Skill provenance 问题

### 8. GEN Skill 不是 upstream 原版

skills/video-generate/SKILL.md 标注 upstream_skill: true，但实际做了 benchmark 改造（去掉人工停点、重新整理成 API capabilities）。

建议改成 skill_type: benchmark-adapted，同时冻结 upstream_SKILL.md + benchmark_SKILL.md + adaptation_rationale.md。

### 9. P1 原则应更新

candidate_comparison.md 仍写"P1 真实 Agent/Skill，不是自己编一套假 Skill"，但 EDIT 现在是 benchmark-owned SKILL，逻辑冲突。应改成"P1 真实能力来源 + 可审计 Skill"。

---

## 五、Adapter 兼容性风险

### 10. StubLLMClient 与 upstream 不兼容

_adapter_base.py 构造 StubLLMClient 只有 sample()，但 upstream FilterClipsNode/GroupClipsNode/UnderstandClipsNode 调用 llm.complete()。LLM/VLM 类型 Node 不能可靠工作。

### 11. understand_clips 输入结构风险

adapter 构造 inputs["media"]["media"][...]，但 upstream 期待 inputs["media"][media_id]。

---

## 六、Docker 镜像不可复现

### 12. EDIT Dockerfile 问题

- COPY FireRed-OpenStoryline-main/ 不是固定 commit SHA
- pip install torch torchaudio 没锁版本
- requirements 安装失败后 fallback 手工依赖
- download.sh || echo WARN（权重下载失败仍 build 成功）

### 13. EDIT Dockerfile 没有 COPY adapters

只创建 /opt/video-tools 空目录，但 prepare.sh 要求 /opt/video-tools/*.py 存在且 executable。

### 14. GEN 路径不一致

Dockerfile 把 Skill 放到 /opt/videoclaw/SKILL.md，但 prepare.sh 检查 /opt/videoclaw/video-claw/SKILL.md。

---

## 七、资源测量问题（最严重）

### 15. 资源窗口算错了

monitor 生命周期包含 prepare + Agent + 后处理 + verifier，但 summarize_run.py 没有按 task_window.json 过滤 samples。wall_time 使用 host 的 docker run 前后时间，不等于 task_window duration。

### 16. 正确做法

summarize_run.py 读取 task_window.json 的 start/end_epoch，只保留窗口内 samples。同时报告 container_total_wall_time 和 task_wall_time。

### 17. Docker stats 单位 parser 缺失

parse_mem() 不支持 kB/MB/GB（SI 单位），Docker NetIO/BlockIO 常用这些。可能导致 GEN 的 NET 数据全部为 0。

### 18. CPU cgroup 路径检测脆弱

猜 /sys/fs/cgroup/<id> 和 /sys/fs/cgroup/docker/<id>，但 systemd cgroup driver 实际路径可能是 /system.slice/docker-<id>.scope。建议用 docker inspect → PID → /proc/<PID>/cgroup 解析。

---

## 八、Entrypoint "补考"问题

### 19. entrypoint.sh 自动 upscale 是作弊

task end 后如果 short_side < 720，用 ffmpeg upscale 覆盖 final.mp4。这会把 Agent 的 L1 FAIL 变成 PASS，掩盖任务失败。

### 20. final.mp4 copy 可保留

copy render output → final.mp4 是 artifact canonicalization（不重新编码、不改内容）。但 upscale 属于内容修复，必须删除。

---

## 九、隐藏 Ground Truth 不隐藏

### 21. Agent 能读到答案

run_video_case.sh 把整个 repo mount 到 /workspace，包含 verifier/hidden/。OpenClaw 有 shell 能力，可以 cat verifier/hidden/edit_ground_truth.json 读到 distractor labels。

应：Agent container 只 mount task.prompt + skill + fixture-visible + tools + output。Verifier 在 host 上独立运行。

---

## 十、Formal Runner 不可复现

### 22. 使用了不在仓库的脚本

run_formal_benchmark.sh GEN 用 /tmp/gen_smoke_entrypoint.sh，EDIT 用 /tmp/edit_smoke_v4.sh，这两个文件不在仓库。

应统一为单一 canonical runner（run_video_case.sh），formal runner 只负责循环调用。

---

## 十一、测试结果不可审计

### 23. results/ 被排除，无法证明跑通过

建议增加 evidence/tested_runs/，放脱敏后的 {git_commit, image_digest, hard_pass, l2_score, task_wall_time} 等。

---

## 十二、Verifier 深度不够

### 24. L0 太浅

script.json 只检查文件存在，哪怕 {} 也算。应验证：script 是有效 JSON 且含 scenes/story；storyboard shot_count ≥ 4；reference image count ≥ 2；video clip count ≥ 4。

### 25. 没有验证 9:16

只看 short_side ≥ 720，1280×720 横屏也 PASS。需要检查 aspect ratio ≈ 9/16。

### 26. BGM 没有被验证

只看 audio stream exists，不验证 BGM 存在。应从 timeline/provenance 验证 bgm asset。

### 27. 字幕验证偏松

sidecar .srt 文件存在就 PASS，但视频里可能看不到字幕。需定义：允许 sidecar 还是要求 burn-in。

### 28. Timeline verifier 太宽

只要有一个 clip 就 PASS。应检查：source_ref 合法、start < end、不超过 source duration、timeline duration ≈ final duration、至少使用 N 个 source。

---

## 十三、L2 Judge 问题

### 29. Judge 不知道 creative brief

只给 VLM rubric dimensions，不给 creative_brief.json 或 task brief。Judge 无法回答"有没有符合指定创意"。

### 30. >20MB 视频发 file://

DashScope 云端访问不到 file:// 路径。应统一生成 evaluation copy（360×640/540×960 合理 bitrate）。

### 31. L2 缺少 JSON schema 校验

只检查 json.loads 成功，应验证：所有 dimension 存在、值是 integer、0 ≤ score ≤ 4。

---

## 十四、预算未执行

### 32. 预算是文档不是约束

manifest 定义了 max_video_api_calls 等，但没有 API call accounting → budget verifier。需要从 backend log 解析 API 调用次数，超预算判 BUDGET_EXCEEDED。

---

## 十五、统计问题

### 33. Formal 汇总分母 bug

gen_scores 用 len(gen_scores) 作分母，L2 失败时不计入，导致 1/1 而非 1/2。分母应为 formal run count。

### 34. 应用 median 而非 mean

GEN ×2 / EDIT ×3 样本量小，mean 易被异常值拖走。应报告 P50/median、min、max、mean（附带）、success rate。
