# 开发与运行环境

> 本文件是阶段三补的。**不要用 conda base 环境跑本项目**——历史教训见 §4。

## 1. 专用环境（必须）

本项目使用独立的 conda 环境，**不污染 base**：

```bash
conda create -n gated-mem python=3.9 -y
conda activate gated-mem
pip install pydantic pytest coverage
pip install fastembed          # 可选：语义向量引擎
```

专用环境解释器占位符：`<conda-env>/python`

> **当前工作区说明**：跑零依赖全量 `191` 项单测与 `python -S` 检查可直接使用当前环境中的 `python`（仅需 `pytest`）；严禁向 conda `base` 环境直接 `pip install fastembed`。若运行 GitNexus（`.gitnexus/run.cjs`）时 `node` 不在默认 `PATH` 中，需先将本机 Node.js 安装目录与 `$env:APPDATA\npm` 加入 `PATH`。

| 组件 | 版本 | 说明 |
| :--- | :--- | :--- |
| Python | 3.9.25 | 与生产要求一致（禁 match 语句） |
| pydantic | 2.13.5 | 领域模型 |
| pytest | 8.4.2 | 单测 |
| coverage | 7.x | Gate 2/3 覆盖率门槛 |
| SQLite | 3.54.1 | FTS5 + bm25 + 递归 CTE 均可用 |
| fastembed | 0.7.4（可选） | bge-small-zh-v1.5，512 维 |

## 2. 两条向量引擎路径

```python
from src.gated_mem.embeddings import get_default_provider

get_default_provider("builtin")   # 零依赖：BuiltinHashEmbedder，384 维，纯字面
get_default_provider("fastembed") # 本地 ONNX：bge-small-zh-v1.5，512 维，真语义
```

**选择依据**（阶段三实测，20 组 E2E 集 Top-3 命中率）：

| 引擎 | FTS | 向量 | 融合 | 适用场景 |
| :--- | ---: | ---: | ---: | :--- |
| BuiltinHashEmbedder | 40% | 45% | **55%** | CI / 断网 / 零依赖安装 |
| FastEmbedProvider | 45% | 95% | **95%** | 真实使用 |

**重要**：内置哈希器是**纯字面**的，对「持久层瓶颈」↔「MySQL 连接池打满」这类
零字符重叠的语义改写无能为力（实测 cos=0.00）。它内置了一张人工概念词典
（`embeddings.CONCEPT_LEXICON`）做有限的跨词桥接，但**不能替代真实语义模型**。
需要语义能力时必须装 fastembed。

## 3. 常用命令

```bash
# 专用环境（含 fastembed 与 coverage）
PY="<conda-env>/python"

$PY -m pytest tests/ -q                                    # 191 项
$PY -m coverage run --source=src/gated_mem -m pytest tests/ -q
$PY -m coverage report -m                                  # 90%
$PY benchmarks/gate3_check.py                              # Gate 3 六项
$PY benchmarks/eval_phase3_hybrid.py --provider fastembed  # 混合检索评测
```

零依赖验证与 GitNexus 常用命令：

```powershell
# 1. 运行全量 191 项零依赖单测
python -m pytest tests/ -q

# 2. 验证核心包零第三方依赖 (-S 隔离 site-packages)
python -S -c "import sys; sys.path.insert(0, 'src'); import gated_mem, gated_mem.cli, gated_mem.server, gated_mem.adapters"

# 3. GitNexus（若 node 不在 PATH，先追加本机 Node.js 安装目录）
$env:Path = "<nodejs-bin-dir>;$env:APPDATA\npm;" + $env:Path
node .gitnexus/run.cjs analyze --index-only
```

## 4. 踩过的坑（务必避开）

1. **不要在 base 环境 pip install**
   `fastembed` 会连带把 numpy 升到 2.x，当场打断 base 里的
   numba / spyder / torch。阶段三真实发生过，恢复过程很麻烦
   （残留的 `~umpy-*.dist-info` 会让 pip 一直报 invalid distribution）。
2. **不要并发跑两个 pip install**
   两个安装同时改同一个 site-packages，会产生「dist-info 与源码版本不一致」的
   半损坏状态。阶段三因此把 base 的 numpy 搞成 1.26.4 源码 + 2.0.2 元数据的混合体。
3. **Windows 控制台默认 GBK**
   CLI 里打印 `✓` 会直接抛 `UnicodeEncodeError`。cli.py 已用
   `_safe_console_stream()` 在入口把 stdout 重配为 UTF-8。
4. **subprocess 捕获要显式 encoding**
   门禁脚本里 `capture_output=True, text=True` 不带 encoding 时按 GBK 解码，
   遇到 UTF-8 输出直接崩。已统一加 `encoding="utf-8", errors="replace"`。
