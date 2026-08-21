# 候选系统选择记录

## 1. 选择原则

| 原则 | 说明 |
|------|------|
| P1 真实能力来源 + 可审计 Skill | 核心业务能力必须来自真实公开系统/Agent/Skill；benchmark 可以根据跨项目共性编写 orchestration Skill，但必须记录能力来源及映射关系，不得自行重新实现核心视频算法 |
| P2 覆盖同类共性操作 | 实现应能覆盖前述共性链路中的主要步骤，而不是只能完成单一 API 调用 |
| P3 能够冻结 | 必须能够固定源码 commit、Skill 内容、依赖和模型/provider 配置 |
| P4 适合基准环境运行 | 本地执行环境应可以 CPU-only；高成本生成模型允许通过外部 API 使用 |
| P5 具有可观测中间产物 | 需要看到 script、storyboard、timeline、clips 等，而不能只是一个黑盒 mp4 |
| P6 可以独立验收 | 最终必须能编写独立 verifier，而不是依赖原项目自己报告"成功" |

---

## 2. 生成类候选筛选

| 候选 | P1 真实 skill | P2 覆盖共性 | P3 可冻结 | P4 外部 API | P5 中间产物 | P6 独立验收 | 结论 |
|------|--------------|------------|----------|------------|------------|------------|------|
| **VideoClaw** | ✅ 真实 OpenClaw skill (MIT, 1.7k stars, openclaw-skills topic) | ✅ 6 阶段=生成类共性 8 步最完整单载体 | ✅ commit 可冻结 | ✅ 原生 DashScope/可灵/Seedance | ✅ script/images/clips/final | ✅ | **选定** |
| ViMax | ⚠️ 非 skill 形态，需自建包装层 | ✅ 自带 benchmark 35 用例 | ✅ | ✅ OpenRouter/Doubao/Veo | ✅ | ✅ | P1 不满足 |
| workrally | ✅ 腾讯开源真实 skill (ClawHub) | ❌ SaaS-locked，生成在 workrally.qq.com 发生，本地只编排 | ✅ | ❌ 锁定 workrally.qq.com，无法用豆包 | — | — | P2/P4 不满足 |
| vox-director | ✅ 真实 skill | ⚠️ Vox 拼贴型，非全生成 | ✅ | ✅ Atlas Cloud | ✅ | ✅ | P2 部分满足 |
| VideoWeaver | ✅ benchmark + skill library | ✅ 285 cases | ✅ | ✅ | ✅ | ✅ | 研究 value 最高但本身是 benchmark/harness，不适合直接承担单个 case |

### 选定理由

VideoClaw 的优势不是"世界上唯一的 Video Skill"，而是：在调研候选中，它对生成类共性流程的覆盖度、开放程度、中间产物可观察性以及本地 Backend 可部署性组合最好。其官方主流程直接覆盖剧本、角色/场景、分镜、参考图、视频生成和最终剪辑。同时它支持 OpenClaw Skill 集成并保留全链路资产。Backend 能够配置 DeepSeek、DashScope/Wan、Volcengine/Seedance、Kling 等独立 Provider，并监听本地 `127.0.0.1:8000`，非常适合在 benchmark 中区分 Agent 本地计算和远端生成 API。

ViMax 覆盖度非常高，是最重要的共性来源之一，但它本身更接近完整 multi-agent framework，而不是一个简单、固定的业务 Skill。它更适合作为"共性证据"和对照实现。

---

## 3. 剪辑类候选筛选

| 候选 | P1 真实 skill | P2 覆盖共性 | P3 可冻结 | P4 适合 CPU | P5 中间产物 | P6 独立验收 | 结论 |
|------|--------------|------------|----------|------------|------------|------------|------|
| **OpenStoryline** | ✅ openstoryline-use skill + Dockerfile (Apache-2.0, 3.2k stars) | ✅ 18 节点完整覆盖 E1-E9 | ✅ commit + 镜像 tag + 权重 SHA256 | ✅ transnet_device=cpu 默认 | ✅ 所有中间产物可观察 | ✅ | **选定（core 实现）** |
| video-use | ✅ 真实 skill (MIT, 21k stars) | ⚠️ 偏 transcript/audio-first，视觉理解弱 | ✅ | ✅ | ✅ EDL + 自检 | ✅ | 保留为 evidence source |
| Crayotter | ⚠️ 研究型 multi-agent workbench | ✅ 覆盖最广 | ⚠️ 完整框架较重 | ⚠️ 部分 GPU | ✅ | ✅ | 保留为 evidence source |
| CutClaw | ✅ paper + repo (955 stars) | ⚠️ 偏 hours-long + music montage | ✅ | ⚠️ 官方建议 GPU/NVDEC | ✅ | ✅ | P4 不满足 |

### 选定理由

OpenStoryline 的 default editing workflow skill 已直接给出了一套"通用剪辑流程"：search media → load media → split shots → understand clips → filter clips → group clips → generate script → recommend elements → voiceover → BGM → plan timeline → render video。这不是我们根据代码猜出的流程，而是项目作者自己定义的 generic editing workflow。

当前 OpenStoryline `config.toml` 中 `transnet_device = "cpu"` 是默认配置，很适合构造真实的 CPU 视频编辑工作负载。

video-use 是非常好的 shell-Agent 视频编辑 Skill（21k stars，browser-use 团队出品），但其官方流程明显偏 transcript/audio-first，视觉检查通过 `timeline_view` 在关键决策点按需进行。本 benchmark 使用 talking-head + B-roll + 无对白视觉素材 + 图片 + 干扰素材，希望真实执行 shot segmentation + ASR + visual understanding + filter/group + timeline + render，OpenStoryline 对这些操作覆盖更完整。因此 video-use 保留为 evidence source 和候选对照，OpenStoryline 作为 EDIT 的底层实现。

---

## 4. EDIT 不采用 OpenStoryline 双层 Agent

OpenStoryline 官方 `openstoryline-use` skill 规定 OpenClaw 的职责是：检查配置 → 启动 MCP server → 启动 Web service → 创建 session → 发送剪辑 prompt → 观察进度 → 拿 output.mp4。真正的节点执行（filter_clips、group_clips、generate_script、generate_voiceover、render_video）由 OpenStoryline 内部 editing Agent 运行。

这构成双层 Agent：outer OpenClaw + inner OpenStoryline agent。本 benchmark 不采用此模式，因为会使"测谁的编排能力"变模糊。

正式采用：**OpenClaw 是唯一负责任务理解、规划、操作选择和下一步决策的 Agent。** OpenStoryline 只作为真实的视频处理软件库，通过 thin CLI adapter 暴露其核心能力。

---

## 5. Skill 定位

不再坚持"所有 Skill 必须原封不动来自 upstream"。正式原则改为：**真实能力来源 + 可审计 Skill。**

- GEN：尽量直接冻结 VideoClaw 官方 OpenClaw Skill。
- EDIT：`video-edit/SKILL.md` 是 benchmark-owned Skill。它不是声称 OpenStoryline 官方 Skill，而是基于 E1-E9 共性操作映射到 OpenStoryline frozen implementations。`source_mapping.json` 记录每个 adapter 调用的 upstream module/symbol/commit，证明 benchmark 自己只写了接口适配层，核心算法仍来自真实冻结 upstream。

> Adapter only adapts; it does not decide.
