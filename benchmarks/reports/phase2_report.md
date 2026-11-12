# 阶段二（Day 1–4）交付报告 · Gated-Mem v2.1.2

> 指令：GM-DIRECTIVE-P2-v2.1.2
> 主程：DeepSeek-V4.1F（独占 100% 生产代码）
> 状态：**Gate 2 六项硬指标 15/15 PASS**，异构审计进行中

---

## 1. 指令确认与 5 项 P0 落实对照

| P0 | 红线要求 | 落实情况 | 证据 |
| :--- | :--- | :--- | :--- |
| **P0-1** | 候选 20–30 个、Δ∈[0,500]、TOPK=5 下强制 ≥80% 截断 | ✅ 15 组场景各 25 节点、22 个 active、span≈395 步；**截断触发率 100%** | `benchmarks/run_phase2_stress.py` |
| **P0-2** | 递归 CTE / BFS 多跳，MAX_DEPTH=8，防环，3 代告警 | ✅ 递归 CTE + visited 防环；MAX_DEPTH=8；4 代链 H1←H2←H3←H4 实测 H4 跨 3 跳识别 H1 | `storage.ancestors_recursive` / `retrieval._stale_ancestors` |
| **P0-3** | 彻底删除软降级惩罚；warning 落库 + 进 RECALL_DELIVERED + 进 XML | ✅ 全库零 psi / 零连坐扣分（AST 扫描保证）；warning 落 `payload_json.stale_warnings`；XML 有 `STALE_ANCESTOR_WARNING` | `tests/test_purity.py` / `gate2_check.py` |
| **P0-4** | injected_active_memories 与 evolution_traces 物理隔离 | ✅ `RecallReceipt` 两个独立字段 + 两个独立 XML 块；实测注入正文旧词命中 **0 次** | `schema.RecallReceipt.to_injection_xml` |
| **P0-5** | embedding BLOB + FTS5 同步 + undo 跨表跨索引原子 | ✅ `memories.embedding BLOB` + 触发器同步；undo 单事务回放，主表/边表/FTS 三方快照逐字段相等 | `storage.undo` / `gate2_check.py` |

---

## 2. 任务包 1 交付清单

| 文件 | 行数 | 核心实现 |
| :--- | ---: | :--- |
| `src/gated_mem/schema.py` | 345 | 五状态枚举、四类型 β/t0、5×5 迁移矩阵、Pydantic 模型、双通道 `RecallReceipt`、`to_injection_xml` |
| `src/gated_mem/gates.py` | 132 | `compute_t0` / `compute_half_life` / `compute_retention` / `compute_vitality` / `compute_retrieval_score`，**无状态纯函数，零连坐** |
| `src/gated_mem/storage.py` | 584 | WAL + FTS5 + 5 张表 + 触发器同步 + 递归 CTE + 原子 undo + 全表快照 |
| `src/gated_mem/events.py` | 152 | 事务批次、causation 链、`rebuild_projection`（含 EVENT_UNDONE 回放） |
| `src/gated_mem/conflicts.py` | 204 | 两阶段裁决、别名归一、`[Replaced: X]` 拼装、覆盖零连坐 |
| `src/gated_mem/retrieval.py` | 334 | FTS5+向量混合、多跳告警、TOPK 截断、双通道回执、RECALL_DELIVERED 落盘 |
| `tests/` 7 个文件 | 1011 | 79 个用例，**覆盖率 93%** |

---

## 3. 任务包 2（GLM 造数）交付

- `benchmarks/build_phase2_stress.py`（662 行，确定性生成器）
- `benchmarks/data/phase2_dense_stress_15.json`（599 KB，sha256 `c0a621c2…`）
- **队长独立复核**：12 条硬约束全 OK，连跑两次逐字节相同，与已提交文件一致。

---

## 4. Gate 2 六项硬指标实测

| # | 指标 | 门槛 | 实测 | 结论 |
| :--- | :--- | :--- | :--- | :---: |
| 1 | 幂律闭式解 | R(0)=1, R(H)=0.5, R(2H) 符公式且 >0.25 | 四类型全部满足，误差 <1e-9 | **PASS** |
| 2 | G2-Rank | λ=0.3 比 λ=0.0 提升 ≥25pp | **+100.00pp**（100% vs 0%） | **PASS** |
| 3 | G2-MultiHop | 3 代告警落盘率 100%，环路不死锁 | 15/15 场景命中，落盘 + XML 双透出 | **PASS** |
| 4 | G2-State | 非法迁移拦截 100%，模糊冲突挂起 100% | 5×5 矩阵拦截；模糊冲突必挂起；覆盖不影响子孙 | **PASS** |
| 5 | G2-Undo | 任意中间步 undo 三方一致 100% | 主表 / 边表 / FTS 快照逐字段相等 | **PASS** |
| 6 | 覆盖率 | ≥90% | **93%** | **PASS** |

**Gate 2：15/15 PASS。**

---

## 5. 关键实现决策（值得记录的取舍）

### 5.1 连坐的物理封印方式
不做「注释里说不连坐」，而是让连坐**在类型系统里无处安放**：`compute_vitality` 的签名只接受 `parent_retentions_cited`（已引用父节点的 R 列表），父节点被废弃时传空列表——只能产生「没有增益」，**没有任何参数能让它产生扣减**。再用 AST 扫描保证代码里不出现 psi 类标识符。

### 5.2 TOPK 截断必须可观测
阶段一最大的盲点是「排序公式根本没受压」。这次 `RecallReceipt` 显式携带 `candidate_pool_size` 与 `truncated_candidates`，把「有没有真的淘汰」变成可断言的事实，而不是靠推断。

### 5.3 undo 的原子性靠单事务而非补偿链
`undo` 在一个 `BEGIN IMMEDIATE` 里逆序回放整个 correlation 批次，FTS5 由触发器跟随主表变化。所以「主表回滚了但索引还在」这种半吊子状态在物理上不可能出现——`gate2_check.py` 用三方快照逐字段比对来证明这点。

### 5.4 `rebuild_projection` 必须消费 EVENT_UNDONE
写测试时发现的真 bug：初版投影重建忽略 `EVENT_UNDONE`，导致 undo 后「逻辑投影」与「物理表」脱节。已修复——先扫描出全部被撤销的 event_id，再跳过它们重放。这条如果漏了，事件溯源的可信度就是假的。

---

## 6. 已知边界（诚实声明）

1. **embedding 是伪向量**：外部数据集给的是基于 sha256 的 32 维确定性向量，用于验证 BLOB 存取与余弦计算链路，**不代表真实语义**。真实 embedding 模型接入属于阶段三。
2. **混合检索的向量路目前只是候选补充**：当前排序主信号是 `rel`（分词重叠）+ vitality 门控。BM25 已接入候选池（`fts_search`），但未做分数归一融合。阶段三需补 BM25 与余弦的加权融合。
3. **µ 参数扫描未做**：本次只固定 λ=0.3 / γ=0.2 验证门禁，未做 λ∈{0,0.1,0.3,0.6,1.0} 的完整敏感性分析。
4. **`max_tokens` 预算为粗略估算**：按「中文按字、英文按 4 字符」折算，不是真实 tokenizer。

---

## 7. Git 提交记录

```
feat(gate2): 六项硬指标验证全绿 + 93% 覆盖率 + 纯净度扫描
feat(core): 阶段二核心底盘 schema/gates/storage/events/conflicts/retrieval + 高压实测
docs(contract): 阶段二压测数据集契约 P2-STRESS v1.0.0
```

---

## 8. 复现命令

```bash
# 单元测试（79 个）
python -m pytest tests/ -q

# 覆盖率（Gate 2 第 6 项，需 >= 90%）
python -m coverage run --source=src/gated_mem -m pytest tests/ -q
python -m coverage report -m

# 高压压测（自造 15 场景）
python benchmarks/pressure_phase2.py

# 高压压测（GLM 外部数据集）
python benchmarks/run_phase2_stress.py

# Gate 2 六项硬指标一键验证
python benchmarks/gate2_check.py
```

环境：Python 3.9.13 + pydantic 2.13.5 + SQLite 3.39.3（FTS5），零外部 API 调用。
