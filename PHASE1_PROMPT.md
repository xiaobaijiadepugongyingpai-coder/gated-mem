# 任务：执行 Gated-Mem v2.1.1 阶段一（首刀验证）

## 0. 基本信息

- 工作目录：`<repo-root>`
- 环境：Windows + git-bash，**Python 3.9.13**
- 预算：**¥0**，禁止任何外部 API 调用、禁止 pip 安装第三方包，全部用标准库
- 审批策略：never ask，不需要向我确认，直接干
- 本轮只做**阶段一（Day 1–2）**，做完写交接文档，不要提前开工阶段二

## 1. 先读这些文件（必须完整读完再动手）

| 文件 | 用途 |
|---|---|
| `total_plan/gated_mem_implementation_plan.md` | **主计划**，v2.1.1 定版，重点读 §3/§5/§6/§7 |
| `total_plan/gated_mem_decision_dossier.md` | 终审裁决案卷，说明哪些机制被砍、为什么砍 |
| `大模型建议.txt` | 三个 Schema 补丁（embedding / FTS5 / RECALL_DELIVERED）+ 团队分工建议 |
| `Preliminary_Exploration/review/gated_mem_review.md` | 独立复核，负收益证据来源（可选，重点看争议二） |

## 2. 阶段一目标（不要跑偏）

用零成本确定性脚本，在 **40 组软件架构演进测试集**上跑三分支消融，拿到能写进 README 的硬核数据，跨过**阶段门禁 1**。

**明确不在本阶段做**：SQLite、事件溯源、MCP、CLI、HTML 导出、任何 Web UI。这些是阶段二、三的事。

---

## 3. 团队组建（**关键：必须显式指定模型**）

上一次失败的根因之一：三个成员全部继承了默认模型，导致"监察官自己审自己"，治理机制形同虚设。

可用路由（已在本机核实存在）：

```
workbuddy/deepseek-v4.1-flash   ← 主程（数学与内核）
workbuddy/glm-5.3-flash         ← 数据与评测（批量造数据）
antigravity/gemini-3.8-flash    ← 异模型监察（独立审计）
```

建队时**每个成员都要显式传 provider + model**：

```js
agent_teams_create({
  name: "gated-mem-phase1",
  approval: "required",
  plan: {
    members: [
      { name: "kernel",  provider: "workbuddy",   model: "deepseek-v4.1-flash" },
      { name: "qa",      provider: "workbuddy",   model: "glm-5.3-flash" },
      { name: "auditor", provider: "antigravity", model: "gemini-3.8-flash" }
    ],
    tasks: [ /* 见 §5 */ ]
  }
})
```

> 注意：`antigravity` 走 agy CLI 通道，可能不稳定。若 auditor 反复启动失败，降级到 `workbuddy/deepseek-v4.1-flash`，但必须在最终报告里**明确记录这个偏离**。
>
> 另：子代理**不能再派生子代理**（delegation depth 上限 1），所以三层嵌套是不行的，只能一层三名成员。

---

## 4. 第一步：自己写死契约 `benchmarks/CONTRACT.md`

你是 Tech Lead，**先签发契约再派人干活**。契约必须固化下面这些，照抄，不要自由发挥。

### 4.1 数学常数（来自计划书 §3.1）

| memory_type | beta | t0_base |
|---|---|---|
| DECISION | 0.10 | 100 |
| CONSTRAINT | 0.05 | 200 |
| PREFERENCE | 0.15 | 80 |
| EPHEMERAL | 1.20 | 5 |

```
t0(v)  = t0_base(type) * (0.5 + input_weight)
Δ      = max(0, CASE_STEP - last_cited_step)      # last_cited_step 初值 = 节点 step
R(v)   = (1 + Δ / t0(v)) ** (-beta)
F_t(v) = 1.0                      若 pinned
       = min(1.0, R(v) + GAMMA * max{ R(u) : u = v.parent 且 active } )   否则
LAMBDA = 0.3    GAMMA = 0.2    TopK = 5
```

**重要**：连坐系数 ψ 已被终审**物理砍掉**。B 分支只是实验对照组，ψ 在读代码时体现为"子节点被标 superseded"，不存在任何连乘。

### 4.2 三分支语义（整个实验的核心）

- **分支 A（纯向量基线）**：所有节点恒 `active`，不做槽位覆盖，不记录 `residual_diff`。检索 = 全部节点按 `rel(q,v)` 取 Top-5。
- **分支 B（v2.0 强连坐对照组）**：槽位 `(subject, predicate, scope)` 完全相同时覆盖旧节点，并**沿 `parent_id` 把全部子孙标为 superseded**（传递闭包）。检索只取 active。
- **分支 C（v2.1.1 终审机制）**：槽位相同只覆盖**直接**旧节点；子孙仅置 `stale_parent_warning=True` 但**保留 active**；新节点 `residual_diff = "[Replaced: " + old.subject + " / " + old.content[:30] + "] " + 原始原因`。

### 4.3 事实通道 vs 解释通道（**上次踩过的坑，务必照做**）

**`residual_diff` 绝对不能进入 `injected_text`。**

- `injected_text`（事实通道）：只由注入节点的 `content` 用换行符拼接
- `returned_diff`（解释通道）：C 分支的 `[Replaced: … MySQL 8.0]` 只出现在这里

原因：C 分支的招牌能力就是把旧技术名写进回执。如果它同时进了注入正文，而 `must_exclude` 里又写着 "MySQL"，C 分支会**在自己的核心卖点上被判失败**。判定 `current_state` 时只扫 `injected_text`，不扫 `returned_diff`。

### 4.4 分词与相似度（两套独立实现必须一致）

```
tokenize(text):
  1. NFKC 归一化 + 转小写
  2. ASCII 整词：re.findall(r"[a-z0-9_]+", text)      # 不做词干化
  3. 每个连续中文片段 run：
       加入全部单字；若 len(run) >= 2，再加入全部相邻二元组

rel(a, b) = |A ∩ B| / sqrt(|A| * |B|)      # 空集返回 0.0
排序：score 降序，同分按 node_id 升序（保证可复现）
```

### 4.5 判定规则（机械判定，零人味）

- `current_state`：`injected_text` 含全部 `must_include` **且** 不含任何 `must_exclude`
- `anti_trap`：`must_include` 全含 **且** `expect_survive` 的节点 id 全在 `injected_node_ids` 里
- `evolution_why`：`returned_diff` 非空 **且** `must_include` 全含 **且** `old_keyword` 出现

> 计划书原文写的是"双盲 LLM 裁判"。**不要真的去调 LLM 当裁判**——不可复现，且违反零预算。改成更强的替代：Auditor 按契约从零重写评分器，逐 probe 交叉核对，要求零分歧。这个偏离必须在报告里显式声明。

### 4.6 门禁 1（摘自计划书 §5）

1. C 在 `current_state` 上比 A 提升 **≥ 20pp**
2. C 在 `anti_trap` 上严格 **大于** B（证明连坐确实负收益）
3. C 在 `evolution_why` 上 **≥ 85%**

**门禁 fail 时严禁改数据集或调阈值凑数**，如实记录并给出诊断。

---

## 5. 任务分解（5 个任务，按依赖排）

| ID | 内容 | 负责人 |
|---|---|---|
| T1 | 写 `benchmarks/tools/build_dataset.py` 生成器 → 产出 `data/eval_cases_40.json` | qa |
| T2 | 写 `benchmarks/tools/validate_dataset.py`（校验 9 条硬约束）+ 标签复核报告 | qa |
| T3 | 实现 `benchmarks/spike_cut1.py`（三分支 + `--self-test`） | kernel |
| T4 | 跑真实数据 → `results/raw_runs.json` + `results/metrics.json` | kernel |
| T5 | 从零重写 `audit/independent_scorer.py` 交叉核对 + 门禁签署 | auditor |

依赖：T1 → T2；T3 可并行（自检不依赖数据集）；T4 依赖 T2 + T3；T5 依赖 T4。

### 测试集结构（40 组）

每组 6–8 个 `session_events` + 恰好 3 条 probe（`current_state` / `anti_trap` / `evolution_why` 各一）。

标准形态：

```
M1  旧决策    "db.engine 选用 MySQL 8.0"
M2  通用规范  "单测必须 mock 外部数据库"          parent=M1   ← 连坐靶子
M3  偏好      "注释一律中文"                      parent=M1
M4  新决策    "db.engine 切换为 PostgreSQL 16"    residual_diff="因需支持 JSONB…"   ← 覆盖 M1
M5  安全约束  "禁止硬编码密钥"                    parent=M1
M6  临时观察  "编译失败疑似缓存未清理"            EPHEMERAL
```

硬约束：至少 6 个 domain、多亲用例 ≥ 3 组、scope 隔离 ≥ 4 组、假冲突 ≥ 2 组、**负控制组 ≥ 8 组**（`is_control=true`，且 `construction_note` 必须写明为何是控制组）。

`residual_diff` 要求：纯自然语言原因，**不带** `[Replaced:` 前缀（前缀由 C 分支运行时拼），但**必须提及**被替代的旧技术关键词。

### 造数据的关键教训

**绝对不要让子代理一次性输出 40 组 JSON**——会被中断，且全部丢失、零产出（上次就是这么失败两次的）。

正确做法：写**生成器脚本** `build_dataset.py`，用数据结构描述用例（每个用例一行 `add(...)` 调用），运行脚本落盘。好处：可中断、可增量、可复现、改一个参数就能整体重生成。

---

## 6. Git 版本控制要求

- 开工先 `git add -A && git commit` 建立基线
- `.gitignore` 必须排除 `.agent-teams/`（AgentTeams 运行时状态，不入库）
- 每个任务交付后单独 commit，信息用中文，例如：
  - `feat(dataset): 40 组演进与 Anti-trap 测试集`
  - `feat(spike): 三分支首刀运行器与自检`
  - `docs(report): 阶段一消融报告`
- 提交前跑 `git status` 确认没有意外文件

---

## 7. 交付物清单

```
benchmarks/
  CONTRACT.md                     # 冻结契约（你自己签发）
  data/eval_cases_40.json         # 40 组测试集
  data/eval_cases.schema.json     # JSON Schema
  tools/build_dataset.py          # 生成器
  tools/validate_dataset.py       # 校验器
  spike_cut1.py                   # 三分支运行器
  results/raw_runs.json           # 逐 probe 原始证据
  results/metrics.json            # 聚合指标 + gate 结论
  audit/independent_scorer.py     # Auditor 独立重写
  reports/audit_phase1.md         # 独立审计 + 门禁签署
  reports/dataset_label_audit.md  # 标签复核
  reports/spike_cut1_report.md    # 汇总报告
docs/
  phase1_handoff.md               # ★ 阶段二交接文档
```

### `docs/phase1_handoff.md` 必须包含

1. 阶段一结论：门禁三项是否达标，一句话定性
2. 三分支消融数据表（每分支 × 每 probe 类型的准确率）
3. 关键发现（例如连坐是否真的负收益，实测是多少 pp）
4. 契约中所有**偏离计划书**的地方及原因（例如"双盲裁判改为机械判定"）
5. 已踩过的坑清单（给阶段二的人避雷）
6. 阶段二的接口约定：`schema.py` / `gates.py` 需要实现哪些函数签名
7. 环境与命令速查（怎么复现这次实验）

---

## 8. 执行纪律（重要）

1. **先契约，后分工**。契约没写完不要派人干活，否则各写各的必翻车。
2. **队长要能接管**。若某成员反复被中断、零产出，立刻 `reassign_task(assignee="captain")` 自己干，别让阶段空转。上次 qa 连续两次零产出，就是没及时接管。
3. **粘贴真实输出**。所有报告里的数字必须能从 `raw_runs.json` / `metrics.json` 反查。禁止臆想数据。
4. **自检先行**。`--self-test` 里必须断言：`R(2H) == (2 * 2**(1/beta) - 1)**(-beta)` 且 **大于 0.25**。原计划写的 `R(2H)=0.25` 是错的，那是指数衰减的值；幂律下四个类型的实测值分别是 0.4665 / 0.4830 / 0.4510 / 0.3231，全部大于 0.25。
5. **两次运行必须逐字节相同**（时间戳等易变字段不要写进结果文件）。
6. **Python 3.9 语法**：禁止 `match` 语句、禁止运行期 `X | Y` 联合类型标注。

---

## 9. 开跑顺序

① 写 `CONTRACT.md` → ② 建 git 基线并提交 → ③ 建队（显式指定三个模型）→ ④ 审批通过 → ⑤ 派活 → ⑥ 收口写报告与交接文档。

现在开始。
