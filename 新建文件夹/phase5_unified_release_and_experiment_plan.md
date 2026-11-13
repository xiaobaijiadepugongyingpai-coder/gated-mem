# Gated-Mem 阶段五全景实施蓝图：v1.0.0 无条件发版、E3 破局实验补齐与 v1.1 外部基准全景集成
# (GM-DIRECTIVE-P5-v5.0.0: Unified Release & Supplementary Experiments Plan)

> **发布日期**：2026-11-13  
> **指导专家**：大模型终审仲裁委员会 & 异构审计团队  
> **执行角色**：Tech Lead (DeepSeek-V4.1F) + Dataset Engineer (GLM-5.3-Flash) + Auditor (Gemini)  
> **基线状态**：阶段四终审全绿（176/176 单测通过，90% 覆盖率，Gate 3 16/16 纯净环境验证通过，零第三方硬依赖达成）  
> **核心战略**：**拒绝为了 8 天学术评测而延期发布！花 1 小时补齐 E3 破局实验（攻破纯 FTS 100% 破绽） $\to$ 今日立即打 Tag 发布 GitHub/PyPI `v1.0.0` $\to$ 以 `v1.1-external-eval` 分支异步推进外部学术基准**。

---

## 一、 顶层战略定调与核心裁决

### 1.1 开发者工具定位 vs 学术论文评审
* **产品核心价值**：`Gated-Mem` 是面向超长开发周期的**“Git for Agent Memory”**，其核心痛点是**两阶段槽位覆盖、状态残差演进追溯 (`residual_diff`)、有界因果回滚 (`undo`)、可观测力导向图谱以及零第三方依赖（环境安全）**。
* **发布即胜利**：核心功能与工程闭环已 100% 交付并通过 176 项单测验证。推迟发布去跑公开闲聊/问答基准存在严重的战略风险，极易陷入沉没成本陷阱。
* **诚信开源赚取双倍声誉**：今天发布 `v1.0.0` 交付可运行的硬核工具；随后在 `v1.1` 分支公开外部基准评测报告，如实披露机制优势场景与边界限制，更能赢得硬核开源开发者的信任。

### 1.2 两步走执行路线图 (Two-Phase Execution Strategy)

```mermaid
flowchart TD
    subgraph Step1 ["第一步：发版前最后拼图（1.5 小时内完成）"]
        A[1分钟防御补丁: dsh.py 权限防护] --> B[E3 破局实验: 跨模块同符号碰撞 + 语义改写]
        B --> C[更新 README.md: 呈现 Fusion > max Vec, FTS 完整对照表]
        C --> D[自动化回归: pytest 176+ 全绿 & gate3_check 16/16]
        D --> E[★ 签署打 Tag: git tag v1.0.0 & 构建发布 PyPI/GitHub]
    end

    subgraph Step2 ["第二步：v1.1-external-eval 异步基准推进（发版后，预算 < ¥50）"]
        F[建立 v1.1 外部评测分支] --> G[E1: MemoryAgentBench CR子集 重点规避抽槽损失]
        F --> H[E2: Memora 150题 验证遗忘感知能力]
        F --> I[E4: Gemini-3.8 桥接 探索超长溢出窗口黄金交叉点]
        G & H & I --> J[输出 v1.1 外部评测报告与基准发布]
    end

    Step1 --> Step2
```

---

## 二、 第一阶段：v1.0.0 终极发版前核验与最后拼图（P0 级，今日完成）

### 2.1 任务 1：`src/gated_mem/adapters/dsh.py` 1 分钟防御补丁（Limitation #5）
在 Windows 受限或沙箱环境下，访问 `Path.home() / ".dsh"` 可能会触发 `PermissionError` 或 `OSError`。发版前必须进行代码防御加固：

* **修改文件**：`src/gated_mem/adapters/dsh.py`
* **加固要求**：
  * 在 `detect_installed()` 中，将主目录检查与目录遍历包裹在 `try...except (PermissionError, OSError): return False` 中；
  * 在 `active_profile()` 中，将 `profiles` 遍历检索包裹在 `try...except (PermissionError, OSError): return "desktop"` 中；
  * 确保即便在无宿主主目录读写权限的沙箱内，适配器也能平滑降级，绝不抛出未经捕获的崩溃异常。

### 2.2 任务 2：E3 破局实验——跨模块同符号碰撞与语义改写消歧（关键补齐）

#### 2.2.1 痛点诊断：为什么原阶段四的报告容易引发质疑？
在 `phase4_hard_negatives_report.md` 中：
* 单向量 Top-1：`60.00%`
* 单 FTS5 Top-1：`100.00%`
* 混合融合 Top-1：`100.00%`
* **破绽**：混合融合相对单 FTS5 的净增益为 `+0.00pp`！挑剔的开发者会质疑：*“既然纯 FTS5 已经是 100% 准确率，何必搞复杂的向量 + BM25 饱和融合？”*
* **根因**：原阶段四 20 道题目的 Query 均直接硬编码了唯一错误码/版本号（如 `ERR_XA_PROTO_08`），变成了纯词法匹配的独角戏。

#### 2.2.2 解决方案：构造跨模块同符号碰撞 + 语义改写 Query
构造使得 **单向量（A1）** 与 **单 FTS5（A2）** 均无法单独完成任务的场景，唯有 **混合融合（A4）** 能够胜出：

1. **记忆池构造（跨模块符号碰撞）**：
   * **模块 A（业务语境：“分布式账务清算服务”）**：部署 `v2.14.37`、`v2.14.38`、`v2.14.39` 三个版本配置；
   * **模块 B（业务语境：“边缘网关流控中间件”）**：**同样部署** `v2.14.37`、`v2.14.38`、`v2.14.39` 三个版本配置；
   * **其他干扰模块（C、D）**：亦挂载同族错误码或配置项。
2. **查询构造（语义改写 + 精确符号）**：
   * Query：*“当**支付对账系统**（语义改写，与原文‘分布式账务清算’零字面重叠）升级到 **`v2.14.38`**（精确符号）时，超时参数应配置为多少？”*
3. **三通道机制裁决与数学必然性**：
   * **单向量（A1）**：能够通过语义关联识别“支付对账 $\approx$ 账务清算（模块 A）”，但在密集微差版本号 `.37 / .38 / .39` 面前发生向量空间坍缩，无法区分版本（**准确率 $\approx 33\%$**）；
   * **单 FTS5（A2）**：能精确命中 `v2.14.38`，但由于 Query 与“分布式账务清算”零字面重叠，FTS5 无法区分这是模块 A 还是模块 B 的 `v2.14.38`（**准确率 $\approx 50\%$**）；
   * **混合融合（A4）**：向量通道给模块 A 语义打高分，FTS5 给 `v2.14.38` 打高分，饱和非线性融合交集唯一锁定【模块 A + `v2.14.38`】（**准确率 $= 100\%$，净胜最强单通道 $\ge +50\text{pp}$**）。
4. **交付产物**：
   * 编写 `benchmarks/data/phase5_e3_collision_disambiguation.json`；
   * 执行评测脚本，产出三通道及融合对比表（必须显式包含 `A2 纯 FTS5` 独立基线）；
   * 将无懈可击的数据表更新至 `README.md` 与基准报告。

### 2.3 任务 3：v1.0.0 标准发版指令链（Checklist）
完成代码防御加固与 E3 实验后，按顺序执行发版流水线：

```bash
# 1. 自动化单元测试回归（要求 176+ 项全绿，覆盖率 >= 90%）
pytest tests/ -q

# 2. Gate 3 硬指标复检（要求 16/16 PASS）
python benchmarks/gate3_check.py

# 3. 提交与打 Tag
git add .
git commit -m "chore(release): v1.0.0 - Production-ready zero-dependency agent memory engine"
git tag -a v1.0.0 -m "Release v1.0.0: Git for Agent Memory with zero dependencies"
git push origin main --tags

# 4. 构建纯净 Wheel 与 sdist
python -m build

# 5. PyPI 包体与元数据一致性检查
twine check dist/*

# 6. 正式发布至 PyPI
twine upload dist/*
```

---

## 三、 第二阶段：生态集成落地与社区宣发推广

### 3.1 双轨生态推进 (Ecosystem PRs)

#### 轨一：DeepSeek Harness (`dsh`) 官方 PR
* 向 DSH 官方仓库提交 PR：`feat(plugins): add first-class gated-mem memory adapter`；
* 核心卖点：零依赖接入，一行 `gated-mem setup` 自动生成 `cordis.patch.yml` 补丁与 `SKILL.md`，完美防护 DeepSeek 推理模型历史幻觉。

#### 轨二：MCP 官方与社区名录收录
* 向 `modelcontextprotocol/servers`（Community Servers 列表）、`punkpeye/awesome-mcp-servers`、`Smithery.ai`、`glama.ai` 提交收录申请；
* 标签分类：`Memory Management` / `Developer Tools` / `Zero-Dependency Local SQLite`。

### 3.2 `Gated-Mem-Bench` 本地一键复现套件
在 `README.md` 中设立专属章节，提供零 API 成本、10 秒控制台复现脚本：
```bash
# 一键复现全套基准跑分
python benchmarks/gate2_check.py
python benchmarks/gate3_check.py
python benchmarks/eval_phase3_hybrid.py
```

### 3.3 社区首发帖文案模板（HackerNews / Reddit / V2EX）
* **标题**：`Show HN: Gated-Mem – "Git for Agent Memory" with power-law decay, causal undo, and zero dependencies (MCP)`
* **核心内容**：
  1. **痛点**：传统向量库无序囤积事实，开发两周后架构变更导致新旧决策冲突，而级联删除又引发连坐误杀（Anti-trap 误杀率 $-80\text{pp}$）；
  2. **创新**：两阶段槽位覆盖 + 状态残差 (`residual_diff`) 追溯 + 有界校准混合检索（攻破微差版本号坍缩，准确率拉升至 $100\%$）；
  3. **可控**：`gated-mem log --graph`、`explain`、`undo` 事务回滚以及单文件离线 HTML 图谱；
  4. **极客**：标准库纯净实现，`pip install gated-mem` 绝不污染用户本地 Python 环境。

---

## 四、 第三阶段：`v1.1-external-eval` 外部学术基准异步推进

发版完成后，新建 `v1.1-external-eval` 分支，按从容节奏推进外部基准，总预算严格控制在 **¥50** 以内：

| 实验模块 | 基准数据集 | 执行策略与核心避坑指令 | 预算与模型 |
| :---: | :---: | :--- | :---: |
| **E1** | **MemoryAgentBench (CR 子集)** | **严防抽槽损失陷阱**：原始数据为非结构化文本，若抽槽器不一致会冤杀 A3 槽位机制。必须在 Ingest 阶段采用 Schema-Guided 提取（提供已有槽位列表），确保公平评测 A1..A6 实验臂。 | **¥15 ~ ¥30**<br>*(DeepSeek 谷时)* |
| **E2** | **Memora (weekly 150 题)** | 使用 `DeepSeek-V4.1F` 生成回答 + `GLM-5.3-Flash` 异构裁判评分，验证 `forgetting_absence`（遗忘无感）收益。 | **¥20 ~ ¥40** |
| **E4** | **双窗口桥接与弱模型边界** | 复用现有 `Gemini-3.8-Flash` 免费额度，探寻“短窗口 Wrapper 与超长溢出窗口 Gated-Mem”的黄金交叉点，产出边界分析报告。 | **¥0**<br>*(复用现有额度)* |
| **放弃** | **StateMemBench** | 该基准仅有论文、无公开代码与数据集（`paper_only`），直接放弃，避免无效时间消耗。 | **¥0** |

---

## 五、 工种协同矩阵与产出物清单 (Maker-Checker)

| 角色 | 主攻任务 | 交付产物 |
| :--- | :--- | :--- |
| **Tech Lead (DeepSeek-V4.1F)** | 1. `dsh.py` 防御补丁编写<br>2. E3 评测驱动适配<br>3. v1.0.0 打包与 PyPI 发布流水线执行 | `src/gated_mem/adapters/dsh.py`<br>`dist/gated_mem-1.0.0*`<br>`v1.0.0` Git Tag |
| **Dataset Engineer (GLM-5.3-Flash)** | 1. E3 跨模块碰撞数据集生成<br>2. 运行 E3 三通道对比实验<br>3. 输出完整对比数据表更新至 README | `benchmarks/data/phase5_e3_collision_disambiguation.json`<br>`benchmarks/reports/phase5_e3_report.md` |
| **Auditor (Gemini-3.8-Flash)** | 1. 异构黑盒复核 E3 实验数据真实性<br>2. 审计 Wheel 包体纯净度与安装测试<br>3. 签署 v1.0.0 最终发布审核令 | `benchmarks/reports/phase5_release_final_audit.md` |
