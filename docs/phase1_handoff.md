# 阶段一 → 阶段二 交接文档

> **阶段**：Gated-Mem v2.1.1 阶段一（Day 1–2，首刀验证）已完成
> **交接人**：Tech Lead   **接手方**：阶段二执行者
> **本阶段结论**：门禁 1 三项全过，但存在必须继承的覆盖缺口（见 §5）
> **最后提交**：`bd7acba feat(audit): 独立评分器与门禁签署（零分歧 360/360）`

---

## 1. 阶段一结论

**门禁 1 三项全部达标，`gate1_overall_pass = true`。**

| 门禁 | 判据 | 实测 | 结论 |
| :--- | :--- | :--- | :---: |
| G1 | rate(C) − rate(A) ≥ 20pp（current_state） | +80.00pp | PASS |
| G2 | rate(C) > rate(B)（anti_trap，严格） | 1.00 > 0.20 | PASS |
| G3 | rate(C) ≥ 0.85（evolution_why） | 1.00 ≥ 0.85 | PASS |

独立签署：`divergence_count = 0`（360/360 probe），`metrics_match = true`，数值层最大偏差 `0.000000000`。

**一句话定性**：槽位覆盖 + 不连坐（C）相对纯向量（A）在 current_state 上 +80pp、相对强连坐（B）在 anti_trap 上 +80pp，方向明确、机制可解释、数字逐字节可复现；但绝对水平受 40 组同构构造强烈支撑，**不得外推为 SOTA**。

---

## 2. 三分支消融数据表（阶段二任何报告都可以直接引用）

| 分支 | current_state | anti_trap | evolution_why |
| :--- | ---: | ---: | ---: |
| **A** 纯向量基线 | 20.00%（8/40） | 100.00%（40/40） | 0.00%（0/40） |
| **B** v2.0 强连坐 | 92.50%（37/40） | 20.00%（8/40） | 100.00%（40/40） |
| **C** v2.1.1 终审 | **100.00%**（40/40） | **100.00%**（40/40） | **100.00%**（40/40） |

反查路径：`benchmarks/results/raw_runs.json`（360 条原始 run，含每个候选的 rel/f/score）→ `benchmarks/results/metrics.json`（聚合）→ `benchmarks/results/RESULTS_SUMMARY.md`（人读）。

---

## 3. 关键发现（阶段二设计的输入）

### 3.1 连坐负收益 = −80.00pp（anti_trap 格）
B 从 A 的 100% 跌到 20%，32 条失败**全部**是 `missing_survive = ["M2"]` —— 靶子节点被传递闭包株连标 superseded，从候选集消失。没有一条是检索质量问题。

### 3.2 连坐的第二类伤害（契约未预期，最有价值）
B 的 current_state 失分 3 条（S07 缺 OpenAPI 3.0、S19 缺 MessagePack、S35 缺金丝雀发布），根因是承载**当前态事实**的旁支节点也被连坐杀掉。
**这直接说明**：连坐不只误杀旧规范，还会误杀新事实的邻接上下文。这条应当写进阶段二 `conflicts.py` 的动机论证，也是 `stale_parent_warning`（只警告不杀）设计的实证依据。

### 3.3 双通道物理隔离成立（上一轮最大的坑已封堵）
- `injected_text` 只由 content 拼接；`returned_diff` 只由 residual_diff 拼接。
- 实测：`must_exclude` 词在 C 的 `injected_text` 中命中 **0 次**；`[Replaced: … MySQL …]` 只走回执。
- C 的 evolution_why = 100%，`diff_empty` 出现 0 次。

### 3.4 【最重要】TOPK 截断几乎从未发生：本实验没有测检索排序
从 `raw_runs.json` 复核（gemini_audit 独家发现，队长已验证）：

| 分支 | 候选数分布 | 未截断(≤5) | 真实截断 |
| :--- | :--- | ---: | ---: |
| A | 6×108、7×12 | 0/120 | 120/120 |
| B | 3×69、4×27、5×24 | 120/120 | **0/120** |
| C | 5×108、6×12 | 108/120 | 12/120 |

**含义（阶段二必须理解）**：
- 单用例 6–8 事件，覆盖/连坐后活跃节点只剩 3–6 个，几乎总被全量注入 → `Score = rel · F^λ` 的排序筛选在 B/C 上**根本没起作用**。
- λ 扫描全过不是「稳健」，而是 λ **没有机会影响注入集合**。
- 阶段一实际验证的是「状态门控正确性」，**不是**「检索排序有效性」。
- A 是唯一真正截断的分支（120/120），所以 A 的 20% 里混着排序影响，与 B/C 口径不完全对等。

### 3.5 A 的失败模式是「事实污染」
`must_exclude` 在 injected_text 的命中次数：A = 32、B = 0、C = 0。S01 典型：正文同时含 MySQL 8.0 与 PostgreSQL 16。

---

## 4. 契约偏离计划书的地方（阶段二需继续遵守）

| 编号 | 偏离内容 | 原因 | 阶段二是否继续 |
| :--- | :--- | :--- | :--- |
| D1 | 双盲 LLM 裁判 → 机械判定 + 独立重写交叉核对 | 不可复现 + ¥0 预算 | 继续，且阶段二应扩展到 pytest 层的交叉断言 |
| D2 | 连坐 ψ 物理砍除，B 只做状态标杀 | 终审裁决 | 继续，ψ 不得复活 |
| D3 | 不用 StateMemBench，用 40 组自造集 | 零预算无网络 | 阶段二若仍 ¥0，继续自造；若放开预算，需补真实基准 |
| D4 | `[Replaced: ` 前缀由运行时拼，数据集侧纯自然语言 | 数据集与机制解耦 | 继续，`conflicts.py` 必须实现前缀拼装 |
| D5 | 阶段一不写生产代码 | 计划书分期 | 已完成，阶段二可开始写 `src/` |

---

## 5. 已踩过的坑清单（给阶段二的人避雷）

### 5.1 组织与执行层
1. **不要让子代理一次性输出 40 组 JSON** —— 会被中断且全部丢失。必须写生成器脚本、由脚本落盘。上一轮连续失败两次的直接原因。本轮 qa 用 `build_dataset.py` 一次通过。
2. **`antigravity`（agy CLI）通道不可靠** —— 本轮 auditor 走该路由 3 小时空闲无输出、零落盘，触发了 `AGENT_TEAM_SETUP.md §7` 的降级预案，改派 `workbuddy/deepseek-v4.1-flash` 后 10 分钟内完成。**阶段二若仍需要 Gemini 做异模型审计，建议直接配成 workbuddy 路由，或预留降级时间。**
3. **多人共用同一 git index 会撞 `.git/index.lock`** —— 已在 CONTRACT §10.4 规定成员一律不跑 git，由队长统一提交。阶段二沿用此纪律。
4. **写作用域必须互不重叠** —— 本轮 5 个任务的作用域全部不相交，零冲突。

### 5.2 数据构造层
5. **`residual_diff` 绝对不能进 `injected_text`** —— C 分支的招牌是把旧技术名写进回执，若同时进注入正文而 `must_exclude` 恰含旧词，C 会死在自己的核心卖点上。契约 §5.2 已物理隔离，实测命中 0 次。
6. **数据集必须包含负控制组** —— 8 组控制组证明 A 的失败是机制性的而非必然的（A 在控制组上 8/8 满分）。没有控制组，整场实验无法排除「A 就是不行」的替代解释。
7. **40 组共用同一事件骨架导致天花板效应** —— 参数扫描 10 种组合门禁全过，说明数据集区分力弱。阶段二必须换非同构数据。

### 5.3 跨模型复核暴露的机制盲点（P0，最高优先级）
13. **TOPK 从未真正截断** —— B 分支 120/120 次、C 分支 108/120 次都是全量注入。`Score = rel · F^λ` 的排序能力零检验。**阶段二必须把单场景节点数扩到 15–30，迫使候选池远大于 TOPK**，否则你无法声称检索公式被验证过。
14. **同模型审计的制衡失效** —— auditor2 与 kernel 同为 deepseek-v4.1-flash，它的「零分歧」只能证明实现符合契约，不能证明机制正确。异模型复核（gemini_audit）才发现了 TOPK 盲点。**阶段二务必保留一个异模型审计位。**

### 5.4 跨模型复核结论（gemini_audit）

`benchmarks/reports/audit_crosscheck_gemini.md`：独立复算 9 格 + 18 分组格逐格一致，360 条 run 判定与注入集合（含顺序）361/360 一致，`divergence_count = 0`，三项门禁 PASS，**同意放行门禁 1**，判定为「有条件支持」：

> 本实验能证明「槽位覆盖消除事实污染、双通道隔离防止旧词自伤、不连坐避免误杀」三项设计假设正确、可复现、方向明确；但因数据强同构与全集注入特性，**禁止外推为通用 SOTA**。

它给出的 3 项 P0 整改约束（阶段二必须继承）：
1. **补多代演进用例**（祖先 → 父 → 子孙），实测传递闭包与多跳连坐；
2. **扩大事件规模到 15–30 节点**，恢复 TOPK 排序筛选；
3. **`stale_parent_warning` 显式落盘**，消除内部黑盒状态。

### 5.5 契约层（1.0.1 建议修订，阶段二如沿用契约需先修）
8. **AMB-3：B 的传递闭包完全没被验证** —— 连坐深度恒为 1，改成「只标直接子节点」后 0/120 差异。阶段二补三代演进用例（覆盖节点 → 子 → 孙）。
9. **AMB-4：`stale_parent_warning` 对外不可观测** —— 打了 59 个标签但从未出现在任何产物里。建议 `raw_runs` 的 run 级增加 `stale_warnings` 字段，把 C 分支的招牌能力做成可验证的。
10. **AMB-1：排序键用原始值还是舍入值** —— 契约未明确。建议写明「排序键用未舍入原始浮点，round 只在序列化时做」。
11. **AMB-2：B 连坐是快照还是持续传染** —— 契约文字没有排除后者。本轮实测无差，但语义必须钉死。
12. **AMB-7：同槽多旧节点时 `old` 的选取时机** —— 每组件恰 1 次覆盖，该路径从未被数据触发。

---

## 6. 阶段二的接口约定

阶段一的产物是**纯脚本**（无包结构、无 import 关系）。阶段二开始写 `src/gated_mem/` 时，以下签名必须与阶段一的契约语义对齐。

### 6.1 `src/gated_mem/schema.py`

```python
# 五状态枚举（阶段一 B/C 分支只用到前两个，其余为阶段二扩展）
STATUS_ACTIVE = "active"
STATUS_CANDIDATE_CONFLICT = "candidate_conflict"
STATUS_SUPERSEDED = "superseded"
STATUS_ARCHIVED = "archived"
STATUS_KILLED = "killed"

# 四记忆类型（阶段一 CONTRACT §1.1 已固化，不得改动）
MEMORY_TYPES = {"DECISION": 0.10, "CONSTRAINT": 0.05, "PREFERENCE": 0.15, "EPHEMERAL": 1.20}   # beta
T0_BASE     = {"DECISION": 100,  "CONSTRAINT": 200,  "PREFERENCE": 80,   "EPHEMERAL": 5}       # 步

# dataclass 字段（与 CONTRACT §3.3 一一对应，阶段一数据集可直接喂进来）
@dataclass
class MemoryNode:
    node_id: str; content: str; subject: str; predicate: str; scope: str
    memory_type: str; input_weight: float; parent_ids: List[str]
    residual_diff: Optional[str] = None
    status: str = STATUS_ACTIVE
    stale_parent_warning: bool = False      # ← 阶段二必须让它可观测，见坑 9
    pinned: bool = False
    step: int = 0

@dataclass
class MemoryEvent:
    event_id: str; step: int; event_type: str
    causation_id: Optional[str]; correlation_id: str
    payload_json: str
```

### 6.2 `src/gated_mem/gates.py`

```python
def t0(node) -> float:
    """t0(v) = t0_base(type) * (0.5 + input_weight)"""

def retention_R(node, delta: int) -> float:
    """R(v) = (1 + delta / t0) ** (-beta)；delta = CASE_STEP - v.step"""

def vitality_F(node, nodes_by_id) -> float:
    """pinned -> 1.0;否则 min(1.0, R + GAMMA * max(R of active parents))；GAMMA=0.2"""

def score(node, query, nodes_by_id) -> float:
    """score = rel(query, retrieval_text(node)) * (F ** LAMBDA)；LAMBDA=0.3"""

def retrieval_text(node, branch: str) -> str:
    """A: content / B,C: content + ' ' + (residual_diff or '')  ← 阶段一已验证的关键点"""

def rank(candidates, query, nodes_by_id, topk: int = 5) -> List[MemoryNode]:
    """降序，同分按 node_id 升序；排序键用未舍入原始浮点（见坑 10）"""
```

### 6.3 `src/gated_mem/conflicts.py`

```python
def slot_of(node) -> Tuple[str, str, str]:
    """(subject, predicate, scope) 精确相等才算同槽"""

def apply_supersede(new_node, old_nodes, nodes_by_id) -> str:
    """C 分支语义:
    - 全部同槽 active 旧节点标 superseded；old 取 node_id 字典序最小者
    - 旧节点的直接子节点置 stale_parent_warning=True，status 保持 active（不递归）
    - 返回拼好的 residual_diff: '[Replaced: ' + old.subject + ' / ' + old.content[:30] + '] ' + 原始原因
    """
```

### 6.4 门禁复核入口

阶段一的门禁逻辑在 `benchmarks/spike_cut1.py` 的 `compute_metrics()`，字段结构见 CONTRACT §8.4。阶段二若要复用，直接抄 `gates` 与 `gate1_overall_pass` 的构造方式即可，**不要重新设计指标口径**。

---

## 7. 环境与命令速查

```bash
# 环境
#   Windows + Python 3.9.13（禁 match 语句、禁运行期 X | Y 联合类型标注）
#   仅标准库：json math re unicodedata hashlib argparse os sys collections typing dataclasses
#   零第三方依赖，零网络调用，零 API 预算

# 全流程复现（4 步）
python benchmarks/tools/build_dataset.py --out benchmarks/data/eval_cases_40.json
python benchmarks/tools/validate_dataset.py --dataset benchmarks/data/eval_cases_40.json
python benchmarks/spike_cut1.py --self-test
python benchmarks/spike_cut1.py --dataset benchmarks/data/eval_cases_40.json \
    --out-raw benchmarks/results/raw_runs.json \
    --out-metrics benchmarks/results/metrics.json
python benchmarks/audit/independent_scorer.py \
    --dataset benchmarks/data/eval_cases_40.json \
    --raw benchmarks/results/raw_runs.json \
    --out benchmarks/results/audit_scores.json
```

### 7.1 预期输出（校验是否跑对）

| 命令 | 期望 |
| :--- | :--- |
| `build_dataset.py` | 退出 0，输出 171617 B，sha256 `8ec9e405…` |
| `validate_dataset.py` | 退出 0，九条全 OK，警告 0 条 |
| `spike_cut1.py --self-test` | 8/8 PASS，退出 0 |
| 正式跑分 | `raw_runs.json` sha256 `eaa29127…`，`metrics.json` sha256 `b63be262…` |
| `independent_scorer.py` | `divergence_count = 0`，`metrics_match = True`，`gate1_overall_pass = True` |

注：sha256 只在数据集不变的前提下有效。若修改了数据集，sha 全部会变，但**门禁口径**与**判定规则**不得随之调整。

---

## 8. 阶段一 Git 提交记录

```
bd7acba feat(audit): 独立评分器与门禁签署（零分歧 360/360）
1a594ee feat(results): 三分支消融原始证据与门禁指标（门禁 1 三项全过）
f18d47f feat(dataset): 40 组演进与 Anti-trap 测试集、九条硬约束校验器与标签复核
31cb84c feat(spike): 三分支首刀运行器与自检
455fbfb chore(baseline): 阶段一基线 - 冻结契约 CONTRACT.md 与 gitignore
76d932f init
```

`.gitignore` 已排除 `.agent-teams/`（AgentTeams 运行时状态）与 `__pycache__/`。

---

## 9. 阶段二开工检查清单

- [ ] 先读 `benchmarks/CONTRACT.md`（12 节全文）与本文档
- [ ] 读 `benchmarks/results/RESULTS_SUMMARY.md` 的 §7 诚实边界
- [ ] 读 `benchmarks/reports/audit_phase1.md` 的 §3（七条契约歧义）与 §5.4（签署效力边界）
- [ ] **P0-1 补三代演进用例**（AMB-3，覆盖节点 → 子 → 孙），并重跑门禁，确认传递闭包真的被测到
- [ ] **P0-2 把单场景节点数扩到 15–30**，让候选池远大于 TOPK=5，真正考核 `rel · F^λ` 的排序淘汰（否则检索公式等于没测）
- [ ] **P0-3 让 `stale_parent_warning` 落盘**（AMB-4），否则 C 的招牌能力无法从产物验证
- [ ] 保留一个**异模型审计位**（阶段一的 auditor2 与 kernel 同模型，制衡失效；靠 gemini_audit 才补上）
- [ ] 契约升版到 1.0.1，修掉 AMB-1 / AMB-2 / AMB-7 的文字漏洞
- [ ] 阶段二只写 `src/gated_mem/` 下的生产代码，**不要**回改 `benchmarks/` 的既有产物
- [ ] 单测必须断言 `R(0)=1`、`R(H)=0.5`、`R(2H) == (2*2**(1/beta)-1)**(-beta)` 且 `R(2H) > 0.25`（阶段一自检已验证数值：0.4665 / 0.4830 / 0.4510 / 0.3231）
- [ ] 边方向严格 `source_id = child → target_id = parent`
- [ ] stdio 严禁任何 `print` 污染 stdout

---

## 10. 一句话给阶段二

**阶段一证明了「槽位覆盖 + 不连坐 + residual_diff 双通道」在受控数据上方向正确、机制可解释、结果可复现。但它同时暴露了三个致命的数据缺口：连坐深度恒为 1（传递闭包没被测到）、TOPK 从未真正截断（检索排序没被测到）、`stale_parent_warning` 从不落盘（C 的招牌能力无法观测）。阶段二的第一件事不是写代码，是把这三块补上——否则你会带着三个未被验证的机制进入生产。**
