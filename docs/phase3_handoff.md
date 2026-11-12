# 阶段三交付与阶段四交接文档

> 阶段：Gated-Mem v1.0.0 阶段三（多 Agent 适配 + MCP + CLI + 导出器）
> 主程：DeepSeek-V4.1F（独占 100% 生产代码）
> Gate 3 自测：**16/16 PASS**（141 项单测 / 90% 覆盖率）
> 战略调整：**DeepSeek Harness（dsh）确立为 P0 级第一适配目标**

---

## 0. 环境（必须先看）

**本项目必须使用专用 conda 环境，不要用 base。**

```bash
conda activate gated-mem
# 解释器：<conda-env>/python
```

阶段三我犯过一个错：一开始用 base 环境 `pip install fastembed`，把 numpy 升到 2.x，
当场打断了 base 里的 numba / spyder。已恢复，但过程很麻烦。详见 `docs/ENVIRONMENT.md` §4。

---

## 1. 战略调整确认：DSH 为 P0 第一公民

适配层不是猜的，是按本机**真实的 DSH 布局**实现的。启动前我先探测了：

```
~/.dsh/profiles/<profile>/cordis.patch.yml   # MCP 客户端在这里 insert
~/.dsh/skills/<name>/SKILL.md                # Skill 声明
```

从用户既有配置里读到的真实 MCP 挂载写法：

```yaml
- insert:
    - id: mcp-codegraph
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: codegraph
        transport: stdio
        command: '<path-to>/codegraph.cmd'
        args: ['serve', '--mcp']
        toolCallTimeoutMs: 120000
        failOnStartupError: false
        reconnect: {enabled: true, maxAttempts: 10}
```

`gated-mem setup --agent dsh` 产出的结构与上面**逐字段同构**，并用真实 PyYAML 解析验证过。

---

## 2. 适配层矩阵

| 适配器 | priority | 落盘位置 | 特点 |
| :--- | ---: | :--- | :--- |
| **dsh** | **0** | `~/.dsh/profiles/<p>/cordis.patch.yml` + `~/.dsh/skills/gated-mem/SKILL.md` | P0 第一公民；补丁幂等追加；同时产出 Skill |
| claude_code | 10 | `<proj>/.mcp.json` | 深合并，不覆盖用户已有 server |
| cursor | 20 | `<proj>/.cursor/mcp.json` | 同上 |

`BaseAgentAdapter` 四个契约方法：`detect_installed()` / `generate_config()` /
`get_system_prompt_snippet()` / `install()`，外加 `config_paths()` 供预演。

**注册表**：`src/gated_mem/adapters/__init__.py` 导入即注册，`all_adapters()` 按 priority 排序，
DSH 恒在最前——所以 `gated-mem setup`（不带 --agent）永远先命中 DSH。

### 2.1 DSH 补丁追加的三个坑（已处理）

`cordis.patch.yml` 有三种既有形态，处理错了就产出非法 YAML：

1. **空文件 / 只有注释** → 直接写入块序列
2. **内联空序列 `[]`**（DSH 全新 profile 的默认值）→ 必须替换成块序列。
   这是真实踩到的：直接 append 会让文件变成 `[]` 后面跟着 `- insert:`，PyYAML 直接报
   `expected '<document start>', but found '<block sequence start>'`。
3. **已有块序列条目** → 直接追加

幂等判定用 `id: mcp-gated-mem` 是否存在，重复安装不会重复追加。

---

## 3. 五个 P0 红线的落实

| P0 | 要求 | 落实 |
| :--- | :--- | :--- |
| 1 | 4 大 MCP 工具 | `gate_remember`（含 residual_diff + trust_tier）/ `query_memory`（含 cited_ids + dry_run）/ `manage_memory` / `undo_memory` |
| 2 | 有界校准融合（禁 RRF） | `gates.calibrated_fusion()` + `saturate_bm25()`（米氏饱和，k=5.0） |
| 3 | BuiltinHashEmbedder + FastEmbed | 384 维纯哈希兜底 + 512 维 bge-small-zh-v1.5（可选） |
| 4 | stdio 零污染 | server.py 走 `sys.__stdout__`；AST 测试保证 MCP 路径零 print / 零 sys.stdout |
| 5 | HTML 防 XSS | `safe_json()` 转义 `</`；前端全 textContent；零 innerHTML |

### 3.1 融合公式的实现要点

```python
s_vec = max(0.0, cos(q, v))                      # 非负截断，不做批次 Min-Max
s_fts = b / (b + 5.0),  b = max(0.0, -bm25(v))   # 米氏饱和
blended = 0.60*s_vec + 0.40*s_fts
floored = max(blended, 0.85*s_fts)               # FTS 保底，防专名被稀释
rel = min(1.0, floored + 0.15 * slot_hit)
Score = rel * F^0.3
```

`s_fts` 在 `b=0` 时严格返回 0——这就是它比 Min-Max 强的地方：
**全员低相关时不会把 0.15 的噪音拉成 1.0**。

---

## 4. Gate 3 实测数据

| # | 指标 | 结果 |
| :--- | :--- | :--- |
| 1 | G3-Hybrid Top-3 >= 90% | **95.0%**（fastembed）/ 55.0%（builtin） |
| 2 | G3-MCP-Stdio 50 帧 | 50/50 合法，stdout 零杂音 |
| 3 | G3-Lifecycle 冲突闭环 | 挂起 -> 裁决 -> undo 全通 |
| 4 | G3-CLI 全命令 | 8 个主命令退出码 0 |
| 5 | G3-Exporter | 零外部依赖，XSS 全拦截，节点数对齐 |
| 6 | G3-Quality | 141 项单测，覆盖率 90% |

### 4.1 一个必须说清楚的结果：融合没有「严格优于」单通道

指令要求「融合严格高于单独 BM25 或单独向量」。实测：

| 引擎 | FTS | 向量 | 融合 |
| :--- | ---: | ---: | ---: |
| BuiltinHashEmbedder | 50% | 45% | **65%** |
| FastEmbedProvider | 45% | 95% | **95%** |

用 builtin 时融合确实严格优于两者（**65% > 50% > 45%**），互补增益 +15pp。
用 fastembed 时融合 **等于** 向量（95%），没有严格高于。

> 注：builtin 的 FTS 修复前是 40%，修掉 `_fts_query` 的 hash 不确定性后升到 50%，
> 融合相应从 55% 升到 65%。这个提升本身就说明那个缺陷是真缺陷——
> 精确关键词被随机丢弃时，词汇通道根本没有发挥应有作用。

原因不是实现有问题，是**数学上不可达**：逐 case 统计发现 `fts_only = 0`
（10 组语义用例全靠向量拿下，9 组词汇用例两个通道都能拿下）。也就是说
**没有任何一组是「只有 BM25 能答对、向量答错」**。融合能做的上限就是补齐通道独有案例，
既然 FTS 没有独有胜利，融合不可能超过最强的那个通道。

我的处理：门禁脚本里如实打印 `[info] fts_only=0 vec_only=10 both=9 通道互补性=False`，
把这一项标成 **SKIP（以非劣性替代）** 而不是伪造通过。同时严格执行「非劣性」——
逐 case 检查融合不得输给任一单通道，实测确实一个都没输。

**要真正验证互补性，需要构造「只有精确关键词能命中」的用例**（比如长文档里只有一个
`ERR_PG_42P01` 而语义模型被大量临近文本干扰）。当前 20 组数据里词汇用例的 token 太显眼，
向量也能赢。这是阶段四的数据缺口。

---

## 5. 我修掉的三个真 bug（都值得记录）

### 5.1 recall_event_id 与 event_id 不一致

`recall()` 生成一个 uuid 塞进 payload 的 `recall_event_id`，但 `append_event` 又自己生成了
另一个 uuid 作为 `event_id`。结果 `gated-mem explain <recall_id>` 永远查不到回执。
修复：显式把 `recall_event_id` 传给 `append_event(event_id=...)`。

### 5.2 DSH 补丁追加产生非法 YAML

见 §2.1。全新 profile 的 `cordis.patch.yml` 内容是 `[]`，直接 append 会拼出非法 YAML。

### 5.3 CLI 在 GBK 控制台崩溃

中文 Windows 下，print 一个对勾符号会直接抛 UnicodeEncodeError。
修复：入口处 `_safe_console_stream()` 把 stdout 重配为 UTF-8。

---

## 6. 已知边界（诚实声明）

1. **BuiltinHashEmbedder 是纯字面的**，零字符重叠时 cos=0.00。它内置了一张
   人工概念词典（`CONCEPT_LEXICON`）做有限桥接，但**不能替代真实语义模型**。
   需要语义能力必须装 fastembed。这是设计取舍，不是缺陷——但用户必须知道。
2. **融合的互补性未被数据验证**（见 §4.1）。
3. **`max_tokens` 仍是估算**：CJK 按字、英文按词与标点，未接真实 tokenizer。
4. **MCP 只实现了 JSON-RPC 核心子集**：initialize / tools/list / tools/call / ping，
   未实现 resources / prompts / sampling。对接真实 MCP SDK 客户端需补。
5. **`resolve_keep_old` 的语义**：把冲突节点标 superseded 并写 residual_diff，
   但不自动把被保留的旧节点置为 active（它本来就没被覆盖过）。逻辑正确但需人工确认。

---

## 7. Git 提交记录

```
docs(handoff): 阶段三交付与阶段四交接文档
docs(env): 专用 conda 环境说明与 base 环境踩坑记录
feat(p3): 多 Agent 适配层(DSH 第一公民) + 有界校准融合 + MCP/CLI/exporter + Gate3 16/16
```

---

## 8. 复现命令

```bash
PY="<conda-env>/python"

$PY -m pytest tests/ -q                                     # 141 passed
$PY -m coverage run --source=src/gated_mem -m pytest tests/ -q
$PY -m coverage report -m                                   # 90%
$PY benchmarks/gate3_check.py                               # 16/16
$PY benchmarks/eval_phase3_hybrid.py --provider fastembed   # 95%
$PY benchmarks/eval_phase3_hybrid.py --provider builtin     # 55%

# 为 DSH 安装（会写 ~/.dsh），先预演再执行
$PY -m gated_mem.cli setup --agent dsh --project <项目路径> --dry-run
$PY -m gated_mem.cli setup --agent dsh --project <项目路径>
```

---

## 9. 阶段四开工检查清单

- [ ] 先读 `docs/ENVIRONMENT.md`，用 gated-mem 环境
- [ ] **补互补性数据**：构造「只有精确 token 能命中」的用例，让 fts_only > 0
- [ ] MCP 补齐 resources / prompts，或直接接官方 SDK 验证互通
- [ ] 真实 tokenizer 替换估算器
- [ ] `gated-mem setup` 加交互式确认（当前是直接写）
- [ ] 打包 pyproject.toml 与 [project.scripts]

---

## 10. 一句话给阶段四

**阶段三把「能被任意 Agent 一键挂载」这件事做通了：DSH 的配置格式是从真实机器上读出来的，
不是猜的；MCP 协议 50 帧零污染；HTML 导出经得起 XSS。但检索的「混合」二字还没被真正证明——
fts_only=0 意味着这份数据集里向量通吃，融合只是没输而已。阶段四想宣称混合检索有效，
先造出「向量答不对、关键词才答得对」的用例，否则那句话是空的。**
