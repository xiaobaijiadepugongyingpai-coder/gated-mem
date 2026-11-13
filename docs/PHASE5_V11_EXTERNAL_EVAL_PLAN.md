# PHASE5 · v1.1-external-eval 分支准备文档

> **文档版本**：GM-PLAN-P5-V11-v1.0
> **写作时间**：2026-11-13（v1.0.0 已 commit + tag + build + twine check 通过之后）
> **状态**：**规划文档**。本文件只准备分支与执行口径，**不包含任何已产生的评测结果**。
> **上游依据**：`total_plan/phase5_release_and_supplementary_experiments.md` §四；`experiments_v2/{README,PROVENANCE,HANDOFF}.md`
> **本文档与旧文档冲突时以本文档为准**（主要冲突见 §6.3：总预算由 ¥45–110 收紧为 ¥48 上限 ¥50）。

---

## 0. 一句话结论

v1.1 的外部评测只做两件事：**E1 MemoryAgentBench（CR 子集）** 与 **E2 Memora（weekly 150 题）**；
**放弃 StateMemBench**（本次已重新核实：确为 `paper_only`，无公开代码与数据集）；
全部外部基准 API 支出**硬上限 ¥50**，分配为 E1 ¥20 + E2 ¥22 + 复核/应急 ¥6 = **¥48**。
**这一阶段是发版【之后】的异步分支工作，不阻塞、不回头修改 v1.0.0 的任何已发布产物**（详见 §5）。

---

## 1. 核实清单（本次实际查证的事实）

红线要求：不编造数据集名称与指标数字。下表每一行都是本次**实际发起并拿到响应**的核对，
并标注了核对方式；拿不到的一律进 §9「待核实」。

| # | 待核实项 | 核对方式 | 结果 |
|---|---|---|---|
| V1 | StateMemBench 有无公开代码/数据 | arXiv `2608.19652` 摘要页正文链接全量扫描 | **无**任何 github / huggingface dataset / zenodo 链接（页面内仅有 huggingface 站内导航链接） |
| V2 | 同上 | GitHub Search API `q=statemembench` | `total_count: 0` |
| V3 | 同上 | HF Hub `/api/datasets?search=StateMemBench` 与 `search=StateMem` | 均为 `[]` |
| V4 | 同上 | HF Hub `/api/models?search=statemem` | 仅命中两个无关权重仓库（`BackRabb1t/State-memory`、`State-memory2`），非本基准 |
| V5 | MemoryAgentBench 是否公开 | HF `huggingface.co/api/datasets/ai-hyz/MemoryAgentBench` | **公开**，`license: mit`，`downloads: 12248` |
| V6 | MAB 代码仓库是否公开 | `github.com/HUST-AI-HYZ/MemoryAgentBench` HTTP 200 | **公开**，标题含 *"Open source code for ICLR 2026 Paper: Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions"* |
| V7 | MAB 各 split 真实规模 | HF datasets-server `/size` | `Accurate_Retrieval=22` / `Test_Time_Learning=6` / `Long_Range_Understanding=110` / `Conflict_Resolution=8`，**合计 146** |
| V8 | MAB CR 的真实题量 | datasets-server `/first-rows`（CR 全 8 行） | **每行 100 题 / 100 组答案 ⇒ 8×100 = 800 题**（旧文档写的「480–800 题」现可精确到 800） |
| V9 | MAB CR 的 `metadata.haystack_sessions` | 同上 | **为 `null`**（CR 行没有分块会话，只有一整块 `context` 扁平事实列表）⇒ ingest 必须自己切块 |
| V10 | MAB CR 的 `metadata.question_types` | 同上 | **为空数组** ⇒ 单跳/多跳分组只能靠 `metadata.source` 字段，不能靠 question_types |
| V11 | MAB CR 的 `metadata.source` | 同上 | row0=`factconsolidation_mh_6k`（context 26,157 字符 / 457 行）、row1=`factconsolidation_mh_32k`（136,565 字符 / 2,312 行）；row2–7 预览中为 `null` → 见 §8 待核实 T1 |
| V12 | MAB 官方判分与严格性警告 | 仓库 `README.md` 原文 | CR→`substring_exact_match`；AR→`substring_exact_match`；LRU/TTL→`exact_match`。原文警告：*"if the ground-truth label is \`43\` but the model returns \`label: 43\`, it will be counted as incorrect. We recommend flexible parsing when adapting the benchmark to your own pipeline."* |
| V13 | Memora 是否公开 | `github.com/geniesinc/Memora` HTTP 200 + `README.md` | **公开**，**Apache-2.0**，ACL 2026，arXiv `2604.20006` |
| V14 | Memora 150 题口径 | 仓库 `README.md` + `evals/README.md` | `data/weekly/<persona>/` 共 **10 persona**，weekly/monthly 每人 **15 题**（Remembering/Reasoning/Recommending 各 5）⇒ **10×15 = 150 题**，与计划一致 |
| V15 | Memora 子问题标签 | `evals/README.md` | 每题带 `evaluation` 块，子问题标 `memory_presence` 或 `forgetting_absence` |
| V16 | FAMA 定义 | `evals/README.md` 原文 | `FAMA = max(0, MPA − λ·(1 − FAA))`，`λ = N_forget/(N_presence+N_forget)`，per-question ∈ [0,1]，Table 3 单元格为该桶内均值 ×100 |
| V17 | Memora 官方 judge 配置 | `evals/README.md` | 三 judge 多数投票：`openai/gpt-4.1`、`anthropic/claude-haiku-4.5`、`google/gemini-2.5-flash`（均经 OpenRouter）；`--no-multi-judge` 可退化为单 judge |
| V18 | Memora Track 2 的接入点 | `evals/README.md` | 两步：`conversation_to_memory.py`（按 `user_id="<persona>_<period>"` ingest）→ `memory_to_answer.py`（同 user_id 检索、`gpt-4o-mini` 作答、同一套 judge） |

**V19 顺带修正一处早期文案错误**：`Preliminary_Exploration/memory_plugin.md:177` 称 Memora 上「即使最强系统也只有 20 多分/100」。
按本次核实的仓库 README 表 3，**20 多分是「纯 LLM」列**（如 Claude Sonnet 4.5 weekly/Remembering = 27.50）；
**记忆 agent 列是 40–72 分**（A-Mem 71.82 / LangMem 71.16 / Nemori 65.06 / MemoryOS 51.84 / MemoBase 43.60 / Mem-0 40.42，均为 weekly/Remembering）。
后续报告引用时必须标清列名与 period，不得混用。

---

## 2. 决策 D1：放弃 StateMemBench（`paper_only`）

### 2.1 结论

**放弃，且不占用任何预算与工时。** 结论由 V1–V4 四条独立证据支撑，方向一致。

### 2.2 依据

1. **论文声明与交付物不一致。** arXiv `2608.19652`（*Can Agent Memory Systems Track Evolving State?*，Submitted 20 Aug 2026）摘要中明确把 `StateMemBench` 作为贡献之一（234 个 multi-session 场景、closed-pool 评分），但**摘要页不存在任何代码或数据链接**。
2. **GitHub 无官方仓库。** `q=statemembench` 全站检索 `total_count: 0`。
3. **HuggingFace 无数据集。** `datasets?search=StateMemBench` 与 `search=StateMem` 均返回空数组；`models?search=statemem` 命中的两个仓库是本会话无关的个人权重，不是该基准。
4. **不可复现 ⇒ 结论不可验证。** 本项目对外只发布「别人能一键复现」的数字。一个拿不到数据集的基准，写进报告的每一个分数都无法被读者核对，这违反 `experiments_v2/PROVENANCE.md` 的自定原则（"任何写进报告的数字，都必须能在此处追溯到来源或复现命令"）。

### 2.3 保留条件（什么情况下重新评估）

只有同时满足以下三条才重新考虑，否则不复议：

- 出现**官方**代码仓库或 HF 数据集（作者主页 / 论文 v2 版本 / 会议 supplementary 三处任一给出链接）；
- 数据集许可明确（允许在开源项目中分发派生结果）；
- 单次评测的 ingest 成本可在 §6 预算内闭环。

> 备注：该基准「逐轮 LLM 抽取」的 ingest 成本模型本身也昂贵（每 turn 一次 LLM 调用），属于本预算量级之外；这也是即便数据集公开也要先做成本测算的原因。

---

## 3. E1 · MemoryAgentBench（CR 子集）

### 3.1 它是什么（按 V5–V12 核实的结构，不引用未核实的说法）

- **全称/来源**：MemoryAgentBench，ICLR 2026，代码仓库 `HUST-AI-HYZ/MemoryAgentBench`，数据 `ai-hyz/MemoryAgentBench`（MIT）。
- **四个能力维度**：Accurate Retrieval (AR) / Test-Time Learning (TTL) / Long-Range Understanding (LRU) / **Conflict Resolution (CR)**。
- **数据形态**：每个样本 = 一大段 `context` + 一组 `questions` + `answers`（每题可接受多个答案）。
- **判分**：CR 用 `substring_exact_match`，**确定性字符串匹配，不需要 LLM judge ⇒ 判分成本 ¥0**。

### 3.2 为什么只选 CR 子集

| 子集 | 行数 | 与 Gated-Mem 的关系 | 是否入选 |
|---|---:|---|---|
| **Conflict_Resolution** | **8** | 直接对应槽位覆盖 / SUPERSEDES / 状态门控——**这是本项目唯一有资格声称的机制** | ✅ **主实验** |
| Accurate_Retrieval | 22 | 测的是"找得到"，向量库与本项目打平，**无差异假设** | ❌ 不跑（若要跑，作为无害对照） |
| Test_Time_Learning | 6 | 测的是 ICL，与记忆存储机制无关 | ❌ |
| Long_Range_Understanding | 110 | 占全库体积 75%，与机制无关，纯烧钱 | ❌ |

理由三条：
1. **机制对齐**：Gated-Mem 的差异化能力是「同一 (subject, predicate, scope) 下新值覆盖旧值、旧值不可被普通写入复活」，CR 的 fact consolidation 正是这件事的可执行版本。
2. **成本可控**：8 行 × 100 题 = 800 题，是四个子集里题量最小、信息量最集中的一块。
3. **判分免费**：确定性匹配，不需要 judge，把预算全部留给答案生成。

> ⚠️ 注意（V9/V10 推翻了一个旧假设）：CR 行 **没有** `metadata.haystack_sessions`，**也没有** `question_types`。
> 这意味着 `experiments_v2/dl/fetch_mab.py` 里「有则用它做 ingest」的分支在本子集上永远走 else，
> 必须有**自己的切块器**；单跳/多跳分组也只能从 `metadata.source`（`factconsolidation_mh_*` / `_sh_*`）推断。

### 3.3 核心设计：`mab_adapter.py` 的 Schema-Guided 槽位抽取

#### 3.3.1 为什么这是 E1 的**生死问题**

Gated-Mem 在真实宿主（DSH / Claude Code）里是靠 MCP 工具让**宿主大模型在写入时顺手传结构化槽位** `(subject, predicate, scope)` 的。
而 MAB 只给**非结构化文本**。如果抽取器写歪了：

- **A3/A4/A5（带槽位覆盖的臂）会被冤枉**——覆盖没触发，分数退化成 A1；
- 结论会变成"槽位机制无效"，而真实原因只是"我们的抽取器没抽出同一个槽位"；
- 这是**最容易把机制冤杀**的失败模式，必须在 ingest 阶段就设计掉。

#### 3.3.2 设计原则：抽取层与实验臂解耦，且只抽一次

```text
mab_cr.jsonl  ──►  slot_schema.py  ──►  mab_slots.jsonl (含 sha256)
   (原始 800 题)      (Stage-1 建池)         │
                                             ├─► A1/A2/A3/A4/A5 全部复用同一份
                                             └─► 保证「臂间差异只来自检索/覆盖逻辑」
```

- **一次性离线抽取、落盘、带 sha256**：任何臂都不得现场抽取。否则重跑会得到不同槽位，A/B 对比失效，且重复烧钱。
- **严禁按臂抽取**：如果 A3 用"好抽取器"、A1 用"差抽取器"，那评测的就不是机制而是我们的 prompt 工程。

#### 3.3.3 Schema-Guided 两阶段抽取

**Stage-1：建 schema 池（每条样本一次，只抽键、不抽值）**

```text
输入：该样本的 context（扁平事实列表，如 "0. Thomas Kyd was born in the city of London."）
输出：schema = {
          subjects:  [去重后的实体名列表],     # 只含键
          predicates:[归一化后的谓词列表],     # 只含键，如 "born_in_city" / "capital_of"
       }
```

三条硬约束：

1. **池里只放 key，绝不放 value**。放了 value 就等于把"当前值是什么"提前告诉模型，构成时间穿越式泄露。
2. **池来自该样本的全量上下文**（不是逐块增量）。CR 样本只有 ~500–2,300 条事实，键空间很小，一次建池即可。
3. **归一化谓词**：`"was born in the city of" / "was born in" / "born in city"` 必须归到同一个 `born_in_city`，否则同一槽位被拆成多个，覆盖永远不触发。**这一步是 slot 覆盖能否生效的分水岭。**

**Stage-2：带池抽取（分块，每块一次 LLM 调用）**

```text
输入：chunk（默认 40–60 条事实）
      + schema.subjects（closed vocabulary）
      + schema.predicates（closed vocabulary）
输出：JSON 数组，元素形如
      {"content": 原事实原文,
       "subject": "<必须从 subjects 里选>",
       "predicate": "<必须从 predicates 里选>",
       "scope": "global",
       "object": "<该事实的取值>"}
拒绝输出的情形：
      实体不在池中 → 输出 "subject": "__OOV__:<原字符串>"（保留原文，不硬塞）
      谓词不在池中 → 输出 "predicate": "__OOV__:<原字符串>"
```

- **closed vocabulary 就是本方案的名字来源**：把"开放式信息抽取"降级为"闭集分类 + 值拷贝"，抽取一致性显著提高，且**可被自动校验**（`__OOV__` 比例是一个可报表的量化指标）。
- 抽取产物必须落盘 `experiments_v2/data/mab_cr_slots.jsonl`，并在 `PROVENANCE.md` 记录 sha256、抽取模型与版本、prompt 模板路径。

#### 3.3.4 公平性护栏（写进 runner，不是口头承诺）

| 护栏 | 做法 | 失败后的处理 |
|---|---|---|
| 抽取一致性 | 抽 30 条人工/异构模型复核 | `__OOV__` 率 > 15% ⇒ 报告必须把 A3 标为**下界**，不得据此判死刑 |
| 覆盖确实触发 | 统计 `SUPERSEDES` 边数量与 `superseded` 状态节点数 | 若为 0 ⇒ **先修抽取，不许跑分**（跑了也没有信息量） |
| scope 中立 | 全部 `scope="global"` | 报告显式声明「scope 维度在本基准上未受检验」 |
| 上下文不泄露 | 答案模型只看 `RecallReceipt.injected_text()` | 任何把整段 `context` 塞进 prompt 的臂必须单独标注为 A6/wrapper |

> 为什么"覆盖为 0 就不许跑"值得单列：这正是 `experiments_v2` 已记录过的踩坑模式——向量没写进 `embedding` 字段时 `s_vec` 恒为 0，各臂退化成同一结果、命中率恒 0% 却不报错。**槽位没触发覆盖时同样静默失败。**

### 3.4 实验臂与判分

- **臂**：沿用 `experiments_v2/arms/definitions.py` 的 A0–A6（`A2_fts` 必须**独立报告**，这是 `phase4_hard_negatives_report.md` 从未单列的臂）。
- **判分**：官方 `substring_exact_match` + `arms/lenient_match.py` 的宽松解析（V12 官方自己建议灵活解析，否则 `"label: 43"` 会被判错、系统性虚低）。
- **必须同时报表**：`single_hop_acc` / `multi_hop_acc` / **`in_pool_rate`** / `ctx_tokens` / `__OOV__` 率。
  `in_pool_rate`（答案是否出现在被注入的上下文里）缺了，"靠拒答刷低污染率"会被伪装成好结果。

### 3.5 判定阈值（开跑前写死，禁止事后解释）

```text
H1 槽位覆盖有效        A3 − A1 单跳 ≥ +5pp 且 多跳 ≥ +2pp
H2 融合优于最强单通道   A4 − max(A1, A2) ≥ +3pp     ← 历史实验从未检验
H3 生命力有增量        A5 − A4 ≥ +3pp
H4 存储优于纯 prompt   max(A3..A5) − A6 ≥ +5pp      ← 最关键
```

### 3.6 已知风险与陷阱

| # | 风险 | 缓解 |
|---|---|---|
| R1 | `context` 是扁平事实列表，没有对话结构 | 按编号行切块，保留行号作 `created_step` |
| R2 | 单行 136,565 字符（row1）⇒ 全部灌进 prompt 会超预算且失真 | 固定 `topk` 与 `max_tokens`，所有臂同一上限 |
| R3 | CR 行无 `question_types`（V10） | 用 `metadata.source` 的 `mh`/`sh` 前缀分组；row2–7 见 §9 T2 |
| R4 | 每行 100 题但 8 行同质，可能 1–2 行主导结论 | 报告**分行**分数，不只报总均值 |
| R5 | 抽取模型与答案模型同族，存在自评倾向 | 抽取与作答用同一固定版本模型可以，但**判分不依赖 LLM**（CR 是字符串匹配），天然规避 |

---

## 4. E2 · Memora（weekly 150 题）

### 4.1 它是什么（V13–V18）

- Memora，ACL 2026，arXiv `2604.20006`，仓库 `geniesinc/Memora`，**Apache-2.0**。
- 数据：`data/{weekly,monthly,quarterly}/<persona>/`，10 个 persona。
  weekly = 7 天、每 persona 约 150 个会话；每人 **15 题**（Remembering / Reasoning / Recommending 各 5）⇒ **150 题**。
- 每题带 `evaluation` 块，由若干 yes/no 子问题组成，标 `memory_presence` 或 `forgetting_absence`。

### 4.2 为什么它是"遗忘"的唯一战场

本项目的 **`forgetting_absence`（遗忘无感）** 收益，只能在这里被官方指标度量。
Memora 是本次核实的**唯一**带 `forgetting_absence` 子项的公开基准（AR/LRU/TTL 都只奖励"记得"，不惩罚"记得不该记的"）。

**官方指标（V16 原文）**：

```text
FAMA = max(0, MPA − λ · (1 − FAA))

MPA = 答对的 memory_presence   子问题数 / 该类子问题总数
FAA = 答对的 forgetting_absence 子问题数 / 该类子问题总数
λ   = N_forget / (N_presence + N_forget)
```

per-question FAMA ∈ [0,1]；Table 3 单元格 = 该桶内均值 × 100。

**这个公式结构本身就说明了验证路径**：FAMA 同时奖励"该记的记住"（MPA）与"该忘的忘掉"（FAA），
而 `λ` 让**遗忘类子问题越多的题，FAA 的权重越大**。所以：
**只要 Gated-Mem 真能让旧值不浮出（SUPERSEDES / kill 生效），收益必然体现在 FAA → FAMA 上，而不是靠 MPA。**

### 4.3 如何验证 `forgetting_absence` 收益（实验设计）

**接入方式**（对齐官方 Track 2 的两步式，V18）：

```text
Step 1  conversation_to_memory 的等价实现：
        逐 session 读 data/weekly/<persona>/conversations/session_NNNN.json
        用 gated_store.remember(...) 写入，user_id 统一为 "<persona>_weekly"
        ✓ 必须与 Step 2 用同一个 user_id，官方明示否则检索为空

Step 2  memory_to_answer 的等价实现：
        对每题：store.recall(question) → RecallReceipt.injected_text()
        → 固定答案模型作答 → 交 judge 按子问题打分
```

**对照与统计（预先写死）**：

| 项 | 设定 |
|---|---|
| 臂 | **A1_vector（基线） vs A3_slot（槽位覆盖）**；预算允许再加 A4 |
| 题量 | 150 题（10 persona × 15） |
| 配对单位 | **persona**（10 对）→ per-persona 求均值后做 **Wilcoxon signed-rank**，α = 0.05 |
| 主指标 | **FAA**（forgetting_absence 正确率）与 **FAMA** |
| 必报 | per-persona 的 min/max/spread（n=15 的桶均值噪声大，只报总均值会误导） |
| judge | 默认**单 judge**（`google/gemini-2.5-flash`）跑全量；若两组 FAMA 差 < 3 分（临界），改用官方三 judge 多数投票复核 |

**判定阈值 H5（写死）**：

```text
H5 遗忘有收益：A3 的 FAA > A1 的 FAA，且 FAMA 提升 ≥ +2 分（0–100 标度）
   若 FAA 提升但 FAMA 未达 +2 ⇒ 结论写"方向一致但未达显著"，不得宣称收益
   若 FAA 无提升 ⇒ 如实报告负结果，并说明是「覆盖未触发」还是「触发了但检索没利用」
```

**诊断性必报表（即使全是坏消息也要报）**：SUPERSEDES 边数、superseded 节点数、每题命中被覆盖旧值的次数（`stale_hit_count`）。
这一列直接区分两种失败：**机制没生效** vs **机制生效但答案模型没用上**。

### 4.4 已知风险

| # | 风险 | 缓解 |
|---|---|---|
| M1 | 每题 15 个样本/桶，噪声大 | 报告分布 + 配对检验，不报单点 |
| M2 | `λ` 随题变化，跨题比较 FAMA 需谨慎 | 只用官方聚合口径，不自创加权 |
| M3 | 部分题可能没有 `forgetting_absence` 子项 | 统计「有 forget 子项的题数」，先报表再算分 |
| M4 | 三 judge 成本是本预算里最大单项 | 单 judge 优先，仅临界项升多 judge（见 §6） |
| M5 | weekly 会话数约 150/人 ⇒ ingest 调用量不小 | 先跑 2 个 persona 冒烟，量出每题单价再放量 |

---

## 5. 与 v1.0.0 的关系（红线）

1. **不阻塞发布。** 本阶段在 `v1.0.0` tag 打完之后进行；发布清单（`pytest` 全绿 / Gate3 / build / twine check）**不依赖本阶段的任何产出**。
2. **不修改已发布产物。** 外部评测只读调用 `src/gated_mem/`；若要为新基准补适配代码，一律新增在 `experiments_v2/` 下（历史上该目录已确立"只读调用、不改 `src/`"的纪律）。
3. **不改 `benchmarks/` 既有脚本与数据。**
4. **结论只写在本分支的报告里**，不回灌 `README.md` 主分支的已发布版本；若要更新主分支文案，走单独的 PR 并在 PR 描述里引用本分支报告链接。
5. **失败也是交付**：负结果同样发布（本目录已有先例：E3 零成本拿到"FTS 优势来自数据构造"的负结果）。

---

## 6. 预算：外部基准 API 总支出 **硬上限 ¥50**

### 6.1 分配表

| 编号 | 内容 | 估算调用量 | 冻结上限 |
|---|---|---|---:|
| **E1.0** | CR 全 8 样本的 schema 建池 + Schema-Guided 分块抽取（结果缓存复用） | ~130–180 次 LLM 调用 | **¥6** |
| **E1.1** | 冒烟：20 题 × 6 臂 | 120 次作答 | **¥1.5** |
| **E1.2** | 全量：800 题 × 6 臂 | 4,800 次作答（判分 ¥0） | **¥12** |
| **E1 小计** | | | **¥20**（含 1 次重跑余量） |
| **E2.0** | 冒烟：2 persona × 15 题 × 2 臂 + 单 judge | 60 次作答 + 60 次判分 | **¥2** |
| **E2.1** | 全量：150 题 × 2 臂 + 单 judge | 300 次作答 + 300 次判分 | **¥16** |
| **E2.2** | 临界项升级为官方三 judge 复核（限 100 题） | +200 次判分 | **¥4** |
| **E2 小计** | | | **¥22** |
| **E3/E4** | 自然语言改写集（零 LLM 检索层）+ Gemini 桥接（复用现有额度） | — | **¥0** |
| **复核与应急** | 抽取一致性复核、意外重跑、汇率/单价波动缓冲 | — | **¥6** |
| **合计** | | | **¥48**（硬上限 **¥50**，余 ¥2 不预分配） |

### 6.2 三道预算闸门（写进 runner，不是口头约定）

1. **单价未知不放量。** 任何全量跑之前，必须先跑冒烟子集，从 usage ledger 量出「每次调用实际 token 数」，再按开跑当日查证的单价换算单题成本，把外推值写进 `PROVENANCE.md`。**单价表目前为「待核实」（§9 T4），本文件不填任何单价数字。**
2. **80% 熔断。** 任一编号累计花费达到其冻结上限的 80%，runner 直接退出并要求人工复核后才可续跑。
3. **超额即停，不挪用。** 不允许把 E3/E4 的 ¥0 额度或别项结余挪来补 E1/E2；需要加预算必须回到本文档改分配表并留痕。

### 6.3 与旧文档的口径冲突（已裁决）

`experiments_v2/HANDOFF.md` §7 记的「合计 ¥45–110」与 `README.md` §7 的「API ¥45–110」**超出发版后的 ¥50 硬约束**。
**以本文档的 ¥48 / 上限 ¥50 为准**，差额靠三处压缩：

| 压缩项 | 旧口径 | 新口径 |
|---|---|---|
| 答案臂数 | E1 全 6 臂 × 多次重复 | 6 臂 **×1 次**（重复只降方差、不增独立观测） |
| judge | Memora 一律三 judge | **单 judge 跑全量**，仅临界项升三 judge |
| 题量 | Memora weekly + quarterly | **只跑 weekly 150 题**（quarterly 300 题移出 v1.1 范围） |

### 6.4 记账要求

- 每次 LLM 调用写一行 JSONL（`experiments_v2/results/usage_ledger.jsonl`）：`ts / experiment / arm / model / prompt_tokens / completion_tokens / est_cost`。
- 报告里的每个金额都必须能对上 ledger 汇总，禁止手写估数。

---

## 7. 分支与执行编排

### 7.1 分支建立（发版后执行，本次未执行）

```bash
# 前置：v1.0.0 已完成 commit + tag
git switch -c v1.1-external-eval v1.0.0
```

> 注意：本仓库主分支名为 **`master`**（不是 `main`）。分支从 **tag `v1.0.0`** 切出，而不是从 master HEAD 切出——保证评测对象的代码与已发布 wheel 逐字节一致。

### 7.2 分支上新增的目录

```text
experiments_v2/            ← 已有骨架，作为种子整体带入
├── adapters/
│   ├── gated_store.py     ✅ 已有（已验证）
│   ├── mab_adapter.py     ⬜ **本阶段新建**（§3.3 的落地点）
│   └── memora_adapter.py  ⬜ **本阶段新建**（§4.3 的落地点）
├── slots/
│   └── schema_guided.py   ⬜ Stage-1 建池 + Stage-2 带池抽取
├── runners/
│   ├── e1_mab_cr.py       ⬜ 核心 runner
│   └── e2_memora.py       ⬜ FAMA / forgetting_absence
├── data/
│   ├── mab_cr.jsonl       ⬜ 归一化后 800 题
│   ├── mab_cr_slots.jsonl ⬜ 抽取产物（带 sha256）
│   └── memora_weekly.jsonl⬜ 150 题归一化
└── results/               ⬜ 每次跑生成 md + json
```

### 7.3 执行顺序（每步一个可交付状态）

```text
D1  分支建立 + 依赖就绪（datasets 无法安装时走离线 parquet：hf 仓库已存在 data/*.parquet，见 V5/V6）
D1  MAB 归一化：8 行 → mab_cr.jsonl（800 题），记录 sha256          ← 零 LLM 成本
D2  Stage-1/2 抽取：mab_cr_slots.jsonl，统计 __OOV__ 率与 SUPERSEDES 数 ← ¥6 上限
D2  闸门：SUPERSEDES == 0 或 __OOV__ > 15% ⇒ 停，先修抽取
D3  E1 冒烟 20 题 × 6 臂 → 量单价                                    ← ¥1.5
D3  E1 全量 800 题 × 6 臂 → e1_mab_cr 报告（含 A2 独立列）            ← ¥12
D4  Memora weekly 归一化 + 2 persona 冒烟                            ← ¥2
D5  E2 全量 150 题 × 2 臂 + 单 judge                                 ← ¥16
D6  临界项三 judge 复核 + 统计检验（Wilcoxon）                        ← ¥4
D7  写 v1.1 外部评测报告；PROVENANCE 补 sha256 / 单价 / ledger 汇总
```

### 7.4 报告命名

```text
experiments_v2/results/e1_mab_cr_report.md
experiments_v2/results/e2_memora_fama_report.md
experiments_v2/results/v1_1_external_eval_summary.md   ← 对外主报告
```

---

## 8. 待核实清单（写报告前必须补齐）

| 编号 | 待核实项 | 为什么必须先核实 | 状态 |
|---|---|---|---|
| **T1** | MAB CR 第 2–7 行的真实 `source` 与 context 规模 | first-rows 预览对第 2–7 行只返回 100 字符且 `source=null`（疑似预览截断），无法确认单跳/多跳构成 | **待核实**（需下载 parquet 或 `rows` 分页） |
| **T2** | 各 CR 行的题量是否均为 100 | 已验证 8 行均返回 100，但仍需在本地 parquet 上复核 | **待核实（预览口径已证）** |
| **T3** | `datasets` 库能否安装 / 离线 parquet 路径能否走通 | 历史记录：`pip install datasets` 曾挂起 15 小时 | **待核实**（HF 已提供 `data/*.parquet`，可绕开） |
| **T4** | DeepSeek / GLM / Gemini 的**当日单价** | 本文档不含任何单价，全部额度是"冻结上限"；单价必须开跑当日查证并落 `PROVENANCE.md` | **待核实** |
| **T5** | Memora 部分题是否缺 `forgetting_absence` 子项 | 影响 H5 的分母 | **待核实**（克隆后统计） |
| **T6** | `gemini-2.5-flash` 等 judge 模型在本地账户是否可路由 | 决定单 judge 方案是否可行 | **待核实** |
| **T7** | A6_wrapper 在 800 题上的上下文窗口是否够 | row1 context 136k 字符 ≈ 超长，可能超窗 | **待核实** |

---

## 9. 附：本文档与既有文档的关系

| 文档 | 关系 |
|---|---|
| `total_plan/phase5_release_and_supplementary_experiments.md` §四 | **上游指令**。本文档落实其 E1/E2 与「放弃 StateMemBench」裁决，并把预算收紧到 ¥50 内 |
| `experiments_v2/README.md` | 方案设计（臂、阈值 H1–H6、模型分工）。**本篇不改其阈值**，只补 E1/E2 的落地设计 |
| `experiments_v2/PROVENANCE.md` | 数据来源与可信度标注。**本阶段新增的每个文件都要在此登记 sha256** |
| `experiments_v2/HANDOFF.md` | 交接与踩坑。其 §4.2 的「`e1_mab_cr.py` 尚未编写」与 §7 的 ¥45–110 预算由本文档接续/修正 |
| `benchmarks/CONTRACT.md:428` | 阶段一「不使用 StateMemBench」的记录；本次用 V1–V4 独立复核，结论从"零预算无网络所以不用"升级为"**该基准不可得，故永远不用**" |
