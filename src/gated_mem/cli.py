"""命令行入口。

设计原则：
  - 零第三方重依赖：rich 存在则用，不存在则回退到 ANSI 转义（标准库）
  - 所有子命令在真实子进程里都能跑通（Gate 3 会用 subprocess 逐一验收）
  - 绝不把调试信息写到 stdout 的协议帧里（CLI 是终端工具，stdout 是给人看的）

子命令：init / status / doctor / remember / query / log --graph / explain /
        conflicts / resolve / undo / export-html / setup
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import adapters
from .adapters import base as adapter_base
from .conflicts import format_residual_diff
from .embeddings import get_default_provider
from .events import EventLog
from .retrieval import Retriever
from .schema import MemoryNode, MemoryStatus, MemoryType
from .storage import Store

# ---------------------------------------------------------------------------
# 控制台编码安全
# ---------------------------------------------------------------------------
def _safe_console_stream():
    """把 stdout 包装成 UTF-8，避免中文 Windows 的 GBK 编码崩溃。

    这是真实踩过的坑：默认 GBK 下 print("✓") 直接抛 UnicodeEncodeError。
    """
    stream = sys.stdout
    enc = (getattr(stream, "encoding", None) or "").lower()
    if enc in ("utf-8", "utf8", "cp65001"):
        return stream
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
        return stream
    except Exception:
        return stream


# ---------------------------------------------------------------------------
# 颜色（rich 优先，标准库 ANSI 回退）
# ---------------------------------------------------------------------------
try:  # pragma: no cover - 取决于环境
    from rich.console import Console as _RichConsole

    _RICH = True
except Exception:
    _Rich = None
    _RICH = False


class Paint(object):
    """极简着色器。TC 环境或无 TTY 时自动降级为无色。"""

    CODES = {
        "red": "31", "green": "32", "yellow": "33",
        "blue": "34", "magenta": "35", "cyan": "36", "gray": "90",
        "bold": "1", "dim": "2",
    }

    def __init__(self, enabled: Optional[bool] = None) -> None:
        if enabled is None:
            enabled = hasattr(sys.stdout, "isatty") and sys.stdout.isatty() and os.name != "nt"
            if os.name == "nt" and os.environ.get("WT_SESSION"):
                enabled = True
        self.enabled = bool(enabled)

    def __call__(self, text: str, *styles: str) -> str:
        """给文本套色。"""
        if not self.enabled or not styles:
            return text
        codes = [self.CODES[s] for s in styles if s in self.CODES]
        if not codes:
            return text
        return "\x1b[%sm%s\x1b[0m" % (";".join(codes), text)


# ---------------------------------------------------------------------------
# 数据库定位
# ---------------------------------------------------------------------------
def default_db_path() -> Path:
    """默认数据库路径：项目内 .gated-mem/memory.db。"""
    env = os.environ.get("GATED_MEM_DB")
    if env:
        return Path(env)
    return Path.cwd() / ".gated-mem" / "memory.db"


def open_store(args) -> Store:
    """按参数打开存储。"""
    db = Path(args.db) if getattr(args, "db", None) else default_db_path()
    if str(db) != ":memory:":
        db.parent.mkdir(parents=True, exist_ok=True)
    project = getattr(args, "project_id", None) or "default"
    return Store(str(db), project_id=project)


# ---------------------------------------------------------------------------
# 子命令实现
# ---------------------------------------------------------------------------
def cmd_init(args) -> int:
    """初始化记忆库并打印落盘位置。"""
    store = open_store(args)
    p = Paint()
    n = len(store.all_memories())
    print(p("✓ 记忆库已就绪", "green", "bold"))
    print("  路径: %s" % store.conn.execute("PRAGMA database_list").fetchone()[2])
    print("  现有节点: %d" % n)
    store.close()
    return 0


def cmd_status(args) -> int:
    """打印库状态概览。"""
    store = open_store(args)
    p = Paint()
    nodes = store.all_memories()
    by_status: Dict[str, int] = {}
    for n in nodes:
        by_status[n.status.value] = by_status.get(n.status.value, 0) + 1
    ev = store.conn.execute("SELECT COUNT(*) AS c FROM memory_events").fetchone()["c"]
    print(p("Gated-Mem 状态", "bold"))
    print("  节点总数: %d" % len(nodes))
    for st in sorted(by_status):
        print("    %-20s %d" % (st, by_status[st]))
    print("  事件总数: %d" % ev)
    store.close()
    return 0


def cmd_doctor(args) -> int:
    """体检：WAL / FTS5 / 向量维度一致性。"""
    store = open_store(args)
    p = Paint()
    ok = True

    mode = store.conn.execute("PRAGMA journal_mode").fetchone()[0]
    good = str(mode).lower() == "wal"
    ok = ok and good
    print("  [%s] journal_mode = %s" % ("OK" if good else "FAIL", mode))

    try:
        store.conn.execute("SELECT count(*) FROM memories_fts").fetchone()
        print("  [OK] FTS5 虚表可查询")
    except Exception as exc:
        ok = False
        print("  [FAIL] FTS5: %s" % exc)

    dims = set()
    for n in store.all_memories():
        if n.embedding:
            dims.add(len(n.embedding))
    if len(dims) <= 1:
        print("  [OK] 向量维度一致: %s" % (sorted(dims) or "无向量"))
    else:
        ok = False
        print("  [FAIL] 向量维度混杂: %s" % sorted(dims))

    models = {n.embedding_model for n in store.all_memories() if n.embedding}
    if len(models) <= 1:
        print("  [OK] 向量模型一致: %s" % (sorted(models) or "无向量"))
    else:
        ok = False
        print("  [FAIL] 向量模型混杂: %s" % sorted(models))

    store.close()
    print("\n结论: %s" % ("健康" if ok else "存在问题"))
    return 0 if ok else 1


def cmd_remember(args) -> int:
    """写入一条记忆。"""
    store = open_store(args)
    provider = get_default_provider(os.environ.get("GATED_MEM_EMBEDDING", "builtin"))
    step = int(
        (store.conn.execute("SELECT MAX(step) AS s FROM memory_events").fetchone()["s"] or 0)
    ) + 1
    node = MemoryNode(
        memory_id="mem-" + os.urandom(6).hex(),
        project_id=store.project_id,
        content=args.content,
        memory_type=MemoryType(args.type),
        subject=args.subject,
        predicate=args.predicate,
        scope=args.scope,
        input_weight=args.weight,
        residual_diff=args.residual_diff,
        embedding=provider.embed_one(args.content),
        embedding_model=provider.model_id,
        created_step=step,
        last_cited_step=step,
    )
    # 必须走两阶段槽位裁决，否则 CLI 写入永远不会触发覆盖，
    # 导致旧决策一直 active（命令行与 MCP 两条写入路径行为不一致）。
    from . import conflicts

    decision, olds = conflicts.decide(
        store,
        {"content": node.content},
        node.subject,
        node.predicate,
        node.scope,
    )

    if decision == conflicts.CANDIDATE_CONFLICT:
        conflicted = conflicts.mark_candidate_conflict(store, node, olds, step)
        print(p("⚠ 已挂起为候选冲突", "yellow"))
        print("  memory_id: %s" % conflicted.memory_id)
        print("  与 %s 槽位相同但内容不明确，待人工裁决"
              % ",".join(o.memory_id for o in olds))
        print("  用 gated-mem resolve %s --keep-new|--keep-old" % conflicted.memory_id)
        store.close()
        return 0

    eid = store.insert_memory(node)
    action = "CREATED"
    if decision == conflicts.SUPERSEDES and olds:
        updated = conflicts.apply_supersede(
            store, node, olds, step, reason=args.residual_diff
        )
        store.conn.execute(
            "UPDATE memories SET residual_diff=? WHERE memory_id=?",
            (updated.residual_diff, node.memory_id),
        )
        action = "SUPERSEDED"

    p = Paint()
    print(p("✓ 已写入", "green"))
    print("  memory_id: %s" % node.memory_id)
    print("  event_id : %s" % eid)
    print("  action   : %s" % action)
    if action == "SUPERSEDED":
        for o in olds:
            print("  覆盖    : %s -> superseded" % o.memory_id)
        print("  residual : %s" % (updated.residual_diff or ""))
    elif args.residual_diff:
        print("  residual : %s" % node.residual_diff)
    store.close()
    return 0


def cmd_query(args) -> int:
    """检索并打印双通道回执。"""
    store = open_store(args)
    provider = get_default_provider(os.environ.get("GATED_MEM_EMBEDDING", "builtin"))
    r = Retriever(store, topk=args.top_k, provider=provider)
    # 默认落盘 RECALL_DELIVERED，否则用户跑完 query 再 explain 必然查不到。
    # --dry-run 可显式关闭（不写事件、不刷新引用）。
    receipt = r.recall(args.text, topk=args.top_k, write_event=not args.dry_run)
    p = Paint()
    print(p("当前有效记忆", "bold", "green"))
    if not receipt.injected_items:
        print("  (无命中)")
    for item in receipt.injected_items:
        flag = p(" [⚠ STALE]", "yellow") if item.stale_parent_warning else ""
        print("  • %s%s  (score=%.4f)" % (p(item.memory_id, "cyan"), flag, item.score))
        print("      %s" % item.content)
    if receipt.evolution_traces:
        print(p("\n演进轨迹", "bold", "magenta"))
        for tr in receipt.evolution_traces:
            print("  ↳ %s" % tr.residual_diff)
    if receipt.recall_event_id and not args.dry_run:
        print(p("\n回执事件: %s" % receipt.recall_event_id, "gray"))
        print(p("  用 gated-mem explain 查看完整回执", "gray"))
    store.close()
    return 0


def cmd_log(args) -> int:
    """打印演进历史。--graph 时渲染树。"""
    store = open_store(args)
    p = Paint()
    log = EventLog(store)
    events = log.history(limit=args.limit)
    if not args.graph:
        for ev in events:
            print("%-6s %-22s %s" % (ev.step, ev.event_type.value, ev.event_id[:12]))
        store.close()
        return 0

    # 图模式：按节点画时间线
    nodes = {n.memory_id: n for n in store.all_memories()}
    for ev in events:
        try:
            payload = json.loads(ev.payload_json)
        except ValueError:
            payload = {}
        mid = payload.get("memory_id") or ""
        node = nodes.get(mid)
        if ev.event_type.value == "MEMORY_CREATED" and node is not None:
            print("%s %s %s" % (p("●", "green"), p(mid, "cyan"), _truncate(node.content, 48)))
        elif ev.event_type.value == "MEMORY_SUPERSEDED":
            print("  %s %s %s" % (p("└─", "red"), p(mid, "cyan"), p("[SUPERSEDED]", "red")))
    # 标出 stale
    for n in store.all_memories():
        anc = [a for a, _d in store.ancestors_recursive(n.memory_id, max_depth=8)]
        stale = [
            a for a in anc
            if (store.get_memory(a) is not None and store.get_memory(a).status.value
                in ("superseded", "killed"))
        ]
        if stale:
            print("  %s %s %s" % (p("⚠", "yellow"), p(n.memory_id, "cyan"),
                                  p("[⚠ STALE_PARENT]", "yellow")))
    store.close()
    return 0


def cmd_explain(args) -> int:
    """解析某次召回的完整回执。"""
    store = open_store(args)
    row = store.conn.execute(
        "SELECT payload_json FROM memory_events WHERE event_id=? AND event_type=?",
        (args.recall_event_id, "RECALL_DELIVERED"),
    ).fetchone()
    if row is None:
        sys.stderr.write("找不到该 RECALL_DELIVERED 事件：%s\n" % args.recall_event_id)
        store.close()
        return 1
    payload = json.loads(row["payload_json"])
    p = Paint()
    print(p("召回回执", "bold"))
    print("  query: %s" % payload.get("query", ""))
    print("  候选池: %s  淘汰: %s  tokens: %s"
          % (payload.get("candidate_pool_size"), payload.get("truncated_candidates"),
             payload.get("tokens_used")))
    print(p("\n  入选节点", "green"))
    for mid in payload.get("injected_ids", []):
        print("    • %s" % mid)
    print(p("\n  拦截的过期节点", "red"))
    for mid in payload.get("excluded_stale_ids", []):
        print("    ✗ %s" % mid)
    warns = payload.get("stale_warnings") or []
    if warns:
        print(p("\n  ⚠ 祖先废弃告警", "yellow"))
        for w in warns:
            print("    %s -> %s" % (w.get("memory_id"), ",".join(w.get("stale_ancestor_ids", []))))

    # 演进轨迹：payload 里只存了 id，这里回表取 residual_diff 渲染出来
    trace_ids = payload.get("evolution_trace_ids") or []
    rendered = []
    for mid in trace_ids:
        node = store.get_memory(mid)
        if node is not None and node.residual_diff:
            rendered.append((mid, node.residual_diff))
    if rendered:
        print(p("\n  演进轨迹（[Replaced: ...]）", "magenta"))
        for mid, diff in rendered:
            print("    %s  %s" % (p(mid, "cyan"), diff))
    else:
        print(p("\n  演进轨迹: 无", "gray"))
    store.close()
    return 0


def cmd_conflicts(args) -> int:
    """列出挂起的冲突节点。"""
    store = open_store(args)
    p = Paint()
    rows = store.all_memories([MemoryStatus.CANDIDATE_CONFLICT.value])
    if not rows:
        print("没有挂起的冲突。")
    for n in rows:
        print("%s  %s" % (p(n.memory_id, "yellow"), _truncate(n.content, 60)))
    store.close()
    return 0


def cmd_resolve(args) -> int:
    """裁决一个挂起冲突。"""
    store = open_store(args)
    step = int(
        (store.conn.execute("SELECT MAX(step) AS s FROM memory_events").fetchone()["s"] or 0)
    ) + 1
    node = store.get_memory(args.memory_id)
    if node is None:
        sys.stderr.write("节点不存在：%s\n" % args.memory_id)
        store.close()
        return 1
    if node.status != MemoryStatus.CANDIDATE_CONFLICT:
        sys.stderr.write("该节点不处于 candidate_conflict（当前 %s）\n" % node.status.value)
        store.close()
        return 1
    if args.keep_new:
        store.set_status(args.memory_id, MemoryStatus.ACTIVE, step)
        print("已保留新状态：%s" % args.memory_id)
    else:
        diff = format_residual_diff(node, args.reason or "人工裁决保留旧状态")
        store.conn.execute("UPDATE memories SET residual_diff=? WHERE memory_id=?",
                           (diff, args.memory_id))
        store.set_status(args.memory_id, MemoryStatus.SUPERSEDED, step)
        print("已保留旧状态，新节点标记为 superseded：%s" % args.memory_id)
        print("  %s" % diff)
    store.close()
    return 0


def cmd_undo(args) -> int:
    """撤销事件。"""
    store = open_store(args)
    try:
        res = store.undo(args.event_id)
    except Exception as exc:
        sys.stderr.write("撤销失败：%s\n" % exc)
        store.close()
        return 1
    print("已撤销 %d 个事件" % len(res["undone_event_ids"]))
    for eid in res["undone_event_ids"]:
        print("  - %s" % eid)
    store.close()
    return 0


def cmd_export_html(args) -> int:
    """导出离线单文件 HTML 图谱。"""
    from .exporter import export_html

    store = open_store(args)
    out = Path(args.output) if args.output else Path("memory_graph.html")
    stats = export_html(store, out)
    print("已导出：%s" % out)
    print("  节点 %d / 边 %d / 文件 %.1f KB"
          % (stats["nodes"], stats["edges"], stats["bytes"] / 1024.0))
    store.close()
    return 0


def cmd_setup(args) -> int:
    """自动扫描并安装适配器。"""
    p = Paint()
    project = Path(args.project or os.getcwd())

    if args.agent:
        try:
            ad = adapter_base.get_adapter(args.agent)
        except adapter_base.AdapterError as exc:
            sys.stderr.write("%s\n" % exc)
            return 2
        targets = [ad]
    else:
        targets = adapter_base.detect_available()
        if not targets:
            sys.stderr.write(
                "未检测到任何已安装的 Agent。请显式指定 --agent（可选：%s）\n"
                % ", ".join(a.agent_name for a in adapter_base.all_adapters())
            )
            return 2

    print(p("Gated-Mem 安装向导", "bold"))
    for ad in targets:
        installed = ad.detect_installed()
        tag = p("已检测到", "green") if installed else p("未检测到", "gray")
        print("\n  %s %s  [%s]" % (p("▸", "cyan"), ad.display_name, tag))
        for path in ad.config_paths(project):
            print("      将写入: %s" % path)
        if args.dry_run:
            print("      (dry-run，未写入)")
            continue
        written = ad.install(project)
        for w in written:
            print("      %s %s" % (p("✓", "green"), w))

    if not args.dry_run and targets:
        print("\n%s" % p("安装完成。重启对应 Agent 后即可使用 gated-mem 工具。", "green"))
    return 0


# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。"""
    ap = argparse.ArgumentParser(
        prog="gated-mem",
        description="Gated-Mem：面向超长开发周期的本地可审计、可回滚架构状态引擎",
    )
    ap.add_argument("--db", help="数据库路径（默认 .gated-mem/memory.db）")
    ap.add_argument("--project-id", dest="project_id", default=None)
    sub = ap.add_subparsers(dest="command")

    sub.add_parser("init", help="初始化记忆库").set_defaults(func=cmd_init)
    sub.add_parser("status", help="显示状态概览").set_defaults(func=cmd_status)
    sub.add_parser("doctor", help="体检 WAL/FTS5/向量一致性").set_defaults(func=cmd_doctor)

    r = sub.add_parser("remember", help="写入一条记忆")
    r.add_argument("content")
    r.add_argument("--type", default="DECISION",
                   choices=["DECISION", "CONSTRAINT", "PREFERENCE", "EPHEMERAL"])
    r.add_argument("--subject", required=True)
    r.add_argument("--predicate", required=True)
    r.add_argument("--scope", default="global")
    r.add_argument("--weight", type=float, default=0.5)
    r.add_argument("--residual-diff", dest="residual_diff", default=None)
    r.set_defaults(func=cmd_remember)

    q = sub.add_parser("query", help="检索记忆")
    q.add_argument("text")
    q.add_argument("--top-k", dest="top_k", type=int, default=5)
    q.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="不写入 RECALL_DELIVERED 事件（评测用）")
    q.set_defaults(func=cmd_query)

    lg = sub.add_parser("log", help="演进历史")
    lg.add_argument("--graph", action="store_true")
    lg.add_argument("--limit", type=int, default=100)
    lg.set_defaults(func=cmd_log)

    ex = sub.add_parser("explain", help="解析召回回执")
    ex.add_argument("recall_event_id")
    ex.set_defaults(func=cmd_explain)

    sub.add_parser("conflicts", help="列出挂起冲突").set_defaults(func=cmd_conflicts)

    rs = sub.add_parser("resolve", help="裁决挂起冲突")
    rs.add_argument("memory_id")
    g = rs.add_mutually_exclusive_group(required=True)
    g.add_argument("--keep-new", dest="keep_new", action="store_true")
    g.add_argument("--keep-old", dest="keep_new", action="store_false")
    rs.add_argument("--reason", default=None)
    rs.set_defaults(func=cmd_resolve)

    un = sub.add_parser("undo", help="撤销事件")
    un.add_argument("event_id")
    un.set_defaults(func=cmd_undo)

    eh = sub.add_parser("export-html", help="导出离线 HTML 图谱")
    eh.add_argument("-o", "--output", default=None)
    eh.set_defaults(func=cmd_export_html)

    st = sub.add_parser("setup", help="为宿主 Agent 自动安装 MCP 配置")
    st.add_argument("--agent", default=None,
                    help="指定 agent（dsh / claude_code / cursor）；省略则自动扫描")
    st.add_argument("--project", default=None)
    st.add_argument("--dry-run", dest="dry_run", action="store_true")
    st.set_defaults(func=cmd_setup)

    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    """入口。"""
    _safe_console_stream()
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "command", None):
        ap.print_help()
        return 0
    return int(args.func(args))


def _truncate(s: str, n: int) -> str:
    """截断并加省略号。"""
    return s if len(s) <= n else s[: n - 1] + "…"


if __name__ == "__main__":
    sys.exit(main())
