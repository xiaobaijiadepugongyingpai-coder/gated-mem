# experiments_v2 · 外部效度验证

> **本目录只读调用 `src/gated_mem/`，不修改任何既有文件。**
> 现有 Gate 2 / Gate 3 的验证与 176 项单测保持原样不受影响。
> 本目录的唯一目的：补上「**公开数据上的外部效度验证**」。

---

## 0. 为什么要有这个目录

现有四轮实验（phase1–phase4）的工程交付是扎实的：176 单测、90% 覆盖、零依赖净室安装、
跨表原子 undo、AST 防连坐回流、setup/uninstall 逐字节可逆。

但**验证链有一个结构性缺口**：所有实验都在**自己造的数据**上，回答的是
「机制实现了没有」，而不是「**在别人造的数据上，是否比基线更好**」。

三个具体缺口：

| # | 缺口 | 证据 |
|---|---|---|
| G1 | 融合相对**最强单通道**是 +0pp | `phase4_hard_negatives_report.md:19-25`：vec 60% / **fts 100%** / fusion 100% |
| G2 | 严格优于单通道被代码自己判为不可达 | `benchmarks/gate3_check.py:101` 注释："严格高于"在数学上不可达 |
| G3 | 数据集构造决定结论 | 20 组全部「query 内嵌唯一精确标识符」+ 同模板，是 FTS 主场；`RESULTS_SUMMARY.md:159` 自述"模板高度同构" |

---

## 1. 三个新问题（现有实验都答不了）

| # | 问题 |
|---|---|
| **Q1** | 在**别人造的**数据上，槽位覆盖是否优于纯向量？ |
| **Q2** | 融合是否优于**最强单通道**（A2 纯 FTS），而非仅优于向量？ |
| **Q3** | 在**自然语言改写、无精确标识符**的查询上，融合是否还能赢？ |

---

## 2. 目录结构

```text
experiments_v2/
├── README.md                  ← 本文件
├── PROVENANCE.md              ← 数据与数字的来源、版本、sha256
├── run_env.py                 ← 环境探测 + 模型可用性 + token 记账
├── dl/
│   ├── fetch_mab.py           ← MemoryAgentBench（公开，MIT）
│   └── fetch_memora.py        ← Memora（公开，Apache-2.0）
├── adapters/
│   ├── gated_store.py         ← 只调用 src/gated_mem，不修改
│   └── mab_adapter.py         ← MAB 数据格式 → ingest/query
├── arms/
│   ├── definitions.py         ← 7 臂定义
│   ├── lenient_match.py       ← 宽松匹配（MAB 必需）
│   └── wrapper_prompt.py      ← A6/A7 的 prompt（附录 F.1 结构）
├── runners/
│   ├── e1_mab_cr.py           ← 核心：MAB Conflict_Resolution
│   ├── e2_memora.py           ← FAMA / forgetting_absence
│   └── e3_naturalized.py      ← 无标识符改写集
├── data_gen/
│   └── build_naturalized.py   ← 从 20 组难负例派生改写集
└── results/                   ← 输出
```

---

## 3. 实验臂

| ID | 名称 | use_slots | λ | fusion | wrapper | 作用 |
|---|---|---|---|---|---|---|
| A0 | nomem | ✗ | 0 | ✗ | ✗ | 下界 |
| A1 | vector | ✗ | 0 | ✗ | ✗ | 主基线 |
| **A2** | **fts** | ✗ | 0 | ✓ | ✗ | **最强单通道候选（新增）** |
| A3 | slot | ✓ | 0 | ✗ | ✗ | 槽位覆盖 |
| A4 | slot_fusion | ✓ | 0 | ✓ | ✗ | 槽位+融合 |
| A5 | full | ✓ | 0.3 | ✓ | ✗ | 全量 |
| **A6** | **wrapper** | ✗ | 0 | ✗ | ✓ | **纯 prompt 现算（关键臂）** |

> **A2 是现有四轮实验从未单独报告的臂。** 阶段四数据显示它可能就是最强单通道；
> 若 A2 ≥ A4，融合的价值必须重新表述。

---

## 4. 判定阈值（提前写死，防事后解释）

```text
H1 槽位覆盖有效      A3 - A1 单跳 ≥ +5pp  且  多跳 ≥ +2pp
H2 融合优于最强单通道 A4 - max(A1, A2) ≥ +3pp          ← 现有实验从未检验
H3 生命力有增量      A5 - A4 ≥ +3pp
H4 存储优于纯 prompt  max(A3..A5) - A6 ≥ +5pp          ← 最关键
H5 遗忘有收益        A3 的 forgetting_absence > A1 且 FAMA +2 以上
H6 改写形态落差      见 E3 的落差表
```

---

## 5. 模型分工

| 用途 | 模型 | 理由 |
|---|---|---|
| 答案生成（E1/E2/E3） | deepseek v4.1f | 需固定版本可复现；谷时便宜 |
| Judge（Memora FAMA） | glm5.3f | 需与生成模型**不同族**，避免自评偏差 |
| 异构终审 | gemini3.8f | 沿用现有 Maker-Checker |
| E4 桥接（agentic） | gemini3.8f 订阅 | agentic loop token 膨胀，且模型是**控制变量** |
| 弱模型对照 | 本地小模型 | **不用于省钱跑实验**，只验证"机理在弱模型上不可见" |

### 本地小模型的正确用途（重要）

StateMem 论文 Table 5：弱 backbone 上机制差异几乎消失
（Qwen 上 StateMem drift 64.3% vs 其他 60.9–65.5%），只有强模型才降到 49.1%。

正确用法：

```text
E1 上同时用 deepseek v4.1f 和本地小模型跑 A1 vs A3
  强模型 A3-A1 = +8pp，弱模型 = +1pp
  → 证明"机制收益依赖答案模型能力"
  → 写入 README 边界，避免用户换小模型后认为方案无效
```

---

## 6. 数据来源（全部公开可核查）

| 数据集 | 协议 | 规模 | 用途 | 状态 |
|---|---|---|---|---|
| MemoryAgentBench | MIT | CR 8 样本 / 480–800 题 | **首站** | ✅ 可下载 |
| Memora | Apache-2.0 | weekly 150 题 | FAMA | ✅ 可下载 |
| LoCoMo / LongMemEval | MIT/学术 | — | 仅冒烟 | ✅ 可下载 |
| **StateMemBench** | — | 234/322 | — | ❌ **paper_only，不可得** |

> StateMemBench 论文声明公开，但 arXiv 无代码链接、GitHub/HF 均无官方仓库，
> 社区标 `paper_only`。**此前"用 StateMemBench 做第一站"的建议作废。**

---

## 7. 执行顺序

```text
D1   本骨架 + E0 实测 + token 记账
D2   E1（MAB CR）      → ★H1/H2/H3/H4
D3   E2（Memora）      → ★H5
D4   E3（自然语言改写） → ★H6 ← 本目录最关键的补充
D5-7 E4 桥接           → ★最终 Go/转向/停止
D8   弱模型对照         → 边界声明
```

预算：API ¥45–110；E4 走订阅 ¥0。

---

## 8. 不在本目录范围内

- 不修改 `src/`、`tests/`、`benchmarks/` 任何既有文件
- 不重跑已通过的 Gate 2 / Gate 3 验证
- 不重跑 published baseline（引用论文数字并注明协议差异）
- 不做 UI / CLI / 导出器相关工作
