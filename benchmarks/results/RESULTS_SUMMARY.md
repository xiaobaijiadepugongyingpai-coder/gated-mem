# Gated-Mem 阶段一 · Spike Cut #1 三分支消融结果汇总

- **契约**：`benchmarks/CONTRACT.md` v1.0.0
- **数据集**：`benchmarks/data/eval_cases_40.json`，171617 bytes
  - `dataset_sha256 = 8ec9e4053143d40c16b48d4ef6a96a024ee4e65d7ec7135e8cfc6308f6fd5c5b`
- **运行器**：`benchmarks/spike_cut1.py`（--self-test 8/8 PASS）
- **样本量**：40 组 × 3 类探针 × 3 分支 = **360 条 run**
- **门禁口径**：只按全量 40 组计算（`cases_total = 40`，`probes_per_branch = 120`）

---

## 1. 三分支 × 三探针 准确率九宫格

| 分支 | current_state | anti_trap | evolution_why |
| :--- | ---: | ---: | ---: |
| **A**（纯向量基线） | 8/40 = **20.00%** | 40/40 = **100.00%** | 0/40 = **0.00%** |
| **B**（v2.0 强连坐） | 37/40 = **92.50%** | 8/40 = **20.00%** | 40/40 = **100.00%** |
| **C**（v2.1.1 终审） | 40/40 = **100.00%** | 40/40 = **100.00%** | 40/40 = **100.00%** |

> `rate = passed / total`，total 恒为 40。全部数值可由 `raw_runs.json` 逐条反查；已用独立脚本重算 `per_branch_probe` 与 `by_group`，与 `metrics.json` **完全一致**。

### 1.1 分组明细（仅供参考，不参与门禁）

| 分组 | 分支 | current_state | anti_trap | evolution_why |
| :--- | :--- | ---: | ---: | ---: |
| control（8 组） | A | 8/8 = 100.00% | 8/8 = 100.00% | 0/8 = 0.00% |
| control（8 组） | B | 8/8 = 100.00% | 8/8 = 100.00% | 8/8 = 100.00% |
| control（8 组） | C | 8/8 = 100.00% | 8/8 = 100.00% | 8/8 = 100.00% |
| non_control（32 组） | A | 0/32 = 0.00% | 32/32 = 100.00% | 0/32 = 0.00% |
| non_control（32 组） | B | 29/32 = 90.63% | 0/32 = 0.00% | 32/32 = 100.00% |
| non_control（32 组） | C | 32/32 = 100.00% | 32/32 = 100.00% | 32/32 = 100.00% |

**控制组设计验证成功**：A 分支在 8 组控制组上 current_state 全部通过（8/8），证明 A 的失败并非必然，而是被“新旧并存”这一具体机制打出来的。

---

## 2. 门禁结论（三项全过）

| 门禁 | 判据 | 实测 | 结论 |
| :--- | :--- | :--- | :---: |
| **G1** current_state 领先 | `rate(C) - rate(A) >= 0.20` | A = 20.00%，C = 100.00%，**delta = +80.00pp** ≥ 20pp | **PASS** |
| **G2** anti_trap C 优于 B | `rate(C) > rate(B)`（严格大于） | B = 20.00%，C = 100.00%，**+80.00pp** | **PASS** |
| **G3** evolution_why 达标 | `rate(C) >= 0.85` | C = **100.00%** ≥ 85% | **PASS** |

### `gate1_overall_pass = true`

> 门禁结果为契约机械判定的原始输出，未做任何阈值、口径或数据集的调整。

---

## 3. 关键观察

### 3.1 B 分支 anti_trap 掉了多少 pp —— 掉了 **80.00pp**

- B 从 A 的 100.00% 掉到 **20.00%**，是三个分支里唯一出现“负收益”的格子。
- 掉分全部集中在 **32 个非控制组**（0/32），8 个控制组全部保留（8/8）。
- **失分机制**：`expect_survive` 靶子 `M2` 挂在被覆盖的旧决策 `M1` 之下。B 的传递闭包把 `M1` 的全部子孙标 `superseded`，`M2` 因此从检索候选集中消失（`missing_survive = ["M2"]`），判定直接判负，与正文内容无关。
- **控制组为什么能过**：控制组的 `M2` 是根节点（`parent_ids` 为空），不处于任何被覆盖节点的下游，连坐链条够不到它。这正是负控制组要证明的事——B 的失败来自机制，而非实现。
- 结论：**强连坐（ψ 已物理砍除、仅保留状态标杀）在“规范节点挂在旧决策下”这一常见拓扑上造成 80pp 净损失**，C 的“只打标签不杀”路线被这条对照直接验证。

### 3.2 A 分支 current_state 为什么失败 —— 32/32 非控制组全灭

- 根因单一且彻底：**A 分支不做槽位覆盖，所有节点恒 active**。新旧同槽节点（旧 `M1` 与新 `M4`）同时进入候选集，且旧节点内容里含被淘汰的技术词。
- 统计证据：`must_exclude` 词在 `injected_text` 中的命中次数按分支为 **A = 32 次、B = 0 次、C = 0 次**。A 是唯一发生“事实污染”的分支。
- 典型样例（S01）：`hit_exclude = ["MySQL"]`，注入正文同时含 "MySQL 8.0" 与 "PostgreSQL 16"，模型无法判断哪个是当前状态。
- 为什么恰好 20.00%：8 个控制组的 `must_exclude` 按契约留空（`must_exclude = []`），A 因此天然通过；32 个非控制组无一幸免。`20.00% = 8/40` 完全由控制组比例决定，不是能力分布。
- A 的 `evolution_why` 为 **0.00%（0/40）**：A 从不记录 `residual_diff`，`returned_diff` 恒为空，`diff_empty = True` 出现 **40 次**（B/C 均为 0 次）。这是 §5.3 明写的设计意图，不是 bug。

### 3.3 C 分支 evolution_why 具体失分在哪几组 —— **没有失分组，40/40**

- `C.evolution_why = 100.00%`，`diff_empty = True` 在 C 分支出现 **0 次**，`missing_include` 与 `old_keyword` 缺失均为 0 次。
- 得分路径：C 在覆盖时把 `[Replaced: 旧subject / 旧content[:30]] + 原始原因` 写入新节点 `residual_diff`；§4 的 `retrieval_text` 在 B/C 分支拼上 `residual_diff`，使该节点被检索命中；§5.2 的回执通道再把 `residual_diff` 送进 `returned_diff`。旧技术词（`old_keyword`）因此稳定出现在回执里。
- 双通道隔离已验证：`must_exclude` 词在 C 的 `injected_text` 中命中 **0 次**——`[Replaced: … MySQL …]` 只走回执、不进正文，C 没有死在自己的核心卖点上。

---

## 4. 失败 case 完整清单（107 条 run 判负）

### 4.1 A 分支 · current_state · 32 条（全部非控制组）

`S01 S02 S03 S04 S05 S06 S07 S09 S10 S11 S12 S14 S15 S16 S18 S19 S20 S22 S23 S25 S26 S27 S28 S30 S31 S32 S33 S35 S36 S37 S38 S40`

失败原因统一为 **`hit_exclude` 命中**（`missing_include` 恒为空）。被命中的旧技术词：

| 技术词 | 命中组 | 技术词 | 命中组 |
| :--- | :--- | :--- | :--- |
| MySQL | 3（S01/S11/S31） | Guava | 2（S09/S19） |
| Memcached | 4（S02/S12/S22/S32） | Jenkins | 4（S10/S20/S30/S40） |
| webpack | 3（S03/S23/S33） | Swarm | 4（S05/S15/S25/S35） |
| Selenium | 2（S04/S14） | StatsD | 4（S06/S16/S26/S36） |
| SOAP | 3（S07/S27/S37） | ModSecurity | 3（S18/S28/S38） |

### 4.2 A 分支 · evolution_why · 40 条（全部，含控制组）

`S01–S40`（连续 40 组全负）

失败原因：`detail.diff_empty = True`，`returned_diff` 为空字符串。A 分支按 §2 一律不记录 `residual_diff`，故 `returned_diff` 恒空——**契约设计意图，非缺陷**。

### 4.3 B 分支 · anti_trap · 32 条（全部非控制组）

`S01 S02 S03 S04 S05 S06 S07 S09 S10 S11 S12 S14 S15 S16 S18 S19 S20 S22 S23 S25 S26 S27 S28 S30 S31 S32 S33 S35 S36 S37 S38 S40`

失败原因统一为 **`missing_survive = ["M2"]`**：靶子 `M2`（变更流程规范）是旧决策 `M1` 的直接子节点，被传递闭包株连标 `superseded`，跌出 `injected_node_ids`。`missing_include` 均为空。

### 4.4 B 分支 · current_state · 3 条（非控制组）

| scenario_id | 缺失项 | 根因 |
| :--- | :--- | :--- |
| **S07** | `OpenAPI 3.0` | `M3`（文档格式偏好，挂在被覆盖的 M1 下）被连坐标死；该节点同时承载 "OpenAPI 3.0" 这一当前态事实。B 此时只剩 `M4/M5/M6` 三个 active 节点，注入集里没有它。 |
| **S19** | `MessagePack` | 同上，被株连的是 `M3`（序列化格式偏好）。 |
| **S35** | `金丝雀发布` | 同上，被株连的是 `M3`（发布节奏偏好）。 |

> 这三组同时带 `fake_conflict` 标签，其 `must_include` 跨越两个槽位（新决策 + 挂在不冲突槽位上的偏好）。B 的传递闭包把“没被覆盖的偏好节点”一并杀掉，暴露出连坐会误伤与覆盖动作无关的旁支事实。

### 4.5 C 分支 · 0 条

**C 分支占用 120 条 run，判负 0 条。**

---

## 5. 两次运行的 sha256 对照（§9 确定性硬要求）

| 文件 | 第 1 次（写入仓库） | 第 2 次（写入系统临时目录） | 结论 |
| :--- | :--- | :--- | :---: |
| `raw_runs.json` | `eaa2912707f21fe5ab898d315e331159deb59e2d78373072220288202dfd126e` | `eaa2912707f21fe5ab898d315e331159deb59e2d78373072220288202dfd126e` | **逐字节相同** |
| `metrics.json` | `b63be26227707236c46102f1492d272eb6253d76d0680e35153f786873f2ad48` | `b63be26227707236c46102f1492d272eb6253d76d0680e35153f786873f2ad48` | **逐字节相同** |

- `raw_runs.json` = 667344 bytes，`metrics.json` = 3562 bytes。
- 两个输出文件均无时间戳、主机名、耗时、绝对路径；`dataset_sha256` 由数据集原始字节计算，与文件实际 sha256 一致。

---

## 6. 结构与一致性自检

| 检查项 | 结果 |
| :--- | :---: |
| `metrics.json` 含 §8.4 全部顶层字段（8 个） | PASS |
| G1 字段 a/c/delta_pp/threshold_pp/pass 齐全，threshold_pp = 20 | PASS |
| G2 字段 b/c/pass 齐全 | PASS |
| G3 字段 c/threshold/pass 齐全，threshold = 0.85 | PASS |
| cases_total = 40，probes_per_branch = 120 | PASS |
| runs 共 360 条，顺序 = branch(A,B,C) → scenario_id → probe_index | PASS |
| per_branch_probe 由 raw 独立重算一致 | PASS |
| by_group（control / non_control）由 raw 独立重算一致 | PASS |
| must_exclude 词在 injected_text 命中：A=32 / B=0 / C=0 | 双通道隔离成立 |
| diff_empty = True：A=40 / B=0 / C=0 | 与 §5.3 设计一致 |

---

## 7. 诊断与诚实边界（必读）

门禁三项全部通过，但以下四点必须在阶段二引用本结果前知晓，**不得据此推断 SOTA 或外推**：

### 7.1 C 的 100.00% 存在结构性乐观偏差（非造假，但不可外推）

C 在三类探针上全部满分，经逐条取证确认判定路径真实有效（`injected_text` 确含 "PostgreSQL"、`returned_diff` 确含 "MySQL"，不是判据被绕过）。但满分与下列数据特征强相关：

1. **单一必须排除词**：40 组 current_state 的 `must_exclude` 词数分布为 {0, 1}——要么空（8 组控制组），要么恰好 1 个词。C 只需让**一个**旧节点 superseded 即可清空该词。
2. **模板高度同构**：40 组共用同一事件骨架（M1 旧决策 / M2 规范 / M3 偏好 / M4 新决策 / M5 凭据 / M6 观察），覆盖点、父边拓扑、探针结构全部一致。C 在一种拓扑上满分，不代表在其他拓扑上同样成立。
3. **无“旧词游离于未覆盖节点”的场景**：若某个 must_exclude 旧技术词同时出现在一个**不参与覆盖**的旁支节点 content 中，C 的 superseded 机制清不掉它，current_state 会失败。本次数据集中不存在该类用例。

### 7.2 B 的 80pp 损失同样被数据构造放大

- 数据集中共有 **27 处**“覆盖事件发生之后才挂到被覆盖旧节点上”的节点，这些节点天然构成 B 传递闭包的靶子。anti_trap 的 `expect_survive` 靶子 `M2` 在 32 个非控制组里全部是 `M1` 的直接子节点。
- 该构造符合真实场景（规范确实常挂在决策之下），但也意味着 B 的 20.00% 是**该拓扑下的**结果，不能读作“强连坐在任何情况下的准确率”。

### 7.3 哪些是契约设计、哪些是机制问题

| 现象 | 性质 | 说明 |
| :--- | :--- | :--- |
| A evolution_why = 0.00% | **契约设计**（§5.3 明写） | A 不记录 diff，回执恒空，必然判负。不是缺陷。 |
| A current_state = 20.00% | **机制问题** | 无槽位覆盖 → 新旧并存 → must_exclude 词污染正文。A 的唯一通过项全部来自控制组。 |
| B anti_trap = 20.00% | **机制问题** | 传递闭包株连到与覆盖无关的旁支规范节点（§11 D2 已声明 ψ 砍除，此处是纯状态标杀）。 |
| B current_state = 92.50%（3 组失败） | **机制问题的旁证** | 连坐不只杀伤靶子，还连带丢失挂在旧节点上的当前态事实（S07/S19/S35）。 |
| C 三类全 100.00% | **机制有效 + 数据同构** | 判定路径真实（已取证），但覆盖面窄，见 7.1。 |

### 7.4 未做的事

- 未修改 `benchmarks/spike_cut1.py` 的任何判定逻辑、阈值或指标口径。
- 未修改数据集、未重新生成数据集。
- 未执行任何 git 命令。
- 本次只写 `benchmarks/results/` 下的三个文件（raw_runs.json、metrics.json、RESULTS_SUMMARY.md）。

---

## 8. 复现命令

```bash
python benchmarks/spike_cut1.py \
    --dataset benchmarks/data/eval_cases_40.json \
    --out-raw benchmarks/results/raw_runs.json \
    --out-metrics benchmarks/results/metrics.json
```

运行后应得到上表所列的两个 sha256；若非该值，说明数据集或运行器已被改动，应先查 dataset_sha256。
