# 阶段二 → 阶段三 交接文档

> 阶段：Gated-Mem v2.1.2 阶段二（Day 1–4）已完成
> 交接人：Tech Lead（DeepSeek-V4.1F）
> Gate 2：**6 项硬指标 15/15 PASS**，异构审计员 Gemini-3.8-Flash 已签署【放行】
> 最后提交：`444baec feat(report): 阶段二交付报告 + Gemini 异构审计签署放行 Gate 2`

---

## 1. 阶段二结论

**`src/gated_mem/` 核心安全底盘已交付：6 个模块 1751 行生产代码、79 个单测、93% 覆盖率、Gate 2 六项全绿。**

阶段一暴露的四大盲点全部清零：

| 阶段一盲点 | 阶段二如何解决 | 验证方式 |
| :--- | :--- | :--- |
| TOPK 从未真正截断，排序公式没受压 | 15 组 25 节点/22 active 场景，截断率 100% | λ=0.3 vs λ=0.0 生死对照 +100pp |
| 传递闭包零覆盖 | 4 代链 H1←H2←H3←H4 实测，跨 3 跳识别废弃根 | 原生 SQLite 查询 stale_ancestor_ids 落盘 |
| `stale_parent_warning` 幽灵变量 | 落 `RECALL_DELIVERED.payload_json` + XML `STALE_ANCESTOR_WARNING` | 直接查库 + 检查 XML |
| 旧词污染正文 | `RecallReceipt` 双字段物理隔离 | 30 probes 实测 injected_text 零泄露 |

---

## 2. 模块清单与接口契约

### 2.1 `schema.py`（345 行）
```python
MemoryType    # DECISION/CONSTRAINT/PREFERENCE/EPHEMERAL，带 .beta 与 .t0_base 属性
MemoryStatus  # 五状态：active/candidate_conflict/superseded/archived/killed
TrustTier     # user_verified / tool_derived / model_inferred
EdgeType      # BELONGS_TO / SUPERSEDES / REFINES / CONTRADICTS
EventType     # 8 种，含 RECALL_DELIVERED 与 EVENT_UNDONE
is_transition_allowed(src, dst) -> bool       # 5x5 矩阵查询
tokenize(text) -> frozenset                    # NFKC+lower，ASCII 整词+中文单字+二元组

MemoryNode / MemoryEdge / MemoryEvent          # Pydantic，frozen=True
RecallItem                                     # 含 stale_parent_warning 与 stale_ancestor_ids
RecallReceipt                                  # injected_items 与 evolution_traces 物理分离
RecallReceipt.injected_text()                  # 只拼正文
RecallReceipt.evolution_text()                 # 只拼 [Replaced: ...]
RecallReceipt.to_injection_xml()               # <active_memories> 与 <evolution_history> 双块
```

### 2.2 `gates.py`（132 行，无状态纯函数）
```python
compute_t0(mem_type, input_weight) -> float
compute_half_life(t0, beta) -> float
compute_retention(delta_steps, t0, beta) -> float
compute_retention_2h(mem_type, input_weight=0.5) -> float   # 闭式解，供断言
compute_vitality(node, parent_retentions_cited=(), gamma=0.2, case_step=None) -> float
compute_retrieval_score(rel, vitality, lam=0.3) -> float
compute_relevance(query_tokens, doc_tokens) -> float
rank_by_score(scored, topk=5, sort_by_raw=True) -> list
```

**连坐封印的设计**：`compute_vitality` 的签名只接受「已引用父节点的 R 列表」。父节点被废弃时传空列表 —— 只能产生「没有增益」，**参数空间里不存在任何能产生扣减的输入**。这是比注释更硬的保证，`tests/test_purity.py` 再用 AST 扫描兜底。

### 2.3 `storage.py`（584 行）
```python
Store(path, project_id)
  .append_event(event_type, step, payload, causation_id, correlation_id) -> event_id
  .insert_memory(node) / .insert_edge(edge)
  .get_memory(id) / .all_memories(statuses, scope)
  .set_status(id, new_status, step)            # 强制 5x5 矩阵校验
  .find_active_by_slot(subject, predicate, scope)
  .parents_of(id, edge_type) / .children_of(id, edge_type)
  .ancestors_recursive(id, max_depth=8)        # 递归 CTE + 防环
  .upsert_alias(alias, canonical) / .resolve_alias(name)
  .fts_search(query, limit) -> [(memory_id, bm25)]
  .undo(event_id) -> dict                      # 单事务，跨表跨索引原子
  .snapshot() -> dict                          # memories/edges/fts 三方全字段快照
```

### 2.4 `events.py`（152 行）
```python
EventLog(store)
  .new_correlation() -> str
  .record_batch(events, step, correlation_id) -> correlation_id   # 事件以 causation_id 串链
  .undo(event_id) -> dict
  .history(project_id, limit) -> List[MemoryEvent]
  .causation_chain(event_id, max_depth=64) -> List[MemoryEvent]
  .rebuild_projection(project_id) -> Dict[str, MemoryNode]        # 消费 EVENT_UNDONE
```

### 2.5 `conflicts.py`（204 行）
```python
normalize_slot(store, subject, predicate, scope) -> tuple
extract_entity_keyword(content) -> str          # 优先取 ASCII 技术名词
format_residual_diff(old_node, reason) -> str   # [Replaced: X] reason，幂等
decide(store, draft, subject, predicate, scope) -> (decision, old_nodes)
apply_supersede(store, new_node, old_nodes, step, reason) -> MemoryNode
mark_candidate_conflict(store, new_node, old_nodes, step) -> MemoryNode
resolve_candidate(store, memory_id, decision, step, reason)
```

决策常量：`EXACT_MATCH`（≥0.92）、`SUPERSEDES`（≥0.55）、`CANDIDATE_CONFLICT`（其余）、`NO_CONFLICT`。

### 2.6 `retrieval.py`（334 行）
```python
Retriever(store, lam=0.3, gamma=0.2, topk=5, max_depth=8)
  .recall(query, case_step=None, topk=None, max_tokens=None,
          write_event=True, use_fts=True, use_vitality=True) -> RecallReceipt
```

**`write_event` 的副作用**（审计员指出，务必注意）：默认 `True` 时 `recall` 会 `touch_citation` 刷新命中节点的 `last_cited_step`。**做 A/B 对比实验时必须传 `write_event=False`**，否则第一轮命中的噪音会在第二轮被「续命」，实验失效。

---

## 3. Gate 2 实测数据

| # | 指标 | 门槛 | 实测 |
| :--- | :--- | :--- | :--- |
| 1 | 幂律闭式解 | R(0)=1, R(H)=0.5, R(2H)>0.25 | 四类型全满足，误差 <1e-9 |
| 2 | G2-Rank | ≥25pp | **+100.00pp**（100% vs 0%） |
| 3 | G2-MultiHop | 落盘率 100%，环路不死锁 | 15/15，环输入 2ms 返回 |
| 4 | G2-State | 非法迁移拦截 100% | 5×5 矩阵 + 模糊冲突必挂起 |
| 5 | G2-Undo | 三方一致 100% | 主表/边表/FTS 逐字段相等 |
| 6 | 覆盖率 | ≥90% | **93%** |

高压数据集（GLM 生成，队长独立复核 12 条硬约束全 OK）：
- `benchmarks/data/phase2_dense_stress_15.json`，599 KB，sha256 `c0a621c2e1e134cef761338584c87850446b59dca21e76977dfb5661db3f917b`
- 15 组 × 25 节点，22 个 active，span ≈395 步，5 个 kill_worm 生死对照场景

---

## 4. 审计员提出的三条注意事项（阶段三必须继承）

1. **Parent gain 的边类型范围**：`compute_vitality` 的父增益只沿 `BELONGS_TO` 传递，不包含 `REFINES`/`CONTRADICTS`。审计员在 P10 发现 QA 脚本未限定边类型导致排名差异 1 位（Rank 2 vs Rank 1）。**队长核验结论：当前实现正确**，因为指令明确要求 `BELONGS_TO` 祖先链。阶段三若要扩展增益范围，必须重新跑生死对照确认结论不变。
2. **`write_event` 的副作用**：见 2.6。
3. **环形边输入**：数据集里每条防环边都会让 `insert_edge` 成功（不拒绝），环在遍历时由 visited + MAX_DEPTH 阻断。**不要在插入层加环检测**——那会让「防环」变成「防输入」，掩盖真实的遍历健壮性问题。

---

## 5. 已知边界（诚实声明，阶段三需处理）

1. **embedding 是伪向量**：数据集给的是 sha256 派生的 32 维确定性向量，只验证了 BLOB 存取与余弦计算链路，**不代表真实语义**。接真实 embedding 模型属于阶段三。
2. **混合检索尚未做分数融合**：BM25 已接入候选池（`fts_search`），但排序主信号仍是 `rel`（分词重叠）+ vitality 门控，**没有做 BM25 与余弦的加权归一**。这是阶段三的头号任务。
3. **λ 敏感性分析未做**：只固定 λ=0.3 / γ=0.2 验证门禁，未跑 λ∈{0, 0.1, 0.3, 0.6, 1.0} 的完整扫描。
4. **`max_tokens` 是粗略估算**：中文按字、英文按 4 字符折算，不是真实 tokenizer。接 MCP 时需换成真实计数。
5. **`candidate_conflict` 无自动裁决**：目前挂起后需人工调 `resolve_candidate`，没有规则化自动裁决策略。

---

## 6. 阶段三（MCP Server + CLI + 导出器）接口约定

### 6.1 MCP Server 必须遵守
```python
# 三个工具
gate_remember(content, memory_type, subject, predicate, scope, input_weight, parent_ids) -> memory_id
query_memory(query, top_k=5, max_tokens=None) -> RecallReceipt
undo_memory(event_id) -> dict
```
- **stdio 铁律**：`src/` 已零 `print`（AST 测试保证）。MCP 层新增代码必须延续，所有日志走 `sys.stderr`。
- `query_memory` 必须调用 `Retriever.recall(write_event=True)`，让 `RECALL_DELIVERED` 自动落盘。
- 返回给宿主的内容用 `RecallReceipt.to_injection_xml()`，保证双通道块结构不被破坏。

### 6.2 CLI 必须复用
```python
gated-mem log --graph          # 用 eventlog.history() + causation_chain()
gated-mem explain <recall_id>  # 查 RECALL_DELIVERED 的 payload_json
gated-mem undo <event_id>      # 直接调 store.undo()
```

### 6.3 导出器
```python
gated-mem export-html [out]    # 读 store.snapshot() + ancestors_recursive() 构建图
```
零外部 CDN 依赖，内联 SVG/Canvas。

---

## 7. 环境与命令速查

```bash
# 依赖（已安装）
#   Python 3.9.13, pydantic 2.13.5, pytest 7.1.2, coverage, numpy 1.21.5
#   SQLite 3.39.3（FTS5 + bm25 + 递归 CTE 全部可用）

# 单测
python -m pytest tests/ -q                        # 79 passed

# 覆盖率（Gate 2 第 6 项）
python -m coverage run --source=src/gated_mem -m pytest tests/ -q
python -m coverage report -m                      # TOTAL 93%

# 高压压测（自造）
python benchmarks/pressure_phase2.py              # +100pp

# 高压压测（GLM 外部数据）
python benchmarks/run_phase2_stress.py

# Gate 2 六项一键验证
python benchmarks/gate2_check.py                  # 15/15 PASS

# 重新生成压测数据
python benchmarks/build_phase2_stress.py --out benchmarks/data/phase2_dense_stress_15.json
```

---

## 8. Git 提交记录

```
444baec feat(report): 阶段二交付报告 + Gemini 异构审计签署放行 Gate 2
7aaf070 chore(git): 忽略覆盖率产物
d7b3f58 feat(gate2): 六项硬指标验证全绿 + 93% 覆盖率 + 纯净度扫描
4029bb6 feat(core): 阶段二核心底盘 schema/gates/storage/events/conflicts/retrieval + 高压实测
d6c726a docs(contract): 阶段二压测数据集契约 P2-STRESS v1.0.0
```

---

## 9. 阶段三开工检查清单

- [ ] 先读 `benchmarks/reports/phase2_report.md` 与本文档
- [ ] 读 `benchmarks/reports/phase2_gemini_audit.md` 的语义歧义与攻破记录
- [ ] **补 BM25 与余弦的分数融合**（当前最大缺口）
- [ ] 接真实 embedding 模型前，先确认 `embedding BLOB` 的维度约定（当前 `embedding_model` 字段已预留）
- [ ] MCP Server 实现后，用 `python -c` 验证 stdout 零污染（`src/` 已有 AST 测试，MCP 层需补同样测试）
- [ ] CLI 的 `explain` 必须复现双通道：正文块与演进块分别渲染
- [ ] 不要回改 `src/gated_mem/` 的既有语义，除非有新的审计证据

---

## 10. 一句话给阶段三

**阶段二把「状态门控」这一层做扎实了：连坐在参数空间里无处安放，告警从内存一路落到磁盘和 XML，undo 跨三张表原子且可逐字段验证。但检索排序的向量侧仍是骨架——BM25 进了候选池却没参与打分，embedding 是伪向量。阶段三接 MCP 之前，先把真实向量与分数融合补上，否则你只是把一套未验证的排序逻辑包进了协议里。**
