# 阶段二压测数据集契约（P2-STRESS v1.0.0）

> 签发：Tech Lead（DeepSeek-V4.1F）
> 用途：阶段二 P0-1 / P0-2 高压检索与多跳拓扑验证的唯一数据真源
> 状态：**冻结**。生成方（GLM-5.3-Flash）不得修改本契约；消费方（kernel / auditor）按此实现与审计。

---

## 1. 产物

| 路径 | 说明 |
| :--- | :--- |
| `benchmarks/build_phase2_stress.py` | 确定性生成脚本（纯标准库，Python 3.9） |
| `benchmarks/data/phase2_dense_stress_15.json` | 15 组高压场景 |

命令：
```bash
python benchmarks/build_phase2_stress.py --out benchmarks/data/phase2_dense_stress_15.json
```

**铁律**：禁止在对话里直接吐 JSON。必须脚本落盘。脚本连跑两次输出逐字节相同（禁 random / time / 环境变量）。

---

## 2. 顶层结构

```json
{
  "dataset_version": "p2-stress-1.0.0",
  "scenario_count": 15,
  "scenarios": [ { ...scenario... } ]
}
```

## 3. scenario 字段

| 字段 | 类型 | 必填 | 约束 |
| :--- | :--- | :---: | :--- |
| `scenario_id` | string | ✅ | `P01`..`P15`，连续唯一 |
| `domain` | string | ✅ | 自由字符串 |
| `description` | string | ✅ | 一句话中文描述 |
| `nodes` | array | ✅ | **恰好 25 个** |
| `edges` | array | ✅ | 显式边（用于防环测试），见 §5 |
| `aliases` | array | ✅ | 槽位别名对，见 §6 |
| `probes` | array | ✅ | 恰好 2 条：`current_state` 与 `evolution_why` 各一 |
| `kill_worm` | object | ❌ | λ 生死对照用例标记，见 §7 |

## 4. node 字段

| 字段 | 类型 | 必填 | 约束 |
| :--- | :--- | :---: | :--- |
| `id` | string | ✅ | `N01`..`N25`，scenario 内唯一 |
| `content` | string | ✅ | 中文正文，技术名词保留英文 |
| `memory_type` | string | ✅ | `DECISION` / `CONSTRAINT` / `PREFERENCE` / `EPHEMERAL` |
| `subject` | string | ✅ | 槽位实体 |
| `predicate` | string | ✅ | 槽位属性 |
| `scope` | string | ✅ | `global` 或 `branch:xxx` |
| `step` | int | ✅ | `1..400`，**全程不得重复**，且同一 scenario 内 step 必须覆盖 `[1, 400]` 的宽跨度 |
| `input_weight` | float | ✅ | `[0.1, 1.0]` |
| `last_cited_step` | int | ✅ | `<= step`；用于制造「高相似但久未被引用」的衰减陷阱 |
| `pinned` | bool | ✅ | 每个 scenario **至少 1 个** true |
| `status` | string | ✅ | `active` / `superseded` / `killed` |
| `residual_diff` | string | ❌ | 若 `status=superseded` 则必填；纯自然语言原因，**不带** `[Replaced:` 前缀，**必须提及**被替代旧节点的技术关键词 |
| `embedding` | array\<float\> | ✅ | 长度 **32** 的伪向量，`[-1,1]`；见 §8 生成规则 |

## 5. edge 字段

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :---: | :--- |
| `source_id` | string | ✅ | **子节点** |
| `target_id` | string | ✅ | **父节点** |
| `edge_type` | string | ✅ | `BELONGS_TO` / `SUPERSEDES` / `REFINES` / `CONTRADICTS` |

**多跳要求（P0-2）**：每个 scenario 的 `BELONGS_TO` 链必须至少有一条 **4 代链**：
`N_leaf -> N_child -> N_parent -> N_root`（即 3 跳，4 个节点），且 `N_root` 的 `status` 必须是 `superseded` 或 `killed`，`N_leaf` 必须是 `active`。
这样 `N_leaf` 必须跨 3 跳才能发现根源失效节点。

**防环输入（P0-2）**：每个 scenario 的 `edges` 里必须**额外**包含 1 条会成环的边（例如已有 `A->B`、`B->C`，再加 `C->A`），并在 edge 上标记 `"is_cycle_probe": true`。消费方遍历时必须靠 visited 集合阻断，**不得死锁**。

## 6. aliases 字段

```json
{"alias_name": "db.primary", "canonical_slot": "主数据库"}
```

每个 scenario **至少 2 对**。其中至少 1 对必须真实制造「同一实体用别名写了两次、应被归一化为同槽并触发覆盖」的情形（两条 node 的 subject 一个用别名、一个用规范名，predicate 与 scope 相同，step 一前一后）。

## 7. kill_worm：λ 生死对照用例

**至少 5 个 scenario** 必须带 `kill_worm`：

```json
{
  "query": "当前主数据库选型是什么？",
  "must_include": ["PostgreSQL"],
  "must_exclude": ["MySQL"],
  "target_node_id": "N24",
  "noise_node_ids": ["N05", "N06", "N07"]
}
```

构造要求（这是 P0-1 的核心，必须真正成立）：
- `target_node_id`：**真正有效**的当前状态节点。它与 query 的 `rel` **较低**（因为内容写法较朴素），但 `last_cited_step` 较新、`vitality` 高。
- `noise_node_ids`（≥3 个）：与 query `rel` **很高**（内容里堆满 query 的原词），但 `step` 极旧（如 step=2..10）且 `last_cited_step` 也极旧，导致 `R` 衰减到很低。
- 目标：当 `lambda=0`（纯相关度）时，noise 霸占 Top-5，`must_include` 落空；当 `lambda=0.3` 时，target 被抬进 Top-5。

> 生成脚本必须内置一个**离线自检**（自己实现 rel 与 F 公式，不得 import src/），打印每个 kill_worm 的「λ=0 时 target 排名」与「λ=0.3 时 target 排名」，并断言至少 5 组满足 `rank_lambda0 > 5` 且 `rank_lambda0.3 <= 5`。若断言失败，脚本必须退出码 1，不允许静默产出废数据。

## 8. embedding 生成规则（确定性）

```python
def pseudo_embedding(text, dim=32):
    # 基于文本字节的确定性伪向量，禁止 random
    import hashlib, math
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vals = []
    for i in range(dim):
        b = h[i % len(h)]
        vals.append((b / 255.0) * 2.0 - 1.0)
    return vals
```

同 content 必须得到同向量（可复现）。

## 9. probe 字段

```json
{
  "probe_type": "current_state",
  "query": "...",
  "must_include": ["..."],
  "must_exclude": ["..."],
  "expect_nodes": ["N24"]
}
```

- `current_state`：验当前态，`must_exclude` 必须含被淘汰的旧技术词。
- `evolution_why`：问「为什么不用 X 了」，`must_include` 放原因关键词，必须带 `old_keyword`。

## 10. 硬约束自检（脚本必须打印 OK/FAIL 并据此决定退出码）

1. `scenario_count == len(scenarios) == 15`，id 为 `P01..P15`。
2. 每 scenario `nodes` 恰好 25。
3. 每 scenario `step` 互不重复，且 `max(step) - min(step) >= 300`（宽跨度）。
4. 每 scenario 至少 1 个 `pinned=true`。
5. 每 scenario 至少 1 条 4 代 `BELONGS_TO` 链，且根为 superseded/killed、叶为 active。
6. 每 scenario 至少 1 条 `is_cycle_probe=true` 的边。
7. 每 scenario `aliases` ≥ 2 对。
8. 带 `kill_worm` 的 scenario ≥ 5，且全部满足 λ 生死对照断言。
9. 每 scenario `probes` 恰好 2 条（current_state 与 evolution_why 各一）。
10. 所有 `superseded` 节点必须有 `residual_diff` 且提及旧关键词。
11. `embedding` 长度 32，元素 ∈ [-1,1]。
12. **可复现**：连跑两次输出字节相同。

## 11. 交付报告要求

生成方必须报告：落盘绝对路径、文件大小、sha256、15 组的节点总数、4 代链清单、防环边清单、别名对清单、5 个 kill_worm 的 λ 对照排名表、以及 12 条硬约束的逐条 OK 输出。

---

*契约冻结。消费方按 §4–§8 的字段名实现，不得改名。*
