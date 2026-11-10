# Gated-Mem 终极架构方案：事件溯源 + 门控级联 + 残差记忆图谱

> **版本**：v2.0（融合严谨状态机、级联激活、双重残差与零经费开源冷启动）  
> **更新日期**：2026-11-10  
> **核心定位**：面向 Claude Code / Cursor 开发者的**本地、可解释、可回放、可撤销（Undoable）**的 Agent 状态记忆引擎。  
> **设计哲学**：内核极度克制（Event Sourcing + 结构化防误杀），外显极度直观（因果覆盖链 + 残差直连图谱）。

---

## 一、 方案可行性评估与取舍（为什么这样融合？）

另一个 AI 给出的 `v1.0` 规划是一份**满分的工业级/学术级风控文档**，但在“零经费独立开源”的约束下，我们必须做**“取其硬核骨骼、去其繁琐流程”**的剪裁：

### 1.1 必须 100% 吸收的四大工程铁律（来自另一 AI 的核心贡献）
1. **不可变事件日志（Event Sourcing）**：当前记忆状态与图谱边只是 `memory_events` 表的投影。任何误覆盖、误衰减、人工 Kill，只需一行 `gated-mem undo <event_id>` 即可 100% 无损回滚——这是解决“自动遗忘怕删错”的终极安全网。
2. **拒绝纯余弦阈值覆盖，改用 `Subject / Predicate / Scope` 槽位对齐**：向量检索只负责捞候选，必须比对结构化槽位（如 `Subject: Database`, `Predicate: primary_engine`, `Scope: backend`）才允许判定为 `SUPERSEDES`（状态覆盖）或 `CANDIDATE_CONFLICT`（待确认冲突）。
3. **未回传反馈 $\neq$ 未使用（废除 `IGNORED` 自动降权）**：宿主 LLM 经常忘了填 `cited_ids`，或者负面约束（“禁止用 Redis”）在回答里根本不留痕迹。因此，**只做正向激活与显式覆盖降权，绝不因为单轮未回传而扣减半衰期**。
4. **Claude Code Hooks 与 MCP 职责解耦**：MCP 提供大模型主动调用的读写工具；Hooks（`SessionStart` / `Stop`）负责确定性的上下文注入与本地日志落盘，不假设 MCP Server 能偷看到宿主最终回复。

### 1.2 必须修正的三个脱离实际之处（适配“零经费开源”现实）
1. **废除“先跑完昂贵 Benchmark 和 10 人两周留存才做可视化”的瀑布流**：没有经费跑 3-Judge 评测，就用**黄金回归测试集（Golden Fixtures，50 组真实项目架构演进的确定性状态反转用例）**来验证核心准确率；图谱可视化不是“花架子”，而是开发者用来执行 `Pin / Kill / Undo` 和理解“残差覆盖链”的**核心交互界面**。
2. **引入“单向激活扩散 + 覆盖连坐”**：解决孤立记忆节点缺乏结构联动的问题。
3. **引入“双重残差（结构 Shortcut + 状态 Diff）”**：替代破坏拓扑的哈夫曼树重构，让高频深层记忆实现 0 跳直达，同时保留历史变更原因。

---

## 二、 核心理论创新：门控、级联与双重残差机制

我们将 LSTM 门控语义与图谱拓扑深度绑定，但所有公式均可由纯数学在 `< 1ms` 内算完，无需训练神经网络。

### 2.1 记忆保留率与级联传播公式（Retention & Cascading Gate）

每条记忆节点 $v$ 在逻辑步数（或时间）距离上次激活经过 $\Delta \ge 0$ 后的基础保留率 $R(v)$ 采用标准化半衰期幂律公式：

$$R(v, \Delta) = \left(1 + \frac{\Delta}{t_0}\right)^{-\beta_{\text{type}}}, \qquad H_v = t_0 \left(2^{1/\beta_{\text{type}}} - 1\right)$$

在此基础上，节点 $v$ 在当前轮次 $t$ 的**合成有效生命力 $F_t(v)$** 由三部分叠加而成：

$$F_t(v) = \Big( \underbrace{R(v, \Delta)}_{\text{1. 基础幂律保留}} + \underbrace{\sum_{u \in \mathcal{N}_{\text{parent}}(v)} \gamma \cdot \mathbb{I}(u \text{ active}) \cdot F_t(u)}_{\text{2. 上级正向激活扩散}} + \underbrace{\alpha_{\text{res}} \cdot \mathbb{I}(\text{Shortcut}(Root, v))}_{\text{3. 结构残差直连加成}} \Big) \times \underbrace{\prod_{p \in \mathcal{A}(v)} \psi(p)}_{\text{4. 祖先覆盖连坐乘子}}$$

* **法则 1（正向激活扩散，不搞反向连坐）**：当父节点或所属模块 $u$（如 `[后端存储架构]`）被激活引用时，其下属子节点 $v$ 获得 $\gamma \in (0.2, 0.4)$ 的递减权重增益；若父节点本轮未被提及，子节点仅按自身 $R(v, \Delta)$ 自然慢速衰减，**绝不施加额外惩罚**。
* **法则 2（状态覆盖连坐坍缩 $\psi(p)$）**：只有当祖先节点 $p \in \mathcal{A}(v)$ 的状态变为 `superseded` 或 `killed` 时（例如 `[使用 MySQL]` 被 `[改用 PostgreSQL]` 正式覆盖），连坐乘子 $\psi(p)$ 从 $1.0$ 瞬间变为 $0.15$——所有依附于旧 MySQL 的子配置记忆（如 `[MySQL 连接池大小=20]`）自动集体失活，彻底清除关联上下文污染！

### 2.2 双重残差机制（Dual Residual Connections）

#### 机制 A：结构残差（Skip-Connection / 哈夫曼式动态提权）
* **触发条件**：某个挂载在第 $3+$ 层的深层叶子节点 $v$（例如：`Root -> 规范 -> 测试 -> 数据库 -> [禁止在单测中连接真实线上库]`），累计被验证引用（`self_reported` 或 `user_verified`）达到 $K=3$ 次。
* **残差动作**：**不破坏原有的语义树结构**，直接在 `Root`（项目根节点）与节点 $v$ 之间生成一条类型为 `RESIDUAL_SHORTCUT` 的残差跳跃边。
* **实际收益**：在检索与 Token 预算截断时，带有 `RESIDUAL_SHORTCUT` 的节点享有与顶层架构决策同等的 $0$ 跳优先级（实现哈夫曼编码“高频项路径最短”的物理效果，但零拓扑重构成本）。

#### 机制 B：状态残差（Delta Memory / 变更原因留存）
* **触发条件**：当新记忆 $M_{\text{new}}$（`改用 PostgreSQL`）覆盖旧记忆 $M_{\text{old}}$（`使用 MySQL`）时。
* **残差动作**：不仅建立 `M_new --[SUPERSEDES]--> M_old` 的边，还在该边上挂载一个轻量结构化字段 `residual_diff`（记录**“为什么变”**，例如：`"因需要 JSONB 索引支持而废弃 MySQL"`）。
* **实际收益**：日常写代码检索时，输出门过滤掉 $M_{\text{old}}$ 只注入 $M_{\text{new}}$（省 Token、防冲突）；当开发者追问“为什么不用 MySQL”时，输出门顺着 `SUPERSEDES` 边提取 `residual_diff` 一并回答，做到**“忘掉过期指令，但记住演进教训”**。

---

## 三、 核心数据与事件溯源设计（SQLite 单文件底盘）

启用 SQLite `WAL` 模式与外键约束，所有表均带 `project_id` 实现多项目严格隔离。

### 3.1 记忆主表（`memories`）
```text
memory_id           TEXT PRIMARY KEY
project_id          TEXT NOT NULL
content             TEXT NOT NULL
memory_type         TEXT NOT NULL  -- decision | constraint | preference | observation
subject             TEXT NOT NULL  -- 实体/主题，如 'database_primary'
predicate           TEXT NOT NULL  -- 属性槽位，如 'engine_choice'
scope               TEXT NOT NULL  -- 作用域，如 'global' | 'auth_service'
status              TEXT NOT NULL  -- active | candidate_conflict | superseded | archived | killed
input_weight        REAL NOT NULL  -- 初始写入重要度 i_t ∈ (0, 1]
retention_beta      REAL NOT NULL  -- 按类型固定的衰减指数 β
half_life_steps     REAL NOT NULL  -- 动态半衰期 H
citation_count      INTEGER DEFAULT 0
has_shortcut        INTEGER DEFAULT 0  -- 是否已激活结构残差直连 (0/1)
pinned              INTEGER DEFAULT 0  -- 人工锁定不衰减 (0/1)
created_step        INTEGER NOT NULL
last_active_step    INTEGER NOT NULL
source_event_id     TEXT NOT NULL
embedding_model_id  TEXT NOT NULL
```

### 3.2 图谱关系与残差边表（`memory_edges`）
```text
edge_id             TEXT PRIMARY KEY
project_id          TEXT NOT NULL
source_id           TEXT NOT NULL  -- 起点 memory_id (或 'ROOT')
target_id           TEXT NOT NULL  -- 终点 memory_id
edge_type           TEXT NOT NULL  -- BELONGS_TO | SUPERSEDES | CONTRADICTS | REFINES | RESIDUAL_SHORTCUT | CO_CITED
residual_diff       TEXT           -- 状态残差摘要：记录覆盖或细化的核心增量原因
confidence          REAL NOT NULL
created_event_id    TEXT NOT NULL
revoked_event_id    TEXT           -- 若被 Undo 撤销，记录撤销事件 ID
```

### 3.3 不可变事件日志表（`memory_events` —— 可回放与 Undo 的基石）
```text
event_id            TEXT PRIMARY KEY
project_id          TEXT NOT NULL
step                INTEGER NOT NULL
event_type          TEXT NOT NULL  -- MEMORY_CREATED | CONFLICT_FLAGGED | MEMORY_SUPERSEDED | CASCADE_DEMOTED | SHORTCUT_FORMED | MEMORY_PINNED | MEMORY_KILLED | EVENT_UNDONE | RECALL_DELIVERED | FEEDBACK_RECORDED
payload_json        TEXT NOT NULL  -- 包含变更前后的状态快照 (before_state / after_state)，确保 O(1) 逆向撤销
created_at          TEXT NOT NULL
```

---

## 四、 关键工作流设计（防呆、可控、可解释）

### 4.1 写入与两阶段冲突裁决（杜绝余弦误杀）

```text
宿主调用 gate_remember(content, subject, predicate, scope, memory_type, residual_reason)
  │
  ├─► 1. 候选召回：同 project_id 下，按 (subject, predicate, scope) 精确/模糊匹配 + 向量 Top-10
  │
  ├─► 2. 关系分类器：
  │     ├── 完全无关 → 直接写入 active，挂载到对应 Scope 父节点 (BELONGS_TO)
  │     ├── 语义重复 (Sim > 0.92 且槽位值一致) → 不新建，仅触发原记忆事件刷新 last_active_step
  │     ├── 槽位完全对齐 + 显式传入 supersedes_id 或高置信反转：
  │     │     → 新记忆标为 active
  │     │     → 旧记忆标为 superseded，写入 SUPERSEDES 边并附带 residual_diff
  │     │     → 【触发级联连坐】：遍历旧记忆的所有子节点，批量记入 CASCADE_DEMOTED 事件
  │     └── 疑似矛盾但槽位/作用域不明确 (如一个在 global，一个在 test)：
  │           → 绝不自动覆盖！建立 CONTRADICTS 边，状态标为 candidate_conflict
  │           → 在 CLI / UI 和下次召回尾部提示用户一行命令裁决
```

### 4.2 检索、输出门与可解释性回执

每次检索必须在固定 Token 预算（如 `max_tokens=800`）内完成，并返回结构化的**可解释性回执（Explain Receipt）**：

1. **注入列表（Injected）**：当前生效的记忆 + 残差直连记忆。
2. **拦截日志（Filtered Stale / Cascaded）**：本次有哪些向量相似度很高、但因为处于 `superseded` 或被父节点连坐降权而被拦截的旧记忆（直接证明插件防污染的价值）。
3. **残差演进提示（Residual Context）**：若注入的记忆存在最近 1 跳的 `SUPERSEDES` 边，顺带附上一行极简括号说明：`(注：于 Step 42 替代了旧方案 MySQL，原因：需 JSONB 支持)`。

---

## 五、 务实的 7 天 MVP 落地计划（单人 + AI 结对编程）

我们将另一 AI 建议的“5 天硬核 Spike”与我们的“可解释图谱 UI”结合，定为 **7 天可交付开源版本**：

| 阶段 | 核心任务 | 验收标准（必须跑通的硬指标） |
| :--- | :--- | :--- |
| **Day 1**<br>状态机与事件溯源 | 编写 `schema.py`, `events.py`, `gates.py`。实现标准化半衰期公式、正向级联、覆盖连坐与结构残差判定。 | 单元测试 100% 通过：`R(0)=1, R(H)=0.5`；父节点 `superseded` 时子节点自动连坐降权；任意事件执行 `undo()` 后状态完全复原。 |
| **Day 2**<br>SQLite 与槽位冲突 | 编写 `storage.py`, `conflicts.py`。配置 SQLite WAL，实现 `subject/predicate/scope` + 本地向量（或 NumPy 回退）的候选检索与分类。 | 构造 30 组黄金测试集（含同主题覆盖、不同 Scope 并存、参数细化）：**自动覆盖误杀率 = 0%**（拿不准的全部进 `candidate_conflict`）。 |
| **Day 3**<br>MCP 与 Hooks 闭环 | 编写 `server.py` 与 `adapters/claude_code.py`。打通 stdio 通信与项目级隔离（按 Git 根目录哈希自动生成 `project_id`）。 | 在真实 Claude Code 中完成：写入架构决策 → 切换决策 → 询问当前架构，验证旧决策被精准拦截，且两不同目录项目绝不串库。 |
| **Day 4**<br>CLI 诊断与时光机 | 编写 `cli.py`。实现 `list`, `explain <recall_id>`, `conflicts`, `pin`, `kill`, `undo <event_id>`, `replay --step N`。 | 敲入 `gated-mem explain` 能清晰打印出本次召回为什么选 A、为什么拦截了高相似的过期记忆 B。 |
| **Day 5**<br>离线单文件图谱 UI | 编写 `web/app.py` 与本地无 CDN 依赖的图谱页（内嵌轻量 Canvas/SVG 力导向与时间轴）。支持点击节点执行 Pin / Kill / Undo。 | 视觉清晰呈现三类核心边：🔴 `SUPERSEDES`（带 `residual_diff` 标签）、⚡ `RESIDUAL_SHORTCUT`（跨层金色虚线）、🔵 `BELONGS_TO`（级联树）。 |
| **Day 6**<br>黄金基准对比实验 | 编写 `scripts/eval_golden.py`。在完全不调外部付费 API 的前提下，用 50 个真实多步编码演进场景对比 `Pure Vector` vs `Gated-Mem`。 | 输出严谨的检索层指标对比表：展示同 Token 预算下，`Current-State Recall@K` 的提升幅度与 `Stale-Fact Contamination Rate`（过期污染率）的下降幅度。 |
| **Day 7**<br>实战吃狗粮与发布 | 在你自己的 2 个真实日常开发项目中挂载使用，修复边界 Bug，录制真实 CLI `explain/undo` + 图谱残差演进 GIF。 | 满足开源发布红线：安装耗时 `< 3 分钟`、零 Docker 依赖、断网可用、所有宣传数据均来自 Day 6 实测脚本。 |

---

## 六、 零经费如何做严谨验证？（替代昂贵的 LLM-Judge 实验）

既然没有 ¥4100 的 API 预算去跑三模型裁判，我们就把评测边界锚定在**“检索与注入层（Retrieval & Injection Layer）”**——这是 100% 确定性、零 API 费用、且审稿人和硬核开发者完全认可的评测方式：

1. **构建 `Golden-Coding-Evolution-50` 本地评测集**：
   编写 50 个贴合真实开发的演进序列（每个序列包含 10~20 步事件：初始选型 $\to$ 子配置衍生 $\to$ 局部重构覆盖 $\to$ 跨模块高频调用某条深层约束 $\to$ 最终查询）。
2. **三大零成本硬核指标（直接用 Python 脚本算）**：
   * **有效状态命中率（Active-State Hit Rate @ Token Budget）**：在限制 500 Token 注入预算下，正确召回当前最新状态及残差原因的比例。
   * **过期状态泄露率（Stale Leak Rate）**：被明确覆盖（`superseded`）或被父节点连坐废弃的子配置，依然挤进 Top-K 注入列表的比例（目标：传统向量基线 $> 40\%$，本方案 $< 2\%$）。
   * **深层高频规则召回率（Deep-Rule Shortcut Recall）**：测试结构残差 `RESIDUAL_SHORTCUT` 开启前后，挂载在第 4 层的核心约束能否在全局模糊查询中被稳定带出。

---

## 七、 最终执行口诀（写给开发过程的护栏）

1. **向量只找候选，槽位决定覆盖；拿不准就挂起（`candidate_conflict`），绝不静默删改。**
2. **上级激活向下传（正向扩散），上级作废全家瘫（覆盖连坐），平时没用只慢衰（无反向连坐惩罚）。**
3. **高频叶子拉残差（`Shortcut` 直连根节点），状态覆盖留残差（`residual_diff` 记变更原因）。**
4. **一切变更皆事件（`memory_events`），任何错误可一键 `undo`。**