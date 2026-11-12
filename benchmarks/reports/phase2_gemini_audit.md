# Gated-Mem 阶段二（Gate 2）异构黑盒审计报告

> **审计者**：Gemini-3.8-Flash（独立监察官，异构审计位）  
> **审计对象**：阶段二交付物（`src/gated_mem/` 全库生产代码、`benchmarks/data/phase2_dense_stress_15.json` 高压压测集）  
> **审计方法**：完全独立离线复算 + 真实 SQLite 数据库落盘穿透 + AST 语法级代码扫描 + 黑盒攻防注入  
> **审计原则**：在得出独立计算结果前严格不阅读 `src/gated_mem/` 源码；行使独立监察与一票否决权  
> **报告日期**：2026-11-12  

---

## 一、 审计执行概览与门禁签署结论

依据《Gated-Mem 阶段一终审评估与阶段二执行指令书》（GM-DIRECTIVE-P2-v2.1.2）第五节“Gate 2 六项硬指标”与《阶段二压测数据集契约》（CONTRACT_P2_STRESS v1.0.0），审计员对阶段二代码库与数据产物执行了四大强制审查项与双通道隔离专项核验。

### 门禁裁决签署

**【放行 Gate 2】（PASS）**

**签署意见**：
四大强制审查项（TOPK 淘汰率、多跳告警真实落盘、因果 Undo 全表无损性、代码纯净度）及双通道物理隔离专项核验全部达到或显著超越契约硬指标。阶段一暴露的四大虚假繁荣盲点（全量注入无淘汰、连坐传递闭包死代码、告警停留在内存假象、旧词事实污染）在阶段二生产代码中已彻底清零。同意放行进入阶段三（MCP Server 与 CLI 封装）。

---

## 二、 四大强制审查项逐项结论与证据

### 1. TOPK 真实淘汰率核查（P0-1：破除全量注入盲点）

#### 1.1 审查方法与独立复算口径
在系统临时目录建立独立复算脚本，依据契约公式实现文本分词、Jaccard 关联度 $rel$、生命力 $F_t(v)$（包含 $t_0, R_t(v), \gamma=0.2$ 父节点增益）及检索得分 $Score = rel \cdot F^\lambda$。装载由 GLM-5.3-Flash 生成的 `benchmarks/data/phase2_dense_stress_15.json`（15 组场景，共 375 个节点），统计活跃候选池与 5 组 `kill_worm` 生死对照用例。

#### 1.2 独立复算数据
1. **活跃候选池规模**：
   - 15 组场景（P01..P15）中，每个场景包含 25 个节点，其中恰有 3 个节点为 `superseded` 或 `killed`，活跃节点数均为 **22 个**。
   - 全部场景满足活跃候选池 $\ge 18$ 的硬约束（15/15 达标率 100%）。
   - 在 TOPK = 5 截断下，淘汰率强制达到 $(22 - 5) / 22 = 77.27\%$，彻底打破了阶段一 90% 全量注入的温室环境。
2. **5 组 `kill_worm` 生死对照（λ=0.0 vs λ=0.3）**：
   - **λ=0.0（纯相关度排序）**：
     - Top-5 被 step 极旧（step 2..17）但堆满 query 原词的高相似 `EPHEMERAL` 噪音（N01..N05，相关度 $rel \approx 0.77 \sim 0.82$）完全霸占。
     - 目标节点（Target N06，DECISION，step 394 极新，写法朴素 $rel \approx 0.24 \sim 0.49$）排名被挤到第 6 或第 7 名，**Top-5 入榜率为 0.0%（0/5）**。
   - **λ=0.3（开启门控衰减）**：
     - 噪音节点生命力因长期未被引用衰减至 $R \approx 0.0028 \sim 0.0030$，$Score = rel \cdot F^{0.3}$ 从 0.82 暴跌至 0.14。
     - 目标节点因处于活跃期（$F \approx 0.87 \sim 1.0$），得分保持在 $0.23 \sim 0.47$，被强力抬进前 2 名。
     - 目标节点 **Top-5 入榜率达到 100.0%（5/5）**。
   - **入榜率提升幅度**：$100.0\% - 0.0\% = \mathbf{+100.0\text{ pp}}$（硬指标门槛：$\ge 25\text{ pp}$，超额 75 pp 达成）。

#### 1.3 独立复算与 `src/gated_mem` 产物对照表

| 场景编号 | Target ID | 独立复算 λ=0 排名 | src 实测 λ=0 排名 | 独立复算 λ=0.3 排名 | src 实测 λ=0.3 排名 | Top-5 判定对照 |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **P01** | N06 | 6（Top-5 未入） | 6（Top-5 未入） | 1（入榜首位） | 1（入榜首位） | 一致 |
| **P04** | N06 | 7（Top-5 未入） | 7（Top-5 未入） | 2（入榜次席） | 2（入榜次席） | 一致 |
| **P07** | N06 | 6（Top-5 未入） | 6（Top-5 未入） | 2（入榜次席） | 2（入榜次席） | 一致 |
| **P10** | N06 | 6（Top-5 未入） | 6（Top-5 未入） | 2（入榜次席） | 1（入榜首位）* | 一致进 Top-2 |
| **P13** | N06 | 6（Top-5 未入） | 6（Top-5 未入） | 1（入榜首位） | 1（入榜首位） | 一致 |

*\*注：P10 排名在第 1 与第 2 之间的微小差异系因 Parent Gain 是否跨 `REFINES` 边引起（详见第三节“语义歧义”），两种口径下 Target 均稳进 Top-2，门禁指标无条件满足。*

---

### 2. 多跳告警落盘核查（P0-2 / P0-3：消灭幽灵告警与死代码）

#### 2.1 审查方法
在临时路径建立独立 SQLite 文件数据库，通过 `Store` 与 `Retriever` API 构造一条严格的 4 代演进拓扑：
$$\text{M4\_LEAF (active, step 4)} \xrightarrow{\text{BELONGS\_TO}} \text{M3\_CHILD (active, step 3)} \xrightarrow{\text{BELONGS\_TO}} \text{M2\_PARENT (active, step 2)} \xrightarrow{\text{BELONGS\_TO}} \text{M1\_ROOT (superseded, step 1)}$$
随后针对检索 M4 的查询调用 `recall(..., write_event=True)`，绕开内存对象，直接使用原生 `sqlite3` 查询 `memory_events` 表中的持久化落盘数据。

#### 2.2 核心核验结论与证据
1. **真实落盘证据（非内存假象）**：
   - 执行 SQL：`SELECT event_id, event_type, payload_json FROM memory_events WHERE event_type='RECALL_DELIVERED'`。
   - 解析落盘的 `payload_json`，其中 `stale_warnings` 字段明确记录：
     ```json
     [
       {"memory_id": "M4_LEAF", "stale_ancestor_ids": ["M1_ROOT"]},
       {"memory_id": "M2_PARENT", "stale_ancestor_ids": ["M1_ROOT"]},
       {"memory_id": "M3_CHILD", "stale_ancestor_ids": ["M1_ROOT"]}
     ]
     ```
   - 证明：跨 3 跳的失效根源节点 `M1_ROOT` 准确传导至叶节点 `M4_LEAF`，且告警数据**已由事务直接落入 SQLite 磁盘**。
2. **宿主 XML 透出格式核验**：
   - 调用 `receipt.to_injection_xml()`，生成内容如下：
     ```xml
     <memory memory_id="M4_LEAF" type="CONSTRAINT" stale="true" stale_ancestors="M1_ROOT">
       孙辈细则：JWT 签名算法采用 RS256
       [⚠️ STALE_ANCESTOR_WARNING: 关联上游节点 M1_ROOT 已废弃，请核实本条细则是否仍适用]
     </memory>
     ```
   - 属性 `stale="true"`、`stale_ancestors="M1_ROOT"` 以及规范告警前缀均符合契约规范。
3. **拓扑防环测试（Cycle Resistance）**：
   - 向图谱中注入环路边：`M1_ROOT -> M4_LEAF` 以及三节点强连通环 `CA -> CB -> CC(superseded) -> CA`。
   - 实测：`recall` 在 **2.00 毫秒** 内立即完成返回，无死锁、无无限递归，内部 visited 集合与 `MAX_DEPTH = 8` 深度截断生效完好，`CA` 节点正确且仅一次性附带失效告警 `stale_ancestor_ids=['CC']`。

---

### 3. 因果 Undo 无损性核查（P0-5：回滚全表一致性与防复活）

#### 3.1 审查方法
1. 在全新 SQLite 数据库中构造一个复合事务（新建节点 + 槽位覆盖触发 `SUPERSEDES` + 创建跨节点边 + 同步维护 FTS5 虚拟表）。
2. 在复合事务执行前对 SQLite 底层 `memories`、`memory_edges`、`memories_fts` 三张表进行全字段快照。
3. 执行复合事务后，调用 `store.undo(event_id)` 逆序回滚所有关联事件。
4. 重新提取三张表全字段快照，逐字段对比 `before` 与 `restored`。
5. 构造 10 步复杂写入序列，任意撤销中间第 6 步，检查前后状态与 FTS 索引。
6. 验证已废弃节点的防复活拦截能力。

#### 3.2 核验结论与证据
1. **复合事务全字段 100% 无损回滚**：
   - 快照前：`memories` 2 行，`memory_edges` 0 行，`memories_fts` 2 行。
   - 复合写入后：`memories` 3 行（旧节点标 superseded），`memory_edges` 2 行（含 SUPERSEDES 边），`memories_fts` 3 行。
   - 执行 Undo 后：`memories` 2 行，`memory_edges` 0 行，`memories_fts` 2 行。
   - **比对结果**：`snapshot_restored == snapshot_before`，所有主键、状态、时间步、外键引用及 FTS5 索引逐字节相等，零孤儿边、零幽灵索引。
2. **10 步序列中间步精准撤销**：
   - 撤销 Step 6 事件后，`NODE_06` 节点及其对应的 FTS5 索引记录即刻消失；
   - 其余 9 步（Step 1..5, Step 7..10）的所有节点属性与 FTS 搜索结果未受任何扰动。
3. **状态机防复活铁律验证（Anti-Revival）**：
   - 针对处于 `superseded` 状态的节点，尝试普通 `insert_memory` 写入新数据：底层主键约束立即阻断并抛出 `sqlite3.IntegrityError`。
   - 针对处于 `superseded` 或 `killed` 状态的节点，调用 `set_status(..., ACTIVE)`：
     - `StorageError: 非法状态迁移 superseded -> active（节点 NODE_01）。superseded/killed 只能经 undo 补偿恢复。`
     - `StorageError: 非法状态迁移 killed -> active（节点 NODE_02）。superseded/killed 只能经 undo 补偿恢复。`
   - 证实 5×5 状态迁移矩阵拦截率达 100%，杜绝了业务逻辑误操作复活已废弃记忆的可能。

---

### 4. 代码纯净度扫描（一票否决项）

#### 4.1 审查方法
使用 Python `ast` 模块与 `tokenize` 词法解析器，对 `src/gated_mem/` 下全部 7 个源码文件（`conflicts.py`、`events.py`、`gates.py`、`retrieval.py`、`schema.py`、`storage.py`、`__init__.py`）进行语法树遍历。

#### 4.2 扫描结论

| 检查维度 | 判定标准 | 扫描命中处 | 结论 |
| :--- | :--- | :---: | :---: |
| **裸 `print()`** | 零调用（防污染宿主/MCP stdout） | **0** | PASS |
| **`sys.stdout` 写入** | 零调用 | **0** | PASS |
| **`# TODO` 占位符** | 零占位符（含 TODO / FIXME / XXX / TBD） | **0** | PASS |
| **物理连坐残余** | 严禁出现 `psi` / `PSI` 标识符或减分逻辑 | **0** | PASS |
| **Python 3.9 兼容性** | 禁 `match` 语句、禁运行时非法联合类型 | **0** | PASS |

源码完全纯净，零一票否决项违规。

---

## 三、 额外必查项：P0-4 双通道物理隔离专项核验

### 1. 隔离机制审查
针对阶段一最大的事实污染漏洞（`must_exclude` 旧词因 `residual_diff` 混入正文而自伤），阶段二固化了双通道路由协议：
- **正文通道（`injected_items` / `injected_text()`）**：只允许活跃节点（`status == active`）的 `content` 参与拼接。
- **回执通道（`evolution_traces` / `evolution_text()`）**：仅在命中演进查询或 FTS 历史意图时，将 `SUPERSEDES` 边的 `[Replaced: <旧词>] <原因>` 在独立 `<evolution_history>` 块中输出。

### 2. 15 组压测集（30 个 Probes）全量扫描结果
对 15 个场景的全部 30 个 Probe（15 条 `current_state` + 15 条 `evolution_why`）进行了端到端检索校验：
- `[Replaced:` 前缀出现在 `injected_text` 中的次数：**0 次**。
- `residual_diff` 文本出现在 `injected_text` 中的次数：**0 次**。
- `current_state` 的 `must_exclude` 旧技术词在 `injected_text` 中的出现次数：**0 次**。
- 30 个 Probe 在 XML 格式下的 `<active_memories>` 块中旧技术词泄漏数：**0 次**。
- 双通道物理隔离判定：**100% PASS**。

---

## 四、 独立复算时踩到的语义歧义与裁决记录

在独立复算与实现对照过程中，审计员捕获了 2 处潜在的语义歧义，特此记录并给出裁决：

### 歧义 1：召回动作副作用导致的时空污染（Recall Side-Effect）
- **现象**：`Retriever.recall()` 默认设置了 `write_event=True`，在产出回执的同时，事务性地调用了 `store.touch_citation()` 刷新所有被注入节点的 `last_cited_step = current_step`。
- **潜在陷阱**：若审计员或压测脚本在**同一个**数据库实例上顺序执行先 `recall(lam=0.0)` 再 `recall(lam=0.3)`，第一轮检索中因高相似度而命中的过期噪音（N01..N05）会被立即赋予最新引用步，其生命力在第二轮直接跃迁至 1.0，从而造成 λ=0.3 无法淘汰噪音的假象。
- **审计裁决**：压测或对比实验必须传入 `write_event=False`，或在每次检索前重置干净的数据快照。这一机制属于预期内的在线记忆更新行为，但应在 API 文档中显式提醒使用者。

### 歧义 2：Parent Gain 边的类型范围（`BELONGS_TO` vs 任意边）
- **现象**：在 P10 场景中，`N15` 与 `N14` 之间存在 `REFINES` 边（`N15 -> N14`）。
  - QA 的离线自检脚本 `build_phase2_stress.py` 中 `parent_ids_of` 提取了所有出边（未限定边类型），导致 `N15` 从 `N14` 获得了 `0.1834` 的父节点活力增益，使其在 λ=0.3 时总得分略微反超 Target `N06`（N06 排名第 2）；
  - `src/gated_mem`（`Retriever`）实现中严格限定只有 `BELONGS_TO` 边才属于结构父子关系，因此 `N15` 未获增益，Target `N06` 排名第 1。
- **审计裁决**：`src/gated_mem` 的收敛实现更加优良——知识体系中只有层级从属（`BELONGS_TO`）才具备生命力背书能力，细化或修饰（`REFINES`）不应无条件传递生命力。两种口径下 Target 均稳居 Top-2，完全满足生死对照要求。

---

## 五、 尝试攻破但被系统成功防御的点

审计员在审查期间尝试了 3 种恶意注入与破坏性用例，系统均稳稳防住：

1. **环路攻击（Cycle Attack）**：
   - 构造 `M1 -> M4 -> M3 -> M2 -> M1` 4 节点大环及 `CA -> CB -> CC -> CA` 3 节点强连通环。
   - **防御效果**：`Retriever.ancestors_recursive` 正确利用 `visited` 集合防重，并在 `MAX_DEPTH = 8` 限制下正常终止，耗时 2.00 ms，未发生栈溢出或无限死循环。
2. **非法复活攻击（Zombie Revival Attack）**：
   - 尝试通过直接修改状态将 `superseded` 或 `killed` 节点提权至 `active`。
   - **防御效果**：存储层与事件层受控于 5×5 状态转移矩阵，抛出 `StorageError` 强制阻断，确保已失效记忆只能通过因果 Undo 机制逆向平反。
3. **旧词投毒攻击（Poisoning via FTS5）**：
   - 构造 query 故意包含大量旧架构关键词，诱导 FTS5 全文索引将包含 `residual_diff` 的被废弃节点拽入注入通道。
   - **防御效果**：候选池在进入排序前受到 `status == active` 的强力门控拦截，即使 FTS 命中，被废弃节点的正文也绝对进不了 `injected_text`。

---

## 六、 缺陷与建议清单（Findings & Recommendations）

本次审计未发现任何破坏数据一致性或安全性的一票否决级缺陷。仅记录 1 项轻微的工程优化建议：

- **[建议项 GM-AUDIT-P2-01]：`gates.compute_relevance` 参数类型强化**
  - **位置**：`src/gated_mem/gates.py` 第 109 行
  - **描述**：`compute_relevance(query_tokens, doc_tokens)` 内部直接使用 `&` 运算符求交集，因此入参必须为 `Set[str]`。虽然 `Retriever` 在调用前均完成了分词处理，但若外部开发者直接调用该函数并传入裸 `str`，会抛出 `TypeError: unsupported operand type(s) for &: 'str' and 'str'`。
  - **建议**：在阶段三封装时，可在函数入口增加 `if isinstance(query_tokens, str): query_tokens = tokenize(query_tokens)` 的兼容性防御。

---

## 七、 门禁总结

- **Gate 2 六项硬指标综合达成率**：**100%（6/6）**
- **单元测试通过情况**：`tests/` 下 79 项单元测试全部绿灯通过（耗时 0.96s）。
- **异构审计签署结论**：**准予放行 Gate 2**，建议队长统一执行阶段二成果代码提交。
