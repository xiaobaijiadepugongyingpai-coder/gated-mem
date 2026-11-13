# PROVENANCE · 数据与数字来源

> 本文件记录 `experiments_v2/` 中每一项数据、每一个数字的来源、版本与可复现方式。
> 原则：**任何写进报告的数字，都必须能在此处追溯到来源或复现命令。**

---

## 1. 外部数据集

| 名称 | 协议 | 获取方式 | 用途 | 状态 |
|---|---|---|---|---|
| **MemoryAgentBench** | MIT | `datasets.load_dataset("ai-hyz/MemoryAgentBench")`<br>HF: `ai-hyz/MemoryAgentBench` | E1 主实验 | ⚠️ **未完成**：`datasets` 库安装挂起，未跑通 |
| **Memora** | Apache-2.0 | `git clone https://github.com/geniesinc/Memora`<br>数据在仓库 `data/` 目录 | E2 FAMA | ⚠️ 未开始 |
| LoCoMo / LongMemEval | 学术 | 各自仓库 | 仅冒烟 | ⚠️ 未开始 |
| **StateMemBench** | — | — | — | ❌ **不可得** |

### 关于 StateMemBench（重要更正）

论文（arXiv:2608.19652）正文声明 "we release StateMemBench"，但截至 2026-10
**arXiv 页面无代码链接，GitHub 与 HuggingFace 均无官方仓库**，社区索引将其标为
`paper_only`。**因此本项目早期计划中"用 StateMemBench 做第一站"的路线作废。**

替代方案见 `README.md` §6。

### MemoryAgentBench 已核实的结构事实

```text
split 划分（总数 146 例）：
  Accurate_Retrieval        22 例
  Test_Time_Learning         6 例
  Long_Range_Understanding 110 例   ← 占 75% 体积，与本项目无关，跳过
  Conflict_Resolution        8 例   ← 本项目主目标

字段：
  context                    str
  questions                  list[str]
  answers                    list[list[str]]      # 每题可接受多个答案
  metadata.haystack_sessions list[list[msg]]      # 分块会话，用于 ingest
  metadata.question_types    list[str]            # 单跳/多跳分组
  metadata.qa_pair_ids       list[str]

数据规模注意：每个样本带 60–100 道题 ⇒
  Conflict_Resolution 8 个样本 ≈ 480–800 题，不是 8 题。
  这直接决定 E1 的调用量与成本。

判分指标（官方）：
  Conflict_Resolution -> substring_exact_match
  Accurate_Retrieval  -> substring_exact_match
  Test_Time_Learning  -> exact_match
  Long_Range_Understanding -> exact_match
  ⇒ 全部是确定性字符串匹配，**不需要 LLM judge，成本为 0**

官方已发表的严格性警告：
  "if the ground-truth label is "43" but the model returns "label: 43",
   it will be counted as incorrect."
  ⇒ 适配到自己的 pipeline 时必须用宽松解析（见 arms/lenient_match.py）
```

---

## 2. 内部数据（本目录生成）

| 文件 | 生成命令 | sha256 | 说明 |
|---|---|---|---|
| `experiments_v2/data/e3_naturalized.json` | `python experiments_v2/data_gen/build_naturalized.py` | `e1d0d96ad278330fc4fda9fa7ee2c211dd56cc10a06131da88304210fb449254` | 80 条查询 = 20 case × 4 形态 |
| `experiments_v2/results/e0_env.json` | `python experiments_v2/run_env.py` | — | 环境探测快照 |
| `experiments_v2/results/e3_naturalized_builtin.{md,json}` | `python experiments_v2/runners/e3_naturalized.py --provider builtin` | — | E3 实测结果 |

### E3 数据来源

派生自 `benchmarks/data/phase4_hard_negatives_20.json`
（sha256 `e679a18066f225fecad0a01b86ec3501d6dfce7ab74b28388d2981c83758bf26`）。

**只读该文件，未修改它。** 派生方式见 `data_gen/build_naturalized.py` 的
`make_variants()`：对同一批 100 条记忆、同样的 `expected_id`，生成 4 种查询形态：

| 形态 | 示例 |
|---|---|
| `q0_original` | …模块里**错误码 ERR_XA_PROTO_08** 的退避参数应按哪条记录调整？ |
| `q1_synonym` | …模块里**那次报错**的退避参数应按哪条记录调整？ |
| `q2_pronoun` | …模块里**那个错误码**的退避参数应按哪条记录调整？ |
| `q3_colloquial` | …模块那块儿，上次**那个报错码**定成多少来着？ |

设计意图：`q0` 是 FTS 主场（唯一精确标识符产生高 IDF 爆发）；
`q1–q3` 移除标识符，模拟真实开发者的提问方式。

---

## 3. E3 实测结果（本次唯一产出的真实数字）

生成条件：`provider = BuiltinHashEmbedder`（384 维，零依赖字符 n-gram 哈希，
**不是真实语义模型**）。命令：

```bash
python experiments_v2/runners/e3_naturalized.py --provider builtin
```

### Top-1 命中率

| 查询形态 | A1_vector | A2_fts | A4_slot_fusion |
|---|---|---|---|
| 含精确标识符 | 65.0% | **100.0%** | **100.0%** |
| 同义改写 | 25.0% | 25.0% | 25.0% |
| 指代改写 | 25.0% | 25.0% | 25.0% |
| 口语改写 | 15.0% | 15.0% | 15.0% |

### Top-3 命中率

| 查询形态 | A1_vector | A2_fts | A4_slot_fusion |
|---|---|---|---|
| 含精确标识符 | 90.0% | 100.0% | 100.0% |
| 同义改写 | 65.0% | 65.0% | 60.0% |
| 指代改写 | 65.0% | 65.0% | 60.0% |
| 口语改写 | 55.0% | 55.0% | 55.0% |

### 三条结论

1. **FTS 在含标识符时 100%，去掉标识符后崩到 15%**（Top-1 落差 −85pp）。
   这证实了阶段四那组 +40pp 是**数据构造的产物**，不是融合的优势。

2. **三个臂在改写形态上完全同分（25/25/15）**。
   说明在无标识符时，`BuiltinHashEmbedder` 与 FTS 都提供不了区分信号——
   这是**哈希向量器能力不足**导致的天花板，不是融合逻辑失效。

3. **这个结果目前不能用来评价融合的真实上限**。
   必须换 `FastEmbedProvider`（真实语义模型，bge-small-zh-v1.5）重跑，
   才能看到向量通道在改写形态上的真实表现。见 `HANDOFF.md` §3 待办。

---

## 4. 引用的一手文献

| 编号 | 内容 | 链接 |
|---|---|---|
| L1 | StateMem：234 场景 / 322 probes；依赖传播消融为负收益（Set B anti-trap −12.5pp，去掉后 0.373 > 0.363）；**Table 6：纯 prompt wrapper 56.7–71.7 vs 完整系统 23.3–36.3**；§6.3 drift-rate 是反向指标（LightMem 14.9% 但 accuracy 0.012） | [arXiv:2608.19652](https://arxiv.org/abs/2608.19652) |
| L2 | MemStrata：确定性 (subject, relation, object) 覆盖 + 双时序账本；余弦区分矛盾/重复 **AUROC 0.59** | [arXiv:2606.26511](https://arxiv.org/abs/2606.26511) |
| L3 | 真实 GitHub 修复上验证：707 → 130 个干净原子转移（覆盖率 18.4%） | [arXiv:2608.20685](https://arxiv.org/abs/2608.20685) |
| L4 | 时效操作本身只值 2.0pp；主要收益来自"证据识别/策略执行分离" | [arXiv:2606.01435](https://arxiv.org/abs/2606.01435) |
| L5 | **90.1% 的 agent 跟随过期指令文件**，即使指出冲突仍照做 | [arXiv:2610.30571](https://arxiv.org/abs/2610.30571) |
| L6 | Memora / FAMA，ACL 2026 Findings；weekly 150 题 / quarterly 300 题 | [ACL Anthology](https://aclanthology.org/2026.findings-acl.1337/) |
| L7 | MemoryAgentBench 官方仓库与数据 | [GitHub](https://github.com/HUST-AI-HYZ/MemoryAgentBench) / [HF](https://huggingface.co/datasets/ai-hyz/MemoryAgentBench) |
| L8 | Agent Memory Leaderboard（Add/Search 双端点即可接入，需公网可达） | [agentmemoryleaderboard.ai](https://agentmemoryleaderboard.ai/api-guide) |

---

## 5. 可信度标注

| 内容 | 可靠性 |
|---|---|
| 外部数据集规模、字段、协议 | **高**（直接读 HF dataset card 与仓库 README） |
| StateMemBench 不可得 | **中高**（多方交叉：arXiv 无链接 + 社区索引标 paper_only） |
| E3 的 80 条查询与 sha256 | **高**（确定性生成，可复现） |
| E3 实测命中率 | **中**（数字真实，但受 BuiltinHashEmbedder 能力上限限制，不可外推） |
| 引用文献的数字 | **中**（读的是 arXiv 摘要与 HTML 正文，未逐页核对全部表格） |
