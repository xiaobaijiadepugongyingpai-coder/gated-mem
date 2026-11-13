# HANDOFF · experiments_v2 交接说明

> **交接时间**：2026-11-13
> **状态**：骨架可运行，`E0` 与 `E3` 已跑通并产出真实数据；`E1` / `E2` / `E4` 未开始。
> **边界**：本目录**只读调用** `src/gated_mem/`，**未修改** `src/`、`tests/`、
> `benchmarks/`、`docs/`、`total_plan/` 下任何文件。

---

## 1. 这个目录是干什么的

现有四轮实验（phase1–phase4）全部在**自造数据**上验证，回答的是
「机制实现了没有」。本目录补的是另一个问题：

> **在别人造的数据上，它是否比基线更好？**

三个具体的验证缺口（详见 `README.md` §0 与 `PROVENANCE.md`）：

| # | 缺口 | 证据 |
|---|---|---|
| G1 | 融合相对**最强单通道**只是 +0pp | `phase4_hard_negatives_report.md`：vec 60% / **fts 100%** / fusion 100% |
| G2 | "严格优于单通道"被代码自己判为不可达 | `benchmarks/gate3_check.py:101` 注释："严格高于"在数学上不可达 |
| G3 | 数据集构造决定结论 | 20 组全是"query 内嵌唯一精确标识符" + 同模板 |

---

## 2. 已完成的工作

### 2.1 文件清单

```
experiments_v2/
├── README.md                      ← 方案设计（目标、臂、判定阈值、模型分工）
├── HANDOFF.md                     ← 本文件
├── PROVENANCE.md                  ← 数据与数字的来源、sha256、可信度
├── run_env.py                     ← E0 环境探测              ✅ 已跑通
├── selfcheck_e0.py                ← 适配层自检                ✅ 全过
├── dl/
│   └── fetch_mab.py               ← MemoryAgentBench 获取      ⚠️ 依赖未装，未跑
├── adapters/
│   └── gated_store.py             ← 驱动 src/gated_mem 的适配层 ✅ 已验证
├── arms/
│   ├── definitions.py             ← 7 臂定义                  ✅
│   └── lenient_match.py           ← 宽松匹配                  ✅ 13/13 自测通过
├── data_gen/
│   └── build_naturalized.py       ← 生成 4 种查询形态          ✅ 产出 80 行
├── runners/
│   └── e3_naturalized.py          ← E3 检索层评测             ✅ 已跑出数据
├── data/
│   └── e3_naturalized.json        ← 80 条查询（sha256 见 PROVENANCE）
└── results/
    ├── e0_env.json
    ├── e3_naturalized_builtin.md
    └── e3_naturalized_builtin.json
```

### 2.2 已验证通过

| 项 | 命令 | 结果 |
|---|---|---|
| 环境探测 | `python experiments_v2/run_env.py` | `src/gated_mem` v1.0.0 可导入，接口齐全；sqlite 3.39.3、numpy 1.26.4 正常 |
| 适配层自检 | `python experiments_v2/selfcheck_e0.py` | **3/3 通过**（基础驱动 / A1 无覆盖语义 / 各臂开关生效） |
| 宽松匹配 | `python experiments_v2/arms/lenient_match.py` | **13/13 通过** |
| E3 数据生成 | `python experiments_v2/data_gen/build_naturalized.py` | 80 行，sha256 `e1d0d96a…` |
| E3 检索评测 | `python experiments_v2/runners/e3_naturalized.py --provider builtin` | 见 §3 |

---

## 3. E3 的实测结果与它的意义（**本次最重要的产出**）

### 结果

Top-1 命中率：

| 查询形态 | A1_vector | A2_fts | A4_slot_fusion |
|---|---|---|---|
| 含精确标识符 | 65.0% | **100.0%** | **100.0%** |
| 同义改写 | 25.0% | 25.0% | 25.0% |
| 指代改写 | 25.0% | 25.0% | 25.0% |
| 口语改写 | 15.0% | 15.0% | 15.0% |

### 三条解读

**① FTS 从 100% 崩到 15%（−85pp）。**
这证实了阶段四的 "+40pp" 是**数据构造的产物**：那组 query 全部内嵌唯一精确
标识符，正是 FTS 的绝对主场。一旦按真实提问方式去掉标识符，FTS 的优势完全消失。

**② 三个臂在改写形态上完全同分（25 / 25 / 15）。**
说明无标识符时，`BuiltinHashEmbedder` 与 FTS 都提供不了区分信号。

**③ 但这个结果还不能用来评价融合的真实上限。**
因为 `BuiltinHashEmbedder` 是**字符 n-gram 哈希，不是真实语义模型**。
要看到向量通道在改写形态的真实表现，**必须换 `FastEmbedProvider` 重跑**。
这是下一棒最该先做的事（见 §4.1）。

### 顺带修掉的一个真实数字问题

阶段四报告与 README 里写的「难负例混合增益 **+40pp**」，
严格说是「融合 vs **单向量**」的差值。同一张表里 **fts 单通道已是 100%**，
所以融合相对**最强单通道**是 **+0pp**。

`gate3_check.py:101` 自己已经诚实处理为 `SKIP` 并注明原因，
但对外文案容易读成"混合比单通道好 40 点"。建议改为：

> 「融合 vs 单向量 +40pp；本数据集上单 FTS 亦达 100%，即融合 ≥ 任一单通道
> 但未超越 FTS。」

---

## 4. 下一棒要做什么（按优先级）

### 4.1 【最高优先】用真实语义模型重跑 E3

**为什么最优先**：这是唯一能验证「融合是否真的优于任何单通道」的实验，
而且是**零 LLM 成本、纯本地、完全确定性**的。

```bash
# 需要先在已装 fastembed 的环境里跑（注意：不是 base 环境）
<conda-env>/python experiments_v2/runners/e3_naturalized.py --provider fastembed

# 再补上 A5_full 与 A3_slot，跑全 6 臂
python experiments_v2/runners/e3_naturalized.py --provider fastembed \
    --arms A1_vector,A2_fts,A3_slot,A4_slot_fusion,A5_full
```

**预期**：向量通道在 q1–q3 上应明显高于 25%/15%。
若成立，则第一次拿到「融合严格优于任何单通道」的证据。

**注意**：`gated_store.py` 已修复过一个关键坑——
向量必须在写入时落进 `embedding` 字段，否则 `s_vec` 恒为 0，
各臂会退化成同一结果（这个坑本次踩过，注释已留）。

### 4.2 【次优先】E1 · MemoryAgentBench Conflict_Resolution

**卡点**：`datasets` 库未装好（本次 `pip install datasets` 挂起 15 小时未完成，
已 kill）。两条出路：

**A. 装库**（推荐先试，换国内源）
```bash
python -m pip install datasets -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**B. 离线 parquet**（网络受限时）
```bash
# 在能联网的机器上
huggingface-cli download ai-hyz/MemoryAgentBench --repo-type dataset --local-dir ./mab
# 拷回本机后
python experiments_v2/dl/fetch_mab.py --parquet "./mab/data/Conflict_Resolution-*.parquet"
```

装好后：
```bash
python experiments_v2/dl/fetch_mab.py            # 打印真实规模 + 落 jsonl
python experiments_v2/runners/e1_mab_cr.py       # ← 尚未编写，见下
```

**`e1_mab_cr.py` 尚未编写**。编写时必须遵守：

| 要求 | 原因 |
|---|---|
| 用 `lenient_match.match()` 判分 | 官方 `exact_match` 极严，`"label: 43"` 判错 |
| 同时报 `single_hop_acc` / `multi_hop_acc` / **`in_pool_rate`** / `ctx_tokens` | `in_pool_rate` 缺了会让"靠拒答刷低污染率"伪装成好结果（L1 §6.3） |
| `recall(write_event=False)` | 否则命中的噪音会被 `touch_citation` 续命，A/B 失效 |
| 用**强**答案模型且固定版本 | 弱模型上机制不可见（L1 Table 5） |

**已发表的对照锚点**（不重跑，直接引用）：
- 单跳：GPT-4o 记忆 agent **60%**
- 多跳：**所有方法 ≤7%**

### 4.3 E2 · Memora（FAMA）

```bash
git clone https://github.com/geniesinc/Memora
cd Memora && uv sync
```
只跑 `data/weekly/`（10 persona × 15 题 = 150 题）。
**唯一有 `forgetting_absence` 子项的官方指标**，这才是"遗忘"的卖点所在。
需要 LLM judge，成本省不掉。

### 4.4 E4 · 40 项目桥接（决定生死）

**只有它能回答「agent 是否真的少写错代码」。任何公开 benchmark 都测不了。**

- 脚手架：`github.com/WenJing95/stale-docs-data`
  （⚠️ **仅核实到仓库存在，未验证内容结构，clone 后先确认**）
- 五臂：①无记忆 ②纯向量 ③**纯 prompt 状态改写** ④Gated-Mem ⑤一行话修复
- 两个 regime：**(a) ~5k tokens（装得下）** / **(b) ~40k tokens（装不下）**
  ← 只有 (b) 能体现存储价值
- 用 gemini3.8f 订阅跑（agentic loop，模型是**控制变量**不是被测对象）

**判定逻辑（已写死，防事后解释）**
```
④≤③ 且 ④≤⑤                → 停止，存储无价值
④>③ 但 ④≤⑤                → 转向 prompt/skill 模板
④>⑤ 且 Δ(b)>Δ(a)           → Go
④>⑤ 但 Δ(b)≈Δ(a)           → 可疑，赢的是 prompt 质量
```

---

## 5. 踩过的坑（省下一棒的时间）

这四条都是本次实际调试出来的，不看会重走一遍：

### 5.1 `insert_memory()` 返回的是 **event_id，不是 memory_id**

```python
mid = store.insert_memory(node)   # ❌ mid 是 event_id
store.insert_memory(node)
mid = node.memory_id              # ✅ 正确
```

踩坑表现：命中率恒为 **0%**，且不报任何错。
因为拿 event_id 去和 `RecallItem.memory_id` 比对，永远不相等。

### 5.2 向量通道只在 `provider` 非 None 时才算

`src/gated_mem/retrieval.py:150`：
```python
if q_vec is not None and node.embedding:   # q_vec 只在 self.provider 存在时产生
```
⇒ 不注入 provider，`s_vec` 恒为 0，**所有臂会退化成同一结果**。
另外 embedding 必须在**写入时**落进 `node.embedding` 字段。

### 5.3 phase4 数据里记忆的 ID 字段叫 `id`，不是 `memory_id`

```text
memories[i] keys: content / id / identifier / input_weight /
                  memory_type / predicate / step / subject / value
```

### 5.4 PowerShell 重定向会写成 GBK

`python xxx.py > out.txt` 在中文 Windows 上会产出非 UTF-8 文件，
Python 读不了。用 `| Out-File -Encoding utf8`，或
`$env:PYTHONIOENCODING="utf-8"`。

---

## 6. 判定阈值（已写死在 README，勿事后改）

```text
H1 槽位覆盖有效      A3 - A1 单跳 ≥ +5pp  且  多跳 ≥ +2pp
H2 融合优于最强单通道 A4 - max(A1, A2) ≥ +3pp        ← 现有实验从未检验
H3 生命力有增量      A5 - A4 ≥ +3pp
H4 存储优于纯 prompt  max(A3..A5) - A6 ≥ +5pp        ← 最关键
H5 遗忘有收益        A3 的 forgetting_absence > A1 且 FAMA +2 以上
H6 改写形态落差      见 E3 落差表
```

---

## 7. 预算现状

| 实验 | 已花 | 预计 |
|---|---:|---:|
| E0 环境探测 | **¥0** | ¥0 |
| E3 检索层（零 LLM） | **¥0** | ¥0 |
| E1（MAB CR × 6 臂） | — | ¥10–30 |
| E2（Memora weekly） | — | ¥20–50 |
| E4（订阅，¥0 现金） | — | ¥0 |
| **合计** | **¥0** | **¥45–110**（走 DeepSeek 谷时再省约 50%） |

**目前一分钱没花，已拿到一条有信息量的负结果。**

---

## 8. 需要下一棒先确认的三件事

1. **`fastembed` 装在哪个环境？**
   本次 `run_env.py` 用的是 `<base-python>`（base，Python 3.9.13），
   但 phase4 报告提到专用环境 `<conda-env>/`。
   跑 `--provider fastembed` 要用后者。

2. **`datasets` 装不上的原因？**
   本次挂起 15 小时未完成，可能是网络。需要换源或走离线 parquet 路径。

3. **`deepseek v4.1f` 走 API key 还是订阅通道？**
   这决定 `e1_mab_cr.py` 里 LLM 客户端的写法。
   目前 `run_env.py` 只探测了环境变量（`DEEPSEEK_API_KEY` 等），
   四个 provider **全部未配置**。

---

## 9. 一句话交接

> **骨架能跑、适配层已验证、已用零成本拿到一条真实负结果
> （FTS 的优势完全来自"query 内嵌精确标识符"这个数据构造，
> 去掉标识符后从 100% 崩到 15%）。**
> **下一棒最该做的第一件事，是换 `FastEmbedProvider` 重跑 E3 ——
> 那是唯一能判断"融合是否真的优于任何单通道"的实验，且仍然零成本。**
