# Gated-Mem 阶段三缺陷修复终审复核报告

> **审计者**：Gemini-3.8-Flash（独立监察官，紫军异构终审位）  
> **复核任务**：`t3 — auditor: 复核自己报的 4 项缺陷是否已闭环`（Attempt ID: `01ec4ff4-9f30-4b11-ba87-9d5bdf8cdd45`）  
> **执行环境**：专用 Conda 环境 `<conda-env>/python`（Python 3.9.25，禁动 base）  
> **前序报告**：[phase3_gemini_final_audit.md](benchmarks/reports/phase3_gemini_final_audit.md)  
> **复核日期**：2026-11-12  

---

## 一、 复核裁决与闭环判定总表

独立监察官对主程针对上一轮终审报告提交的修复代码进行了黑盒脚本穿透测试。各项复核结论如下：

| 编号 | 审查项名称 | 涉及模块 | 原报问题描述 | 终审复核判定 | 核心判定依据 |
| :---: | :--- | :--- | :--- | :---: | :--- |
| **P1-1** | `_fts_query` 无序 Set 截断 | `retrieval.py` | `tokenize()` 返回 set 切片受哈希随机扰动，丢弃复合专有词 | **CLOSED** | 多随机种子下输出 100% 逐字符全等；分层权重保证 `ERR_PG_42P01` 绝对保留；lexical 命中率提升至 10/10 |
| **P1-2** | `touch_citation` 约束与落盘 | `storage.py` | 缺 commit、缺 project_id 约束、`insert_memory` 跨实例读不到 | **CLOSED**<br>*(commit 项澄清为 NOT_A_BUG)* | 连接为 `isolation_level=None`（自动提交）；已补齐 `project_id` 约束；同项目双实例即时读写通过 |
| **P2-1** | CLI `query` 不落盘事件 | `cli.py` | `cmd_query` 默认未记事件，导致后续 `explain` 查无此项 | **CLOSED** | 默认落盘 `RECALL_DELIVERED` 并回显 `recall_event_id`；`--dry-run` 严格 0 增长 |
| **P2-2** | `explain` 未显式透出轨迹 | `cli.py` | 回执中包含轨迹 ID 但未回表渲染 `[Replaced: ...]` | **CLOSED** | `explain` 输出中新增高亮章节 `演进轨迹（[Replaced: ...]）`，完整显示演进原因 |
| **额外** | CLI `remember` 槽位覆盖裁决 | `cli.py` | CLI 写入直接插库，绕过两阶段裁决，旧决策永远 active | **STILL_BROKEN**<br>*(引入新阻塞缺陷)* | `SUPERSEDES` 覆盖路径生效；但在 `CANDIDATE_CONFLICT` 挂起路径中因变量 `p = Paint()` 未提前初始化，**直接触发 `UnboundLocalError` 崩溃** |

### 门禁裁决令：**【需修改后复验（NEEDS_REVISION）】**

> **监察官批注**：  
> 原报的 4 项缺陷在算法和存储层均已高标准解决。然而在修复 CLI `remember` 裁决链路时，`cli.py` 第 215 行在调用 `p("⚠ 已挂起为候选冲突", ...)` 时，`p = Paint()` 却被写在第 235 行，导致**任何触发候选冲突的命令行写入操作 100% 抛出运行时崩溃**。  
> 秉持紫军独立监察“绝不给虚假 CLOSED”的铁律，在此正式亮黄灯。请 Tech Lead 将 `p = Paint()` 移至函数入口即可闭环。

---

## 二、 逐项独立黑盒实测证据与分析

### 1. P1-1 `_fts_query` 无序 Set 切片（`retrieval.py`）—— 【CLOSED】

#### 1.1 验证要求
- 同一长 query 在 `PYTHONHASHSEED = 0, 1, 2, 3, 7, 42, 999` 下产出**完全相同**的 FTS 查询串；
- `ERR_PG_42P01`、`max_wal_size`、`pghost_addr` 等复合 ASCII 专有 token 在包含 50+ token 的长自然语言查询中**必须绝对保留**。

#### 1.2 实测过程与证据
采用包含中文叙述、复合专有名词、配置项、路径的极端长查询：
`"线上订单服务昨晚发布后开始报 ERR_PG_42P01，如何结合 max_wal_size 与 PGHOST_ADDR 定位配置并排查 /v2/orders/{id}/refund 和 kafka-broker-quota-throttle.yaml？"`

在 7 个独立哈希种子下跨进程调用，截取实测输出：
```text
=== Testing PYTHONHASHSEED Consistency ===
[PASS] Seed 0 matches Seed 0
[PASS] Seed 1 matches Seed 0
[PASS] Seed 2 matches Seed 0
[PASS] Seed 3 matches Seed 0
[PASS] Seed 7 matches Seed 0
[PASS] Seed 42 matches Seed 0
[PASS] Seed 999 matches Seed 0

Sample FTS query string:
err_pg_42p01 OR max_wal_size OR pghost_addr OR v2 OR throttle OR broker OR orders OR refund OR kafka OR quota OR yaml OR id OR 上订 OR 位配 OR 何结 OR 务昨 OR 单服 OR 发布 OR 后开 OR 如何
```
- **关键 Token 保留检查**：
  - `err_pg_42p01` $\to$ **True**（位列第一位）
  - `max_wal_size` $\to$ **True**（位列第二位）
  - `pghost_addr` $\to$ **True**（位列第三位）
- **混合检索实测增益**：
  在 `benchmarks/data/phase3_hybrid_e2e_20.json` 上重新运行 `eval_phase3_hybrid.py`：
  - Lexical 组 FTS 命中率从上一轮的 **6/10（波动）** 彻底稳定提升至 **10/10（100.0%）**；
  - Builtin 引擎融合命中率从 **60.0%** 提升至 **65.0%（13/20）**。
- **结论**：算法通过 `rank(tok)` 引入（信息量分层 + 长度降序 + 字典序保底），彻底消除了跨进程的不确定性，核心专有 token 得到最高优先级保护。**判定 CLOSED**。

---

### 2. P1-2 `touch_citation` 约束与多 Project 存储隔离（`storage.py`）—— 【CLOSED】

#### 2.1 审查澄清（commit 项定性为 NOT_A_BUG）
经查阅 `Store.__init__`：
```python
self.conn = sqlite3.connect(path, isolation_level=None)
```
SQLite 连接已配置为自动提交模式（Autocommit），无未闭合事务包裹的单条 UPDATE/INSERT 语句会即时由驱动自动提交入 WAL，因此原审计对未调用 `self.conn.commit()` 的质疑不成立，定性为 **NOT_A_BUG**。

#### 2.2 跨 Project 隔离与约束修复实测
主程不仅在 `touch_citation` 中追加了 `AND project_id = ?`，更修复了 `insert_memory` 错用 `node.project_id` 的深层隐患。独立脚本设计了三维测试：
1. **同 Project 双实例可见性**：
   - 实例 1（`project_id="proj_alpha"`）写入节点 `ALPHA_01`（故意传入 `node.project_id="junk"`）；
   - 实例 2（同为 `"proj_alpha"`）立即通过 `get_memory("ALPHA_01")` 读取。
   - **实测**：实例 2 成功读出节点，且数据库中 `project_id` 字段已被自动校准为 `"proj_alpha"`。
2. **跨 Project 物理隔离**：
   - 实例 Beta（`project_id="proj_beta"`）调用 `get_memory("ALPHA_01")`。
   - **实测**：返回 `None`，跨项目不可见。
3. **`touch_citation` 防篡改**：
   - 实例 Beta 拥有节点 `BETA_01`（初始 `last_cited_step=10, citation_count=0`）；
   - 实例 Alpha 故意调用 `store_alpha.touch_citation("BETA_01", step=999)`；
   - 检查实例 Beta 中的 `BETA_01` 状态。
   - **实测**：`BETA_01` 步数仍为 10，计数仍为 0，跨项目更新被 `AND project_id = ?` 严格阻断！
   - 实例 Beta 自身调用 `store_beta.touch_citation("BETA_01", step=50)`，状态正确更新为 `step=50, count=1`。
- **结论**：**判定 CLOSED**。

---

### 3. P2-1 CLI `query` 事件落盘与 `explain` 连通性（`cli.py`）—— 【CLOSED】

#### 3.1 实测过程
1. **默认检索（落盘）**：
   - 调用 `gated-mem query "主数据库选型"`；
   - 检查数据库 `memory_events`：新增 1 条 `RECALL_DELIVERED` 事件；
   - 终端输出：
     ```text
     当前有效记忆
       • mem-b502fbaf1aff  (score=0.9500)
           主数据库选用 MySQL 8.0

     回执事件: 9142f9ae-7913-4318-ae25-27a3c3f912cd
       用 gated-mem explain 查看完整回执
     ```
2. **回执查验**：
   - 执行 `gated-mem explain 9142f9ae-7913-4318-ae25-27a3c3f912cd`；
   - 进程退出码为 **0**，成功解析并打印候选池规模、入选节点、拦截节点与演进链路。
3. **`--dry-run` 幂等性**：
   - 执行 `gated-mem query --dry-run "主数据库选型"`；
   - 检查数据库 `memory_events`：行数保持严格不变（$\Delta = 0$）；
   - 终端不输出 `回执事件:` 提示行。
- **结论**：**判定 CLOSED**。

---

### 4. P2-2 `explain` / `log` 展示 `evolution_traces`（`cli.py`）—— 【CLOSED】

#### 4.1 实测过程
构造包含演进替换的记忆链（`MySQL 8.0` $\to$ 被替换为 `PostgreSQL 16`，附带原因 `因并发瓶颈切换为 PG`）。执行检索后调用 `explain`：
```text
召回回执
  query: 主数据库选型
  候选池: 2  淘汰: 0  tokens: 42

  入选节点
    • mem-6d738f921a4e

  拦截的过期节点
    ✗ mem-b502fbaf1aff

  演进轨迹（[Replaced: ...]）
    mem-6d738f921a4e  [Replaced: MySQL 8.0] 因并发瓶颈切换为 PG
```
- **实测证据**：`explain` 准确提取出 `evolution_trace_ids`，回表提取出替换实体的名称与演进原因，并在终端高亮输出。
- **结论**：**判定 CLOSED**。

---

### 5. 额外项复核：CLI `remember` 覆盖裁决链路与新引入缺陷 —— 【STILL_BROKEN】

#### 5.1 正常覆盖路径（`SUPERSEDES`）
实测执行：
1. `gated-mem remember "主数据库选用 MySQL 8.0" --subject db --predicate engine --type DECISION`
   $\to$ 分配 `mem-b502fbaf1aff`，`action: CREATED`；
2. `gated-mem remember "主数据库选用 PostgreSQL 16 替代 MySQL 8.0 三节点集群" --subject db --predicate engine --type DECISION --residual-diff "因并发瓶颈切换为 PG"`
   - 终端输出：
     ```text
     ✓ 已写入
       memory_id: mem-6d738f921a4e
       event_id : fa3a887b-40fa-40ee-b384-5f5f59c8e228
       action   : SUPERSEDED
       覆盖    : mem-b502fbaf1aff -> superseded
       residual : [Replaced: MySQL 8.0] 因并发瓶颈切换为 PG
     ```
   - 数据库验证：旧节点状态已翻转为 `superseded`，新节点带有规范的 `[Replaced: ...]` 前缀。该分支工作完好。

#### 5.2 候选冲突路径（`CANDIDATE_CONFLICT` 崩溃复现）
实测执行同槽位但内容不明确的冲突决策写入：
`gated-mem remember "完全无关的离散缓存讨论" --subject db --predicate engine --type DECISION`

**终端直接抛出致命未捕获异常退出**：
```python
Traceback (most recent call last):
  File "<conda-env>/lib/runpy.py", line 197, in _run_module_as_main
    return _run_code(code, main_globals, None,
  File "<conda-env>/lib/runpy.py", line 87, in _run_code
    exec(code, run_globals)
  File "src\gated_mem\cli.py", line 565, in <module>
    sys.exit(main())
  File "src\gated_mem\cli.py", line 556, in main
    return int(args.func(args))
  File "src\gated_mem\cli.py", line 215, in cmd_remember
    print(p("⚠ 已挂起为候选冲突", "yellow"))
UnboundLocalError: local variable 'p' referenced before assignment
```

#### 5.3 缺陷机理与定位
查看 `src/gated_mem/cli.py` 的源码顺序：
```python
179: def cmd_remember(args) -> int:
         ...
213:     if decision == conflicts.CANDIDATE_CONFLICT:
214:         conflicted = conflicts.mark_candidate_conflict(store, node, olds, step)
215:         print(p("⚠ 已挂起为候选冲突", "yellow"))  # <-- 此处引用了局部变量 p
216:         print("  memory_id: %s" % conflicted.memory_id)
             ...
220:         store.close()
221:         return 0
         ...
235:     p = Paint()  # <-- 但 p 的实例化被写在第 235 行！
236:     print(p("✓ 已写入", "green"))
```
由于 Python 在函数编译期将 `p` 识别为局部变量，在执行到第 215 行时 `p` 尚未完成赋值，导致运行时崩溃。

#### 5.4 全库其他写入路径安全审查
监察官对全库所有可能的记忆写入路径进行了排查：
1. **`Store.insert_memory`**：存储层基础写入接口，仅负责行插入与 FTS 索引，不执行业务裁决，符合底盘定义；
2. **`GatedMemServer.gate_remember`**：MCP Server 核心写入路径，两阶段裁决、挂起冲突处理、`residual_diff` 拼装与事件写入全链路闭环，无缺陷；
3. **`adapters/ (dsh, claude_code, cursor)`**：纯配置生成与提示词注入工具，不包含任何记忆插入逻辑。
- **审查结论**：业务级写入入口仅有 MCP 与 CLI 两处。MCP 链路完好；CLI 链路的冲突挂起分支受制于上述 `UnboundLocalError`。

---

## 三、 整改指令书（1 行改动即可闭环）

请 Tech Lead（`DeepSeek-V4.1F`）在 `src/gated_mem/cli.py` 中执行以下微调：

**修改文件**：`src/gated_mem/cli.py`  
**修改位置**：`cmd_remember` 函数入口  
**修改方式**：
将 `p = Paint()` 提升至第 182 行（`store = open_store(args)` 紧随其后），确保 `if decision == conflicts.CANDIDATE_CONFLICT` 分支打印时 `p` 已处于就绪状态。

```python
# 修改前
def cmd_remember(args) -> int:
    store = open_store(args)
    provider = get_default_provider(...)
    ...
    if decision == conflicts.CANDIDATE_CONFLICT:
        ...
        print(p("⚠ 已挂起为候选冲突", "yellow"))  # Crash!

# 修改后
def cmd_remember(args) -> int:
    store = open_store(args)
    p = Paint()  # <-- 提前就绪
    provider = get_default_provider(...)
    ...
```

---

## 四、 终审签字与状态

- **复核结论**：4 项报修已有效闭环，但修复过程中附带引入了 CLI 冲突挂起路径的 `UnboundLocalError`（STILL_BROKEN）。
- **流程建议**：Tech Lead 修改 `cli.py` 第 182 行后即可完成最终封版，无需返工底盘。

**独立监察官签名**：`Gemini-3.8-Flash (Auditor)`  
**签署时间戳**：`2026-11-12T17:52:00+08:00`
