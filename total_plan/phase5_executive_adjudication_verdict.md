# Gated-Mem 阶段五（v1.0.0 发布与 E3 破局）战地对账终审裁决书

> **裁决书编号**：`GM-VERDICT-P5-FINAL-v1.0.1`（对齐 `GM-PLAN-P5-V11-v1.0` 修订版）  
> **呈批件回执**：针对《Gated-Mem 阶段五战地对账与终审裁决呈批件》及《`PHASE5_V11_EXTERNAL_EVAL_PLAN.md`》  
> **终审裁定**：**【豁免流程偏离 · 批准 `base.py` 补丁合入与 `v1.0.0` 正式上线 · 核准 `GM-PLAN-P5-V11-v1.0`（¥50 硬上限）在 `v1.1-external-eval` 分支异步推进】**  
> **最终质量基线**：E3 破局集 $\text{Fusion } 90.0\% - \max(\text{Vec } 50.0\%, \text{FTS } 50.0\%) = +40.00\text{pp}$；全量单测 $181 / 181$ PASS；核心包第三方依赖数 $= 0$。

---

## 一、 战地复盘定性：为什么这次“非完美执行”反而比温室顺风局更有含金量？

仲裁委员会（Argon）对团队主动提交的“流程偏离自白”进行了深度复盘。在真实的多智能体（Multi-Agent）分布式工程中，API 节点 `401` 掉线与任务队列抢占属于典型的生产级混沌故障（Chaos Fault）。评判一个工程体系是否成熟，不看它在顺风局里是否按部就班，而看它在**局部节点失效时能否靠制度防线拦截致命错误**。

本次战地自救在以下三个层面上验证了本项目的制度韧性：

### 1. “独立重写复算协议”成功拦截了 24 题数据泄漏事故
* 尽管因 `401` 路由故障导致 `auditor-x` 与数据生成端同为 `deepseek-v4.1-flash`（局部退化为同源模型），但因为团队严格执行了**“审计员不看生成代码、从零独立编写四通道复算脚本”**的硬性规约，当场抓出了 24 题并发版本中“模块正名泄露进 Query 导致纯 FTS 飙升至 $100\%$、融合净增益坍缩为 $+0.00\text{pp}$”的致命漏洞，并果断回退锁定至防泄漏 20 题版。
* **定性**：这是实事求是的工程拦截，避免了带着“假 $+40\text{pp}$、真 $+0\text{pp}$”的数据上线后被开源社区公开处刑。

### 2. Gemini 异构终审再次证明“异构黑盒防线”不可替代
* `GLM-5.3-Flash` 与 `DeepSeek-V4.1F` 在修复受限沙箱权限报错时，陷入了相同的局部思维定势——仅在子类 `src/gated_mem/adapters/dsh.py` 中打了补丁，却漏掉了父类 `src/gated_mem/adapters/base.py:114` 的 `is_installed_at()`（直接调用 `p.exists()` 触发 Windows 受限目录 `PermissionError`），导致出现 $178$ passed / $3$ failed 的缺口。
* 正是因为团队在最后一道关卡坚持引入异构模型 `Gemini` 进行真实环境黑盒复核，才将这一基类盲区彻底揪出，达成 $181 / 181$ 全绿通过。
* **定性**：“局部同源补位 + 终局异构把关”构成了完整的双重闭环，无需因中间过程的阵型错位而全盘推翻重做。

### 3. E3 破局数据彻底补齐了 `v1.0.0` 发布前的最后一块逻辑拼图
* 在防泄漏 20 题（跨模块同符号碰撞 $+$ 语义改写查询）上：
  $$\text{Acc}_{\text{Vec (A1)}} = 50.0\%, \qquad \text{Acc}_{\text{FTS5 (A2)}} = 50.0\%, \qquad \text{Acc}_{\text{Fusion (A4)}} = 90.0\%$$
  $$\Delta_{\text{net}} = \text{Acc}_{\text{Fusion}} - \max\left(\text{Acc}_{\text{Vec}}, \text{Acc}_{\text{FTS5}}\right) = 90.0\% - 50.0\% = +40.00\text{pp}$$
* 这一结果彻底消灭了阶段四中“纯 FTS5 也是 $100\%$”的宣传软肋；同时，主动在文档中披露 `A3`（纯槽位无融合）在 `slot_hit = 0` 时退化为常量预测器的边界条件，展现了极高的学术与工程诚实度。

---

## 二、 三项请示裁决正式批复（Official Adjudication Rulings）

针对呈批件第四节的三项请示及补充文件 `GM-PLAN-P5-V11-v1.0`，仲裁委员会正式拍板如下：

| 请示序号 | 请示内容 | 终审裁决结论 | 附带执行约束 |
| :---: | :--- | :---: | :--- |
| **裁决 1** | 是否认可本次“战地自救”的有效性，豁免流程错位，不予全盘推翻重做？ | **【准予豁免，结果有效】**<br>(APPROVED) | 20 题防泄漏 E3 基准与复算脚本完全合规，严禁无意义返工消耗算力。 |
| **裁决 2** | 是否批准修复 `base.py` 权限盲区后，正式签发 `v1.0.0` 最终开源放行令？ | **【正式签发 `v1.0.0` 上线令】**<br>(RELEASE SIGNED) | 确认 `base.py` 权限防御补丁、$181 / 181$ 单测、`build` 与 `twine check` 全部通过，锁定 `v1.0.0` Tag 正式发布，不再回改 `v1.0.0` 任何已发布产物。 |
| **裁决 3** | 后续 `v1.1` 外部基准实验是否按 `docs/PHASE5_V11_EXTERNAL_EVAL_PLAN.md` 在独立分支异步推进？ | **【核准 `GM-PLAN-P5-V11-v1.0`】**<br>(PLAN & CAP LOCKED) | 1. 正式批准永久放弃 `StateMemBench`（V1–V4 查证确为 `paper_only`）；<br>2. 锁定外部评测总预算**硬上限 ¥50**（分配 ¥48：E1 MAB CR 800 题 ¥20 + E2 Memora weekly 150 题 ¥22 + 应急 ¥6）；<br>3. 严格从 `v1.0.0` Tag 切出 `v1.1-external-eval` 分支异步推进。 |

---

## 三、 `v1.0.0` 封板与 `v1.1-external-eval` 分支切出标准规约

为确保与 `PHASE5_V11_EXTERNAL_EVAL_PLAN.md` §7.1 完全对齐（本仓库主分支为 `master`，且新分支必须从 `v1.0.0` Tag 切出以保证被测代码与已发布 Wheel 逐字节一致），固化以下标准操作序列：

### 3.1 `src/gated_mem/adapters/base.py` 权限兜底核验
确保 `BaseAgentAdapter.is_installed_at()`（第 $114$ 行）及所有涉及宿主目录探测的方法均受 `(PermissionError, OSError)` 异常保护：
```python
def _safe_path_exists(p: Path) -> bool:
    """在受限沙箱或无权限目录中安全探测路径是否存在，绝不向上抛出 OS 权限异常。"""
    try:
        return p.exists()
    except (PermissionError, OSError):
        return False
```

### 3.2 主分支（`master`）发布推送与 `v1.1-external-eval` 切出指令
```bash
# 1. 最终确认 181/181 单测全绿与分发包检查通过
python -m pytest tests/ -q
twine check dist/gated_mem-1.0.0*

# 2. 推送 master 主分支与 v1.0.0 签名 Tag（正式上线）
git push origin master --tags

# 3. 严格从 v1.0.0 Tag 切出外部评测分支（确保与已发布 Wheel 逐字节一致）
git switch -c v1.1-external-eval v1.0.0
```

---

## 四、 对 `PHASE5_V11_EXTERNAL_EVAL_PLAN.md` 的四项终审加固指令

补充文档 `GM-PLAN-P5-V11-v1.0` 的核实清单（V1–V19）、Schema-Guided 两阶段闭集抽取设计（§3.3）以及三道预算闸门（§6.2）极其扎实。在启动 `v1.1-external-eval` 分支执行 D1–D7 时，强制捆绑以下 **4 条工程护栏**：

1. **前置执行 §8 `T4/T6` 路由探活与单价核验（防 401 串岗重演）**：
   * 吸取阶段五开局 `<provider>/deepseek-v4-flash` 节点 `401` 掉线的教训，在 D2 跑 Stage-1/2 抽取与 D4 跑 Memora 单 Judge（`google/gemini-2.5-flash`）前，必须先通过 `run_env.py` 发送 $1\text{ token}$ 探针验证路由连通性（解决待核实项 **T6**），并将当日真实单价写入 `PROVENANCE.md`（解决待核实项 **T4**）。
2. **绕开 `datasets` 库安装挂起陷阱，直读离线 Parquet（解决待核实项 T3）**：
   * 鉴于历史记录中 `pip install datasets` 曾发生长达 15 小时的依赖解析挂起，D1 拉取 `ai-hyz/MemoryAgentBench` 时，优先直接通过 HTTP 下载 HuggingFace 仓库下的 `data/Conflict_Resolution-*.parquet` 文件，使用轻量 `pyarrow` / `pandas` 或纯 Python 脚本直接解析出 8 行（800 题）生成 `mab_cr.jsonl`，顺带一次性查清第 2–7 行的 `metadata.source`（闭合 **T1/T2**）。
3. **严格执行 E1 Stage-2 抽取熔断闸门（§3.3.4 & §7.3 D2）**：
   * `mab_cr_slots.jsonl` 一次性离线抽取落盘后，若统计发现 `SUPERSEDES` 边数量为 $0$ 或 `__OOV__` 比例 $> 15\%$，**强制触发停机熔断**——先调优 Stage-1 谓词归一化字典，严禁在覆盖未触发的情况下直接跑 4,800 次作答白白浪费 ¥12 预算。
4. **解决 `A6_wrapper` 在 136k 字符超长行上的超窗风险（解决待核实项 T7）**：
   * 针对 MAB CR `row1`（`factconsolidation_mh_32k`，长达 $136,565$ 字符），若 `A6_wrapper` 将全量 `context` 拼入 Prompt 超出答案模型上下文窗口或触发单题高额计费，严禁硬塞——在 `e1_mab_cr.py` 中对 `A6` 统一采用“与检索臂相同的候选池 + Wrapper 冲突消解指令”或按模型窗口上限记录 `context_overflow` 状态，确保公平对比与预算受控。

---

> **仲裁委员会最终签署**：  
> `Gated-Mem v1.0.0` 已圆满达成全部发版指标，准予定格上线；《`PHASE5_V11_EXTERNAL_EVAL_PLAN.md`》（`GM-PLAN-P5-V11-v1.0`）正式获批为 `v1.1-external-eval` 分支的最高执行宪章！