"""MCP Server 协议与工具测试。"""
from __future__ import annotations

import io
import json

import pytest

from src.gated_mem.server import GatedMemServer, serve, TOOL_DEFINITIONS
from src.gated_mem.schema import MemoryStatus


def make_server(tmp_path=None):
    db = str(tmp_path / "m.db") if tmp_path else ":memory:"
    return GatedMemServer(db_path=db, project_id="test")


def test_tools_list_has_four_tools():
    names = {t["name"] for t in TOOL_DEFINITIONS}
    assert names == {"gate_remember", "query_memory", "manage_memory", "undo_memory"}


def test_initialize_handshake():
    s = make_server()
    resp = s.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp["result"]["serverInfo"]["name"] == "gated-mem"
    assert "protocolVersion" in resp["result"]


def test_gate_remember_creates():
    s = make_server()
    out = s.gate_remember(
        content="主数据库选用 PostgreSQL 16",
        memory_type="DECISION", subject="db", predicate="engine",
    )
    assert out["action"] == "CREATED"
    assert out["memory_id"].startswith("mem-")


def test_gate_remember_supersede_generates_replaced_prefix():
    s = make_server()
    s.gate_remember(content="主数据库选用 MySQL 8.0 作为生产存储方案",
                    memory_type="DECISION", subject="db", predicate="engine")
    out = s.gate_remember(
        content="主数据库选用 MySQL 8.0 作为生产存储方案的替代：PostgreSQL 16",
        memory_type="DECISION", subject="db", predicate="engine",
        residual_diff="因需支持 JSONB 高并发索引查询",
    )
    assert out["action"] in ("SUPERSEDED", "CREATED")
    node = s.store.get_memory(out["memory_id"])
    assert "[Replaced:" in (node.residual_diff or "")


def test_gate_remember_conflict_pending():
    s = make_server()
    s.gate_remember(content="主数据库选用 MySQL 8.0 三节点集群部署方案",
                    memory_type="DECISION", subject="db", predicate="engine")
    out = s.gate_remember(content="完全不相关的缓存层讨论内容",
                          memory_type="DECISION", subject="db", predicate="engine")
    assert out["action"] == "CONFLICT_PENDING"


def test_query_memory_returns_xml_with_readonly():
    s = make_server()
    s.gate_remember(content="主数据库选用 PostgreSQL 16",
                    memory_type="DECISION", subject="db", predicate="engine")
    xml = s.query_memory("主数据库选型", top_k=5)
    assert "<gated_memory_context" in xml
    assert "readonly" in xml
    assert "<active_memories>" in xml


def test_query_memory_dry_run_is_pure():
    s = make_server()
    s.gate_remember(content="主数据库选用 PostgreSQL 16",
                    memory_type="DECISION", subject="db", predicate="engine")
    before = s.store.conn.execute("SELECT COUNT(*) AS c FROM memory_events").fetchone()["c"]
    for _ in range(10):
        s.query_memory("主数据库选型", dry_run=True)
    after = s.store.conn.execute("SELECT COUNT(*) AS c FROM memory_events").fetchone()["c"]
    assert before == after, "dry_run 不得写入任何事件"


def test_query_memory_dry_run_does_not_touch_citation():
    s = make_server()
    out = s.gate_remember(content="主数据库选用 PostgreSQL 16",
                          memory_type="DECISION", subject="db", predicate="engine")
    n1 = s.store.get_memory(out["memory_id"])
    for _ in range(5):
        s.query_memory("主数据库选型", dry_run=True)
    n2 = s.store.get_memory(out["memory_id"])
    assert n1.last_cited_step == n2.last_cited_step


def test_recall_does_not_auto_touch():
    """P3 §3.3：召回本身不续命，只有 cited_ids 才续命。"""
    s = make_server()
    out = s.gate_remember(content="主数据库选用 PostgreSQL 16",
                          memory_type="DECISION", subject="db", predicate="engine")
    n1 = s.store.get_memory(out["memory_id"])
    s.query_memory("主数据库选型")
    n2 = s.store.get_memory(out["memory_id"])
    assert n1.last_cited_step == n2.last_cited_step, "普通召回不得刷新 last_cited_step"


def test_cited_ids_refreshes_citation():
    s = make_server()
    out = s.gate_remember(content="主数据库选用 PostgreSQL 16",
                          memory_type="DECISION", subject="db", predicate="engine")
    before = s.store.get_memory(out["memory_id"])
    s.query_memory("主数据库选型", cited_ids=[out["memory_id"]])
    after = s.store.get_memory(out["memory_id"])
    assert after.citation_count > before.citation_count


def test_manage_memory_pin_unpin():
    s = make_server()
    out = s.gate_remember(content="安全约束：禁止硬编码密钥",
                          memory_type="CONSTRAINT", subject="sec", predicate="rule")
    mid = out["memory_id"]
    s.manage_memory("pin", mid)
    assert s.store.get_memory(mid).pinned is True
    s.manage_memory("unpin", mid)
    assert s.store.get_memory(mid).pinned is False


def test_manage_memory_kill():
    s = make_server()
    out = s.gate_remember(content="临时观察：编译失败疑似缓存",
                          memory_type="EPHEMERAL", subject="tmp", predicate="obs")
    s.manage_memory("kill", out["memory_id"])
    assert s.store.get_memory(out["memory_id"]).status == MemoryStatus.KILLED


def test_manage_memory_resolve_conflict():
    s = make_server()
    s.gate_remember(content="主数据库选用 MySQL 8.0 三节点集群部署方案",
                    memory_type="DECISION", subject="db", predicate="engine")
    out = s.gate_remember(content="完全不相关的缓存层讨论内容",
                          memory_type="DECISION", subject="db", predicate="engine")
    assert out["action"] == "CONFLICT_PENDING"
    s.manage_memory("resolve_keep_new", out["memory_id"])
    assert s.store.get_memory(out["memory_id"]).status == MemoryStatus.ACTIVE


def test_undo_memory_roundtrip():
    s = make_server()
    out = s.gate_remember(content="主数据库选用 PostgreSQL 16",
                          memory_type="DECISION", subject="db", predicate="engine")
    s.undo_memory(out["event_id"])
    assert s.store.get_memory(out["memory_id"]) is None


def test_unknown_tool_returns_error_frame():
    s = make_server()
    resp = s.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                     "params": {"name": "nope", "arguments": {}}})
    assert "error" in resp


def test_parse_error_returns_valid_frame():
    s = make_server()
    stdin = io.StringIO("not json at all\n")
    stdout = io.StringIO()
    serve(s, stdin=stdin, stdout=stdout)
    line = stdout.getvalue().strip()
    frame = json.loads(line)
    assert frame["error"]["code"] == -32700


def test_notification_gets_no_response():
    s = make_server()
    resp = s.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp is None
