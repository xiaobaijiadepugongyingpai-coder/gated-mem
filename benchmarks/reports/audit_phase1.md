# 阶段一独立审计报告（紫军监察 / Gate 1 签署）

- **审计人**：auditor2（独立监察，降级路由 `workbuddy/deepseek-v4.1-flash`，任务书标注为 antigravity/gemini-3.8-flash 通道）
- **契约版本**：`benchmarks/CONTRACT.md` 1.0.0（冻结，未修改）
- **审计对象**：`benchmarks/results/raw_runs.json`、`benchmarks/results/metrics.json`、`benchmarks/spike_cut1.py`
- **产物**：`benchmarks/audit/independent_scorer.py`、`benchmarks/results/audit_scores.json`、本报告
- **结论一句话**：**独立复算与 kernel 零分歧（360/360 probe 全一致），metrics 逐字段相等，门禁 1 三项独立通过，签署 PASS**；但 C 分支 100% 的确立程度显著弱于数字给人的印象，见 §4 的三条诚实边界。

---

## 0. 独立性声明（审计前提）

按任务书红线：在 `benchmarks/audit/independent_scorer.py` **写完并跑出结果之前**，本人**未阅读** `benchmarks/spike_cut1.py` 的任何实现代码。期间只读过：

- `benchmarks/CONTRACT.md` 全部 12 节；
- `benchmarks/data/eval_cases_40.json`（被审计的输入数据）；
- `benchmarks/results/raw_runs.json`、`benchmarks/results/metrics.json`（被审计的输出数据）。

独立评分器落盘并跑出 `divergence_count=0` 之后，才回头阅读 `spike_cut1.py` 的 `simulate_case` / `_supersede_descendants` / `_mark_direct_children_stale` / `retrieval_text` / `rank_candidates` / `judge` 六个函数做**事后对照**（§3.3）。此顺序保证「零分歧」不是抄写结果。

可复核的独立性证据：两边实现在结构上确实不同——
- 本实现把 `covered_old_id` 记录在节点上、diff 前缀在仿真结束后统一拼装；kernel 在处理事件时**当场**拼装。
- 本实现用显式栈 + `seen` 集合做 BFS/DFS 混合的子孙闭包；kernel 用 `_children_map` 索引 + `queue.pop(0)` 的纯 BFS。
- 本实现对 `rel`/`f`/`score` 保留原始浮点用于排序、只在序列化时 round；kernel 同样保留原始值排序。两者**独立**地落到了同一读法（这本身是一个值得记录的巧合，见 §3 AMB-1）。
- 本实现的 `judge` 是三个独立 `if` 分支早返回；kernel 是单一函数内累积 detail 字典。

---

## 1. 独立复算 vs kernel 对照表

### 1.1 三分支 × 三探针准确率（全量 40 组，`rate = passed/40`）

| 分支 | current_state | anti_trap | evolution_why |
| :--- | :--- | :--- | :--- |
| **A** 纯向量基线 | 8/40 = **0.20** ✅ | 40/40 = **1.00** ✅ | 0/40 = **0.00** ✅ |
| **B** v2.0 强连坐 | 37/40 = **0.925** ✅ | 8/40 = **0.20** ✅ | 40/40 = **1.00** ✅ |
| **C** v2.1.1 终审 | 40/40 = **1.00** ✅ | 40/40 = **1.00** ✅ | 40/40 = **1.00** ✅ |

逐格 9/9 全部一致（✅ = 独立复算与 `metrics.json` 的 passed/total/rate 完全相等）。

### 1.2 三项门禁

| 门禁 | 判据 | kernel | 独立复算 | 一致 |
| :--- | :--- | :--- | :--- | :---: |
| **G1** | rate(C) − rate(A) ≥ 0.20（20pp） | 1.00 − 0.20 = **+80.00pp** PASS | 1.00 − 0.20 = **+80.00pp** PASS | ✅ |
| **G2** | rate(C) > rate(B)（anti_trap，严格） | 1.00 > 0.20 PASS | 1.00 > 0.20 PASS | ✅ |
| **G3** | rate(C) ≥ 0.85（evolution_why） | 1.00 ≥ 0.85 PASS | 1.00 ≥ 0.85 PASS | ✅ |
| **overall** | G1 ∧ G2 ∧ G3 | **true** | **true** | ✅ |

### 1.3 分组明细（contract §7 要求，仅供参考，不参与门禁）

| 组 | 分支 | current_state | anti_trap | evolution_why | 一致 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| control (8 组) | A | 8/8 = 1.00 | 8/8 = 1.00 | 0/8 = 0.00 | ✅ |
| control (8 组) | B | 8/8 = 1.00 | 8/8 = 1.00 | 8/8 = 1.00 | ✅ |
| control (8 组) | C | 8/8 = 1.00 | 8/8 = 1.00 | 8/8 = 1.00 | ✅ |
| non_control (32 组) | A | 0/32 = 0.00 | 32/32 = 1.00 | 0/32 = 0.00 | ✅ |
| non_control (32 组) | B | 29/32 = 0.90625 | 0/32 = 0.00 | 32/32 = 1.00 | ✅ |
| non_control (32 组) | C | 32/32 = 1.00 | 32/32 = 1.00 | 32/32 = 1.00 | ✅ |

18 格全部一致。**`metrics_match = true`**（比对方式是整个 `recomputed_metrics` 与 `metrics.json` 深比较，不是只比门禁）。

### 1.4 数值层

除判定与集合外，还逐节点比对了 `rel` / `f` / `score`：

- 共比对 **1779** 个（节点 × 探针 × 分支）三元组的三个数值字段；
- 最大绝对偏差 **0.000000000**（严格为 0，不是「在公差内」）；
- 说明两边浮点运算路径（`(1 + Delta/t0) ** (-beta)`、`rel * (F ** LAMBDA)`）在 IEEE-754 双精度下逐位相同。

---

## 2. Divergence 清单

### **零分歧。**

- **核对 probe 数**：`probes_checked = 360`（3 分支 × 40 组 × 3 探针），即 kernel 的 `raw_runs.json` 中全部 360 条 run，无抽样、无豁免。
- **`divergence_count = 0`**。
- 一致性判据（三条同时满足才算一致，任一不满足即计入 divergence）：
  1. `injected_node_ids` **顺序敏感**逐位相等（顺序影响 `injected_text` 拼接顺序，进而影响子串判定，因此必须比顺序而不只是比集合）；
  2. `verdict` 相等；
  3. 记录键集合双向完整——kernel 有而审计缺、审计有而 kernel 缺，都各记一条 divergence（本次两侧均为 360 条，无缺漏）。

### 2.1 审计器灵敏度自证（证明"零分歧"不是因为比较器什么都不看）

一份永远返回 0 分歧的比较器毫无价值。因此做了 5 组变异测试：把 kernel 产物人为破坏，再喂给同一份审计器。

| 变异 | 破坏内容 | divergence | metrics_match | overall | 是否被抓到 |
| :--- | :--- | :---: | :---: | :---: | :---: |
| baseline | 无 | 0 | true | true | — |
| mut_verdict_flip | 翻转第 1 条 run 的 `verdict` | **1** | true | false | ✅ |
| mut_inject_order | 反转第 8 条 run 的 `injected_node_ids` 顺序 | **1** | true | false | ✅ |
| mut_missing_run | 删除第 14 条 run | **1** | true | false | ✅ |
| mut_metrics_rate | 只改 `metrics.json` 里 C/current_state 的 rate 为 0.999 | 0（run 层无辜） | **false** | **false** | ✅ |

结论：判定层、集合层、顺序层、记录完整性、指标层五个维度，任一被破坏都会立刻反映到 `divergence_count` 或 `metrics_match`，且 `gate1_signoff.overall` 会同步翻成 false。审计器不是空转的。

---

## 3. 重实现时踩到的契约歧义点（本报告最有价值的部分）

以下每一条都是我在**只看契约文字**时无法唯一确定、必须二选一的地方。列出所选读法 + 是否影响结论。

### AMB-1（排序键：原始浮点 vs 舍入后值）——**已实测，无影响**

- **条文**：§1.6「写入 `raw_runs.json` 的 `rel`/`f`/`score` 一律 `round(x, 6)`」；§5.1「降序排序（同分按 node_id 升序）」。
- **两种读法**：(a) 用未舍入的原始浮点做排序键，只在序列化时 round；(b) 先把值 round 到 6 位，再用舍入后的值排序。
- **本实现选择**：(a)，并有 `SORT_BY_RAW` 开关可切到 (b) 复算。
- **实测**：两种口径下 360 条 probe 的 `injected_node_ids` 与 `verdict` **完全无差**（0/120 注入顺序不同、0/120 判定不同）。原因是唯一的第 5/6 名贴边情形（C 分支 12 次截断）最小分差 0.0886，远大于 1e-6 的舍入量级。
- **事后核对**：kernel 也选了 (a)（`rank_candidates` 排序用未 round 的 `item["score"]`，round 在序列化时做）。**两边独立选了同一读法**。
- **建议**：契约 1.0.1 应明确写「排序键用未舍入的原始值」。当前这行字是真实存在的漏洞，只是本数据集没踩到。

### AMB-2（B 分支连坐是"覆盖瞬间快照"还是"持续生效"）——**读法不同会改变语义，需澄清**

- **条文**：§2 表格「沿 `parent` 边把全部子孙（传递闭包）标 `superseded`」；§2.2「处理第 i 条时只能看到前 i-1 条的状态」；§2.1「然后写入新节点，status = active」。
- **两种读法**：
  - (a) **快照闭包**：在覆盖发生的那一瞬间算一次闭包，把当时已存在的子孙标掉。之后新写入的节点一律 `active`，即使它 `parent_ids` 指向一个早已 `superseded` 的节点。
  - (b) **持续传染**：一个节点只要其任一父处于 `superseded`，自身也应被视为失效；新节点挂到死父下就立刻死。
- **本实现选择**：(a)。依据是 §2.1 明说「写入新节点 status = active」且 §2.2 禁止预建图。
- **实测影响**：数据集里**确实存在** 27 处「覆盖发生后才挂到已 superseded 父节点下的新节点」（例如 S01 的 M5 挂在 M1 下，而 M1 已被 M4 覆盖），所以 (a) 与 (b) 的**图状态不同**。但我把 (b) 也完整实现并复算了 B 分支的 120 条 probe，结果：
  - B 的准确率 (a) 与 (b) **完全相同**：current_state 0.925 / anti_trap 0.20 / evolution_why 1.00；
  - 逐 probe 判定差异 **0/120**。
  - 原因：这 27 个节点挂的是「安全约束」类旁支，既不在 `expect_survive` 靶子位上，也不承载 `must_include`/`must_exclude` 关键词，因此它们死不死不影响任何判定。
- **结论**：读法 (a)/(b) 在本数据集上**不可区分**（不是因为没有这种节点，而是因为受影响节点恰好都不承载判据）。这是一个**真实存在但未被探针触及**的契约分支。
- **事后核对**：kernel 是 (a)。**两边读法一致，但契约文字没有排除 (b)**。

### AMB-3（B 的传递闭包深度是否被测到）——**重大：本数据集无法区分"全部子孙"与"仅直接子节点"**

- **条文**：§2 表格 B 分支「沿 `parent` 边把**全部子孙（传递闭包）**标 `superseded`」（契约特意加粗强调）。
- **本实现**：严格实现传递闭包（显式栈 + seen 集合）。
- **实测**：本数据集**所有 40 组的连坐深度恒为 1 层**（被覆盖节点的子节点数为 59，孙辈及以上为 **0**）。也就是说：把 B 分支实现成"只标直接子节点"（即 C 的连坐范围但用 superseded 语义），产出的 `injected_node_ids` 与 `injected_text` 与真正的传递闭包版本**逐 probe 100% 相同（0/120 差异）**，三格准确率也完全相同（0.925 / 0.20 / 1.00）。
- **含义**：契约 §2 里被加粗强调的"传递闭包"这个设计点在**本数据集上完全没有被验证到**。B 分支的 80pp 损失**全部来自一跳连坐**，与"传递"无关。kernel 的实现正确，但**数据没有测到它**。这不是 kernel 的错，是数据集构造的覆盖缺口。建议阶段二补一组"覆盖节点 → 子 → 孙"的三代用例。

### AMB-4（C 分支"直接子节点"的作用域）——读法不同稍有差异，未触发

- **条文**：§2 表格 C 分支「**仅直接子节点**置 `stale_parent_warning=True`，status 保持 active；孙辈不受影响」。
- **两种读法**：(a) 被覆盖**旧节点**的直接子节点；(b) 被覆盖旧节点 ∪ 新节点的直接子节点（新节点理论上不会有子节点，因为它是刚写入的）。
- **本实现选择**：(a)。实测 (a)/(b) 在本数据集上等价（新节点写入时无子节点）。
- **附带发现**：`stale_parent_warning` 这个 C 分支的招牌产物**从未出现在任何输出文件里**——`raw_runs.json` 的 run 级字段只有 12 个键，没有它；`ranked` 里每个候选只有 `node_id/rel/f/score/status`，也没有它。也就是说本阶段 C 分支打的 59 个 stale 标签是**纯内部状态，对判定零贡献、对外不可观测**。这不是 bug（契约 §8.3 的 raw_runs 结构本来就没给它留字段），但意味着「C 只警告不误杀」这个卖点在本阶段**只能靠 anti_trap 的节点存活率间接体现，无法从产物直接验证**。

### AMB-5（大小写不敏感的比较基准）——已消除

- **条文**：§6「两边都 `NFKC` + `lower()` 后再比较」。
- **含糊处**：只说了"两边"，没说 `injected_text` 整体也要 NFKC 还是只对被比较子串 NFKC。
- **本实现**：对 haystack 和 needle **都**做 NFKC + lower（`contains_ci`）。
- **实测**：本数据集所有 `must_include`/`must_exclude`/`old_keyword` 均为纯 ASCII 或纯中文，NFKC 不改变任何字符，因此两种读法**无差**。

### AMB-6（`returned_diff` 空值语义）——已消除

- **条文**：§5.2「`returned_diff = "\n".join(v.residual_diff for v in injected if v.residual_diff)`」。
- **含糊处**：全部候选都无 diff 时，是 `""` 还是 `None`？§6 的 `evolution_why` 判据写「`returned_diff` 非空」。
- **本实现**：空串 `""`。与 §8.3 示例（`"returned_diff": ""`）一致。
- **实测**：A 分支 40/40 全空，两种表示在 `bool()` 下等价，无差。

### AMB-7（多旧节点同槽时 `old` 的选取时机）——本数据集未触发

- **条文**：§2.1「若存在多个，取 `node_id` 字典序最小的那一个作为 `old`；**实际规则**：凡是同槽且 active 的旧节点，**全部**被标 `superseded`」。
- **含糊处**：`old` 的候选池是"覆盖瞬间同槽 active 的节点"还是"历史上所有同槽节点"？若某个同槽节点在更早的覆盖里已被标 superseded，它还能当 `old` 吗？
- **本实现**：(a) 覆盖瞬间 active 的那批里取最小。
- **实测**：本数据集每组**恰好只发生 1 次覆盖**（40 组覆盖次数全为 1），**从未出现"同槽多旧节点"**（`multi_old = 0`），该分支未被触发。
- 注：t3 报告称用自检微用例验证过「M1 < M2 前缀取 M1」，但那是在合成数据上；**真实数据集完全没走到这条路径**。该规则目前只有单测覆盖，没有数据覆盖。

### 歧义汇总

| 编号 | 歧义点 | 是否影响本次结论 | 契约 1.0.1 是否需要修订 |
| :--- | :--- | :---: | :---: |
| AMB-1 | 排序键用原始值还是舍入值 | 否（实测无差） | 建议明确 |
| AMB-2 | B 连坐是快照还是持续 | 否（27 处存在但均不承载判据） | 建议明确 |
| AMB-3 | 传递闭包深度未被测到 | **否（但暴露覆盖缺口）** | 数据层面需补用例 |
| AMB-4 | C 的 stale 标签不可观测 | 否 | §8.3 可考虑加字段 |
| AMB-5 | NFKC 作用范围 | 否 | 不必 |
| AMB-6 | returned_diff 空值表示 | 否 | 不必 |
| AMB-7 | 多旧节点 old 的选取时机 | 否（每组恰 1 次覆盖，未触发） | 建议明确 |

---

## 4. 对三分支机制的独立判断

### 4.1 B 分支连坐的负收益：在本数据集上为 **80.00pp**（anti_trap 格）

- 数字：B 的 anti_trap = 0.20，C 的 anti_trap = 1.00，差 **80.00pp**（G2 判据）。
- **机制核验**：B 的 32 条 anti_trap 失败，我逐条确认全部是同一个原因——`expect_survive` 指向的靶子节点在 B 分支里 `status != active` 被剔除出候选集，导致 `missing_survive` 非空。**32/32 都是"靶子被连坐杀死"**，没有一条是"没检索到"或"must_include 缺失"。这证明负收益的来源纯粹是连坐语义，不是检索质量。
- **但 80pp 需要打折看**（这是我认为必须写明的）：
  - 数据集里 **anti_trap 靶子 100% 被放在"被覆盖节点的直接子节点"位置**（32 个非控制组全部如此：`direct_child_of_covered = 32`，控制组 8 个则是 `not_under_covered`）。这是一个**最不利于 B 的极端构造**——靶子精准踩在连坐半径的正中心。
  - 若靶子放在被覆盖节点的**兄弟**位置、或挂在未被覆盖的根下，B 的 anti_trap 会立刻回到接近 1.0。
  - 因此正确的表述是：**"在本数据集这个针对性构造下，B 的连坐负收益是 80pp"**，而不是"连坐的普适代价是 80pp"。t4 报告 §7 已经诚实声明了这一点，我独立核验后**同意该声明**。

### 4.2 B 的 3 条 current_state 失分（0.925 而非 1.0）——契约未预期的**真缺陷**

- 三条：S07 缺 `OpenAPI 3.0`、S19 缺 `MessagePack`、S35 缺 `金丝雀发布`。
- **机制**：这三组里 `must_include` 的承载节点（M3 之类的旁支节点）挂在**被覆盖节点**之下，B 的连坐把它一起标了 superseded，于是候选集里没有它，`must_include` 落空。
- **我的判断**：这**不是** kernel 的 bug（kernel 严格按 §2 实现），也**不是**数据集的 bug（数据符合 §3.5 九条硬约束）。这是**连坐语义本身的设计缺陷被 current_state 探针意外照到**——契约 §2 只想着「连坐会让规范节点消失（anti_trap 捕捉）」，没想过「连坐也会让**本轮正确答案的载体**消失」。这是一个有价值的真实发现，建议写进阶段二的动机论证里：连坐不只误杀旧规范，还会误杀**新事实的邻接上下文**。
- 附带：B 的 current_state 0.925 已经**低于 C 的 1.0**，所以即使 G1 用 B 来比也照样通过（+7.5pp 不够 20pp 阈值，但方向一致）。

### 4.3 C 分支的满分：**是"数据构造 + 机制"共同作用，不能单独归功于机制**

这是我对本次结果最重要的一条独立判断。

**支撑 C 满分的三个必要条件，本数据集全部满足了：**

| 条件 | 本数据集实测 | 若换成另一种构造会怎样 |
| :--- | :--- | :--- |
| ① `must_exclude` 的旧技术词**全部**落在"必被覆盖"的节点上 | **成立**：40 组 current_state 里，所有 `must_exclude` 词在 C 分支的 active 节点中出现次数 = **0** | 若旧词出现在一个**未被覆盖**的旁支节点（如"我们以前也考虑过 MySQL，但那是另一个服务"），C 会在 current_state 上失分，因为 C 只覆盖同槽，不覆盖语义相关 |
| ② `must_include` 的新事实**全部**在 active 节点上 | **成立**：0 个反例 | 若新事实写在被覆盖节点的子节点里（B 的三条失分正是这种结构），C 能过是因为 C 不杀子节点；但若新事实写在一个被误判为同槽的节点上，C 也会杀 |
| ③ `must_exclude` 词数分布极窄 | **只有 {0,1} 两档**：32 组是 1 个词、8 个控制组是 0 个词 | 没有"2 个旧词分处不同槽"的用例，无法检验 C 在多旧词场景下是否漏覆盖 |

**结论**：C 的 1.00 / 1.00 / 1.00 是**必要条件全部被数据构造满足**的结果，而不是"机制在任意演化场景下都满分"。**C 的失分不是"真缺陷"——在本数据集上它确实没有失分；但"不失分"的可信度受限于数据同构**（40 组共用同一事件骨架、must_exclude 至多 1 词、无"旧词游离于未覆盖节点"用例、无三代演进）。t4 报告已声明这一点，我**独立复核后确认该声明属实且必要**，并在此补充一条它没说的：**连 B 与 C 的区分度也依赖构造**——见 AMB-3，本数据集连"传递 vs 一跳"都分不开。

**因此我拒绝把这个结果表述为"v2.1.1 优于 v2.0"的普适结论。**正确表述是：**在本 40 组同构构造上，槽位覆盖 + 不连坐（C）相比纯向量（A）在 current_state 上 +80pp、相比强连坐（B）在 anti_trap 上 +80pp，方向明确、机制可解释、数字可复现；但绝对水平受数据集构造强烈支撑，阶段二必须用非同构数据重测。**

### 4.4 参数稳健性（补充自查，非任务要求）

用独立评分器做了参数敏感性扫描，确认结论不是参数碰巧凑出来的：

| 改动 | A/cs | B/at | C/cs | C/at | C/ew | 三門禁 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 基线 TOPK=5, γ=0.2, λ=0.3 | 0.200 | 0.200 | 1.000 | 1.000 | 1.000 | 全过 |
| TOPK=3 | 0.325 | 0.200 | 0.925 | 1.000 | 1.000 | 全过 |
| TOPK=4 / 6 / 8 | 0.200 | 0.200 | 1.000 | 1.000 | 1.000 | 全过 |
| γ=0.0 / 0.5 | 0.200 | 0.200 | 1.000 | 1.000 | 1.000 | 全过 |
| λ=0.0 / 0.6 | 0.200 | 0.200 | 1.000 | 1.000 | 1.000 | 全过 |
| 排序键改舍入后值 | 0.200 | 0.200 | 1.000 | 1.000 | 1.000 | 全过 |

门禁在全部 10 种参数组合下都通过，说明结论对 TOPK / GAMMA / LAMBDA / 排序口径**不敏感**——这既是好消息（结论稳健），也是警示（**说明本数据集对参数几乎没有区分力，天花板效应明显**）。TOPK=3 时 A 的 current_state 反而升到 0.325（挤掉了一个旧节点），但 G1 仍过（+60pp）。

---

## 5. 门禁 1 签署

### 5.1 逐项签署

| 门禁 | 判据 | 独立复算值 | 结论 |
| :--- | :--- | :--- | :---: |
| **G1** | `rate(C) - rate(A) >= 0.20`（current_state ≥ 20pp） | C=1.00, A=0.20, **delta = +80.00pp** | **PASS** |
| **G2** | `rate(C) > rate(B)`（anti_trap，严格大于） | C=1.00, B=0.20, **1.00 > 0.20** | **PASS** |
| **G3** | `rate(C) >= 0.85`（evolution_why） | C=1.00, **1.00 ≥ 0.85** | **PASS** |

### 5.2 总签署

```
gate1_signoff:
  G1:      true
  G2:      true
  G3:      true
  overall: true          ← PASS
  signed_by: auditor2 / gemini-3.8-flash
```

- **`divergence_count = 0`**（360/360 probe 全一致，含注入集合、顺序、判定）
- **`metrics_match = true`**（整个 metrics 深比较相等，18 个分组格全对）
- **`node_set_match = true`**（S05 / S07 / S24 三组 × 三分支 × 三探针的候选集合、状态、注入集合全一致）

### 5.3 签署理由（一句话）

**独立从零重写的评分器在 360 条 probe 上与 kernel 零分歧、数值层最大偏差 0.000000000、整个 metrics 逐字段相等，且该比较器经 5 组变异测试证明非空转；因此三项门禁按独立复算值均成立，签署 PASS。**

### 5.4 签署的效力边界（诚实声明，签署不覆盖以下内容）

本签署**仅**证明：「在 `eval_cases_40.json` 这份数据上，kernel 的实现与契约 1.0.0 的文字一致，且独立复算得到相同的门禁结论」。它**不**证明：

1. 三分支机制在**非同构数据**上仍然成立（见 §4.3 三个必要条件）；
2. B 分支"传递闭包"这个设计点被验证到了（见 AMB-3，深度恒为 1）；
3. C 的 100% 可外推为 SOTA（契约 §11 D3 已明确禁止，我附议）；
4. `stale_parent_warning` 这个 C 的招牌产物在产物链路中可见（见 AMB-4，它从未落盘）。

**不建议**因上述边界拒签——拒签的判据是「独立复算与 kernel 不一致」，本次为 0。这些问题应作为**阶段二的任务输入**，而不是阶段一的门禁阻断。

---

## 6. 附录：复现命令与文件指纹

### 6.1 复现命令

```bash
# 独立复算（任意工作目录可运行）
python benchmarks/audit/independent_scorer.py \
    --dataset benchmarks/data/eval_cases_40.json \
    --raw benchmarks/results/raw_runs.json \
    --out benchmarks/results/audit_scores.json

# 可选：指定 metrics 路径与抽样 case
python benchmarks/audit/independent_scorer.py \
    --dataset benchmarks/data/eval_cases_40.json \
    --raw benchmarks/results/raw_runs.json \
    --metrics benchmarks/results/metrics.json \
    --retrace-cases S05,S07,S24 \
    --out benchmarks/results/audit_scores.json
```

`--help` 可用；退出码 0。

### 6.2 文件指纹（sha256）

| 文件 | 大小 (B) | sha256 |
| :--- | ---: | :--- |
| `benchmarks/CONTRACT.md` | 21542 | `8539bfc377f09111e43a0b4070931c4b5a8bdbf88b8e78ae214a7c9a9655c518` |
| `benchmarks/data/eval_cases_40.json` | 171617 | `8ec9e4053143d40c16b48d4ef6a96a024ee4e65d7ec7135e8cfc6308f6fd5c5b` |
| `benchmarks/spike_cut1.py` | 37399 | `75d97eb19d29edf05ec11b7e7cad254c0ce534d968488d3b12617c37f3e4ff72` |
| `benchmarks/results/raw_runs.json` | 667344 | `eaa2912707f21fe5ab898d315e331159deb59e2d78373072220288202dfd126e` |
| `benchmarks/results/metrics.json` | 3562 | `b63be26227707236c46102f1492d272eb6253d76d0680e35153f786873f2ad48` |
| `benchmarks/audit/independent_scorer.py` | 27991 | `dadb028336ca3f9d5f57deba49a50b2b90ced71b407459317783fdfb4a4cb0a2` |
| `benchmarks/results/audit_scores.json` | 5111 | `e4840da5b37202b66b8f456a690aec58e4212805343ddd119c01f7979d3d88b2` |

数据集 sha256 与 t2 交接的最终版一致（`8ec9e405…`），说明审计跑的是最终数据，不是 t1 的旧版。

### 6.3 确定性验证

`audit_scores.json` 连跑两次（仓库内路径 + 系统临时目录路径）**逐字节相同**：
`e4840da5b37202b66b8f456a690aec58e4212805343ddd119c01f7979d3d88b2`（两处一致）。
产物内无时间戳、无主机名、无绝对路径、无运行耗时，符合契约 §9。

### 6.4 工程纪律自查

- ✅ 仅新增 `benchmarks/audit/independent_scorer.py`、`benchmarks/results/audit_scores.json`、`benchmarks/reports/audit_phase1.md` 三个文件；
- ✅ 未修改 `benchmarks/data/`、`benchmarks/spike_cut1.py`、`benchmarks/results/raw_runs.json`、`benchmarks/results/metrics.json`、`benchmarks/CONTRACT.md` 中任何既有文件；
- ✅ 未执行任何 `git` 命令；
- ✅ 纯标准库（`argparse` `hashlib` `json` `math` `os` `re` `sys` `unicodedata` `typing`），Python 3.9.13 实跑；
- ✅ 无 `random` / `time` / `os.environ` 影响输出；所有排序显式 `sorted()` 或 `list.sort(key=...)`；
- ✅ 临时文件已清理。

---

*本报告由 auditor2 独立撰写。签署结论基于独立复算，而非采信 kernel 的自述。*
