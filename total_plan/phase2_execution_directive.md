# Gated-Mem 阶段一终审评估与阶段二（Phase 2）团队执行指令书

> **文档编号** ：GM-DIRECTIVE-P2-v2.1.2
> 
> **签发依据** ：《Gated-Mem 阶段一综合执行审计与大模型裁决案卷》
> 
> **门禁 1 终审结论** ： **有条件通过（Conditional PASS）—— 冻结阶段一基线，强制捆绑五大 P0 级调整进入阶段二**
> 
> **执行架构** ：Maker-Checker 红蓝对抗制（ `DeepSeek-V4.1F` 独揽 100% 生产代码 + `GLM-5.3-Flash` 脚本化造数 + `Gemini-3.8-Flash` 异构黑盒终审）
> 
> 

## 一、 阶段一执行报告综合评估（What Worked & What Failed）

阶段一的执行质量在 **工程纪律性** 和 **架构证伪价值** 上远超预期，但也暴露了单模型同源验证的典型盲区。总体评估如下：

### 1.1 三大核心战果（足以支撑项目立项与论文/README 叙事）

1. **以铁证彻底宣判“物理连坐机制（** ψ **）”死刑** ：
   不仅在 32 组非控制集上实测验证了强连坐导致 `anti_trap` 从 100% 暴跌至 20% （ − 80.00 pp ），更意外发现了连坐的“第二类伤害”——在 S07、S19、S35 中，挂载于旧架构节点下的最新生效事实随着旧节点废弃被一并连坐抹杀（导致 B 分支在 `current_state` 上反而丢了 3 分）。这一发现极具工程含金量，彻底终结了关于“是否保留软连坐”的争论。
2. **验证了“ `residual_diff` 双通道物理隔离”的精妙性** ：
   C 分支之所以能同时拿到 `current_state = 100%` （零旧词污染）与 `evolution_why = 100%` （完整溯源旧技术替换原因），核心在于将 `[Replaced: <旧词>] <原因>` 严格隔离在回执通道（ `returned_diff` ）而非直接混入常规注入正文（ `injected_text` ）。这一设计必须在阶段二生产代码中固化为铁律。
3. **验证了“同源模型查算术、异构模型查盲区”的团队治理定律** ： `DeepSeek-V4.1F` （ `kernel` \+ `auditor2` ）做到了 360/360 零浮点分歧与 5 组变异注入 100% 报警，保证了计算实现零 Bug；而 `Gemini-3.8-Flash` 的异构黑盒穿透则一针见血地揪出了 **“** TOPK = 5 **截断退化（C 分支** 90% **全量注入，排序方程与时间衰减根本没受压）”** 等四大虚假繁荣盲点。证明当前的红蓝对抗团队配置完全正确。

## 二、 案卷四大拍板议题终审裁决（Adjudication Verdict）

针对阶段一案卷第 8 节提交的 4 项待决争议，正式拍板如下：

|议题编号 |终审拍板选项 |裁决指令与执行约束 |
| --- | --- | --- |
|**议题 1：门禁 1 放行裁决** |**选项 B（有条件通过）** |批准放行进入阶段二。阶段一的 100% 仅定性为“状态机逻辑与双通道隔离的机制正确性证明”， **严禁对外宣称为通用基准 SOTA** ；阶段二必须完成全部 P0 整改项方可解锁门禁 2。 |
|**议题 2：连坐机制（** ψ **）去留** |**选项 A（永久物理封印）** |**连软连坐（** ψ = 0.8 **）的开关都不准留！** 生产代码中严禁出现任何因祖先废弃而扣减子孙生命力 F_t(v) 或修改子孙 `status` 的逻辑；全线唯一合法动作是透出只读告警 `stale_parent_warning` 。 |
|**议题 3：TOPK 截断退化处置** |**选项 A+（阶段二集成高压补测）** |阶段一代码与数据就地冻结，不回炉重跑；但在阶段二的 `tests/test_retrieval_pressure.py` 中， **强制增加 15 组“高密度噪声 + 跨度 500 步”高压测试集** （单场景活跃节点数 ≥ 25 ，强制淘汰率 ≥ 80% ）。 |
|**议题 4：阶段二团队协作模式** |**选项 A（强化版 Maker-Checker）** |`DeepSeek-V4.1F` 任 Tech Lead 并独占 100% 生产代码与单测编写； `GLM-5.3-Flash` 仅通过编写 Python 生成脚本造测试数据； `Gemini-3.8-Flash` 在阶段二收官时执行黑盒静态与数学穿透审计。 |

## 三、 后续方案调整清单（阶段二必须执行的 5 项技术修正 + 4 条协作铁律）

基于阶段一暴露的四大盲点与工程事故，对原《实施方案》阶段二（Day 3–5）做出以下 **强制性调整** ：

### 3.1 五大 P0 级技术调整（直接写入阶段二验收契约）

1. **【P0-1 补齐排序与衰减压力测试】告别“全量注入”温室，强制检验** Score = rel · [F_t(v)]^λ ：
   
    + 在阶段二测试中，单场景活跃节点必须扩展至 20 ∼ 30 **个** （包含与查询高度相似但长期未被引用的旧观察 `EPHEMERAL` 、中等相似但刚被 `CITED` 激活的架构规范 `CONSTRAINT` 、以及 `pinned=1` 的锁定节点），逻辑步数跨度拉大至 Δ ∈ [ 0 , 500 ] 。
    + **硬指标** ：在 TOPK = 5 截断下，必须包含至少 5 组“若 λ = 0 （无门控衰减）则被过期高相似噪音霸榜，唯有开启 λ = 0.3 才能将真正有效节点排进前 5”的生死对照用例。
2. **【P0-2 补齐三代以上多跳 DAG 与防环保护】消灭传递闭包死代码** ：
   
    + 在 SQLite `memory_edges` 查询中，使用带访问路径去重的递归 CTE（ `WITH RECURSIVE` ）或 Python 集合防环 BFS，向上追溯 `BELONGS_TO` （ `source=child` → `target=parent` ）祖先链 A ( v ) ，最大追溯深度设为 `MAX_DEPTH = 8` 。
    + 测试集中必须包含至少 **3 代演进拓扑** （ `M1[爷爷决策: 废弃]` ← `M2[父模块规范: 活跃]` ← `M3[孙辈细则: 活跃]` ），验证当 `M1` 变为 `superseded` 时， `M3` 能跨两跳准确浮现 `stale_parent_warning = True` 且指明根源失效节点为 `M1` 。
3. **【P0-3 显式化 `stale_parent_warning` 全链路落盘与透出】消灭幽灵变量** ：
   
    + `stale_parent_warning` 绝不能只停留在内存对象属性里。在 `retrieval.py` 返回的 `RecallItem` 、写入 `memory_events` 的 `RECALL_DELIVERED` 事件负载（ `payload_json` ），以及最终注入给宿主的 XML 文本块中，必须显式附带告警头： `[ ⚠️ STALE_ANCESTOR_WARNING: 关联上游节点 <M1_id: M1_subject> 已于 Step <N> 废弃，请核实本条细则是否仍适用]` 。
4. **【P0-4 固化双通道检索路由协议】防止生产环境下旧词污染** ：
   
    + 将阶段一验证成功的“正文与回执分离”机制正式编码进 `retrieval.py` ：
         
        - `injected_active_memories` ：仅存放 `status == 'active'` 的节点正文，严禁在此通道拼接被覆盖节点的旧文本。
        - `evolution_traces` ：专门存放当前命中节点所关联的 `SUPERSEDES` 边及其 `[Replaced: <旧节点核心词>] <residual_diff>` 。当查询命中历史演进意图或命中 `memories_fts` 中的 `residual_diff` 列时，在独立 `<evolution_history>` 块中透出。
5. **【P0-5 补齐 SQLite FTS5 + 向量混合检索与因果撤销闭环】** ：
   
    + 落地上一轮修补的完整 DDL： `memories` 表必须含 `embedding BLOB` ，同步建立 `memories_fts` 虚拟表（通过 SQLite Trigger 或事务内同步写入维护 `subject, content, residual_diff` 索引）。
    + `undo(event_id)` 必须通过 `causation_id` 和 `correlation_id` 精确回滚整个事务批次，并同步刷新 `memories_fts` 索引。

### 3.2 四条团队工程协作铁律（吸收阶段一踩坑教训）

1. **严禁 Agent 直接吐长 JSON 数据文件** ： `GLM-5.3-Flash` 构造阶段二高压测试集时， **一律编写确定性 Python 生成脚本（ `scripts/build_phase2_stress_data.py` ）** ，通过运行脚本在本地生成 JSON 并自动校验 SHA256，彻底杜绝长文本截断事故。
2. **Git 提交权收归 Tech Lead 串行独占** ：严禁任何子代理执行 `git add / commit` 。所有成员仅在各自指定目录落盘文件，由 `DeepSeek-V4.1F` （或人类指挥官）在单测通过后统一串行提交，杜绝 `.git/index.lock` 冲突。
3. **外部 Agent 调用设置 15 分钟硬超时** ：调用 `Gemini-3.8-Flash` 或 `GLM-5.3-Flash` 通道若超过 15 分钟无字节落盘，立即中断并切换备用调用方式，严禁原地死等。
4. **异构审计保留一票否决权** ： `DeepSeek-V4.1F` 写完阶段二代码后，不能自己宣布过关，必须经过 `Gemini-3.8-Flash` 的“盲点穿透审查”签字后方可结项。

## 四、 阶段二（Phase 2）团队工作任务分解书（WBS Directives）

阶段二目标： **在 3 天内交付 100% 可运行、零占位符、通过高压排序与因果回滚验证的 `src/gated_mem/` 核心安全底盘。**

### 🔵 任务包 1：Tech Lead & 核心主程指令（派发给 `DeepSeek-V4.1F` ）

* **角色权限** ：独占 `src/gated_mem/` 与 `tests/` 下全部 `.py` 代码的编写权，严禁其他模型修改你的业务代码。
* **交付物清单与技术规格** ：

|序号 |交付文件路径 |必须实现的生产级契约规格 |
| --- | --- | --- |
|**1** |`src/gated_mem/schema.py` |定义枚举 `MemoryType` （含 β 与 t_{0,base} ）、 `MemoryStatus` （5 状态）、 `TrustTier` 、 `EdgeType` ；定义 Pydantic 模型 `MemoryNode` 、 `MemoryEdge` 、 `MemoryEvent` （含 `causation_id` , `correlation_id` ）、 `RecallItem` （显式包含 `stale_parent_warning: bool` 与 `stale_ancestor_ids: list[str]` ）、 `RecallReceipt` （分离 `injected_items` 与 `evolution_traces` ）。 |
|**2** |`src/gated_mem/gates.py` |实现无状态纯函数： 1. `compute_t0(mem_type, input_weight)` ： t_0 = t_{0,base} ⋅ ( 0.5 \+ i_v ) ； 2. `compute_half_life(t0, beta)` ： H = t_0 ⋅ ( 2 1/ β − 1 ) ； 3. `compute_retention(delta_steps, t0, beta)` ： R = ( 1 \+ Δ/ t_0 ) − β ； 4. `compute_vitality(node, parent_retentions_cited)` ：若 `pinned` 则返回 1.0 ，否则返回 min ( 1.0 , R \+ 0.2 ⋅ max R parent_cited ) （ **物理废除一切连坐扣分** ）； 5. `compute_retrieval_score(rel, vitality, lam=0.3)` ： Score = rel ⋅ ( vitality ) λ 。 |
|**3** |`src/gated_mem/storage.py` `src/gated_mem/events.py` |1. 启用 SQLite `WAL` 、 `foreign_keys = ON` 、 `busy_timeout = 5000` ； 2. 创建 `memory_events` 、 `memories` （含 `embedding BLOB` ）、 `memory_edges` （严格执行 `source_id=child` → `target_id=parent` ）、 `slot_aliases` 及 `memories_fts` （FTS5 虚拟表）； 3. 实现 5×5 状态迁移矩阵校验（严禁普通写入复活 `superseded` / `killed` 节点）； 4. 实现 `undo(event_id)` ：按 `correlation_id` / `causation_id` 逆序回放 `before_state` 快照，写入 `EVENT_UNDONE` 补偿事件，并同步更新主表与 FTS5 索引。 |
|**4** |`src/gated_mem/conflicts.py` |实现两阶段槽位冲突裁决： 1. 先查 `slot_aliases` 将 `(subject, predicate, scope)` 归一化； 2. 同槽位活跃节点比对：内容等价 → `EXACT_MATCH` （仅刷新 `last_cited_step` ）；明确覆盖 → `SUPERSEDES` （旧节点标 `superseded` ，自动拼装 `[Replaced: <旧节点关键词>] <原因>` 写入新节点与边的 `residual_diff` ）；作用域模糊或疑似矛盾 → `CANDIDATE_CONFLICT` （挂起待决，绝不自动覆盖）。 |
|**5** |`src/gated_mem/retrieval.py` |实现混合检索与输出门： 1. 结合 BM25 ( `memories_fts` ) 与向量余弦（支持 NumPy 零依赖计算）获取候选池； 2. 通过防环多跳向上遍历 `BELONGS_TO` （最大深度 8），若任一祖先处于 `superseded/killed` ，置位 `stale_parent_warning = True` 并记录 `stale_ancestor_ids` ； 3. 按 `compute_retrieval_score` 排序並在 `top_k` / `max_tokens` 预算内截断； 4. 自动向 `memory_events` 写入 `RECALL_DELIVERED` 事件（完整落盘 `stale_warnings` 、拦截列表与演化轨迹），返回 `RecallReceipt` 。 |
|**6** |`tests/test_gates.py` `tests/test_events_undo.py` `tests/test_conflicts.py` `tests/test_retrieval_pressure.py` |完整单元测试与高压集成测试（见第五节门禁 2 验收标准）。 |

### 🔴 任务包 2：高压测试集生成指令（派发给 `GLM-5.3-Flash` ）

* **角色权限** ：不接触 `src/gated_mem/` 源码，独立编写数据生成脚本 `benchmarks/build_phase2_stress.py` ，运行产出 `benchmarks/data/phase2_dense_stress_15.json` 。
* **脚本生成规格（专门针对阶段一的四大盲点设计）** ：
  
    1. **高密度候选池（破除盲点 1 & 4）** ：共 15 个大型演进场景，每个场景包含 **25 个记忆节点** （其中同主题域高相似干扰项 ≥ 10 个），步数从 `Step 1` 跨度至 `Step 400` 。确保在 `top_k = 5` 时，系统必须淘汰掉 80% 的活跃候选，逼迫 λ = 0.3 衰减指数与 1-Hop 正向激活 γ = 0.2 真正发挥决定性排序作用。
    2. **三代至四代依赖树（破除盲点 2）** ：每个场景至少包含一条 `M1(爷爷决策) <- M2(父模块规范) <- M3(子配置) <- M4(孙辈细则)` 的 3~4 跳 `BELONGS_TO` 链条，以及 1 个故意构造的尝试成环边输入（测试系统防环能力）。
    3. **槽位别名漂移（测试 `slot_aliases` ）** ：同一实体在不同 Step 使用不同别名（如 `db.primary` vs `primary_database` ），验证别名归一化表能否精准对齐并触发覆盖。

### 🟣 任务包 3：异构黑盒与代码穿透审计指令（派发给 `Gemini-3.8-Flash` ）

* **介入时机** ：当 `DeepSeek-V4.1F` 完成全部代码且本地 `pytest` 100% 绿灯后介入。
* **四大强制审查项（出具 `benchmarks/reports/phase2_gemini_audit.md` ）** ：
  
    1. **TOPK 真实淘汰率核查** ：统计在 15 个高压场景下，活跃候选池大小是否全部 ≥ 18 ，且开启 λ = 0.3 相比 λ = 0.0 （纯相关度）在时间敏感探针上的准确率提升是否 ≥ 25 pp 。
    2. **多跳告警落盘核查** ：打开 SQLite 数据库文件，直接查询 `memory_events` 中 `event_type = 'RECALL_DELIVERED'` 的 `payload_json` ，核实 3 跳孙辈节点的 `stale_parent_warning` 和 `stale_ancestor_ids` 是否真实落盘（而非内存假象）。
    3. **因果 Undo 无损性核查** ：任取一个触发了槽位覆盖、边创建、FTS5 更新的复合事件，执行 `undo(event_id)` 后，比对 SQLite 全表快照与覆盖前是否 100% 逐字段相等，且再次执行普通写入不会非法复活已 `killed` 的节点。
    4. **代码纯净度扫描** ：扫描 `src/gated_mem/` 全库，确认零 `# TODO` 占位符、零裸 `print()` （防污染后续 MCP `stdout` ）、零物理连坐残余代码。

## 五、 阶段二门禁（Gate 2）硬性验收指标

阶段二结束时，必须同时满足以下 **6 项硬性指标** 方可放行进入阶段三（MCP Server 与 CLI 封装）：

1. **幂律数学闭式解断言** ： `test_gates.py` 中对全部 4 类记忆验证 R ( 0 ) = 1.0 、 R ( H ) = 0.5 ，且 R ( 2 H ) = ( 2 ⋅ 2 1/ β − 1 ) − β > 0.25 误差 < 1 0 − 9 。
2. **高压检索淘汰有效性（G2-Rank）** ：在 15 组高密度场景（每组 25 节点， TOPK = 5 ）上， λ = 0.3 相比 λ = 0.0 的过期高相似噪音拦截率提升 ≥ 25 pp 。
3. **三代多跳告警透出率（G2-MultiHop）** ：跨 2 ∼ 3 跳祖先废弃时，孙辈节点召回回执中的 `stale_parent_warning` 触发率与落盘率为 100% ，且面对环路输入不死锁。
4. **状态机防复活与覆盖零误杀（G2-State）** ：5×5 状态迁移矩阵非法跳转拦截率 100% ；模糊作用域冲突进入 `candidate_conflict` 挂起率 100% （自动误覆盖率 = 0% ）。
5. **因果链** O ( 1 ) **撤销一致性（G2-Undo）** ：连续 10 步增删改覆盖操作后，任意指定中间某步 `event_id` 执行 `undo` ，主表、边表与 FTS5 全文索引的状态恢复一致率 100% 。
6. **双审计零分歧签署** ： `pytest` 覆盖率 ≥ 90% ，且异构审计员 `Gemini-3.8-Flash` 签署“四大盲点已彻底清零”核验报告。
