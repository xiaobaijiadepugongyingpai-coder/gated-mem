# 阶段五暨最新工程进展与 AI 接手总交接文档

> **更新时间**：2026-11-18  
> **当前基线**：`master` @ `f6e5a7`（含后续文档与脱敏同步） / `v1.1-external-eval` @ `14153fe`  
> **终审裁决**：`GM-VERDICT-P5-FINAL-v1.0.1`（见 [phase5_executive_adjudication_verdict.md](../benchmarks/reports/phase5_executive_adjudication_verdict.md)）  
> **测试状态**：**191 / 191 PASS**（核心运行时 100% 仅依赖 Python 标准库）

---

## 1. 当前仓库基线快照

### 1.1 双轨制分支拓扑（严禁混用）

| 分支 | 当前基线 | 职责定位 | 约束 |
| :--- | :--- | :--- | :--- |
| **`master`** | `f6e5a7`（含后续文档与脱敏同步） | 主干代码、适配器加固、离线 HTML 图谱工作台、文档与阶段报告归档 | 核心包 `src/gated_mem/` 保持 `dependencies = []` 与 AST 纯净度 |
| **`v1.1-external-eval`** | `14153fe`（跟踪 `origin/v1.1-external-eval`） | 外部学术基准异步评测（E1 MemoryAgentBench CR + E2 Memora） | 只读调用 `src/gated_mem/`，实验脚本放 `experiments_v2/`，预算硬上限 ¥50 |

### 1.2 多模型协同与代码情报铁律

1. **决策与执行分离**：
   - **Argon** 仅负责把握大方向、架构设计、门禁裁决与阶段复核；
   - 所有具体代码编写、测试运行、脚本执行与 Git 操作一律交由 **Hydrogen** 或 **3.8 Flash** 执行。
2. **GitNexus 强制守卫**（见 [AGENTS.md](../AGENTS.md)）：
   - 编辑任何函数/方法前，**必须**运行 `node .gitnexus/run.cjs impact "<symbolName>" --direction upstream --repo .`（若返回 `risk: UNKNOWN`，用 `git grep` 核实调用方）。
   - 执行 `git commit` 前，**必须**运行 `node .gitnexus/run.cjs analyze --index-only` 与 `node .gitnexus/run.cjs detect-changes --scope all --repo .`。

---

## 2. 本机环境与运行约定（避坑必读）

> 仓库已完成跨机器迁移，**请勿直接硬编码旧机器的本地 Conda 路径**；统一使用相对路径或环境占位符执行命令。

| 工具/路径 | 当前运行约定与现状 | 注意事项 |
| :--- | :--- | :--- |
| **工作区根目录** | `<repo-root>`（项目根目录） | 本机主分支名为 `master`（非 `main`） |
| **Python 解释器** | `<python-exe>`（推荐使用独立虚拟环境或系统 Python ≥ 3.9） | 零依赖核心包与 191 项单测仅需 `pytest`；**严禁向基础 base 环境直接 `pip install fastembed`**（会强制升级 `numpy>=2` 破坏现有科学计算包） |
| **Node.js / GitNexus** | `<nodejs-bin-dir>` | 若 `node` 不在默认 PowerShell `PATH` 中，运行 `.gitnexus/run.cjs` 前需先将 Node.js 安装目录与 `$env:APPDATA\npm` 追加到 `PATH` |

**快速环境变量配置（PowerShell）**：
```powershell
$env:Path = "<nodejs-bin-dir>;$env:APPDATA\npm;" + $env:Path
```

**常用实测命令**：
```powershell
# 1. 运行全量 191 项单元测试
python -m pytest tests/ -q

# 2. 验证核心包零第三方依赖 (-S 隔离 site-packages)
python -S -c "import sys; sys.path.insert(0, 'src'); import gated_mem, gated_mem.cli, gated_mem.server, gated_mem.adapters"

# 3. 跑 Gate 3 离线导出器专项安全门禁 (4/4 PASS)
python -c "import benchmarks.gate3_check as g3; g3.g3_exporter()"
```

> 说明：若当前环境未安装 `coverage` 与 `fastembed`，运行完整 [gate2_check.py](../benchmarks/gate2_check.py)（14/15 PASS）和 [gate3_check.py](../benchmarks/gate3_check.py)（14/16 PASS）时，所有功能项均通过，仅覆盖率指标（`0% < 90%`）和 `G3-Hybrid`（回退 `builtin` 达 `65.0%`）受缺失可选包影响未满绿；如需跑满这两项，请新建独立虚拟环境安装 `coverage` 与 `gated-mem[onnx]`。

---

## 3. 阶段五至当前核心演进台账（已完成项）

### 3.1 E3 跨模块同符号碰撞与语义改写消歧（`benchmarks/eval_phase5_e3.py`）
- **核心问题修复**：阶段四难负例中纯 FTS5 也达 100%，导致融合相对最强单通道净增益为 `+0.00pp`。阶段五构造了 20 题防泄漏跨模块同符号碰撞集（[phase5_e3_collision_disambiguation.json](../benchmarks/data/phase5_e3_collision_disambiguation.json)，`attrib` 已设为只读防并发覆写）。
- **实测结果**（`FastEmbedProvider` `bge-small-zh-v1.5`，详见 [phase5_e3_report.md](../benchmarks/reports/phase5_e3_report.md)）：
  - `A1_vec`：**50.00%**（10/20，认出模块 90% / 分辨版本 55%）
  - `A2_fts`：**50.00%**（10/20，锁定版本 100% / 分辨模块 50%，**10/10 命中纯靠 `memory_id` 字典序平局**）
  - `A3_slot`：**20.00%**（4/20，因 query 使用旁称致 `slot_hit=0`，**已主动披露退化为恒答 `M01` 常量基线**）
  - `A4_fusion`：**90.00%**（18/20，**净增益 +40.00pp**，平局侥幸 0 次，成功救回 4/5 三单通道全错题）
- **可复现性加固**（`471c299`）：[eval_phase5_e3.py](../benchmarks/eval_phase5_e3.py) 新增 `_dataset_digests()`，并将归一化换行后的 `dataset_md5`（`6e6a966b349f26cf31409c3ff2635118`）与 `dataset_sha256`（`fc728a78064cebc7714f6214effdf862cf86bf8257936563c947ea04d1b4f508`）写入 [phase5_e3_metrics.json](../benchmarks/results/phase5_e3_metrics.json) 与 [phase5_e3_metrics_verify.json](../benchmarks/results/phase5_e3_metrics_verify.json)。

### 3.2 多 Agent 适配层全家族权限与无 HOME 防御闭环（`471c299`）
- 闭环 [phase5_release_final_audit.md](../benchmarks/reports/phase5_release_final_audit.md) 遗留的受限沙箱/无 `HOME` 环境变量边界：
  - [base.py](../src/gated_mem/adapters/base.py)：新增 `_safe_path_exists()` 与 `_safe_home()`，并在 `detect_available()` 中捕获 `(PermissionError, OSError, RuntimeError)` 防止单个异常适配器中断探测。
  - [dsh.py](../src/gated_mem/adapters/dsh.py)：`DshAdapter.detect_installed()` 与 `active_profile()` 捕获扩展至 `(PermissionError, OSError, RuntimeError)`；`active_profile()` 回退 `"desktop"` 时向 `stderr` 输出显式告警并防止在 `except` 块内二次调用 `self.dsh_home()` 抛错。
  - [claude_code.py](../src/gated_mem/adapters/claude_code.py) & [cursor.py](../src/gated_mem/adapters/cursor.py)：`detect_installed()` 均包裹 `(PermissionError, OSError, RuntimeError)` 降级为 `False`。
  - [test_adapters.py](../tests/test_adapters.py)：补充 4 项回归测试验证上述边界。

### 3.3 离线单文件 HTML 图谱工作台重构（`f6e5a7`）
- **演示剧本增强**（[build_demo_graph.py](../benchmarks/build_demo_graph.py)）：在原有 6 条 `BELONGS_TO` 边基础上补齐 `M5 -> M1`（step 140）、`M10 -> M9`（step 210）、`M12 -> M11`（step 260）三条 `EdgeType.SUPERSEDES` 演进边，重新导出 [demo_memory_graph.html](../docs/demo_memory_graph.html)（15 节点 / 9 条边 / `max_step = 340` / 45.3 KB）。
- **前端界面与交互重构**（[exporter.py](../src/gated_mem/exporter.py) `HTML_TEMPLATE`）：
  - **视觉与 KPI**：深空暗色工作台主题（`#07090e` 画布 + `#0d1117` 检查器侧边栏 + 窄屏响应式），顶部展示 4 格随时间步动态刷新的 KPI 卡片（`可见节点`、`Active 有效`、`Superseded`、`Stale 告警`）。
  - **画布物理与交互**：黄金角螺旋居中初始分布（修复原 `+300` 偏心漂移）、跟随缩放的点阵网格、**单节点独立拖拽**、空白处平移、以鼠标为中心的滚轮缩放、悬停/选中 1-hop 因果高亮、区分 `BELONGS_TO` 实线箭头与 `SUPERSEDES` 虚线箭头（聚焦时显示边类型标签），以及右上角浮动 HUD 控制条（缩放/居中/物理开关）与快捷键（`Space` 播放、`R` 居中、`Esc` 取消选中）。
  - **时间感知时光机**：保留 `#slider` 与 `#stepLabel`，新增 `⏮`/`◀`/`▶ 回放`/`▶|`/`⏭` 步进按钮与里程碑快捷芯片（`#stepChips`）；支持按历史时间截面动态重算 `effectiveStatus` 与 `effectiveStaleAncestors`（回退到 `s140` 之前可看到 `M1` 恢复 `active`、后代 `stale` 告警消失）。
  - **检查器与记忆台账**：新增 `#searchInput` 搜索框与 `#filterBar` 6 档状态筛选胶囊、`#detail` 结构化卡片（含可点击跳转的祖先与上下游/覆盖关系胶囊）及可点击联动的 `#nodeList` 记忆台账。
  - **安全红线保持**：零外部 CDN（无 `http://`/`https://`）、零 `innerHTML` 子串、保留全部核心 DOM ID 契约，`</script>` 转义与 `g3_exporter()` 4/4 全过，已补充 `test_render_html_contains_studio_controls_and_escapes_xss`。

---

## 4. 近期 Git 提交记录（`master`）

```text
f6e5a7 feat(exporter): redesign interactive HTML graph studio with time-aware playback, search/filter, and node dragging
43a33df docs(repo): archive phase-5 adjudication verdict and sync DIRECTORY_GUIDE.md with v1.0 layout
471c299 fix(adapters,e3): guard Path.home() RuntimeError across adapters and bind dataset digests in E3 metrics
005aa22 chore(gitnexus): sync repo index metadata to gated-mem and master
026afb9 docs(release): sync pyproject.toml URLs with repo and bump test count badge to 186
```

---

## 5. 下一棒 AI 接手待办清单（按优先级）

1. **方向 A · 开源门面最后收口（`master` 分支）**：
   - [ ] 新增 `.github/workflows/ci.yml`（自动运行 `pytest tests/ -q`、`python -S` 零依赖导入检查与 `g3_exporter()`）。
   - [ ] 更新新版前端工作台的 [demo_screenshot.png](../docs/demo_screenshot.png) 与 [demo.gif](../docs/demo.gif)（当前这两份图片媒体仍为旧版 UI 画面）。
   - [ ] 将本地 `master` 提交推送至远端：`git push origin master`。
2. **方向 B · 零成本真实语义检索实验（`experiments_v2` E3）**：
   - [ ] 在独立虚拟环境中安装 `fastembed` 后，运行 [e3_naturalized.py](../experiments_v2/runners/e3_naturalized.py)（`--provider fastembed`），完成 [experiments_v2/HANDOFF.md](../experiments_v2/HANDOFF.md) §4.1 第一优先级验证。
3. **方向 C · v1.1 外部学术基准评测（切换至 `v1.1-external-eval` 分支）**：
   - [ ] 严格遵循 [PHASE5_V11_EXTERNAL_EVAL_PLAN.md](PHASE5_V11_EXTERNAL_EVAL_PLAN.md) 与 [phase5_executive_adjudication_verdict.md](../benchmarks/reports/phase5_executive_adjudication_verdict.md) §四 的四项工程护栏：
     1. 跑 `run_env.py` 探活路由并核实当日模型单价（闭合 T4/T6）；
     2. 离线直读 HuggingFace Parquet 构建 `mab_cr.jsonl`（800 题，绕开 `datasets` 安装挂起，闭合 T1/T2/T3）；
     3. Schema-Guided 两阶段闭集抽取 `mab_cr_slots.jsonl`，执行 `SUPERSEDES == 0` 或 `__OOV__ > 15%` 熔断检查；
     4. 控制 E1/E2 总 API 支出严格在 **¥50 硬上限** 内（分配 ¥48）。
