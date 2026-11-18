# Gated-Mem 工作区目录全景导航指南
# (Workspace Directory Guide & Architecture Map)

> **更新时间**：2026-11-18  
> **项目定位**：*Git for Agent Memory —— 面向超长开发周期的本地可审计、可回滚架构状态引擎*  
> **使用说明**：本文档为当前仓库根目录（`gated-mem/`）的统一入口导航指南，同步当前 `master` 分支真实文件布局，对所有模块、测试、基准资产、运维文档及异步实验脚手架提供索引。  
> **历史归档说明**：早期方案探索（`Preliminary_Exploration/`）与过程性计划草稿（`total_plan/`）已于发版清理阶段（commit `1f36668`）移出主目录并保存在 Git 历史中；各阶段终审裁决案卷已统一镜像归档于 `benchmarks/reports/`。

---

## 1. 工作区全景架构树 (Directory Tree)

```text
gated-mem/
│
├── 📜 README.md                      # 项目入口说明、核心基准与 30 秒上手指南
├── 📜 DIRECTORY_GUIDE.md             # [当前文件] 完整工作区目录指南与索引
├── 📜 pyproject.toml                 # 零核心依赖打包清单 (dependencies = []，extras: onnx/cli/all/dev)
├── 📜 LICENSE                        # MIT 开源协议
├── 📜 AGENTS.md                      # GitNexus 代码情报规则与 Agent 行为约束
├── 📜 CLAUDE.md                      # Claude Code 适配规范与会话约束
├── 📜 .gitignore                     # Git 忽略配置
│
├── 📂 .claude/                       # GitNexus 代码分析技能卡目录
│   └── 📂 skills/gitnexus-*          # exploring / impact-analysis / debugging / refactoring / guide / cli
│
├── 📂 .github/                       # 【CI/Pages 自动化】GitHub Actions 工作流
│   └── 📂 workflows/
│       ├── 📄 ci.yml                 # Python 3.10/3.11/3.12 全量单测、覆盖率、-S 零依赖与 Gate3 导出门禁
│       └── 📄 pages.yml              # 将 docs/ 自动部署至 GitHub Pages 交互式演示站
│
├── 📂 src/                           # 【核心源码】Gated-Mem 生产级 Python 模块库 (纯标准库)
│   └── 📂 gated_mem/                 # 核心内核实现包 (零第三方运行时依赖)
│       ├── 🐍 __init__.py            # 纯净包定义 (零副作用，导出 __version__)
│       ├── 🐍 schema.py              # 五状态枚举、四类型衰减参数、5×5 状态矩阵、双通道回执契约
│       ├── 🐍 gates.py               # 无状态纯数学门控函数、零连坐扣分设计、有界校准混合融合计算
│       ├── 🐍 storage.py             # WAL 模式 SQLite、BLOB 向量、FTS5 虚表、递归 CTE、原子 Undo
│       ├── 🐍 events.py              # 事件溯源批次链（causation_id）、投影重建（消费 EVENT_UNDONE）
│       ├── 🐍 conflicts.py           # 槽位两阶段裁决、别名归一化、[Replaced: X] 残差装配、覆盖零误杀
│       ├── 🐍 retrieval.py           # 混合检索饱和校准融合、多跳失效追溯、TOPK 强截断、双通道 XML 生成
│       ├── 🐍 embeddings.py          # 向量引擎抽象、384 维内置哈希兜底(BuiltinHashEmbedder)、本地 ONNX(FastEmbed)
│       ├── 🐍 server.py              # 标准 MCP JSON-RPC over stdio 服务端 (4 大标准工具，零杂音字节)
│       ├── 🐍 cli.py                 # 终端命令行工具集 (init/status/doctor/setup/remember/query/log/explain/conflicts/undo/export-html)
│       ├── 🐍 exporter.py            # 零 CDN 离线单文件 HTML 力导向图与时间轴时光机导出器 (XSS 绝对防御)
│       └── 📂 adapters/              # 多 Agent 适配器矩阵 (统一 BaseAgentAdapter 抽象 + 权限/Home 异常防御)
│           ├── 🐍 __init__.py        # 适配器自动注册与优先级调度
│           ├── 🐍 base.py            # 统一适配器抽象基类（含 _safe_path_exists / _safe_home）
│           ├── 🐍 dsh.py             # 【P0 第一公民】DeepSeek Harness 专属适配器 (cordis.patch.yml + SKILL.md)
│           ├── 🐍 claude_code.py     # Claude Code 适配器 (.mcp.json 深合并)
│           └── 🐍 cursor.py          # Cursor 适配器 (.cursor/mcp.json)
│
├── 📂 tests/                         # 【单元测试】自动化单测套件 (14 个测试文件，191 项用例全绿)
│   ├── 🐍 test_adapters.py           # DSH / Claude Code / Cursor 适配器、权限及 Path.home() RuntimeError 防御测试
│   ├── 🐍 test_audit_fixes.py        # 多阶段审计发现问题回归测试
│   ├── 🐍 test_cli_conflict_regression.py # CLI 冲突处理与交互作用域回归测试
│   ├── 🐍 test_cli_exporter.py       # CLI 全命令端到端与离线 HTML 导出器 XSS/零 CDN 一致性测试
│   ├── 🐍 test_conflicts.py          # 槽位冲突裁决、SUPERSEDES 关系标记、别名归一化测试
│   ├── 🐍 test_events.py             # 事件日志批次、causation 链追溯、投影重建测试
│   ├── 🐍 test_events_coverage.py    # 事件溯源边界与投影回放覆盖率补充测试
│   ├── 🐍 test_gates.py              # 幂律闭式解精度、生命力纯函数、有界校准融合测试
│   ├── 🐍 test_phase4.py             # 阶段四难负例、安装可逆性与结构守卫回归测试
│   ├── 🐍 test_purity.py             # AST 语法级扫描 (禁 print/sys.stdout、禁 TODO、零连坐、Python 3.9 兼容)
│   ├── 🐍 test_retrieval.py          # 混合检索、TOPK 淘汰观测、多跳失效告警、双通道隔离测试
│   ├── 🐍 test_server.py             # MCP JSON-RPC 协议解析、4 大工具调用与 stdio 管道零污染测试
│   ├── 🐍 test_storage_coverage.py   # SQLite 增删改查、FTS5 触发器同步、递归 CTE、原子 Undo 测试
│   └── 🐍 test_zero_dependency.py    # 核心包零第三方运行时依赖结构性守卫测试
│
├── 📂 benchmarks/                    # 【基准】阶段一至阶段五基准测试体系、独立复核工具与报告
│   ├── 📜 CONTRACT.md                             # 阶段一冻结契约 (12 节严格技术规范)
│   ├── 🐍 spike_cut1.py                           # 阶段一三分支核心运行器与自检器 (纯标准库)
│   ├── 🐍 build_phase2_stress.py                  # 阶段二高压数据集确定性生成脚本
│   ├── 🐍 pressure_phase2.py                      # 阶段二高压随机场景压力生成与运行器
│   ├── 🐍 run_phase2_stress.py                    # 阶段二高压检索与生死对照运行器
│   ├── 🐍 gate2_check.py                          # 阶段二 Gate 2 六项硬指标自动化验证器 (15 项检查)
│   ├── 🐍 build_phase3_hybrid_e2e.py              # 阶段三混合检索与端到端评测集生成脚本
│   ├── 🐍 eval_phase3_hybrid.py                   # 阶段三混合检索评测驱动 (支持 fastembed / builtin)
│   ├── 🐍 gate3_check.py                          # 阶段三 Gate 3 六项发布级硬指标一键机检器 (16 项检查)
│   ├── 🐍 build_phase4_hard_negatives.py          # 阶段四难负例对抗基准生成脚本
│   ├── 🐍 build_demo_graph.py                     # 离线图谱剧本生成脚本 (15 节点 / 9 条边，生成 docs/demo_memory_graph.html)
│   ├── 🐍 build_phase5_e3_collision.py            # 阶段五 E3 数据集生成器（注：含早先泄漏版本对比，冻结数据以防泄漏版为准）
│   ├── 🐍 eval_phase5_e3.py                       # 阶段五 E3 跨模块同符号碰撞四通道评测驱动（含数据集哈希绑定）
│   ├── 📂 audit/                                  # 独立评分器
│   │   └── 🐍 independent_scorer.py               # 独立黑盒打分器
│   ├── 📂 data/                                   # 评测与压测数据集
│   │   ├── 📄 eval_cases.schema.json              # 阶段一评测集 JSON Schema
│   │   ├── 📄 eval_cases_40.json                  # 阶段一 40 组全栈演进与 Anti-trap 陷阱测试集
│   │   ├── 📄 phase2_dense_stress_15.json         # 阶段二 15 组高密度多跳高压场景压测集
│   │   ├── 📄 phase3_hybrid_e2e_20.json           # 阶段三 20 组端到端混合检索与 XSS 评测集
│   │   ├── 📄 phase4_hard_negatives_20.json       # 阶段四 20 组同语境高碰撞难负例基准集
│   │   └── 📄 phase5_e3_collision_disambiguation.json # 阶段五 E3 20 题防泄漏跨模块同符号碰撞基准集
│   ├── 📂 tools/                                  # 数据构建校验与 E3 独立交叉复算脚本
│   │   ├── 🐍 build_dataset.py / validate_dataset.py
│   │   └── 🐍 build_phase5_e3.py / validate_phase5_e3.py / diag*_phase5_e3.py / verify*_phase5_e3.py
│   ├── 📂 results/                                # 机器可读评测输出与汇总
│   │   ├── 📄 RESULTS_SUMMARY.md / metrics.json / raw_runs.json / audit_scores.json
│   │   └── 📄 phase5_e3_metrics.json / phase5_e3_metrics_verify.json
│   └── 📂 reports/                                # 全阶段交付报告、异构审计与终审裁决案卷
│       ├── 📄 phase5_executive_adjudication_verdict.md # 阶段五战地对账终审裁决书 (GM-VERDICT-P5-FINAL-v1.0.1)
│       ├── 📄 phase5_release_final_audit.md       # 阶段五 v1.0.0 发布前独立复核报告
│       ├── 📄 phase5_e3_report.md                 # 阶段五 E3 跨模块同符号碰撞消歧实测报告 (+40.00pp)
│       ├── 📄 phase4_executive_adjudication_dossier.md # 阶段四发版终审与结项案卷 (GM-DOSSIER-P4-v4.0.0)
│       ├── 📄 phase4_release_audit.md             # 阶段四 Gemini 发版终审报告
│       ├── 📄 phase4_hard_negatives_report.md     # 阶段四难负例三通道实测报告
│       ├── 📄 phase3_executive_adjudication_dossier.md # 阶段三开源发布终审案卷
│       ├── 📄 phase3_gemini_final_audit.md        # 阶段三 Gemini 异构终审报告
│       ├── 📄 phase3_audit_recheck.md             # 阶段三缺陷闭环复核报告
│       ├── 📄 phase2_executive_adjudication_dossier.md # 阶段二门禁 2 终审案卷
│       ├── 📄 phase2_gemini_audit.md              # 阶段二异构黑盒审计报告
│       ├── 📄 phase2_report.md                    # 阶段二主程交付报告
│       ├── 📄 phase1_executive_adjudication_dossier.md # 阶段一门禁 1 终审案卷
│       └── 📄 audit_phase1.md / audit_crosscheck_gemini.md / dataset_label_audit.md / spike_cut1_report.md
│
├── 📂 docs/                          # 【运维】环境规范、演示资产、阶段交接与 v1.1 外部评测规划
│   ├── 📄 phase5_handoff.md                       # 【最新交接】阶段五暨当前工程进展与 AI 接手总交接文档
│   ├── 📄 ENVIRONMENT.md                          # 专用虚拟环境规范 (py3.11)、本机路径说明与 Base 环境避坑指南
│   ├── 📄 PHASE5_V11_EXTERNAL_EVAL_PLAN.md        # v1.1 外部学术基准评测计划 (GM-PLAN-P5-V11-v1.0，上限 ¥50)
│   ├── 🌐 index.html                              # GitHub Pages 演示门户页 (内嵌图谱工作台 + 一键复制安装命令)
│   ├── 🌐 demo_memory_graph.html                  # 离线单文件 HTML5 记忆图谱工作台 (Zero-CDN，15 节点 / 9 条边，含时光机回放与搜索过滤)
│   ├── 🎞️ demo.gif                                # README 双幕动图 (CLI 演进流 + 真实图谱工作台时光机回放)
│   ├── 🖼️ demo_screenshot.png                     # 新版图谱工作台高分交互截图
│   ├── 🖼️ social_preview.png                      # 1280×640 GitHub Social Preview 分享预览卡片
│   ├── 🐍 generate_demo_gif.py                    # demo.gif / demo_screenshot.png / social_preview.png 一键生成脚本
│   ├── 📄 CONTRACT_P2_STRESS.md                   # 阶段二压测数据集契约
│   ├── 📄 CONTRACT_P3_E2E.md                      # 阶段三端到端混合检索评测集契约
│   ├── 📄 phase1_handoff.md / phase2_handoff.md / phase3_handoff.md / phase4_release_report.md
│   ├── 📂 team_operations/                        # Agent Team 角色编排与各阶段执行指令书
│   │   └── 📄 AGENT_TEAM_SETUP.md / PHASE1_PROMPT.md / PHASE2_DIRECTIVE.md / PHASE3_DIRECTIVE.md / PHASE4_DIRECTIVE.md
│   └── 📂 llm_advisories/                         # 早期大模型原始终审指导文本归档
│       └── 📄 01_llm_adjudication_verdict.txt / 02_llm_advice_maker_checker.txt
│
└── 📂 experiments_v2/                # 【外部评测骨架】只读调用 src/gated_mem/ 的外部基准实验区 (主实验在 v1.1-external-eval 分支推进)
    ├── 📄 README.md / HANDOFF.md / PROVENANCE.md  # 实验设计、交接记录与数据溯源 (sha256)
    ├── 🐍 run_env.py / selfcheck_e0.py            # E0 环境探测与适配层自检
    ├── 📂 adapters/gated_store.py                 # 驱动 src/gated_mem/ 的只读适配层
    ├── 📂 arms/{definitions.py, lenient_match.py} # 7 实验臂定义与宽松匹配器
    ├── 📂 data/e3_naturalized.json                # 80 条自然语言改写检索集
    ├── 📂 data_gen/build_naturalized.py           # 自然语言改写集生成器
    ├── 📂 dl/fetch_mab.py                         # MemoryAgentBench 数据获取脚本
    ├── 📂 runners/e3_naturalized.py               # E3 自然语言改写检索评测脚本
    └── 📂 results/                                # e0_env.json / e3_naturalized_builtin.{json,md}
```

---

## 2. 核心目录分层与职责说明

### 2.1 `src/gated_mem/` 与 `tests/` —— 生产代码与单元测试
* **定位**：Gated-Mem 核心引擎与自动化单测资产，核心运行时 **100% 仅依赖 Python 标准库**（`pyproject.toml` 中 `dependencies = []`）。
* **核心资产**：
  - `src/gated_mem/`：包含核心状态机/存储/门控/事件/冲突/检索/向量引擎、MCP stdio 服务端（`server.py`）、命令行工具（`cli.py`）、零 CDN HTML 导出器（`exporter.py`）与多 Agent 适配层（`adapters/`）。
  - `tests/`：14 个测试套件，当前共 **191 项单元测试**，包含 AST 语法级纯净度、零依赖 `-S` 导入守卫、离线导出器工作台/XSS 防御、安装可逆性与适配器权限/Home 异常防御测试。

### 2.2 `benchmarks/` —— 基准测试体系、数据与裁决报告
* **定位**：全阶段实证验证、对抗评测与终审归档目录。
* **核心资产**：
  - [reports/phase5_executive_adjudication_verdict.md](benchmarks/reports/phase5_executive_adjudication_verdict.md)：**阶段五终审裁决书（`GM-VERDICT-P5-FINAL-v1.0.1`）**，核准 `v1.0.0` 上线并确立 `v1.1-external-eval` 异步评测双轨制。
  - [reports/phase5_release_final_audit.md](benchmarks/reports/phase5_release_final_audit.md)：v1.0.0 发布前独立黑盒复核报告。
  - [reports/phase5_e3_report.md](benchmarks/reports/phase5_e3_report.md)：阶段五 E3 跨模块同符号碰撞消歧实测报告（Fusion 90% vs 最强单通道 50%，净增益 +40.00pp）。
  - [eval_phase5_e3.py](benchmarks/eval_phase5_e3.py) / [gate2_check.py](benchmarks/gate2_check.py) / [gate3_check.py](benchmarks/gate3_check.py)：自动化评测与发布门禁机检脚本。

### 2.3 `docs/` 与 `experiments_v2/` —— 运维规范、演示与外部基准演进
* **定位**：环境配置、交互式离线演示及面向 `v1.1-external-eval` 分支的外部基准（MemoryAgentBench CR / Memora）筹备区。
* **核心资产**：
  - [docs/phase5_handoff.md](docs/phase5_handoff.md)：**【最新】阶段五暨当前工程进展与 AI 接手总交接文档**（含双轨分支基线、本机环境路径、前端重构记录与待办清单）。
  - [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)：隔离虚拟环境配置指南、本机路径与多版本 numpy 冲突避坑记录。
  - [docs/PHASE5_V11_EXTERNAL_EVAL_PLAN.md](docs/PHASE5_V11_EXTERNAL_EVAL_PLAN.md)：v1.1 外部学术基准执行规划（`GM-PLAN-P5-V11-v1.0`）。
  - [experiments_v2/HANDOFF.md](experiments_v2/HANDOFF.md)：`experiments_v2` 交接说明与已跑通的 E0/E3（builtin 模式）实测记录。

---

## 3. 常见工作流快速跳转 (Fast-Tracks)

### 🚀 路径 A：运行全量验证套件
在仓库根目录下执行：
```bash
# 1. 运行 191 项单元测试
python -m pytest tests/ -q

# 2. 验证核心包零第三方依赖 (-S 隔离 site-packages)
python -S -c "import sys; sys.path.insert(0, 'src'); import gated_mem, gated_mem.cli, gated_mem.server, gated_mem.adapters"

# 3. 运行 Gate 2 / Gate 3 硬指标机检（需安装 coverage；Gate 3 满血检索需 [onnx]）
python benchmarks/gate2_check.py
python benchmarks/gate3_check.py

# 4. 复现阶段五 E3 跨模块碰撞消歧（零依赖字面模式 / fastembed 语义模式）
python benchmarks/eval_phase5_e3.py --provider builtin
python benchmarks/eval_phase5_e3.py
```

### 🚀 路径 B：双轨制分支开发规范
- **`master` 分支**：承接核心内核稳定性加固、文档同步与版本维护提交。
- **`v1.1-external-eval` 分支**：严格基于 `v1.0.0` Tag 异步推进 E1（MemoryAgentBench CR）与 E2（Memora）外部学术基准实验，保持与已发布 Wheel 逐字节对齐。
