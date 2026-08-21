# 共性操作来源与抽取记录

## 1. 生成类共性操作（G1-G8）

生成类共性操作从以下四组独立来源交叉抽取：

| 来源 | 类型 | 关键证据 |
|------|------|----------|
| VideoWeaver | benchmark + paper | 16 类 285 case，agent 自行组合 foundation skills，agent-as-judge 检查 trace + final video |
| VideoClaw | 真实 OpenClaw skill + 后端 | 6 阶段：script→character/scene→storyboard→reference image→video→post-production |
| ViMax | agentic video generation 系统 | idea2video pipeline：story→characters→script→storyboard→shots→final video |
| vox-director | 真实 agent skill | topic→beat map→style→keyframes→motion→voice/music→ffmpeg→final.mp4 |

### 最终抽象

| 编号 | 共性操作 | Benchmark 定义 | 属性 |
|------|----------|----------------|------|
| G1 | 创意理解与剧本/叙事规划 | 从 brief 形成结构化故事 | 核心 |
| G2 | 角色、场景和视觉约束设计 | 明确主体、环境、风格 | 核心 |
| G3 | 分镜与多镜头规划 | 将故事拆成多个 shot | 核心 |
| G4 | 参考图/关键帧生成 | 为后续视频生成提供视觉条件 | 核心 |
| G5 | 视频片段生成 | 生成多个独立 video clip | 核心 |
| G6 | 音频层组织 | 配音/TTS/BGM，根据任务需要启用 | 条件性 |
| G7 | 后期合成与渲染 | 将各片段和音频形成最终视频 | 核心 |
| G8 | 中间产物管理 | 保存 script/storyboard/images/clips/final | 核心 |

> G1-G8 是 benchmark workload abstraction，不等于 VideoClaw 自身固定拥有八个 Stage。VideoClaw 官方主流程实际上是六个主要阶段。G6 音频/TTS 应被视为生成类视频 Agent 的通用音频能力，不能宣传成 VideoClaw 主流程固定独立阶段。

---

## 2. 剪辑类共性操作（E1-E9）

剪辑类共性操作从以下五组独立来源交叉抽取：

| 来源 | 类型 | 关键证据 |
|------|------|----------|
| AgenticVBench | benchmark + paper | 100 tasks，20 行业专家，Assembly/Repair/Sequencing/Repurpose 四类 |
| OpenStoryline | 真实视频剪辑系统 | 18 节点 default editing workflow：load→split→asr→understand→filter→group→script→voiceover→bgm→timeline→render |
| Crayotter | paper + 多 agent 系统 | source selection→multimodal analysis→timeline→narration/subtitle→render→revision，中间产物全部可观察 |
| CutClaw | paper + repo | hours-long footage→multimodal decomposition→playwriter agent→editor/reviewer agents→short video |
| video-use | 真实 agent skill (21k stars) | transcribe→pack transcript→LLM reasons→EDL→render→self-eval→repair |

### 最终抽象

| 编号 | 共性操作 | Benchmark 定义 | 本 case 是否要求 |
|------|----------|----------------|-----------------|
| E1 | 素材加载与盘点 | 加载视频/图片/音频，提取元数据 | 必须 |
| E2 | 镜头切分/素材结构化 | TransNetV2 shot boundary detection | 必须 |
| E3 | ASR/音频理解 | funasr paraformer-zh 语音转文字 | 必须，fixture 含语言 |
| E4 | 视觉/多模态内容理解 | VLM 分析每个 clip 的内容描述 | 必须 |
| E5 | 内容筛选、分组与素材选择 | LLM 根据用户需求选择和分组 clips | 必须 |
| E6 | 叙事/文案组织 | LLM 生成旁白文案和字幕 | 必须 |
| E7 | 字幕、BGM、配音等音频层处理 | TTS 生成配音，librosa 匹配 BGM | 至少字幕+BGM；配音可选 |
| E8 | 时间线规划 | 拍点对齐、时长约束、片段排序 | 必须 |
| E9 | 渲染与成片检查 | moviepy+ffmpeg 合成最终视频 | 必须 |

> 浓缩表达：Ingest → Segment → Understand → Select → Organize → Timeline → Render → Validate

---

## 3. 抽取方法

本方案不采用"先找到一个项目→看项目有哪些功能→按这些功能设计 benchmark"，而采用：

```
已有 benchmark / research
    ↓
多个独立开源项目交叉分析
    ↓
重复出现的操作
    ↓
抽象为共性 workload
    ↓
选择真实开源实现作为执行载体
    ↓
OpenClaw + Skill 自主完成任务
    ↓
独立 verifier 验证
```

只保留多个系统反复出现的共性操作。最终使用真实冻结代码执行这些操作，而不是自己造一套假的视频处理算法。
