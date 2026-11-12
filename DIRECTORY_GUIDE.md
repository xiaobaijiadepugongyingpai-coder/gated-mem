# Gated-Mem 工作区目录全景导航指南
# (Workspace Directory Guide & Architecture Map)

> **更新时间**：2026-11-12  
> **项目定位**：*Git for Agent Memory —— 面向超长开发周期的本地可审计、可回滚架构状态引擎*  
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
├── 📂 src/                           # 【核心源码】Gated-Mem 生产级 Python 模块库
│   └── 📂 gated_mem/                 # 核心内核实现包 (1751 行生产代码，独占主程 DeepSeek-V4.1F)
│       ├── 🐍 __init__.py            # 纯净包定义 (零副作用)
│       ├── 🐍 schema.py              # 五状态枚举、四类型衰减参数、5×5 状态矩阵、双通道回执契约
│       ├── 🐍 gates.py               # 无状态纯数学门控函数、零连坐扣分设计、闭式解验证
│       ├── 🐍 storage.py             # WAL 模式 SQLite、BLOB 向量、FTS5 虚表、递归 CTE、原子 Undo
│       ├── 🐍 events.py              # 事件溯源批次链（causation_id）、投影重建（消费 EVENT_UNDONE）
│       ├── 🐍 conflicts.py           # 槽位两阶段裁决、别名归一化、[Replaced: X] 残差装配、覆盖零误杀
│       └── 🐍 retrieval.py           # 混合候选池、多跳失效追溯、TOPK 强截断、双通道 XML 生成
│
├── 📂 tests/                         # 【单元测试】阶段二自动化单测套件 (79 个用例，93% 覆盖率)
│   ├── 🐍 test_schema.py             # 状态机迁移合法性、Pydantic 序列化与 XML 格式测试
│   ├── 🐍 test_gates.py              # 幂律闭式解精度、生命力纯函数、排序算法测试
│   ├── 🐍 test_storage.py            # SQLite 增删改查、FTS5 触发器同步、递归 CTE 多跳查询测试
│   ├── 🐍 test_events.py             # 事件日志批次、causation 链追溯、投影重建测试
│   ├── 🐍 test_conflicts.py          # 槽位冲突裁决、SUPERSEDES 关系标记、别名归一化测试
│   ├── 🐍 test_retrieval.py          # 混合检索、TOPK 淘汰观测、多跳失效告警、双通道隔离测试
│   └── 🐍 test_purity.py             # AST 语法级扫描 (禁 print/stdout、禁 TODO、零连坐 psi 扫描)
│
├── 📂 total_plan/                    # 【核心】顶层战略蓝图与大模型终审案卷
│   ├── 📄 gated_mem_decision_dossier.md           # 阶段 0：多 AI 方案综合归纳与大模型拍板案卷
│   ├── 📄 gated_mem_implementation_plan.md        # Plan One：水平切分多模型协同实施方案 (v2.1.1 增补版)
│   ├── 📄 gated_mem_plan_two_maker_checker.md     # Plan Two：Maker-Checker 红蓝对抗推荐实施方案 (v2.2)
│   ├── 📄 phase1_executive_adjudication_dossier.md# 阶段 1：首刀消融综合执行审计与门禁 1 大模型裁决案卷
│   ├── 📄 phase2_execution_directive.md           # 阶段 2：大模型终审指令书 (GM-DIRECTIVE-P2-v2.1.2 阶段二执行指令)
│   ├── 📄 phase2_executive_adjudication_dossier.md# 阶段 2：阶段二综合执行审计与大模型裁决案卷
│   └── 📄 phase3_execution_directive.md           # 阶段 3：【最新终审指令】大模型终审裁决与阶段三执行指令 (GM-DIRECTIVE-P3-v2.2.0)
│
├── 📂 benchmarks/                    # 【基准】阶段一首刀体系与阶段二高压对抗体系
│   ├── 📜 CONTRACT.md                             # 阶段一冻结契约 (12 节严格技术规范)
│   ├── 🐍 spike_cut1.py                           # 阶段一三分支核心运行器与自检器 (纯标准库)
│   ├── 🐍 build_phase2_stress.py                  # 阶段二高压数据集确定性生成脚本 (GLM-5.3-Flash)
│   ├── 🐍 run_phase2_stress.py                    # 阶段二高压检索与生死对照运行器
│   ├── 🐍 pressure_phase2.py                      # 阶段二内部高压压测脚本
│   ├── 🐍 gate2_check.py                          # 阶段二 Gate 2 六项硬指标一键自动化验证器 (15/15 PASS)
│   ├── 📂 data/                                   # 评测与压测数据集
│   │   ├── 📄 eval_cases_40.json                  # 阶段一 40 组全栈演进与 Anti-trap 陷阱测试集 (171 KB)
│   │   ├── 📄 eval_cases.schema.json              # 阶段一测试集 JSON Schema 规范
│   │   └── 📄 phase2_dense_stress_15.json         # 阶段二 15 组高密度多跳高压场景压测集 (599 KB)
│   ├── 📂 tools/                                  # 阶段一数据生成与强约束校验工具
│   │   ├── 🐍 build_dataset.py                    # 阶段一确定性 40 组数据构建脚本
│   │   └── 🐍 validate_dataset.py                 # 阶段一九条硬约束机械校验器
│   ├── 📂 audit/                                  # 阶段一独立审计工具
│   │   └── 🐍 independent_scorer.py               # 独立重写评分器 (支持 5 组变异自检)
│   ├── 📂 results/                                # 评测原始结果与指标聚合
│   │   ├── 📄 raw_runs.json                       # 阶段一 360 条 Run 全量运行明细
│   │   ├── 📄 metrics.json                        # 阶段一聚合准确率指标 JSON
│   │   ├── 📄 audit_scores.json                   # 阶段一独立评分器核验结果 JSON
│   │   └── 📄 RESULTS_SUMMARY.md                  # 阶段一首刀结果人读摘要
│   └── 📂 reports/                                # 阶段一与阶段二详细报告
│       ├── 📄 phase2_report.md                    # 阶段二主程交付报告 (DeepSeek-V4.1F 签发，15/15 PASS)
│       ├── 📄 phase2_gemini_audit.md              # 阶段二异构黑盒审计报告 (Gemini-3.8-Flash 签署放行)
│       ├── 📄 phase2_executive_adjudication_dossier.md # 阶段二门禁 2 终审案卷 (镜像)
│       ├── 📄 spike_cut1_report.md                # 阶段一首刀验证主汇总报告 (Lead 签发)
│       ├── 📄 audit_phase1.md                     # 阶段一独立审计报告 (auditor2 签署)
│       ├── 📄 audit_crosscheck_gemini.md          # 阶段一异模型黑盒交叉复核报告 (Gemini 3.8 Flash)
│       ├── 📄 dataset_label_audit.md              # 阶段一数据集标签质量审计报告 (QA 签发)
│       └── 📄 phase1_executive_adjudication_dossier.md # 阶段一门禁 1 终审案卷 (镜像)
│
├── 📂 docs/                          # 【运维】团队协作、技术交接与大模型原始指示
│   ├── 📜 CONTRACT_P2_STRESS.md                   # 阶段二高压压测数据集契约 (P2-STRESS v1.0.0 冻结)
│   ├── 📄 phase1_handoff.md                       # 阶段一 → 阶段二工程技术交接与避坑指南
│   ├── 📄 phase2_handoff.md                       # 阶段二 → 阶段三工程技术交接与接口规约
│   ├── 📂 team_operations/                        # Agent Team 角色编排与任务卡
│   │   ├── 📄 AGENT_TEAM_SETUP.md                 # Agent Team 阵型设定与通道规则
│   │   ├── 📄 PHASE1_PROMPT.md                    # 阶段一执行用 Prompt 任务卡包
│   │   ├── 📄 PHASE2_DIRECTIVE.md                 # 阶段二团队执行指令书 (镜像)
│   │   └── 📄 PHASE3_DIRECTIVE.md                 # 阶段三团队执行指令书 (镜像)
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

## 2. 核心目录分层与职责说明

### 2.1 `total_plan/` —— 顶层战略规划与大模型终审案卷
* **定位**：整个项目的顶层指导委员会，存放所有交付给前沿大模型进行顶层决策的**裁决案卷（Dossiers）**与**工程实施方案（Plans）**。
* **核心资产**：
  - [phase3_execution_directive.md](total_plan/phase3_execution_directive.md)：**【当前最高执行指令】阶段二终审裁决与阶段三执行指令书（GM-DIRECTIVE-P3-v2.2.0）**，包含 Gate 2 无条件放行令、Embedding 选型（本地优先+哈希回退）、有界校准融合公式、MCP 4大工具补丁及 WBS 任务包。
  - [phase2_executive_adjudication_dossier.md](total_plan/phase2_executive_adjudication_dossier.md)：阶段二综合执行审计与大模型裁决案卷，穿透 Gate 2 六项硬指标与 5 项 P0 落实证据。
  - [phase2_execution_directive.md](total_plan/phase2_execution_directive.md)：大模型签发的二阶段终审执行指令（GM-DIRECTIVE-P2-v2.1.2）。
  - [phase1_executive_adjudication_dossier.md](total_plan/phase1_executive_adjudication_dossier.md)：阶段一门禁 1 终审案卷。
  - [gated_mem_plan_two_maker_checker.md](total_plan/gated_mem_plan_two_maker_checker.md)：Plan Two 实施方案（Maker-Checker 红蓝对抗阵型）。
  - [gated_mem_decision_dossier.md](total_plan/gated_mem_decision_dossier.md)：阶段 0 决策案卷。

---

### 2.2 `src/gated_mem/` 与 `tests/` —— 生产代码与单元测试
* **定位**：Gated-Mem 核心产品代码与自动化单测资产（由 Tech Lead `DeepSeek-V4.1F` 独占开发维护）。
* **核心资产**：
  - `src/gated_mem/`：包含 `schema.py`、`gates.py`、`storage.py`、`events.py`、`conflicts.py`、`retrieval.py` 6 大核心模块（1751 行代码）。
  - `tests/`：7 个测试套件，79 项单测全部绿灯，覆盖率达 **93%**，包含 AST 语法级纯净度与连坐扫描。

---

### 2.3 `benchmarks/` —— 基准测试体系、数据与报告
* **定位**：实证验证与对抗评测大本营。
* **核心资产**：
  - [reports/phase2_report.md](benchmarks/reports/phase2_report.md)：主程提交的阶段二交付报告。
  - [reports/phase2_gemini_audit.md](benchmarks/reports/phase2_gemini_audit.md)：Gemini-3.8-Flash 异构黑盒审计报告与放行签署。
  - [gate2_check.py](benchmarks/gate2_check.py)：Gate 2 六项硬指标一键机检脚本。
  - [data/phase2_dense_stress_15.json](benchmarks/data/phase2_dense_stress_15.json)：15 组高密度多跳压测数据集（599 KB）。

---

### 2.4 `docs/` —— 团队运维、交接与大模型原始指示
* **定位**：工程落地期团队协同、技术交接与历史对话原始凭证。
* **核心资产**：
  - [phase2_handoff.md](docs/phase2_handoff.md)：阶段二至阶段三技术交接文档（接口签名、已知边界、MCP 与 CLI 规约）。
  - [CONTRACT_P2_STRESS.md](docs/CONTRACT_P2_STRESS.md)：阶段二压测数据集契约。
  - [phase1_handoff.md](docs/phase1_handoff.md)：阶段一至阶段二技术交接文档。

---

## 3. 常见工作流快速跳转 (Fast-Tracks)

### 🚀 路径 A：交付大模型进行阶段二终审裁决与阶段三放行
1. 打开 [total_plan/phase2_executive_adjudication_dossier.md](total_plan/phase2_executive_adjudication_dossier.md)；
2. 复制整篇内容发送给大模型（Argon / Arbiter），由大模型根据案卷第七节的【终审裁决选票】做出阶段三放行与算法技术选型决策。

### 🚀 路径 B：运行阶段二完整验证套件 (一键复现)
在工作区根目录下执行：
```bash
# 1. 运行 79 项单元测试
python -m pytest tests/ -q

# 2. 验证代码行覆盖率 (93%)
python -m coverage run --source=src/gated_mem -m pytest tests/ -q
python -m coverage report -m

# 3. 运行 Gate 2 六项硬指标一键机检 (15/15 PASS)
python benchmarks/gate2_check.py

# 4. 运行 15 组外部高压对抗压测集
python benchmarks/run_phase2_stress.py
```

### 🚀 路径 C：启动阶段三开发 (MCP Server 与 CLI)
1. 参阅 [docs/phase2_handoff.md](docs/phase2_handoff.md) 获取阶段三接口契约与开工清单；
2. 查阅 [benchmarks/reports/phase2_gemini_audit.md](benchmarks/reports/phase2_gemini_audit.md) 注意事项（防范 write_event 副作用、补齐 BM25 与向量相似度融合）。
