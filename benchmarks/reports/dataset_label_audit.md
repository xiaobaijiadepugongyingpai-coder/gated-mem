# benchmarks/reports/dataset_label_audit.md — 数据集标签复核报告（阶段一 / Spike Cut #1）

> **作者**：qa（红军出题官）
> **复核对象**：`benchmarks/data/eval_cases_40.json`（`sha256 = 8ec9e4053143d40c16b48d4ef6a96a024ee4e65d7ec7135e8cfc6308f6fd5c5b`，171,479 bytes）
> **判据**：`benchmarks/CONTRACT.md` §3.5（九条硬约束，冻结版本 1.0.0）
> **工具**：`benchmarks/tools/validate_dataset.py`（退出码 0，九条全 OK，警告 0 条）
> **结论**：**复核通过**，数据集可交付 kernel 做三分支消融。

---

## 1. (a) 40 行逐组复核表

列说明：覆盖事件数按 §2.1 槽位三元组规则模拟得出（`新←旧`）；"靶子"指 anti_trap 探针的 `expect_survive`；"—"表示该项为空（控制组无 must_exclude / 表格列空）。

| scenario_id | domain | 控制组 | 覆盖事件数 | 覆盖对 | anti_trap 靶子 | current_state must_exclude | evolution_why old_keyword | 标签 |
|---|---|---|---|---|---|---|---|---|
| S01 | db | 否 | 1 | M4←M1 | M2 | MySQL | MySQL | evolution |
| S02 | auth | 否 | 1 | M4←M1 | M2 | Memcached | Memcached | evolution |
| S03 | frontend | 否 | 1 | M4←M1 | M2 | webpack | webpack | evolution |
| S04 | testing | 否 | 1 | M4←M1 | M2 | Selenium | Selenium | evolution |
| S05 | deploy | 否 | 1 | M4←M1 | M2 | Swarm | Swarm | evolution, multi_parent |
| S06 | observability | 否 | 1 | M5←M1 | M2 | StatsD | StatsD | evolution, scope_isolation |
| S07 | api | 否 | 1 | M4←M1 | M2 | SOAP | SOAP | evolution, fake_conflict |
| S08 | security | **是** | 1 | M3←M1 | M2 | — | logfmt | control |
| S09 | cache | 否 | 1 | M4←M1 | M2 | Guava | Guava | evolution |
| S10 | build | 否 | 1 | M4←M1 | M2 | Jenkins | Jenkins | evolution |
| S11 | db | 否 | 1 | M4←M1 | M2 | MySQL | MySQL | evolution |
| S12 | auth | 否 | 1 | M4←M1 | M2 | Memcached | Memcached | evolution |
| S13 | frontend | **是** | 1 | M3←M1 | M2 | — | Fluentd | control |
| S14 | testing | 否 | 1 | M4←M1 | M2 | Selenium | Selenium | evolution |
| S15 | deploy | 否 | 1 | M4←M1 | M2 | Swarm | Swarm | evolution, multi_parent |
| S16 | observability | 否 | 1 | M5←M1 | M2 | StatsD | StatsD | evolution, scope_isolation |
| S17 | api | **是** | 1 | M3←M1 | M2 | — | CSV | control |
| S18 | security | 否 | 1 | M4←M1 | M2 | ModSecurity | ModSecurity | evolution |
| S19 | cache | 否 | 1 | M4←M1 | M2 | Guava | Guava | evolution, fake_conflict |
| S20 | build | 否 | 1 | M4←M1 | M2 | Jenkins | Jenkins | evolution |
| S21 | db | **是** | 1 | M3←M1 | M2 | — | gzip | control |
| S22 | auth | 否 | 1 | M4←M1 | M2 | Memcached | Memcached | evolution |
| S23 | frontend | 否 | 1 | M4←M1 | M2 | webpack | webpack | evolution |
| S24 | testing | **是** | 1 | M3←M1 | M2 | — | JUnit | control |
| S25 | deploy | 否 | 1 | M4←M1 | M2 | Swarm | Swarm | evolution |
| S26 | observability | 否 | 1 | M5←M1 | M2 | StatsD | StatsD | evolution, scope_isolation |
| S27 | api | 否 | 1 | M4←M1 | M2 | SOAP | SOAP | evolution, multi_parent |
| S28 | security | 否 | 1 | M4←M1 | M2 | ModSecurity | ModSecurity | evolution |
| S29 | cache | **是** | 1 | M3←M1 | M2 | — | PagerDuty | control |
| S30 | build | 否 | 1 | M4←M1 | M2 | Jenkins | Jenkins | evolution |
| S31 | db | 否 | 1 | M4←M1 | M2 | MySQL | MySQL | evolution |
| S32 | auth | 否 | 1 | M4←M1 | M2 | Memcached | Memcached | evolution |
| S33 | frontend | 否 | 1 | M5←M1 | M2 | webpack | webpack | evolution, scope_isolation |
| S34 | testing | **是** | 1 | M3←M1 | M2 | — | JUnit | control |
| S35 | deploy | 否 | 1 | M4←M1 | M2 | Swarm | Swarm | evolution, fake_conflict |
| S36 | observability | 否 | 1 | M4←M1 | M2 | StatsD | StatsD | evolution |
| S37 | api | 否 | 1 | M5←M1 | M2 | SOAP | SOAP | evolution, scope_isolation |
| S38 | security | 否 | 1 | M4←M1 | M2 | ModSecurity | ModSecurity | evolution, multi_parent |
| S39 | cache | **是** | 1 | M3←M1 | M2 | — | YAML | control |
| S40 | build | 否 | 1 | M4←M1 | M2 | Jenkins | Jenkins | evolution |

---

## 2. (b) 九条硬约束统计汇总（校验器实测 vs 门槛）

| # | 约束 | 门槛 | 实测 | 结果 |
|---|---|---|---|---|
| 1 | case_count == len(cases) == 40，S01..S40 连续唯一 | 40 | 40，编号连续唯一零填充 | ✅ OK |
| 2 | 每组 session_events ∈ [6, 8] | 6–8 | 40 组全部 6–8（std/fake/scope/ctrl=6，multi=7） | ✅ OK |
| 3 | probes 恰好 3 条且三类各一 | 3 | 40 组 × 3 = 120 条，类型分布 40/40/40 | ✅ OK |
| 4 | domain 去重 ≥ 6 | ≥ 6 | **10** 种（api/auth/build/cache/db/deploy/frontend/observability/security/testing） | ✅ OK |
| 5 | multi_parent ≥ 3 组 | ≥ 3 | **4** 组：S05/S15/S27/S38（M7 挂 M2+M4 双亲） | ✅ OK |
| 6 | scope_isolation ≥ 4 组（含 branch:* scope + 同槽位异 scope 对 + current_state 验证跨 scope 共存） | ≥ 4 | **5** 组：S06/S16/S26/S33/S37（M3 global vs M4 branch:*，query 同时断言两侧） | ✅ OK |
| 7 | fake_conflict ≥ 2 组 | ≥ 2 | **3** 组：S07/S19/S35（同 subject 不同 predicate，如 M1"主数据库" vs M3"文档格式偏好"） | ✅ OK |
| 8 | 负控制组 ≥ 8，construction_note 说明控制目的 | ≥ 8 | **8** 组：S08/S13/S17/S21/S24/S29/S34/S39；note 均 > 10 字；覆盖 M3←M1 均不涉及靶子 M2（M2 为根节点，不在 M1 子孙传递闭包内，B 分支不会误杀） | ✅ OK |
| 9 | 引用完整性 + 覆盖事件带 residual_diff 且含旧节点技术关键词 + evolution_why 带 old_keyword 且出现在某条 diff 中 | — | 40 个覆盖事件全部带 diff（无 `[Replaced` 前缀）；关键词判据（旧 content 中长度≥3 ASCII 词）全部命中；40 条 evolution_why 的 old_keyword 全部出现在对应 diff 中 | ✅ OK |

附加 WARN 项（契约建议，不参与退出码）：40 组非控制组 current_state 的 query 全部同时提及新旧两个技术名，**0 条警告**。

---

## 3. (c) 最刁钻的 5 组及理由

1. **S06（observability / scope_isolation）**：一个 case 里同时埋了两个独立考点——(i) M3（global"采样策略=全量采样"）与 M4（branch:feat-gw-tail"采样策略=尾部采样"）构成同 subject+predicate 不同 scope 的隔离对，槽位三元组第三维不同，**任何实现若把 scope 拼错或忽略 scope 都会把 M4 覆盖进 M3**；(ii) 与此同时 M5←M1 还在做一次真正的同槽覆盖。current_state 的 must_include 同时要求"全量采样"与"尾部采样"共存，must_exclude 又排除 StatsD，分支 A 会被主槽位污染失败，分支 B/C 还要正确保留两条 scope 节点。
2. **S33（frontend / scope_isolation）**：domain 的 old_word 是小写 `webpack`，专门测试大小写不敏感子串判据与分词器（tokenize 后 `webpack` 为单 token）的一致性；同时 branch 分支名是 `feat-dark-mode`，query 中出现连字符词，检索侧若做错误规范化（如把连字符拆词）会扰动 rel 排序——这是对 §4 分词实现的最小对抗样例。
3. **S05（deploy / multi_parent）**：M7 的 parent_ids=[M2, M4]，同时挂在"靶子规范节点"与"新决策节点"之下。它使 B 分支的传递闭包计算必须处理"子孙集合的并"：M1 被覆盖后，B 的 superseded 闭包 = {M2, M3, M5, M7}——M7 既是 M2 的孩子又是 M4 的孩子，若实现把父边方向弄反或漏掉多亲并集，M7 的归属就错。这是 multi_parent 与 anti_trap 的耦合样例。
4. **S08（security / control）**：控制组却**带一次真实覆盖**（M3←M1，偏好槽位）。它的刁钻在于：A 分支在这里应当**通过**（must_exclude 为空），而覆盖又在 M1 之下没有靶子（M2 是根节点），B 的连坐不会误杀 expect_survive=M2。它专测"控制组 ≠ 无覆盖"，防止实现者偷懒把控制组当"没有任何写事件"处理；若误把 M2 挂到 M1 下，约束 8 的机械检查会立刻 FAIL。
5. **S37（api / scope_isolation）**：与 S06 同构但 domain 不同（SOAP→gRPC），witness 对是"限流策略：固定窗口 vs 滑动窗口"。旧词 `SOAP` 只有 4 个字母，且 query 里 must_include 含"固定窗口/滑动窗口"两个纯中文词——检索侧必须靠中文二元组分词命中，否则 top5 注入里排不进 M3/M4，current_state 会假阴性。它测试中文文本在 rel 排序里的真实可行性，是 G1 能不能拉开 20pp 的关键样例之一。

---

## 4. (d) 设计缺陷与不确定处（诚实清单）

1. **同槽覆盖事件数全部为 1**：40 组每组恰好一次同槽覆盖（多对覆盖、或"同槽多旧节点全被覆盖取 node_id 最小者拼 diff"的 §2.1 规则没有被任何用例触发）。覆盖规则里"多个同槽旧节点时取 node_id 字典序最小者"这条分支在阶段一数据集上是死代码。若阶段二保留该规则，建议补充多旧节点用例。
2. **模板同构性**：std/multi/scope/fake 四族共 32 组共享同一骨架（M1..M6/M7 仅换参数），组间仅在技术名词与 domain 上不同。若某分支的失败模式是"模板级"的，40 组会一起失败/通过，有效独立样本量低于名义 40。控制组 8 组使用不同骨架（PREFERENCE 槽位覆盖），部分缓解但未消除。
3. **must_exclude=旧技术词的判据对 B/C 分支的区分依赖注入通道的物理隔离**（§5.2）。本数据集的 residual_diff 一定含旧技术词（约束 9 保证），所以只要 kernel 实现 diff 混流（把 diff 拼进 injected_text），C 分支会被自己的 old_keyword 击中——这正是契约想暴露的坑，但意味着 **G1 的成败同时检验 kernel 的通道隔离正确性**，不只是检索策略差异。解读门禁结论时须注意归因。
4. **current_state 的 expect_nodes 仅复核用**：校验器不保证 expect_nodes 与真实 top5 注入一致。若某组 expect_nodes 与 TOPK=5 实际注入不符，不影响判定，但人工复核时可能误读。本次抽样检查 S01/S06/S08 的 expect_nodes 均合理，未逐一验证 40 组（kernel 的 raw_runs.json 落盘后可全量复核）。
5. **rel 数值的可区分性未做预演算**：数据集只保证"语义上应命中的节点关键词更贴近 query"，未在生成期逐组计算 rel 排序确认靶子进 top5。机械判定完全依赖 kernel 按 §4/§5 实现后的事实。若出现 anti_trap 大面积 FAIL，首要排查方向是 rel 排序把 M2 挤出 top5，而不是数据标签错误。
6. **控制组仅覆盖 PREFERENCE 槽位**：控制组的覆盖全部发生在 PREFERENCE 类型上，未覆盖 CONSTRAINT/EPHEMERAL 类型的槽位覆盖。若某分支对 memory_type 的处理有偏（例如对 PREFERENCE 有特殊逻辑），控制组将测不出该偏差。
7. **不确定处（记录待队长裁定）**：契约 §3.5 约束 8 说控制组"不包含任何真实覆盖（或覆盖不涉及 anti_trap 靶子）"，本数据集 8 组控制组全部走"覆盖不涉及靶子"路线，没有一组是"完全无覆盖"的纯静默组。契约字面允许（"或"），但若希望 A 分支的基线里包含无覆盖场景，需要补一组纯静默控制组——本报告按契约字面执行，未擅自加。

---

## 5. 破坏性验证证据（校验器自证）

### 5.1 正常数据集

```console
$ python benchmarks/tools/validate_dataset.py --dataset benchmarks/data/eval_cases_40.json
[validate] 数据集: benchmarks\data\eval_cases_40.json
[validate] ===== CONTRACT.md §3.5 九条硬约束 =====
  [OK]   约束 1: case_count=len(cases)=40，scenario_id=S01..S40 连续唯一零填充
  [OK]   约束 2: 全部 40 组 session_events 长度均在 [6,8]
  [OK]   约束 3: 每组恰好 3 条 probes 且 current_state/anti_trap/evolution_why 各一
  [OK]   约束 4: domain 去重 10 种 >= 6: api, auth, build, cache, db, deploy, frontend, observability, security, testing
  [OK]   约束 5: multi_parent 用例 4 组 >= 3: S05(M7); S15(M7); S27(M7); S38(M7)
  [OK]   约束 6: scope_isolation 用例 5 组 >= 4: S06, S16, S26, S33, S37
  [OK]   约束 7: fake_conflict 用例 3 组 >= 2: S07, S19, S35
  [OK]   约束 8: 负控制组 8 组 >= 8: S08, S13, S17, S21, S24, S29, S34, S39；含覆盖的控制组其覆盖均不涉及 anti_trap 靶子
  [OK]   约束 9: 引用完整性/字段合法性/覆盖事件 residual_diff 及关键词/old_keyword 全部通过（含 residual_diff 事件共 40 个）
[validate] ===== 附加 WARN（不参与退出码） =====
  [OK]   WARN 项: 所有非控制组 current_state 的 query 均同时提及新旧技术名（无警告）
[validate] ===== 结果 =====
[validate] OK: 九条硬约束全部通过，警告 0 条
（退出码 0）
```

### 5.2 破坏样例 A：删除 S01/M4 的 residual_diff → exit 1，双 FAIL 精确定位

```console
$ python benchmarks/tools/validate_dataset.py --dataset _broken_a.json
[validate] 数据集: ...\_broken_a.json
  （约束 1–8 与上面相同，全部 OK）
  [FAIL] S01/M4: 同槽覆盖事件缺 residual_diff（被覆盖旧节点 M1）
  [FAIL] S01/probe[2]: old_keyword='MySQL' 未出现在任何 residual_diff 中
[validate] ===== 结果 =====
[validate] FAIL: 共 2 条失败
  - 约束 9: S01/M4: 同槽覆盖事件缺 residual_diff（被覆盖旧节点 M1）
  - 约束 9: S01/probe[2]: old_keyword='MySQL' 未出现在任何 residual_diff 中
（退出码 1）
```

### 5.3 破坏样例 B：S05/M7 的 parent_ids 改为 ["M99", "M7"] → exit 1，双 FAIL 精确定位

```console
$ python benchmarks/tools/validate_dataset.py --dataset _broken_b.json
[validate] 数据集: ...\_broken_b.json
  （约束 1–8 与上面相同，全部 OK）
  [FAIL] S05/M7: parent_ids 引用不存在的 id（M99）
  [FAIL] S05/M7: parent_ids 自引用
[validate] ===== 结果 =====
[validate] FAIL: 共 2 条失败
  - 约束 9: S05/M7: parent_ids 引用不存在的 id（M99）
  - 约束 9: S05/M7: parent_ids 自引用
（退出码 1）
```

### 5.4 交接补丁记录

校验器首轮运行发现 5 条 WARN（S06/S16/S26/S33/S37 的 current_state query 未提及旧技术名）。确认为数据质量问题（非校验器判据 bug）后，回 `build_dataset.py` 修改 scope 模板的 query 文案，重新生成数据集（byte-identical 复现验证通过），复验 WARN 归零。未放宽任何契约判据，未修改 CONTRACT.md。

---

*复核完成于阶段一 t2 任务。生成器与校验器均为纯标准库、确定性输出，可在任意工作目录按 §8.2 命令复现本报告全部结论。*
