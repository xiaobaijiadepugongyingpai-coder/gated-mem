# Gated-Mem 工作区目录全景导航指南
# (Workspace Directory Guide & Architecture Map)

> **更新时间**：2026-11-11  
> **项目定位**：**Git for Agent Memory —— 面向超长开发周期的本地可审计、可回滚架构状态引擎**  
> **使用说明**：本文档为当前工作区（`<repo-root>`）的统一入口导航指南，对所有整理归类的模块、文档、脚本及数据资产提供系统性索引与快速访问通道。

---

## 1. 工作区全景架构树 (Directory Tree)

```text
<repo-root>/
│
├── 📜 README.md                      # 项目入口说明与核心导航
├── 📜 DIRECTORY_GUIDE.md             # [当前文件] 完整工作区目录指南与索引
├── 📜 AGENTS.md                      # GitNexus 代码情报规则与 Agent 行为铁律
├── 📜 CLAUDE.md                      # Claude Code 适配规范与会话约束
├── 📜 .gitignore                     # Git 忽略配置
│
├── 📂 total_plan/                    # 【核心】顶层战略蓝图与大模型终审案卷
│   ├── 📄 gated_mem_decision_dossier.md           # 阶段 0：多 AI 方案综合归纳与大模型拍板案卷
│   ├── 📄 gated_mem_implementation_plan.md        # Plan One：水平切分多模型协同实施方案 (v2.1.1 增补版)
│   ├── 📄 gated_mem_plan_two_maker_checker.md     # Plan Two：Maker-Checker 红蓝对抗推荐实施方案 (v2.2)
│   ├── 📄 phase1_executive_adjudication_dossier.md# 阶段 1：首刀消融综合执行审计与门禁 1 大模型裁决案卷
│   └── 📄 phase2_execution_directive.md           # 阶段 2：大模型终审指令书 (GM-DIRECTIVE-P2-v2.1.2 阶段二执行指令)
│
├── 📂 benchmarks/                    # 【基准】阶段一首刀验证体系、评测工具与报告
│   ├── 📜 CONTRACT.md                             # 阶段一冻结契约 (12 节严格技术规范)
│   ├── 🐍 spike_cut1.py                           # 阶段一三分支核心运行器与自检器 (纯标准库)
│   ├── 📂 data/                                   # 评测数据集与 JSON Schema
│   │   ├── 📄 eval_cases_40.json                  # 40 组全栈演进与 Anti-trap 陷阱测试集 (171 KB)
│   │   └── 📄 eval_cases.schema.json              # 测试集 JSON Schema 规范
│   ├── 📂 tools/                                  # 数据集生成与强约束校验工具
│   │   ├── 🐍 build_dataset.py                    # 确定性 40 组数据构建脚本
│   │   └── 🐍 validate_dataset.py                 # 九条硬约束机械校验器
│   ├── 📂 audit/                                  # 独立审计与复核工具
│   │   └── 🐍 independent_scorer.py               # 独立重写评分器 (支持 5 组变异自检)
│   ├── 📂 results/                                # 评测原始结果与指标聚合
│   │   ├── 📄 raw_runs.json                       # 360 条 Run 全量运行明细 (含 rel/f/score)
│   │   ├── 📄 metrics.json                        # 聚合准确率指标 JSON
│   │   ├── 📄 audit_scores.json                   # 独立评分器核验结果 JSON
│   │   └── 📄 RESULTS_SUMMARY.md                  # 首刀结果人读摘要
│   └── 📂 reports/                                # 阶段一全套详细审计与分析报告
│       ├── 📄 spike_cut1_report.md                # 阶段一首刀验证主汇总报告 (Lead 签发)
│       ├── 📄 audit_phase1.md                     # 紫军监察官独立审计报告 (auditor2 签署)
│       ├── 📄 audit_crosscheck_gemini.md          # 异模型黑盒交叉复核报告 (Gemini 3.8 Flash)
│       ├── 📄 dataset_label_audit.md              # 数据集标签质量审计报告 (QA 签发)
│       └── 📄 phase1_executive_adjudication_dossier.md # 阶段一门禁 1 终审案卷 (镜像)
│
├── 📂 docs/                          # 【运维】团队协作、技术交接与大模型原始指示
│   ├── 📄 phase1_handoff.md                       # 阶段一 → 阶段二工程技术交接与避坑指南
│   ├── 📂 team_operations/                        # Agent Team 角色编排与任务卡
│   │   ├── 📄 AGENT_TEAM_SETUP.md                 # Agent Team 阵型设定与通道规则
│   │   ├── 📄 PHASE1_PROMPT.md                    # 阶段一执行用 Prompt 任务卡包
│   │   └── 📄 PHASE2_DIRECTIVE.md                 # 阶段二团队执行指令书 (镜像)
│   └── 📂 llm_advisories/                         # 大模型原始终审指导文本归档
│       ├── 📄 01_llm_adjudication_verdict.txt     # 初始大模型终审裁决书原文 (拍板.txt)
│       └── 📄 02_llm_advice_maker_checker.txt     # 大模型关于 Plan Two 红蓝对抗架构的建议原文
│
└── 📂 Preliminary_Exploration/       # 【归档】早期方案探索、学术争鸣与文献复核
    ├── 📄 gated_mem.md                            # 总体方案 v2.0 初始设计文档
    ├── 📄 memory_plugin.md                        # 初始探索备忘录 (LSTM 门控语义构想)
    ├── 📄 project_plan.md                         # 早期学术级严格风控规划 (v1.0)
    ├── 🌐 gated_mem_visualizer.html               # v2.0 力导向图原型与时间轴可视化网页
    ├── 📂 artifacts/                              # 早期支撑材料与深度自检
    │   ├── 📄 benchmark_guide.md                  # 早期公开基准与成本测算指南
    │   ├── 📄 competitive_landscape_analysis.md   # 早期竞品全景对比分析
    │   ├── 📄 gated_mem_workflow_guide.md         # 早期核心工作流全解指南
    │   └── 📄 self_critique_and_landscape_enhancement.md # 早期深度自检与四痛点吸收报告
    └── 📂 review/                                 # 早期学术与实证复核
        └── 📄 gated_mem_review.md                 # 独立复核深度报告 (推翻 4 个过时前提)
```

---

## 2. 四大核心目录分层与职责说明

### 2.1 `total_plan/` —— 顶层战略规划与大模型终审案卷
* **定位**：整个项目的顶层指导委员会，存放所有交付给前沿大模型进行顶层决策的**裁决案卷（Dossiers）**与**工程实施方案（Plans）**。
* **核心资产**：
  - [gated_mem_decision_dossier.md](total_plan/gated_mem_decision_dossier.md)：汇总了 AI-0 至 AI-3 所有争议的**阶段 0 决策案卷**，包含六大裁决卡片。
  - [gated_mem_implementation_plan.md](total_plan/gated_mem_implementation_plan.md)：**Plan One 实施方案**（基于 v2.1 终审裁决编制，已合入 FTS5 虚表与向量存储补丁）。
  - [gated_mem_plan_two_maker_checker.md](total_plan/gated_mem_plan_two_maker_checker.md)：**Plan Two 实施方案（当前主推执行方案）**，确立单主程独占代码 + 红蓝对抗的工程架构。
  - [phase1_executive_adjudication_dossier.md](total_plan/phase1_executive_adjudication_dossier.md)：**阶段一门禁 1 终审案卷**，穿透汇总了首刀 360 条测试数据、异模型黑盒复算与四大隐形盲点，供大模型正式签署阶段二放行令。
  - [phase2_execution_directive.md](total_plan/phase2_execution_directive.md)：**阶段二团队执行指令书（GM-DIRECTIVE-P2-v2.1.2）**，大模型签署的阶段二准入令、五项 P0 级技术调整与三大任务包（WBS）规格。

---

### 2.2 `benchmarks/` —— 基准测试体系、数据与首刀报告
* **定位**：阶段一实证验证的大本营，包含数据生成工具、40 组测试集、运行脚本及全套审计报告。
* **核心资产**：
  - [CONTRACT.md](benchmarks/CONTRACT.md)：阶段一冻结技术契约，涵盖 12 节严格口径与数学公式定义。
  - [spike_cut1.py](benchmarks/spike_cut1.py)：首刀消融核心代码，支持 8/8 独立自检与确定性输出。
  - [data/eval_cases_40.json](benchmarks/data/eval_cases_40.json)：覆盖 10 个技术领域的 40 组演进与 Anti-trap 陷阱集。
  - [reports/](benchmarks/reports/) 目录：
    - `spike_cut1_report.md`：首刀实测汇总报告；
    - `audit_crosscheck_gemini.md`：Gemini 3.8 Flash 异模型复核报告（揭露 TOPK 退化等核心盲区）；
    - `audit_phase1.md`：auditor2 独立重写评分器审计报告（零分歧 360/360）；
    - `dataset_label_audit.md`：QA 出题官九条硬约束复核报告。

---

### 2.3 `docs/` —— 团队运维、交接与大模型原始指示
* **定位**：工程落地期团队协同、技术交接与历史对话原始凭证。
* **核心资产**：
  - [phase1_handoff.md](docs/phase1_handoff.md)：阶段一至阶段二技术交接文档（详细记录了踩坑清单与阶段二 `src/` 接口规范）。
  - [team_operations/](docs/team_operations/)：
    - `AGENT_TEAM_SETUP.md`：Agent 团队运行配置与降级策略；
    - `PHASE1_PROMPT.md`：阶段一各 Agent 的任务 Prompt 卡包。
  - [llm_advisories/](docs/llm_advisories/)：
    - `01_llm_adjudication_verdict.txt`：大模型首次终审拍板原文；
    - `02_llm_advice_maker_checker.txt`：大模型关于 Plan Two 架构调整的指示原文。

---

### 2.4 `Preliminary_Exploration/` —— 早期方案探索与文献复核 (归档)
* **定位**：项目启动前期的头脑风暴、理论探索与批判性文献复查归档区。
* **核心资产**：
  - [gated_mem.md](Preliminary_Exploration/gated_mem.md)：方案 v2.0 初始雏形；
  - [memory_plugin.md](Preliminary_Exploration/memory_plugin.md)：LSTM 门控语义灵感来源；
  - [review/gated_mem_review.md](Preliminary_Exploration/review/gated_mem_review.md)：关键性的独立复核文献报告（指出 StateMem Table 6 Wrapper 效应与连坐负收益）。

---

## 3. 常见工作流快速跳转 (Fast-Tracks)

### 🚀 路径 A：交付大模型进行阶段一终审裁决与门禁放行
1. 打开 [total_plan/phase1_executive_adjudication_dossier.md](total_plan/phase1_executive_adjudication_dossier.md)；
2. 复制整篇内容发送给大模型，即可获取关于门禁 1 放行与阶段二前置约束的权威拍板意见。

### 🚀 路径 B：启动 Agent Team 推进阶段二（编写核心代码）
1. 参阅 [total_plan/gated_mem_plan_two_maker_checker.md](total_plan/gated_mem_plan_two_maker_checker.md) 第 4 节与第 5 节（获取标准作业 SOP 与 Prompt 卡包）；
2. 查阅 [docs/phase1_handoff.md](docs/phase1_handoff.md) 获取 `src/gated_mem/` 的标准接口签名与避坑清单；
3. 将任务派发给 `DeepSeek-V4.1F` 开始攻坚 `schema.py`、`gates.py` 与 `storage.py`。

### 🚀 路径 C：复现阶段一首刀跑分与独立审计验证
在工作区根目录下执行以下命令即可全流程自动化复算（0 依赖、0 成本）：
```bash
# 1. 验证运行器自检
python benchmarks/spike_cut1.py --self-test

# 2. 运行首刀跑分并导出指标
python benchmarks/spike_cut1.py --dataset benchmarks/data/eval_cases_40.json \
    --out-raw benchmarks/results/raw_runs.json \
    --out-metrics benchmarks/results/metrics.json

# 3. 独立评分器核验 (验证 360/360 零分歧)
python benchmarks/audit/independent_scorer.py \
    --dataset benchmarks/data/eval_cases_40.json \
    --raw benchmarks/results/raw_runs.json \
    --out benchmarks/results/audit_scores.json
```

---
*本目录指南维护工作区的全局资产对齐，随着后续阶段代码开发将持续更新。*
