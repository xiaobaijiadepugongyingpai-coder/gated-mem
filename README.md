# Gated-Mem: Git for Agent Memory

> **面向超长开发周期的本地、可解释、可回滚 Agent 架构状态记忆引擎**  
> *A local, explainable, undoable state memory engine for long-horizon coding agents (Claude Code / Cursor).*

---

## 📌 当前项目状态 (Project Status)

- **当前里程碑**：**阶段二圆满闭环，阶段三终审指令书（`GM-DIRECTIVE-P3-v2.2.0`）已正式签发**。
- **Gate 2 终审裁决**：**【无条件正式放行】（Unconditional PASS）**。1751 行核心代码底盘基线冻结，进入阶段三（真实向量、有界校准混合检索融合、MCP Server、CLI 与 HTML 导出器交付）。
- **执行架构**：继续锁定 Maker-Checker 红蓝对抗制（`DeepSeek-V4.1F` 独揽 100% 生产代码 + `GLM-5.3-Flash` 脚本化造数评测 + `Gemini-3.8-Flash` 异构黑盒审计）。

---

## 🗺️ 工作区全景导航 (Quick Links)

本工作区已完成系统化分级归档，详细目录索引与各资产说明请参阅：  
👉 **[DIRECTORY_GUIDE.md —— 完整工作区目录全景导航指南](DIRECTORY_GUIDE.md)**

### 核心快速访问通道

| 模块 / 目标 | 推荐入口文档 | 说明 |
| :--- | :--- | :--- |
| **📜 阶段三终审执行指令书** | [total_plan/phase3_execution_directive.md](total_plan/phase3_execution_directive.md) | **【最新签发】GM-DIRECTIVE-P3-v2.2.0**：Gate 2正式放行令、Embedding选型、混合检索融合公式、MCP补丁与WBS。 |
| **⚖️ 阶段二大模型终审裁决案卷** | [total_plan/phase2_executive_adjudication_dossier.md](total_plan/phase2_executive_adjudication_dossier.md) | 阶段二 Gate 2 综合执行审计与大模型裁决案卷（15/15 PASS 穿透依据）。 |
| **📑 阶段二交付报告 (Tech Lead)** | [benchmarks/reports/phase2_report.md](benchmarks/reports/phase2_report.md) | DeepSeek-V4.1F 签发：5 项 P0 落实对照、六项硬指标实测（15/15 PASS）与 93% 覆盖率。 |
| **🛡️ 异构黑盒审计与放行签署** | [benchmarks/reports/phase2_gemini_audit.md](benchmarks/reports/phase2_gemini_audit.md) | Gemini-3.8-Flash 签署【放行 Gate 2】：离线复算对照、落盘穿透、破坏性攻防与 AST 扫描。 |
| **🤝 阶段二 → 阶段三交接文档** | [docs/phase2_handoff.md](docs/phase2_handoff.md) | 核心底盘接口契约、已知边界说明、MCP Server 与 CLI 封装规范及开工清单。 |
| **📜 阶段二团队执行指令书** | [total_plan/phase2_execution_directive.md](total_plan/phase2_execution_directive.md) | 大模型下发的 GM-DIRECTIVE-P2-v2.1.2：五项 P0 调整与 Maker-Checker 执行准则。 |
| **🚀 顶层执行方案 (Plan Two)** | [total_plan/gated_mem_plan_two_maker_checker.md](total_plan/gated_mem_plan_two_maker_checker.md) | Maker-Checker 红蓝对抗架构设计与执行机制。 |
| **⚖️ 阶段一终审案卷** | [total_plan/phase1_executive_adjudication_dossier.md](total_plan/phase1_executive_adjudication_dossier.md) | 阶段一首刀消融 360 条 Run 详细分析与阶段二准入交接。 |

---

## 📂 顶层目录结构一览

```text
<repo-root>/
├── src/gated_mem/             # 【核心源码】6 大生产模块 (schema/gates/storage/events/conflicts/retrieval)
├── tests/                     # 【单元测试】7 套完整单测 (79 个用例，93% 覆盖率，零连坐纯净度 AST 扫描)
├── total_plan/                # 顶层战略规划、执行方案 (Plan One/Two) 与大模型裁决案卷 (Phase 1 & 2)
├── benchmarks/                # 基准测试体系 (契约、高压数据集、压测运行器、Gate 2 一键机检与审计报告)
├── docs/                      # 团队运维、交接文档 (phase1/2_handoff) 与大模型历史指示归档
├── Preliminary_Exploration/   # 早期探索方案 (gated_mem v2.0、memory_plugin、文献复核)
├── DIRECTORY_GUIDE.md         # 详细目录指南与全量文件索引
├── AGENTS.md                  # GitNexus 代码情报规则与行为约束
├── CLAUDE.md                  # Claude Code 开发约定
└── README.md                  # [当前文件] 项目总览
```

---

## 🛠️ 快速复现与验证命令 (Quickstart)

```bash
# 1. 运行阶段二 79 项单元测试
python -m pytest tests/ -q

# 2. 验证代码覆盖率（需 >= 90%）
python -m coverage run --source=src/gated_mem -m pytest tests/ -q
python -m coverage report -m

# 3. 运行 Gate 2 六项硬指标一键自动化验证（15/15 PASS）
python benchmarks/gate2_check.py

# 4. 运行 15 组高压对抗压测集
python benchmarks/run_phase2_stress.py
```
