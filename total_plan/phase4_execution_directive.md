# Gated-Mem v1.0.0 开源发布终审裁决令与阶段四（Phase 4）执行指令书

> **文档编号** ： `GM-DIRECTIVE-P4-v3.0.0` （暨 `v1.0.0` 正式开源发布令）
> 
> **签发依据** ：《Gated-Mem 阶段三（多 Agent 适配与开源发布终验）综合执行审计与大模型裁决案卷》（ `GM-DOSSIER-P3-v3.0.0` ）
> 
> **Gate 3 终审裁定** ： **【无条件正式放行发布 · UNCONDITIONAL PASS FOR RELEASE】**
> 
> **当前基线状态** ：Gate 3 六大硬指标 16/16 全绿通过，全库单元测试 154 项通过，代码行覆盖率 90.0% ，紫军监察官初审捕获的 5 项真实缺陷 100% 闭环清零。
> 
> 

## 一、 阶段三终验评估：为什么这是一次教科书级的收官？

阶段三的交付不仅兑现了 `GM-DIRECTIVE-P3-v2.2.0` 的全部技术指标，更通过真实的红蓝对抗验证了多模型协同工程的最高水准：

1. **红蓝对抗抓出了单模型绝不可能自检出的“幽灵级 Bug”** ：
   紫军监察官（ `Gemini-3.8-Flash` ）在黑盒穿透中捕获的 **`P1-1` （ `_fts_query` 中 `frozenset` 受 `PYTHONHASHSEED` 扰动导致长查询专有名词随机截断丢弃）** 与 **`额外项` （CLI `remember` 冲突挂起分支 `p = Paint()` 先用后定义导致 `UnboundLocalError` ）** ，是典型的高隐蔽生产事故。蓝军主程（ `DeepSeek-V4.1F` ）通过信息量分层确定性排序与 AST 作用域静态扫描单测将其彻底根除，使跨进程 7 组随机种子输出达到 100% 逐字符一致，Lexical 组召回率从 6/10 跃升至 10/10 。
2. **真刀真枪逆向打通了 DeepSeek Harness（ `dsh` ）第一公民生态** ：
   团队没有停留在纸面 Mock，而是针对真实 `~/.dsh/cordis.patch.yml` 的三种初始文件形态（空文件、内联空列表 `[]` 、既有块序列）实现了幂等注入，并配套投递了 `~/.dsh/skills/gated-mem/SKILL.md` 技能卡，使插件具备了真正的开箱即用生产力。
3. **有界校准混合检索与离线安全导出经受住了极限压测** ：
   米氏饱和函数 \{\\text{fts}} = \\frac{b_v}{b_v + 5.0}\$ 在全噪音输入（ b v ​ = 0 ）下严格输出 0.0000 ，彻底杜绝了批次内 Min-Max 归一化的噪音放大效应；离线 HTML 导出器在 10 组高危 XSS 载荷攻防下达成 0 外部链接、 100% 拦截与 DOM 零崩坏。

## 二、 三大呈批议题终审拍板裁决（Release & Phase 4 Ballot Verdict）

针对案卷第 7 节提交的 3 项选票议题，终审拍板如下：

|议题编号 |终审拍板选项 |裁决理由与强制执行规约 |
| --- | --- | --- |
|**议题 1： `v1.0.0` 开源发布令** |**☑ 选项 A【正式签署开源发布令（UNCONDITIONAL PASS FOR RELEASE）】** |Gate 3 全部 16/16 机检项与 154 项单测 100% 达成， 5 项审计缺陷全部 `CLOSED` ，准予立即打上 `v1.0.0` Git Tag 并启动开源分发。 |
|**议题 2：阶段四战略演进路线** |**☑ 选项 C 黄金配比版【双模并进：** 70% **生态无感接入与实战吃狗粮 +** 30% **强语义难负例对抗基准】** |开源工具的生命力在于“零摩擦安装” **与** “一眼看懂的硬核评测表”。阶段四以 **Track A（一键安装器、宿主实战吃狗粮、15 秒终端 GIF 与离线图谱 Demo 页）** 为主攻方向；同时以 **Track B（构造 30 组“长文本近似语义 + 唯一标识符微差”的难负例基准）** 攻克 Limitation #2 中 `FastEmbed` 单通道触顶的数学盲区。 |
|**议题 3：开源协议与分发架构** |**☑ 选项 A+B 融合【MIT 许可证 + PyPI 分层可选依赖打包（ `gated-mem` 核心零依赖 / `gated-mem[onnx]` 语义增强）】** |1. **许可证选择 MIT** ：在 MCP 与 Agent 插件生态中，MIT 协议传播阻力最小、个人与企业二次集成率最高； 2. **分发渠道** ：主包 `gated-mem` 发布至 PyPI，同时向 DeepSeek Harness 生态提供 `dsh-plugin-gated-mem` （或原生 `gated-mem setup --agent dsh` 一键引导）； 3. **【生死级打包强制规范】** ：吸取案卷第 5 节“安装 `fastembed` 升级 `numpy 2.x` 毁坏用户 Conda Base 环境”的惨痛教训， **`pyproject.toml` 的默认 `dependencies` 必须严格保持零重型依赖** （详见下方 3.1 节）。 |

## 三、 发布打包与阶段四核心技术规约（必执行的 3 项关键设计）

### 3.1 规约 1：基于 `ENVIRONMENT.md` 教训的 PyPI 分层依赖防护网

案卷第 5 节记录的事故极具警示意义：在主环境中直接安装 `fastembed` 会强制拉取 `numpy>=2.0` 与 `onnxruntime` ，瞬间破坏开发者原有的 `numba` 、 `torch` 或 `spyder` 环境。若开源用户执行 `pip install gated-mem` 后发现自己的主力科研/开发环境崩了，项目会立刻遭遇差评反噬。

因此，在打 `v1.0.0` 包时， **`pyproject.toml` 必须采用“核心零依赖 + Extras 按需扩展”架构** ：

```
[project]
name = "gated-mem"
version = "1.0.0"
description = "Git for Agent Memory: Local, Auditable, Undoable State Engine for DSH, Claude Code & Cursor"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.9"
# 核心安装 100% 仅依赖 Python 标准库，绝对不碰用户的 numpy / torch 环境！
dependencies = []

[project.optional-dependencies]
onnx = [
    "fastembed>=0.3.0",
    "numpy>=1.24.0",
]
cli = [
    "rich>=13.0.0",
]
all = [
    "fastembed>=0.3.0",
    "numpy>=1.24.0",
    "rich>=13.0.0",
]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
]

[project.scripts]
gated-mem = "gated_mem.cli:main"
```

* **用户体验分级** ：
  
    + **极速安全模式（ `pip install gated-mem` 或 `pipx install gated-mem` ）** ： 2 秒装完，零第三方包冲突风险，默认启用 `BuiltinHashEmbedder` + `SQLite FTS5` + 标准库 ANSI 彩色终端，100% 功能可用。
    + **满血语义模式（ `pip install "gated-mem[onnx]"` ，推荐在独立虚拟环境或 `uv tool install` 下执行）** ：自动激活本地 `bge-small-zh-v1.5` 语义向量通道， `doctor` 命令自动检测并高亮显示当前激活的引擎档位。

### 3.2 规约 2：攻克 Limitation #2 —— 如何在强语义模型（ `FastEmbed` ）下证明混合检索的严格互补性？

案卷 6.2 节诚实披露：在阶段三的 20 组测试集中， `FastEmbed` 单独向量通道命中率已高达 95% （ `fts_only = 0` ），导致混合融合同样为 95% （表现为 100% 非劣性，但未拉开净增量差距）。

* **为什么阶段三会出现 `fts_only = 0` ？** 因为阶段三的 Lexical 测试题中，不同记忆节点的 **背景上下文主题差异较大** ， `bge-small` 仅靠外围语境就能把目标节点排进 Top-3。
* **阶段四 Track B 破局方案：构造「同语境近似语义 + 精确符号微差（Hard-Negative Identifier Collision）」基准集** ：
  在真实大型软件工程中，最让稠密向量（Dense Embedding）崩溃的场景是“同模块多版本/多错误码/相似配置项并存”。例如，记忆库中同时存在以下 5 条长文本活跃记忆（语境 95% 雷同，仅关键符号相差 1 ∼ 2 个字符）：
  
    1. `M1` ：在分布式事务模块中，当遇到错误码 `ERR_XA_RMFAIL_04` 时，需将重试退避阈值 `tx_backoff_ms` 设为 `500` ；
    2. `M2` ：在分布式事务模块中，当遇到错误码 `ERR_XA_RMERR_05` 时，需将重试退避阈值 `tx_backoff_ms` 设为 `1500` ；
    3. `M3` ：在分布式事务模块中，当遇到错误码 `ERR_XA_NOTA_06` 时，需直接触发死信队列告警；
    4. `M4` ：在分布式事务模块中，当遇到错误码 `ERR_XA_INVAL_07` 时，需降级为本地幂等表校验；
    5. `M5` ：在分布式事务模块中，当遇到错误码 `ERR_XA_PROTO_08` 时，需关闭连接池复用。
* **数学必然性** ：
  当查询为\*“高并发下事务模块报 `ERR_XA_PROTO_08` 怎么处理？”\*时，在 `bge-small` 的 384 维稠密空间里， `M1` ～ `M5` 的余弦相似度全部挤在 [ 0.91 , 0.94 ] 的极窄区间内，单向量通道在 Top-1 / Top-3 上会以高概率被前序节点挤占失分；而 FTS5 的 `bm25()` 对精确 Token `ERR_XA_PROTO_08` 具有极高的逆文档频率（IDF）爆发力，通过混合公式：
  
  \text{rel}(q, v) = \\min\\left(1.0, \\max(0.6 \\cdot s_{\\text{vec}} + 0.4 \\cdot s_{\\text{fts}}, 0.85 \\cdot s_{\\text{fts}}) + 0.15 \\cdot \\mathbb{I}(\\text{slot})\\right)
  
  能瞬间将 `M5` 精准置顶！只需构造 **20 组此类“同语境高碰撞专有符号”场景** ，即可在 `FastEmbed` 下实测跑出 **混合检索 Top-1 准确率比单向量通道净提升** ≥ 20 pp 的硬核曲线。

### 3.3 规约 3：开源仓库首屏（README.md）黄金 30 秒叙事结构

为了让开发者在点开 GitHub 仓库的 30 秒内按下 Star，阶段四生成的 `README.md` 必须严格采用以下结构：

1. **一句话定位与徽章栏** ：
   
    + 标题： **Gated-Mem: Git for Agent Memory**
    + 副标题： _Local, Auditable, Undoable Architecture State Engine for DeepSeek Harness ( `dsh` ), Claude Code & Cursor — Zero API Cost, Zero Context Rot._
    + 徽章： `Tests: 154 Passed` | `Coverage: 90%` | `Python: >=3.9` | `Dependencies: Zero (Core)` | `License: MIT`
2. **直击痛点的三栏对比表（Vector RAG vs. Prompt Wrapper vs. Gated-Mem）** ：
   
    + 直接引用阶段一（消融对比）、阶段二（22 节点高压截断 + 100 pp ）、阶段三/四（混合检索与零泄露双通道）的实测数据。
3. **30 秒极速上手（One-Line Setup）** ：
   
   ```
   # 1. 零依赖安全安装（或安装满血语义版 pip install "gated-mem[all]"）
   pip install gated-mem
   
   # 2. 一键挂载到你的 Agent（支持 dsh / claude / cursor 自动探测）
   gated-mem setup --agent dsh
   
   # 3. 像使用 Git 一样审计、解释与回滚 Agent 记忆
   gated-mem log --graph
   gated-mem explain <recall_event_id>
   gated-mem undo <event_id>
   gated-mem export-html -o memory_graph.html
   ```

## 四、 阶段四（Phase 4 · 开源发布与生态扩张）任务分解书（WBS）

阶段四设定为 **2 天轻量冲刺（Release Sprint）** ，保持既有铁三角阵型不变：

### 🔵 任务包 1：主程打包、交互式安装向导与 README 终稿（ `DeepSeek-V4.1F` ）

1. **打包加固（ `pyproject.toml` & `src/gated_mem/__init__.py` ）** ：
   
    + 锁定版本号 `__version__ = "1.0.0"` ；
    + 落地 **3.1 节分层可选依赖配置** ，确保裸装 `gated-mem` 零外部依赖，安装 `[onnx]` 时自动切换 `FastEmbedProvider` ；
    + 在 `gated-mem doctor` 中增加环境健康诊断（输出当前 Python 路径、SQLite WAL 状态、FTS5 状态、当前激活的 Embedder 名称与维度、已配置的 Agent 列表）。
2. **增强 `gated-mem setup` 交互式体验** ：
   
    + 支持 `gated-mem setup` （不带参数时自动按优先级探测本地已安装的 `dsh` 、 `claude` 、 `cursor` 并输出挂载摘要）与 `gated-mem setup --uninstall` （干净卸载注入的 MCP 配置块与 Skill 文件，做到“来去无痕”）。
3. **生成开源演示静态成品与双语 `README.md`** ：
   
    + 运行真实演进剧本，导出一份包含 15 个节点（含 `active` 、 `superseded` 、 `pinned` 、 `stale_parent_warning` 与 `[Replaced: ...]` 轨迹）的 `docs/demo_memory_graph.html` ，供用户在浏览器直接双击体验。

### 🔴 任务包 2：强语义难负例对抗基准集构建（ `GLM-5.3-Flash` ）

1. 独立编写 `benchmarks/build_phase4_hard_negatives.py` ，生成 `benchmarks/data/phase4_hard_negatives_20.json` （20 组“同语境高碰撞错误码/版本号/函数名/配置项”场景，每组含 5 个高度近似的长文本活跃节点）。
2. 评测并输出在 `FastEmbedProvider` （ `bge-small-zh-v1.5` ）下，【单向量 Cosine】vs【单 FTS5 BM25】vs【有界校准混合融合】的 Top-1 与 Top-3 准确率对比表，填补 Limitation #2 的最后一块拼图。

### 🟣 任务包 3：发版前打包安装与卸载净室终审（ `Gemini-3.8-Flash` ）

1. **Wheel 构建与净室安装测试** ：验证 `python -m build` （或 `pip install --no-deps -e .` ）构建产物完整， CLI 入口命令 `gated-mem --version` 与 `gated-mem doctor` 正常响应。
2. **安装与卸载可逆性测试** ：在临时 HOME 目录下执行 `gated-mem setup --agent dsh` → 验证 `cordis.patch.yml` 与 `SKILL.md` 正确生成 → 执行卸载/重装验证幂等性与零残留。
3. **难负例基准独立复核** ：复核 `phase4_hard_negatives_20.json` 上 `FastEmbed` 混合检索的净增益真实性，签署 `v1.0.0` 最终发版核准单。
