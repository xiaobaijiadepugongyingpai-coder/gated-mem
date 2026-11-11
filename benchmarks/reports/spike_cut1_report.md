# 阶段一（首刀验证）汇总报告 · Gated-Mem v2.1.1

> 作者：Tech Lead（队长）  签发人：队长
> 契约：`benchmarks/CONTRACT.md` v1.0.0（冻结，全程未修改）
> 数据集：`benchmarks/data/eval_cases_40.json`（sha256 `8ec9e4053143d40c16b48d4ef6a96a024ee4e65d7ec7135e8cfc6308f6fd5c5b`，171617 bytes）
> 运行器：`benchmarks/spike_cut1.py`（`--self-test` 8/8 PASS）
> 样本量：40 组 × 3 类探针 × 3 分支 = **360 条 run**

---

## 1. 阶段一结论（一句话）

**门禁 1 三项全部达标（`gate1_overall_pass = true`），C 分支（v2.1.1 终审机制）在三个探针维度上均为满分且零分歧通过独立审计；但该满分的可信度受数据集同构性限制，只能作为方向性证据，不得外推为 SOTA 结论。**

| 门禁 | 判据 | 实测 | 结论 |
| :--- | :--- | :--- | :---: |
| **G1** | rate(C) − rate(A) ≥ 20pp（current_state） | 1.00 − 0.20 = **+80.00pp** | **PASS** |
| **G2** | rate(C) > rate(B)（anti_trap，严格大于） | 1.00 > 0.20（**+80.00pp**） | **PASS** |
| **G3** | rate(C) ≥ 0.85（evolution_why） | 1.00 ≥ 0.85 | **PASS** |
| **overall** | G1 ∧ G2 ∧ G3 | — | **PASS** |

独立签署：`benchmarks/results/audit_scores.json` → `gate1_signoff.overall = true`，`divergence_count = 0`（360/360），`metrics_match = true`。

---

## 2. 三分支消融数据表

### 2.1 主表（全量 40 组，rate = passed / 40）

| 分支 | current_state | anti_trap | evolution_why |
| :--- | ---: | ---: | ---: |
| **A** 纯向量基线 | 8/40 = **20.00%** | 40/40 = **100.00%** | 0/40 = **0.00%** |
| **B** v2.0 强连坐 | 37/40 = **92.50%** | 8/40 = **20.00%** | 40/40 = **100.00%** |
| **C** v2.1.1 终审 | 40/40 = **100.00%** | 40/40 = **100.00%** | 40/40 = **100.00%** |

数据来源：`benchmarks/results/metrics.json` → `per_branch_probe`。逐条可反查 `benchmarks/results/raw_runs.json`（360 条 run）。

### 2.2 分组明细（仅供参考，不参与门禁）

| 分组 | 分支 | current_state | anti_trap | evolution_why |
| :--- | :--- | ---: | ---: | ---: |
| control（8 组） | A | 8/8 = 100.00% | 8/8 = 100.00% | 0/8 = 0.00% |
| control（8 组） | B | 8/8 = 100.00% | 8/8 = 100.00% | 8/8 = 100.00% |
| control（8 组） | C | 8/8 = 100.00% | 8/8 = 100.00% | 8/8 = 100.00% |
| non_control（32 组） | A | 0/32 = 0.00% | 32/32 = 100.00% | 0/32 = 0.00% |
| non_control（32 组） | B | 29/32 = 90.63% | 0/32 = 0.00% | 32/32 = 100.00% |
| non_control（32 组） | C | 32/32 = 100.00% | 32/32 = 100.00% | 32/32 = 100.00% |

**负控制组的设计价值**：A 在 8 个控制组上 current_state 满分（8/8），证明 A 的失败不是「必然失败」，而是被「新旧并存」这一具体机制打出来的；B 在控制组上 anti_trap 也满分（8/8），证明 B 的 80pp 损失来自连坐链够不到控制组靶子（靶子为根节点），而非实现缺陷。

---

## 3. 关键发现

### 3.1 连坐确实是负收益：实测 **−80.00pp**

- B 的 anti_trap 从 A 的 100.00% 跌到 **20.00%**，是三个分支里唯一出现负收益的格子。
- 掉分全部集中在 32 个非控制组（0/32），8 个控制组全部保留（8/8）。
- 失分机制单一：`expect_survive` 靶子 `M2` 挂在被覆盖的旧决策 `M1` 之下，B 的传递闭包把 `M1` 全部子孙标 `superseded`，`M2` 从候选集消失 → `missing_survive = ["M2"]`。32/32 全部是「靶子被连坐杀死」，无一条是「没检索到」。
- 与 StateMem 论文的 −12.5pp 方向一致，但量级更大 —— 因为本数据集的 anti_trap 靶子 100% 精准踩在连坐半径正中心（32/32 是 `direct_child_of_covered`）。**这是针对性构造下的上界，不是普适代价。**

### 3.2 连坐还有契约未预期的第二类伤害：误杀「新事实的邻接上下文」

B 的 current_state 是 92.50%（37/40），三条失分 S07 / S19 / S35 缺 `OpenAPI 3.0` / `MessagePack` / `金丝雀发布`。根因不是检索质量，而是承载这些**当前态事实**的旁支节点（M3 偏好节点）也挂在被覆盖的 M1 下，被连坐一并杀掉。

契约 §2 设计 anti_trap 探针是为了捕捉「连坐误杀旧规范」，但**没预料到连坐会连正确答案的载体一起杀**。这是连坐语义本身的设计缺陷被 current_state 探针意外照到，属于阶段二的重要动机论证材料。

### 3.3 A 分支的失败模式是「事实污染」，不是「检索不准」

- 统计证据：`must_exclude` 词在 `injected_text` 中的命中次数 —— **A = 32 次、B = 0 次、C = 0 次**。A 是唯一发生事实污染的分支。
- 典型样例（S01）：注入正文同时含 `MySQL 8.0` 与 `PostgreSQL 16`，下游模型无法判断哪个是当前状态。
- A 的 20.00% 完全由控制组比例决定（8/40），不是能力分布 —— 32 个非控制组无一幸免。
- A 的 evolution_why = 0.00%：A 从不记录 `residual_diff`，`returned_diff` 恒空（`diff_empty = True` 出现 40 次）。这是契约 §5.3 明写的设计意图，不是 bug。

### 3.4 重大发现：TOPK 截断在 B/C 分支上几乎从未发生 —— 本实验测的主要是状态门控，不是检索排序

跨模型审计（gemini_audit）独立发现并经队长从 `raw_runs.json` 复核确认：

| 分支 | 每次检索的候选数分布 | 候选数 ≤ 5（未截断）的 run 数 | 真正发生截断的 run 数 |
| :--- | :--- | ---: | ---: |
| **A** | 6×108、7×12 | **0 / 120** | 120 / 120 |
| **B** | 3×69、4×27、5×24 | **120 / 120** | **0 / 120** |
| **C** | 5×108、6×12 | **108 / 120** | **12 / 120** |

- 单用例仅 6–8 条事件，覆盖/连坐后活跃节点急剧萎缩到 3–6 个，**几乎总是被全量注入**。
- 含义：排序公式 `Score = rel(q,v) · [F_t(v)]^λ` 的**筛选能力在 B/C 分支上基本没有被检验**。阶段一实质上是「图节点状态门控」的正确性验证实验，**不是**检索排序实验。
- λ 参数扫描（0.0 / 0.3 / 0.6）门禁全过，现在有了第二条解释：不是结论稳健，而是**λ 根本没有机会发挥作用**——排序没有取舍，λ 就无从影响注入集合。
- **A 分支是唯一真正发生截断的分支（120/120）**，所以 A 的 20% 里还混入了「排序筛选」的影响，与 B/C 的口径并不完全对等。

### 3.5 C 分支的 `residual_diff` 双通道设计成立

- C 的 evolution_why = 100.00%，`diff_empty` 在 C 分支出现 **0 次**。
- 得分路径：覆盖时写 `[Replaced: 旧subject / 旧content[:30]] + 原始原因` → §4 的 `retrieval_text` 在 B/C 拼上 `residual_diff` → §5.2 回执通道送进 `returned_diff` → 旧技术词稳定出现在回执里。
- **双通道隔离已验证**：`must_exclude` 词在 C 的 `injected_text` 中命中 **0 次**。`[Replaced: … MySQL …]` 只走回执、不进正文，C 没有死在自己的核心卖点上 —— 这正是上一轮最大的坑，本阶段被物理隔离。

---

## 4. 契约偏离计划书的地方及原因

| 编号 | 计划书原文 | 实际执行 | 原因 |
| :--- | :--- | :--- | :--- |
| **D1** | 双盲 LLM 裁判 | 机械判定 + Auditor 从零重写评分器交叉核对（要求零分歧）+ 5 组变异测试自证 | LLM 裁判不可复现，且违反 ¥0 预算。替代方案更强：机械判定可逐位复算，独立重写能抓实现偏差 |
| **D2** | 连坐系数 ψ=0.15 级联连乘 | B 分支实现为「子孙标 superseded」，**不存在任何 ψ 连乘** | ψ 已被终审物理砍除；B 只是对照组，用于证明连坐负收益 |
| **D3** | 使用 StateMemBench（322 probes） | 改用 40 组自造演进集 | 本阶段 ¥0、无网络。因此结论**只能**声称「在本数据集上」的方向性证据 |
| **D4** | `residual_diff` 带 `[Replaced: ` 前缀 | 数据集侧是纯自然语言原因 + 提及旧技术关键词；前缀由运行器在 C 分支运行时拼装 | 保持数据集与机制解耦，且 B 分支需要原始 diff 做对照 |
| **D5** | — | 阶段一不写任何生产代码（无 SQLite / 事件溯源 / MCP / CLI / HTML） | 遵循计划书「阶段一只做首刀验证」 |

补充：计划书 §4.7 的 `R(2H) == 0.25` 断言按终审裁决修正为 `R(2H) == (2 * 2**(1/beta) - 1)**(-beta)` 且 `> 0.25`。实测四类型为 `0.466539 / 0.482968 / 0.450959 / 0.323133`，全部 > 0.25，幂律长尾优势在单测层面被物理证明。

---

## 5. 独立审计结论

### 5.1 零分歧

| 项目 | 结果 |
| :--- | :--- |
| 核对 probe 数 | **360**（3 分支 × 40 组 × 3 探针，全量无抽样） |
| divergence_count | **0**（判定 + 注入集合 + 顺序 + 记录完整性） |
| metrics_match | **true**（整个 recomputed_metrics 深比较相等，18 个分组格全对） |
| node_set_match | **true**（S05 / S07 / S24 三组完整重实现比对） |
| 数值层 | 1779 个 rel/f/score 三元组，最大绝对偏差 **0.000000000** |

### 5.2 审计器非空转自证

5 组变异测试全部被抓到：翻转 verdict → 1 条 divergence；反转注入顺序 → 1 条；删 run → 1 条；只改 metrics rate → `metrics_match = false`。且 `gate1_signoff.overall` 同步翻 false。

### 5.3 跨模型复核（gemini_audit / antigravity-gemini-3.8-flash）

由于 auditor2 与 kernel 同为 `deepseek-v4.1-flash`，为补上制衡，追加了一次**异模型黑盒复核**（`benchmarks/reports/audit_crosscheck_gemini.md`）：

- 独立复算 9 格 + 18 个分组格，与 `metrics.json` **逐格一致**；
- 360 条 run 逐条比对，`verdict` 与 `injected_node_ids`（含顺序）**360/360 一致**，`divergence_count = 0`；
- 三项门禁 + overall **PASS**；
- **独家发现**：TOPK 截断在 B/C 上几乎从未发生（见 §3.4），auditor2 漏掉了这一机制事实。

**签署：同意放行门禁 1，附带阶段二 3 项 P0 整改约束（见交接文档 §5.4）。**

### 5.4 审计发现的覆盖缺口（阶段二必须处理）

| 编号 | 问题 | 影响 |
| :--- | :--- | :--- |
| **AMB-3** | B 分支的「传递闭包」**完全没被验证**：40 组连坐深度恒为 1（被覆盖节点子孙 59 个，孙辈 0 个）。改成「只标直接子节点」后 0/120 差异、准确率一模一样 | 契约 §2 加粗强调的特性在数据上零覆盖 → 阶段二需补三代演进用例 |
| **AMB-4** | C 分支的 `stale_parent_warning` 打了 59 个标签，但**从未出现在任何产物文件** | 纯内部状态，对外不可观测 → 契约 1.0.1 建议在 raw_runs 补字段 |
| **AMB-2** | B 的连坐是「覆盖瞬间快照」还是「持续传染」，契约未排除后者。数据中有 27 处相关结构，但均不承载判据 | 实测 0/120 差异，但契约文字有漏洞 |
| **AMB-1** | 排序键用原始浮点还是舍入后值 | 两侧独立选了同一读法，实测无差 → 契约 1.0.1 建议明确 |
| **AMB-7** | 同槽多旧节点时 `old` 的选取时机 | 每组件恰 1 次覆盖，该路径未被数据触发 |

---

## 6. 必须写进 README 的诚实边界

1. **C 的 100.00% 有结构性乐观偏差**：40 组共用同一事件骨架；`must_exclude` 词数分布仅 {0,1}；不存在「旧词出现在未覆盖旁支节点」的用例 —— 那种情况下 C 的 superseded 机制清不掉该词。**不可外推为 SOTA。**
2. **B 的 80pp 损失同样被构造放大**：数据集有 27 处「覆盖之后才挂到被覆盖旧节点」的旁支，天然是闭包靶子；anti_trap 靶子 100% 精准踩在连坐半径正中心。正确表述是「**在本数据集这个针对性构造下**，B 的连坐负收益是 80pp」。
3. **参数稳健性双向解读**：TOPK ∈ {3,4,5,6,8}、γ ∈ {0, 0.2, 0.5}、λ ∈ {0, 0.3, 0.6} 共 10 种组合下门禁全过。既是稳健性证据，也说明**本数据集对参数几乎没有区分力，天花板效应明显**。
4. **性质划分**：A evolution_why = 0 是契约设计意图；A current_state、B anti_trap、B current_state 是机制问题；C 全绿是「机制有效 + 数据同构」共同作用。

---

## 7. 复现命令

```bash
# 1. 生成数据集（确定性，连跑两次字节相同）
python benchmarks/tools/build_dataset.py --out benchmarks/data/eval_cases_40.json

# 2. 九条硬约束校验（退出码 0 = 全 OK）
python benchmarks/tools/validate_dataset.py --dataset benchmarks/data/eval_cases_40.json

# 3. 运行器自检（8/8 PASS）
python benchmarks/spike_cut1.py --self-test

# 4. 正式跑分
python benchmarks/spike_cut1.py --dataset benchmarks/data/eval_cases_40.json \
    --out-raw benchmarks/results/raw_runs.json \
    --out-metrics benchmarks/results/metrics.json

# 5. 独立复算（零分歧验证）
python benchmarks/audit/independent_scorer.py \
    --dataset benchmarks/data/eval_cases_40.json \
    --raw benchmarks/results/raw_runs.json \
    --out benchmarks/results/audit_scores.json
```

环境：Windows + Python 3.9.13，仅标准库，零第三方依赖，零网络调用。

确定性验证：两次运行 `raw_runs.json` sha256 = `eaa2912707f21fe5ab898d315e331159deb59e2d78373072220288202dfd126e`（逐字节相同），`metrics.json` sha256 = `b63be26227707236c46102f1492d272eb6253d76d0680e35153f786873f2ad48`（逐字节相同）。

---

## 8. 交付物清单

| 路径 | 负责人 | 状态 |
| :--- | :--- | :---: |
| `benchmarks/CONTRACT.md` | Lead | ✅ 冻结 v1.0.0 |
| `benchmarks/tools/build_dataset.py` | qa | ✅ |
| `benchmarks/data/eval_cases_40.json` | qa | ✅ 171617 B |
| `benchmarks/data/eval_cases.schema.json` | qa | ✅ |
| `benchmarks/tools/validate_dataset.py` | qa | ✅ 九条全 OK |
| `benchmarks/reports/dataset_label_audit.md` | qa | ✅ |
| `benchmarks/spike_cut1.py` | kernel | ✅ 1041 行，8/8 自检 |
| `benchmarks/results/raw_runs.json` | kernel | ✅ 360 runs，667344 B |
| `benchmarks/results/metrics.json` | kernel | ✅ 3562 B |
| `benchmarks/results/RESULTS_SUMMARY.md` | kernel | ✅ |
| `benchmarks/audit/independent_scorer.py` | auditor2 | ✅ 27991 B |
| `benchmarks/results/audit_scores.json` | auditor2 | ✅ 零分歧 |
| `benchmarks/reports/audit_phase1.md` | auditor2 | ✅ 门禁签署 |
| `benchmarks/reports/audit_crosscheck_gemini.md` | gemini_audit | ✅ 异模型复核 |
| `benchmarks/reports/spike_cut1_report.md` | Lead | ✅ 本文件 |
| `docs/phase1_handoff.md` | Lead | ✅ 阶段二交接 |
