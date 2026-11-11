# benchmarks/CONTRACT.md — Gated-Mem 阶段一冻结契约（Spike Cut #1）

> **版本**：1.0.0
> **签发人**：Tech Lead（队长）
> **状态**：**冻结**。开工后任何一方不得单方面修改本文件；发现契约缺陷必须先向队长报告，由队长签发 1.0.1 修订并广播。
> **适用**：`benchmarks/` 下阶段一全部产物。阶段二（SQLite / 事件溯源 / MCP / CLI / HTML）**不在本契约范围内**，一行都不要写。

---

## 0. 元信息

- 工作目录：`<repo-root>`
- 解释器：**Python 3.9.13**（禁止 `match`、禁止运行期 `X | Y` 类型标注、禁止 `list[str]` 之外的新语法糖以外的 3.10+ 特性）
- 依赖：**仅标准库**（`json` `math` `re` `unicodedata` `hashlib` `argparse` `os` `sys` `collections`）。禁止 pip 安装任何第三方包，禁止任何网络/API 调用。
- 预算：**¥0**。本阶段一切判定都是**确定性机械判定**，不调用任何 LLM 当裁判（见 §11 偏离声明 D1）。

---

## 1. 数学常数与公式

### 1.1 类型参数表（唯一真源）

| memory_type | beta | t0_base |
| :--- | :---: | :---: |
| DECISION | 0.10 | 100 |
| CONSTRAINT | 0.05 | 200 |
| PREFERENCE | 0.15 | 80 |
| EPHEMERAL | 1.20 | 5 |

全局常数：`LAMBDA = 0.3`，`GAMMA = 0.2`，`TOPK = 5`。

### 1.2 步数与 Δ

- 一个 case 的 `session_events` 按数组顺序分配步数 `step = 1..N`（`N = len(session_events)`，6 ≤ N ≤ 8）。
- 探针在全部事件写入之后提问，故 **`CASE_STEP = N`**。
- 每个节点的 `last_cited_step` 初值 = 该节点自己的 `step`；阶段一不做多轮召回更新，因此
  `Delta(v) = CASE_STEP - v.step = N - v.step`（≥ 0）。

### 1.3 初始时间尺度与保留率

```
t0(v) = t0_base(v.memory_type) * (0.5 + v.input_weight)
R(v)  = (1 + Delta(v) / t0(v)) ** (-beta(v.memory_type))
```

### 1.4 生命力 F_t（无连坐）

```
若 v.pinned:                        F(v) = 1.0
否则:
    base = R(v)
    gain = GAMMA * max( R(u) for u in parents(v) if u.status == "active" )   # 无 active 父则 gain = 0
    F(v) = min(1.0, base + gain)
```

- `parents(v)` = 事件上声明的 `parent_ids`（0 个、1 个或多个）。
- **连坐系数 ψ 已物理砍除**：F 中对父节点的处理只有"若父 active 则加 1-Hop 正增益"，**父节点被覆盖时不得对子节点做任何扣减**（只在 C 分支打 `stale_parent_warning=True` 标签）。

### 1.5 排序得分

```
Score(v | q) = rel(q, v) * (F(v) ** LAMBDA)
```

### 1.6 数值输出约定

- 写入 `raw_runs.json` 的 `rel` / `f` / `score` 一律 `round(x, 6)`；`rate` 一律 `round(x, 6)`。
- 排序：`score` 降序；同分按 `node_id` **升序**（纯 ASCII 字典序）。

---

## 2. 三分支语义（整个实验的核心，逐字实现）

| 分支 | 名称 | 槽位覆盖 | 子孙处理 | `residual_diff` | 检索候选 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A** | 纯向量基线 | **不做**（所有节点恒 active） | 无 | **一律不记录（None）** | 全部节点 |
| **B** | v2.0 强连坐对照组 | 做 | 沿 `parent` 边把**全部子孙（传递闭包）**标 `superseded` | 记录**原始** diff（不拼前缀） | 仅 status == active |
| **C** | v2.1.1 终审机制 | 做 | **仅直接子节点**置 `stale_parent_warning=True`，status **保持 active**；孙辈不受影响 | 记录 `"[Replaced: " + old.subject + " / " + old.content[:30] + "] " + 原始原因` | 仅 status == active |

### 2.1 槽位与覆盖触发

- 槽位 = 三元组 `(subject, predicate, scope)`，**字符串精确相等**才算同槽（不做别名、不做模糊匹配）。
- 处理第 i 个事件时，在**已入库且 status == active** 的节点中查找同槽者：
  - 若存在多个，取 `node_id` 字典序**最小**的那一个作为 `old`（其余保持原状，但必须被同样覆盖——见下条）。
  - **实际规则**：凡是同槽且 active 的旧节点，**全部**被标 `superseded`；`old`（用于拼 `residual_diff`）取其中 `node_id` 最小者。
- 然后写入新节点，status = active。
- A 分支跳过上述全部逻辑。
- 事件自带的 `residual_diff` 用于新节点；若事件未提供 `residual_diff` 且发生了覆盖，A/B/C 均按"无 diff"处理（数据集保证覆盖事件一定带 diff，校验器会卡这条）。

### 2.2 处理顺序

严格按 `session_events` 数组顺序逐条处理；处理第 i 条时只能看到前 i-1 条的状态。**禁止**先全量建图再统一算状态。

---

## 3. 数据契约 `benchmarks/data/eval_cases_40.json`

### 3.1 顶层结构

```json
{
  "dataset_version": "1.0.0",
  "case_count": 40,
  "cases": [ { ...case... } ]
}
```

### 3.2 case 字段

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :---: | :--- |
| `scenario_id` | string | ✅ | `S01`..`S40`，唯一、升序、零填充 |
| `domain` | string | ✅ | 场景域，**至少 6 种**（如 db / auth / frontend / testing / deploy / observability / api / security） |
| `description` | string | ✅ | 一句话场景描述（中文） |
| `is_control` | bool | ✅ | 负控制组标记 |
| `construction_note` | string | ✅ | 该组为何这样构造；`is_control=true` 时**必须**写明"为何是控制组"（非空且 ≥ 10 字） |
| `tags` | array<string> | ✅ | 至少 1 个，取值见 §3.5 |
| `session_events` | array | ✅ | 6–8 条，见 §3.3 |
| `probes` | array | ✅ | **恰好 3 条**，见 §3.4 |

### 3.3 event 字段

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :---: | :--- |
| `id` | string | ✅ | case 内唯一，如 `M1`..`M8`；全数据集不要求跨 case 唯一 |
| `content` | string | ✅ | 自然语言记忆正文（中文为主，技术名词保留英文） |
| `subject` | string | ✅ | 槽位实体 |
| `predicate` | string | ✅ | 槽位属性 |
| `scope` | string | ✅ | `global` 或 `branch:xxx` |
| `memory_type` | string | ✅ | `DECISION` / `CONSTRAINT` / `PREFERENCE` / `EPHEMERAL` |
| `input_weight` | number | ✅ | `[0.1, 1.0]` |
| `parent_ids` | array<string> | ❌ | 省略 = 无父；元素必须是**本 case 中更早出现**的 event id |
| `residual_diff` | string | ❌ | **纯自然语言原因**，不得带 `[Replaced:` 前缀，但**必须提及被替代的旧技术关键词**（如 `MySQL`） |

### 3.4 probe 字段

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :---: | :--- |
| `probe_type` | string | ✅ | `current_state` / `anti_trap` / `evolution_why`，一个 case 内三者各一条 |
| `query` | string | ✅ | 自然语言提问 |
| `must_include` | array<string> | ✅ | 非空；判定时对 `injected_text` / `returned_diff` 做**大小写不敏感**子串包含 |
| `must_exclude` | array<string> | ✅ | 可为空数组 |
| `expect_survive` | array<string> | ❌ | 仅 `anti_trap` 使用：必须出现在 `injected_node_ids` 里的节点 id |
| `old_keyword` | string | ❌ | 仅 `evolution_why` 使用：必须在 `returned_diff` 中出现 |
| `expect_nodes` | array<string> | ❌ | 建议填：`current_state` 期望被注入的节点 id 列表（供人工复核，不参与判定） |

### 3.5 硬约束（校验器必须逐条检查并打印 OK/FAIL）

1. `case_count == len(cases) == 40`，`scenario_id` 为 `S01..S40` 连续唯一。
2. 每个 case 的 `session_events` 长度 ∈ [6, 8]。
3. 每个 case 的 `probes` 恰好 3 条，且 `probe_type` 三者各一。
4. `domain` 去重后 ≥ 6 种。
5. **多亲用例 ≥ 3 组**：至少一个 event 的 `parent_ids` 长度 ≥ 2（`tags` 含 `multi_parent`）。
6. **scope 隔离用例 ≥ 4 组**：至少一个 event 的 `scope` 以 `branch:` 开头，且该 case 内存在**同 subject+predicate 但不同 scope** 的节点（`tags` 含 `scope_isolation`）。此类 case 的 `current_state` 探针必须验证"跨 scope 不互相覆盖"。
7. **假冲突用例 ≥ 2 组**：存在 subject 相同但 predicate 不同（或语义相近但槽位不同）的节点，**不得**发生覆盖（`tags` 含 `fake_conflict`）。
8. **负控制组 ≥ 8 组**：`is_control == true`，且 `construction_note` 说明控制目的。控制组应当**不包含任何真实覆盖**（或覆盖不涉及 anti_trap 靶子），用于证明 A 分支并非必然失败。
9. 引用完整性 + 全局一致性：
   - `parent_ids` 引用的 id 必须在本 case 更早出现（禁止前向引用、禁止自引用、禁止环）。
   - 每个 event 的 `memory_type` 合法、`input_weight` ∈ [0.1, 1.0]、`scope` 非空。
   - 每个发生覆盖的事件（同槽且更早存在）**必须**带 `residual_diff`，且该 diff 必须包含被覆盖旧节点 `content` 中的至少一个"技术关键词"——**校验器按以下确定性判据实现**：取旧节点 `content` 中长度 ≥ 3 的 ASCII 单词（`[A-Za-z][A-Za-z0-9_.\-]*`，如 `MySQL`、`PostgreSQL`、`React`），若旧 content 中无此类单词则取旧 content 的最后一个中文二元组；要求 diff（大小写不敏感）包含其中**至少一个**。
   - 每条 `evolution_why` 探针必须带 `old_keyword`，且该 `old_keyword` 必须出现在某条带 `residual_diff` 的 event 的 diff 文本中。

> 校验器额外产出**警告**（不 FAIL，仅记录）：`current_state` 的 `query` 建议同时提及新旧两个技术名，以暴露 A 分支的污染失败模式。

---

## 4. 分词与相似度（两套独立实现必须逐位一致）

```python
def tokenize(text: str) -> set[str]:
    s = unicodedata.normalize("NFKC", text).lower()
    toks = set(re.findall(r"[a-z0-9_]+", s))          # ASCII 整词，不做词干化
    for run in re.findall(r"[\u4e00-\u9fff]+", s):    # 连续中文片段
        toks.update(run)                               # 全部单字
        if len(run) >= 2:
            for i in range(len(run) - 1):
                toks.add(run[i:i+2])                   # 全部相邻二元组
    return toks

def rel(a_text: str, b_text: str) -> float:
    A, B = tokenize(a_text), tokenize(b_text)
    if not A or not B:
        return 0.0
    return len(A & B) / math.sqrt(len(A) * len(B))
```

- **检索文本**：
  - A 分支：`retrieval_text(v) = v.content`
  - B / C 分支：`retrieval_text(v) = v.content + " " + (v.residual_diff or "")`
- **查询文本**：`probe.query` 原文。

---

## 5. 检索与双通道注入（上次踩过的坑）

### 5.1 候选与排序

1. 候选集：A = 全部节点；B / C = `status == "active"` 的节点。
2. 对每个候选算 `rel(query, retrieval_text(v))` 与 `Score(v)`。
3. 降序排序（同分按 node_id 升序），取前 `TOPK = 5` 个作为 **injected**。

### 5.2 两条通道，严禁混流

```
injected_text  = "\n".join(v.content for v in injected, 按排序顺序)          # 事实通道
returned_diff  = "\n".join(v.residual_diff for v in injected if v.residual_diff)  # 解释通道
```

- **`residual_diff` 绝对不得出现在 `injected_text` 中。**
- 原因：C 分支的招牌就是把旧技术名写进回执（`[Replaced: … MySQL …]`）。若它同时进了注入正文，而 `must_exclude` 恰好写着 `MySQL`，C 会**在自己的核心卖点上被判失败**。这是上一轮踩过的坑，契约在此物理隔离。

### 5.3 `evolution_why` 的特殊性

- `evolution_why` **不做特殊分支**，与其余两类探针走完全相同的候选/排序/注入流程。
- 它能答对的原因只可能来自 §4 的 `retrieval_text` 包含 `residual_diff`（B/C），以及 §4.2 的记录规则。
- A 分支因为从不记录 `residual_diff`，`returned_diff` 恒为空 → `evolution_why` 必然判负（这是设计意图，不是 Bug）。

---

## 6. 判定规则（机械判定，零人味）

对每条 probe（每分支各判一次）：

```
current_state:
    pass = 所有 must_include 都是 injected_text 的子串（大小写不敏感）
           且 没有任何 must_exclude 是 injected_text 的子串

anti_trap:
    pass = 所有 must_include 都是 injected_text 的子串
           且 所有 expect_survive 都在 injected_node_ids 中

evolution_why:
    pass = returned_diff 非空
           且 所有 must_include 都是 returned_diff 的子串
           且 old_keyword 是 returned_diff 的子串
```

- **`current_state` 只扫 `injected_text`，绝不扫 `returned_diff`。**
- 大小写不敏感：两边都 `NFKC` + `lower()` 后再比较。
- 判定细节必须写入 `raw_runs.json` 的 `detail` 字段（缺哪些 include、命中哪些 exclude、缺哪些 survive）。

---

## 7. 指标与门禁

```
G1  current_state: rate(C) - rate(A) >= 0.20        （≥ 20pp）
G2  anti_trap:     rate(C) > rate(B)                （严格大于，证明连坐负收益）
G3  evolution_why: rate(C) >= 0.85
gate1_overall_pass = G1 and G2 and G3
```

- `rate = round(passed / total, 6)`，`total` = 该分支该类型探针总数（= case 数 = 40）。
- 门禁按**全量 40 组**计算；同时必须额外给出 `control` / `non_control` 分组明细（仅供参考，不参与门禁）。
- **门禁 fail 时严禁改数据集、调阈值、换指标凑数。** 如实记录 + 写诊断。

---

## 8. 产物与命令契约

### 8.1 文件清单（写作用域，互不重叠）

| 路径 | 负责人 | 说明 |
| :--- | :--- | :--- |
| `benchmarks/CONTRACT.md` | Lead | 本文件（冻结） |
| `benchmarks/tools/build_dataset.py` | qa | 生成器（数据结构描述 → 落盘 JSON） |
| `benchmarks/data/eval_cases_40.json` | qa | 40 组测试集 |
| `benchmarks/data/eval_cases.schema.json` | qa | JSON Schema（描述性，供人读） |
| `benchmarks/tools/validate_dataset.py` | qa | 校验 §3.5 九条硬约束 |
| `benchmarks/reports/dataset_label_audit.md` | qa | 标签复核报告 |
| `benchmarks/spike_cut1.py` | kernel | 三分支运行器 + `--self-test` |
| `benchmarks/results/raw_runs.json` | kernel | 逐探针原始证据 |
| `benchmarks/results/metrics.json` | kernel | 聚合指标 + 门禁结论 |
| `benchmarks/audit/independent_scorer.py` | auditor | 从零重写的独立评分器 |
| `benchmarks/results/audit_scores.json` | auditor | 独立复算结果 + 分歧清单 |
| `benchmarks/reports/audit_phase1.md` | auditor | 独立审计 + 门禁签署 |
| `benchmarks/reports/spike_cut1_report.md` | Lead | 汇总报告 |
| `docs/phase1_handoff.md` | Lead | 阶段二交接文档 |

> **任何人不得修改他人写作用域内的文件。** 需要改动请报告队长。

### 8.2 CLI 契约

```bash
# 生成数据集
python benchmarks/tools/build_dataset.py --out benchmarks/data/eval_cases_40.json

# 校验数据集（退出码 0 = 全部 OK，1 = 有 FAIL）
python benchmarks/tools/validate_dataset.py --dataset benchmarks/data/eval_cases_40.json

# 自检（退出码 0 = 通过）
python benchmarks/spike_cut1.py --self-test

# 正式跑分
python benchmarks/spike_cut1.py \
    --dataset benchmarks/data/eval_cases_40.json \
    --out-raw benchmarks/results/raw_runs.json \
    --out-metrics benchmarks/results/metrics.json

# 独立复算
python benchmarks/audit/independent_scorer.py \
    --dataset benchmarks/data/eval_cases_40.json \
    --raw benchmarks/results/raw_runs.json \
    --out benchmarks/results/audit_scores.json
```

- 所有脚本必须能在**任意工作目录**下运行（路径参数用相对路径时按 CWD 解析即可，不要求自动定位仓库根）。
- 禁止在脚本里写死绝对路径。
- 所有脚本 `--help` 必须可用。

### 8.3 `raw_runs.json` 结构

```json
{
  "contract_version": "1.0.0",
  "dataset_sha256": "<eval_cases_40.json 的 sha256 hex>",
  "case_count": 40,
  "branches": ["A", "B", "C"],
  "runs": [
    {
      "branch": "A",
      "scenario_id": "S01",
      "is_control": false,
      "probe_index": 0,
      "probe_type": "current_state",
      "query": "……",
      "ranked": [
        {"node_id": "M4", "rel": 0.512345, "f": 0.987654, "score": 0.508, "status": "active"}
      ],
      "injected_node_ids": ["M4"],
      "injected_text": "……",
      "returned_diff": "",
      "verdict": true,
      "detail": {"missing_include": [], "hit_exclude": [], "missing_survive": [], "diff_empty": false}
    }
  ]
}
```

- `runs` 顺序：**branch 外层（A,B,C）→ scenario_id 升序 → probe_index 升序**。确定性排序，禁止依赖 dict 顺序。
- `ranked` 为该次检索的完整候选排序（**截断到 TOPK 之前**，即全部候选），用于复核。

### 8.4 `metrics.json` 结构

```json
{
  "contract_version": "1.0.0",
  "dataset_sha256": "……",
  "cases_total": 40,
  "probes_per_branch": 120,
  "per_branch_probe": {
    "A": {
      "current_state": {"passed": 0, "total": 40, "rate": 0.0},
      "anti_trap":     {"passed": 0, "total": 40, "rate": 0.0},
      "evolution_why": {"passed": 0, "total": 40, "rate": 0.0}
    },
    "B": { "...": "同上" },
    "C": { "...": "同上" }
  },
  "by_group": {
    "control":     {"A": {"current_state": {"passed": 0, "total": 9, "rate": 0.0}, "...": "..."} },
    "non_control": {"A": {"...": "..."} }
  },
  "gates": {
    "G1_current_state_lead_pp": {"a": 0.0, "c": 0.0, "delta_pp": 0.0, "threshold_pp": 20.0, "pass": false},
    "G2_anti_trap_c_gt_b":      {"b": 0.0, "c": 0.0, "pass": false},
    "G3_evolution_why":         {"c": 0.0, "threshold": 0.85, "pass": false}
  },
  "gate1_overall_pass": false
}
```

- `delta_pp = round((c - a) * 100, 6)`。

### 8.5 `audit_scores.json` 结构

```json
{
  "auditor": "gemini-3.8-flash",
  "contract_version": "1.0.0",
  "probes_checked": 360,
  "divergences": [ {"branch": "C", "scenario_id": "S07", "probe_index": 1,
                    "runner_verdict": true, "auditor_verdict": false, "reason": "……"} ],
  "divergence_count": 0,
  "recomputed_metrics": { "...": "与 metrics.json 同构" },
  "metrics_match": true,
  "retrace": {
    "mode": "reimplement",
    "cases_checked": ["S01", "S12", "S23"],
    "node_set_match": true,
    "notes": "……"
  },
  "gate1_signoff": {"G1": true, "G2": true, "G3": true, "overall": true, "signed_by": "auditor"}
}
```

---

## 9. 确定性与可复现（硬性）

1. **同一数据集连续跑两次，`raw_runs.json` 与 `metrics.json` 必须逐字节相同**（`sha256` 相同）。
2. **禁止**把时间戳、主机名、运行耗时、随机数、绝对路径写进任何结果文件。
3. 禁止使用 `random`、`time`、`os.environ` 影响输出；禁止依赖 `set` 的迭代顺序（**排序前必须 `sorted()`**）。
4. JSON 落盘统一：`json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)` + 结尾换行 `\n`。

---

## 10. 工程纪律

1. **Python 3.9 语法**：禁止 `match`、禁止运行期 `X | Y` 标注；类型注解只在函数签名用 `typing.Optional/List/Dict`。
2. **仅标准库**：`import` 任何第三方包即视为交付失败。
3. **中文注释**：所有模块 docstring 与关键注释用中文。
4. **Git**：**成员一律不执行任何 `git` 命令**（多人共用同一 index 会撞 `.git/index.lock`）。由队长在每个任务交付后统一提交，提交信息用中文：
   - `feat(dataset): 40 组演进与 Anti-trap 测试集`
   - `feat(dataset): 九条硬约束校验器与标签复核`
   - `feat(spike): 三分支首刀运行器与自检`
   - `feat(results): 三分支消融原始证据与门禁指标`
   - `feat(audit): 独立评分器与门禁签署`
5. **禁止臆造数据**：报告里每个数字都必须能从 `raw_runs.json` / `metrics.json` 反查。

---

## 11. 与计划书的偏离声明（必须写进最终报告）

- **D1 双盲 LLM 裁判 → 机械判定 + 独立重写交叉核对**。计划书 §5 写"双盲 LLM 裁判"，不可复现且违反 ¥0 预算。改为：kernel 按本契约 §6 机械判定；auditor **独立从零重写**评分器（不读 kernel 的实现思路），逐 probe 交叉核对，要求**零分歧**；再抽 3 个 case 独立重实现仿真，比对 `injected_node_ids`。
- **D2 连坐系数 ψ 已物理砍除**。B 分支只是对照组，实现为"子孙标 `superseded`"，**不存在任何 ψ 连乘**。
- **D3 不使用 StateMemBench**。阶段一为 ¥0、无网络，改用 40 组自造演进集；因此结论**只能**声称"在本数据集上"的方向性证据，不得外推为 SOTA 结论。
- **D4 `[Replaced:` 前缀由运行时拼装**，数据集里的 `residual_diff` 必须是纯自然语言原因 + 提及旧技术关键词。
- **D5 阶段一不写任何生产代码**（无 SQLite / 事件溯源 / MCP / CLI / HTML）。

---

## 12. 自检清单（kernel 的 `--self-test` 必须全部断言）

1. `R(0) == 1.0`（对四种类型）。
2. `R(H) ≈ 0.5`，其中 `H = t0 * (2**(1/beta) - 1)`。
3. `R(2H) == (2 * 2**(1/beta) - 1)**(-beta)`（`rel_tol=1e-6`）**且 `R(2H) > 0.25`**。
4. 四类型在 `input_weight=0.5, Delta=2H` 下的实测值约为 `0.4665 / 0.4830 / 0.4510 / 0.3231`（`rel_tol=1e-3`，用于防止常数表被抄错）。
5. 三分支在同一条内置微用例（MySQL→PG + 挂载规范）上的行为符合 §2：A 注入新旧并存；B 误杀规范；C 规范存活且 `returned_diff` 含 `MySQL`。
6. 分词器：`tokenize("MySQL 8.0 主数据库")` 必须同时含 `"mysql"`、`"8"`、`"0"`、`"主"`、`"数据"`、`"据库"`。
7. `rel` 对称性与空集返回 0.0。
8. 连续跑两次（自检内部构造的小数据集）输出字节相同。

---

*契约冻结于阶段一启动时。任何修改必须由队长签发新版本号并通知全部成员。*
