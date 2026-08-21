# 视频 Agent 代表性负载基准测试

本项目构建两类具有代表性的视频 Agent 工作负载。负载分类及核心操作并非根据单一开源项目设计，而是结合已有 Agentic Video Generation、Agentic Video Post-Production benchmark 以及多个公开视频 Agent、Skill 和视频处理系统进行交叉抽象。

生成类负载覆盖创意理解、叙事与镜头规划、视觉资产生成、多镜头视频生成、音频组织及最终合成；剪辑类负载覆盖素材结构化、镜头切分、ASR、多模态理解、素材筛选与组织、时间线规划及最终渲染。

两类负载均使用 OpenClaw 作为唯一任务规划与工具编排 Agent。生成类使用 VideoClaw 能力（候选冻结版本）；剪辑类使用基于共性操作设计的 benchmark Skill，通过薄 CLI Adapter 调用 OpenStoryline 核心实现。

**VideoClaw 和 OpenStoryline 只是两个适合被冻结、运行和测量的代表实现。Benchmark 真正关注的是当前视频 Agent 中反复出现的通用工作模式，而非复现任何单一闭源产品或开源项目的内部架构。**

## 用例

| 用例 | CASE_ID | 类型 | Skill | 主测维度 |
|------|---------|------|-------|---------|
| 生成类 | SUB-NET-VIDEO-GEN-01 | Agentic Multi-shot Video Generation | VideoClaw | NET/API 编排 |
| 剪辑类 | SUB-CPU-VIDEO-EDIT-01 | Agentic Material-based Video Editing | OpenStoryline core | CPU/磁盘/内存 |

## 从这里开始

1. 复制 `config.env.example` 为 `config.env`，填入 API key。
2. 构建 Docker 镜像：
   ```bash
   docker build -t video-bench-gen:1.0 -f image_build/videoclaw.Dockerfile /home/lcq/video_agent/
   docker build -t video-bench-edit:1.0 -f image_build/openstoryline.Dockerfile /home/lcq/video_agent/
   ```
3. 执行用例：
   ```bash
   ./run_video_case.sh generate
   ./run_video_case.sh edit
   ```
4. 结果在 `results/<RUN_ID>/<CASE_ID>/`。

## 设计方法

```
已有 benchmark / research → 多个独立开源项目交叉分析 → 重复出现的操作
→ 抽象为共性 workload → 选择真实开源实现作为执行载体
→ OpenClaw + Skill 自主完成任务 → 独立 verifier 验证
```

详细证据见 `evidence/source_evidence.json`（所有引用均可独立审计）。

## 验收架构

| 层 | 说明 | 门控 |
|----|------|------|
| L0 过程验证 | 中间产物存在性 + 真实执行验证 | hard PASS/FAIL |
| L1 确定性验证 | ffprobe 时长/分辨率/音视频流 + timeline provenance | hard PASS/FAIL |
| L2 语义验证 | qwen-vl-max rubric 0-4 评分 | quality score (非 hard gate) |

## 与剪映/即梦的关系

本 benchmark 不声称复现剪映或即梦的内部技术栈。它代表的是更高层的用户任务语义和 Agent workload：
- SUB-NET-VIDEO-GEN-01 对应即梦等生成式视频产品所代表的"AI 原生内容生成"工作模式。
- SUB-CPU-VIDEO-EDIT-01 对应剪映等视频编辑产品所代表的"已有素材智能剪辑和重组"工作模式。
