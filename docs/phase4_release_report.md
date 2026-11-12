# 阶段四（v1.0.0 开源发版）交付报告

> 指令：GM-DIRECTIVE-P4-v3.0.0（暨 v1.0.0 开源发布令）
> 终审：Gemini-3.8-Flash 签署 **【放行 v1.0.0】**
> 最终状态：176 项单测 / 90% 覆盖率 / Gate 3 16/16

---

## 1. 三项铁律落实情况

### 铁律 1：PyPI 分层可选依赖

| 项 | 结果 |
| :--- | :--- |
| `version = "1.0.0"` | ✅ `src/gated_mem/__init__.py` 与 pyproject 双处一致 |
| `license = MIT` | ✅ |
| 核心 `dependencies = []` | ✅ **经净室空 env 实测验证** |
| `[onnx]` extra | ✅ `fastembed>=0.3.0` + `numpy>=1.24.0` |
| `doctor` 环境诊断 | ✅ Python 路径/版本、SQLite 版本、WAL、FTS5、Embedder 名称+维度+档位、已配置 Agent 列表 |

### 铁律 2：setup 闭环

- `gated-mem setup` 无参自动探测，优先级 DSH(0) > Claude Code(10) > Cursor(20)
- `gated-mem setup --uninstall` —— **三种初始文件形态全部逐字节可逆**
- `--dry-run` 零改动；重复 install 幂等

### 铁律 3：README + Demo

- `README.md`：徽章栏、三栏对比表、30 秒上手、双通道 XML 示例、CLI/MCP 速查、**真实的已知限制**
- `docs/demo_memory_graph.html`：15 节点 / 6 边，零外部依赖，浏览器实测可交互（截图见 `docs/demo_screenshot.png`）

---

## 2. 最重要的一件事：零依赖原本是假的

打包完成后我在干净 conda 环境里装 wheel 测试，`gated-mem --version` 直接崩溃：

```
ModuleNotFoundError: No module named 'pydantic'
  at src/gated_mem/schema.py line 18
```

**`dependencies = []` 但代码 import 了 pydantic。** 任何用户执行 `pip install gated-mem`
都会立刻拿到一个装完就崩的包 —— 而这恰恰是阶段四最想避免的失败模式（为语义能力
装个包，结果毁掉用户的 numpy 环境）。

修复：把 `schema.py` 从 pydantic 迁到 `dataclass(frozen=True)`，自实现一个仅 30 行的
`_FrozenModel` 基类提供 `model_copy` / 不可变语义，并把枚举归化写进 `__post_init__`
（pydantic 会自动把 `'DECISION'` 转成枚举成员，dataclass 不会 —— 不补这层，从 SQLite
读回的行会让 `compute_t0()` 拿到 str 而崩）。

**还加了 7 项结构性守卫**（`tests/test_zero_dependency.py`）：AST 扫描禁止 src/ 出现任何
第三方 import、禁止 pydantic 回流、验证 schema 可在纯净解释器独立导入。这样「零依赖」
变成可机器验证的事实，而不是 README 里的一句话。

---

## 3. 难负例：Limitation #2 被证明

阶段三遗留问题：FastEmbed 单向量已达 95%，融合追平但无法超越，因为 `fts_only = 0`。

GLM 造的 20 组难负例（同模块、同句式、仅标识符差 1~2 字符，组内文本相似度 95.7%~98.9%）：

| 通道 | Top-1 | Top-3 |
| :--- | ---: | ---: |
| 单向量 | 12/20 = **60.0%** | 16/20 = 80.0% |
| 单 FTS5 | 20/20 = **100.0%** | 20/20 = 100.0% |
| **混合融合** | 20/20 = **100.0%** | 20/20 = 100.0% |

**净增益 +40pp（门槛 20pp）**。8 个 case 从错误排名被修正到 Top-1。
`version` 类别单向量 Top-1 是 **0%** —— 微差版本号在 384 维稠密空间完全坍缩，
这正是稠密检索的真实盲区，也是混合检索存在的理由。

我独立复算了一遍（不采信 GLM 的数字），结果完全一致；Gemini 又独立复算了第三遍，
依然一致（它还额外用 `difflib` 测了构造相似度，确认不是凑数）。

---

## 4. 终审发现的一处细节

Gemini 指出：**空文件**形态卸载后会变成 `[]\n` 而不是还原成 0 字节。

这不是 bug，是刻意设计：DSH 全新 profile 的默认值就是 `[]\n`；若还原成 0 字节空文件，
Cordis loader 会解析出 `None` 而非空列表，导致迭代异常。所以「空文件」这一形态是
**规范化为合法默认值**，而非逐字节还原。另外两种形态（内联 `[]`、已有用户条目）
均为 100% 逐字节还原。二者都已在测试中固化。

---

## 5. 发版卫生

- 构建产物 `dist/` 曾误入 git，已 `git rm --cached` 并加入 `.gitignore`
- `.coverage` / `__pycache__` / `*.egg-info` 均已忽略，Gemini 解析 `.git/index` 确认 0 污染
- README 所有数字经 Gemini 逐项抽查，与实际仓库一致（176 tests / 90% coverage / Gate 3 16/16 / builtin 融合 65%）

---

## 6. 已知边界（发版后仍需诚实标注）

1. **`BuiltinHashEmbedder` 是纯字面的**，零字符重叠时 cos=0.0。内置概念词典只是有限桥接。
2. **混合检索的互补性依赖难负例**：普通数据集（阶段三 20 组）上融合等于向量；只有在
   标识符级碰撞场景（阶段四难负例）才显著超越。这是真实适用边界，不是普适优势。
3. **MCP 只实现核心子集**（initialize / tools/list / tools/call / ping）。
4. **token 计数是估算**，未接真实 tokenizer。
5. **测试集全是自造的**，内部效度高、外部效度有限。

---

## 7. 复现命令

```bash
PY="<conda-env>/python"

$PY -m pytest tests/ -q                                  # 176 passed
$PY -m coverage run --source=src/gated_mem -m pytest tests/ -q
$PY -m coverage report -m                                # 90%
$PY benchmarks/gate3_check.py                            # 16/16
$PY benchmarks/build_phase4_hard_negatives.py            # 难负例基准
$PY benchmarks/build_demo_graph.py                       # 重新生成 demo

# 打包与净室验证
$PY -m build
conda create -n gmtest python=3.9 -y
<clean-venv>/python -m pip install --no-deps dist/gated_mem-1.0.0-py3-none-any.whl
# 在非仓库目录、unset PYTHONPATH 下：
#   import gated_mem → 指向 site-packages
#   python -m gated_mem.cli --version → gated-mem 1.0.0
```

---

## 8. 交接给后续维护者

1. **发版前必须做净室安装测试**。本次就是靠它抓到 pydantic 假零依赖。
2. **改 `schema.py` 要小心枚举归化**：dataclass 不会自动转换字符串，`__post_init__` 里漏一个就会在运行时炸。
3. **改 `dsh.py` 的补丁读写要跑三种形态的往返测试**（`tests/test_phase4.py` 已覆盖）。
4. **任何新的第三方依赖都必须走 extra**，`test_zero_dependency.py` 会拦住直接 import。
