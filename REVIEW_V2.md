# 外部评审意见 V2

> 来源：第三方评审第二轮，基于 commit 78f461a
> 日期：2026-08-21
> 状态：待逐条分析

---

## 一、上一轮修复确认

评审确认以下修复已真实落地（非 README 宣称）：
- run_video_case.sh 不再 mount hidden GT 到 Agent 容器
- Verifier 在宿主侧执行
- 仓库内有正式 entrypoint，task window 只包 OpenClaw 任务阶段
- 不再自动 upscale 修复 Agent 失败
- summarize_run.py 按 task_window 过滤
- Docker stats 单位 parser 支持 SI/IEC
- CPU cgroup 通过 /proc/PID/cgroup
- GEN Skill provenance benchmark-adapted
- L2 传入 brief、evaluation copy、schema 校验

**结论：设计理念已不是原型拼装。**

---

## 二、P0：formal runner 目录逻辑错误

### 2. formal runner 每轮写同一目录

run_formal_benchmark.sh 定义 `run_dir=${RESULTS_DIR}/${case_type^^}_${run_num}`（如 GENERATE_1），但传给 run_video_case.sh 的是 `RESULT_ROOT=${RESULTS_DIR}`，run_video_case.sh 自己构造 `RUN_DIR=${RESULT_ROOT}/${CASE_ID}`。

所以实际结果写到 `formal_xxx/SUB-NET-VIDEO-GEN-01/`，GEN #1 和 #2 写同一目录。formal.log 和 L2 路径也找不到文件。

**必须修成 per-run 独立目录。**

### 3. formal runner case_id 拼错

`--case-id "SUB-NET-VIDEO-${case_type^^}-01"` 产生 `SUB-NET-VIDEO-GENERATE-01`（不是 GEN）和 `SUB-NET-VIDEO-EDIT-01`（不是 SUB-CPU-VIDEO-EDIT-01）。

**直接用硬编码 CASE_ID，不要动态拼字符串。**

### 4. run_video_case.sh GEN verifier 报错被吞

`verify_video_${CASE}.py ... ${GT_FLAG}` 对 GEN 也传了 `--ground-truth`，但 GEN verifier 不支持该参数，argparse 报错后 `|| true` 吞掉。

**应该只有 EDIT 才传 GT，verifier infrastructure error 不应静默。**

---

## 三、EDIT fixture V2 改善大但还不够

### 5. 总时长不足

当前 2.8 分钟，目标 4-6 分钟。2.8→60s 压缩比不够强，selection 压力弱。

**至少 4 分钟 source material。**

### 6. B-roll 太"测试数据化"

source_003-005 是 ffmpeg testsrc/yuvtestsrc/smptebars，对 TransNetV2 CPU workload 没问题，但对 VLM 理解/筛选/分组不够真实。

**建议用 AI 图片做 image-to-video / Ken Burns 产生有真实语义的动态 B-roll。**

### 7. asset_id 重复

source_001 同时出现在 .jpg 和 .mp4 两条，primary key 不唯一。

**改为 source_001_video / source_001_image 或合并为一条。**

---

## 四、冻结不彻底

### 8. EDIT Skill 残留 PLACEHOLDER

SKILL.md frontmatter 仍写 `upstream_commit: "PLACEHOLDER"`，但 source_manifest.json 已改成 `local-snapshot`。

**`grep -R PLACEHOLDER .` 应返回 0 条。**

### 9. OpenStoryline "local-snapshot" 不够

只记了 config.toml + requirements SHA256，但 Docker COPY 整个源码树。config/requirements 没变不代表核心 .py 文件没变。

**需要对整个源码树做 deterministic hash manifest。**

### 10. Torch 没真正锁死

`pip install torch==2.13.0 || pip install torch || true` 意味着 fallback 到最新版或跳过。

**指定确认存在的版本，失败则 build FAIL。**

### 11. case_index.json 与子 manifest 不一致

case_index.json 仍写 `skill_frozen: false`，但 source_manifest.json 已 `frozen: true`。

**case_index.json 必须作为 canonical index，与所有子 manifest 一致。**

---

## 五、Verifier 增强

### 12. 真实切镜判断不够严格

当前只要 segments > 1 且 end > start 就认为 real_split。但如果每个 source 各产生 1 个完整 segment，总数 > 1 但没有内部切分。

**应按 media_id 分组，至少一个 source 有 ≥ 2 个 segment。**

### 13. Provenance mapping 缺失

verifier 直接用 `media_id in distractor_ids`，但 OpenStoryline 可能产生自己的内部 ID。

**inspect_media adapter 应输出 fixture_asset_id → openstoryline_media_id 映射。**

### 14. BGM 验证偏松

`clip.kind == "audio"` 可能是原始讲话音轨、voiceover，不一定是 BGM。

**应验证 select_bgm_result → timeline bgm track 完整 provenance。**

---

## 六、L2 与 Budget

### 15. formal runner 对 EDIT 没传 brief

L2 judge 支持 --brief，但 formal runner 只给 GEN 传了，EDIT 没有。

**给 EDIT 准备 fixtures/edit_brief.json。**

### 16. Budget 有代码但没 enforcement

budget_check.py 存在但 canonical runner 没调用。且固定拿 EDIT budget，不区分 GEN/EDIT。GEN 的 image/video calls 不在 OpenClaw stderr.log 里。

**接入 runner，区分 GEN/EDIT，GEN 从 container.log 解析。**

---

## 七、tested_runs 过时

### 17. tested_runs 记录的是旧版本

smoke_gen.json 硬编码 c30a52b + fixture V1 + hard_pass=false。最新是 78f461a + V2。

**修完 runner 后重新跑 smoke，提交新 tested_runs。GEN 必须 hard PASS。**

---

## 八、Benchmark isolation

### 18. /root/.openclaw 读写 mount

正式 run 之间共享 cache/config/session state。entrypoint 清 session 不够。

**每轮 copy base config 到临时目录再 mount。记录 OpenClaw version + config hash。**

---

## 九、最终 8 项收敛

评审将以上收敛为 8 项必做：

1. 修 formal runner：per-run 独立目录 + 正确 CASE_ID + L2 路径
2. 修 verifier 调用：只有 EDIT 传 GT + verifier error 不静默
3. EDIT fixture ≥4 分钟 + 真实语义 B-roll
4. OpenStoryline tree hash manifest + 清 PLACEHOLDER + 同步 case_index.json
5. Docker 锁死 torch + 冻结 digest/SHA + 去掉 fallback
6. 强化 EDIT provenance：asset_id 唯一 + media_id mapping + 真实 split + distractor + BGM
7. EDIT L2 brief + budget checker 接入 runner 区分 GEN/EDIT
8. 用最新 HEAD 重跑 smoke + 提交 tested_runs + GEN 必须 hard PASS
