"""CLI 与导出器的进程内测试（提升覆盖率至 Gate 3 门槛）。"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from src.gated_mem import cli
from src.gated_mem.embeddings import BuiltinHashEmbedder
from src.gated_mem.exporter import build_snapshot, export_html, render_html, safe_json
from src.gated_mem.schema import MemoryNode, MemoryType
from src.gated_mem.storage import Store


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """准备一个临时库并切换 CLI 的默认路径。"""
    p = tmp_path / "m.db"
    monkeypatch.setenv("GATED_MEM_DB", str(p))
    return p


def _seed(path):
    s = Store(str(path))
    s.insert_memory(MemoryNode(
        memory_id="M1", content="主数据库选用 PostgreSQL 16",
        memory_type=MemoryType.DECISION, subject="db", predicate="engine",
        created_step=1, last_cited_step=1,
    ))
    s.close()


# ---------------------------------------------------------------------------
# Paint / 编码
# ---------------------------------------------------------------------------
def test_paint_disabled_returns_plain():
    p = cli.Paint(enabled=False)
    assert p("x", "red", "bold") == "x"


def test_paint_enabled_wraps_ansi():
    p = cli.Paint(enabled=True)
    out = p("x", "red")
    assert "\x1b[" in out and out.endswith("\x1b[0m")


def test_paint_unknown_style_is_noop():
    p = cli.Paint(enabled=True)
    assert p("x", "nope") == "x"


def test_default_db_path_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GATED_MEM_DB", str(tmp_path / "a.db"))
    assert cli.default_db_path() == tmp_path / "a.db"


def test_truncate():
    assert cli._truncate("abcdef", 4) == "abc…"
    assert cli._truncate("ab", 4) == "ab"


# ---------------------------------------------------------------------------
# 各子命令
# ---------------------------------------------------------------------------
def test_cmd_init(db, capsys):
    rc = cli.main(["init"])
    assert rc == 0
    assert db.exists()


def test_cmd_remember_and_status(db, capsys):
    assert cli.main(["remember", "主数据库选用 PostgreSQL 16",
                     "--subject", "db", "--predicate", "engine"]) == 0
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "节点总数" in out


def test_cmd_query(db, capsys):
    _seed(db)
    assert cli.main(["query", "数据库选型"]) == 0
    out = capsys.readouterr().out
    assert "当前有效记忆" in out


def test_cmd_doctor_ok(db, capsys):
    _seed(db)
    assert cli.main(["doctor"]) == 0


def test_cmd_log_plain_and_graph(db, capsys):
    _seed(db)
    assert cli.main(["log"]) == 0
    assert cli.main(["log", "--graph"]) == 0
    out = capsys.readouterr().out
    assert "M1" in out


def test_cmd_conflicts_empty(db, capsys):
    _seed(db)
    assert cli.main(["conflicts"]) == 0
    assert "没有挂起的冲突" in capsys.readouterr().out


def test_cmd_undo(db, capsys):
    _seed(db)
    store = Store(str(db))
    ev = store.get_memory("M1").source_event_id
    store.close()
    assert cli.main(["undo", ev]) == 0
    out = capsys.readouterr().out
    assert "已撤销" in out


def test_cmd_undo_missing(db, capsys):
    _seed(db)
    assert cli.main(["undo", "no-such"]) == 1


def test_cmd_explain(db, capsys):
    _seed(db)
    store = Store(str(db))
    from src.gated_mem.retrieval import Retriever

    r = Retriever(store, provider=BuiltinHashEmbedder())
    receipt = r.recall("数据库选型", write_event=True)
    store.close()
    assert cli.main(["explain", receipt.recall_event_id]) == 0
    out = capsys.readouterr().out
    assert "召回回执" in out


def test_cmd_explain_missing(db, capsys):
    _seed(db)
    assert cli.main(["explain", "nope"]) == 1


def test_cmd_resolve_keep_new(db, capsys):
    store = Store(str(db))
    from src.gated_mem.schema import MemoryStatus

    store.insert_memory(MemoryNode(
        memory_id="C1", content="模糊冲突", memory_type=MemoryType.DECISION,
        subject="db", predicate="engine", status=MemoryStatus.CANDIDATE_CONFLICT,
        created_step=1, last_cited_step=1,
    ))
    store.close()
    assert cli.main(["resolve", "C1", "--keep-new"]) == 0
    s2 = Store(str(db))
    assert s2.get_memory("C1").status == MemoryStatus.ACTIVE
    s2.close()


def test_cmd_resolve_keep_old(db, capsys):
    store = Store(str(db))
    from src.gated_mem.schema import MemoryStatus

    store.insert_memory(MemoryNode(
        memory_id="C2", content="MySQL 8.0 三节点", memory_type=MemoryType.DECISION,
        subject="db", predicate="engine", status=MemoryStatus.CANDIDATE_CONFLICT,
        created_step=1, last_cited_step=1,
    ))
    store.close()
    assert cli.main(["resolve", "C2", "--keep-old", "--reason", "保留旧方案"]) == 0
    s2 = Store(str(db))
    assert s2.get_memory("C2").status == MemoryStatus.SUPERSEDED
    s2.close()


def test_cmd_resolve_wrong_state(db, capsys):
    _seed(db)
    assert cli.main(["resolve", "M1", "--keep-new"]) == 1


def test_cmd_resolve_missing(db, capsys):
    _seed(db)
    assert cli.main(["resolve", "NOPE", "--keep-new"]) == 1


def test_cmd_export_html(db, capsys, tmp_path):
    _seed(db)
    out = tmp_path / "g.html"
    assert cli.main(["export-html", "-o", str(out)]) == 0
    assert out.exists()


def test_cmd_setup_unknown_agent(db):
    assert cli.main(["setup", "--agent", "nope"]) == 2


def test_cmd_setup_known_agent_dry_run(db, tmp_path):
    assert cli.main(["setup", "--agent", "claude_code", "--project", str(tmp_path),
                     "--dry-run"]) == 0


def test_main_no_args_prints_help(capsys):
    assert cli.main([]) == 0
    assert "Gated-Mem" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# exporter
# ---------------------------------------------------------------------------
def test_safe_json_escapes_script_close():
    out = safe_json({"a": "</script>"})
    assert "</script>" not in out
    assert "<\\/" in out


def test_build_snapshot_counts(tmp_path):
    s = Store(":memory:")
    s.insert_memory(MemoryNode(memory_id="A", content="x", memory_type=MemoryType.DECISION,
                               subject="s", predicate="p", created_step=1, last_cited_step=1))
    snap = build_snapshot(s)
    assert len(snap["nodes"]) == 1
    assert snap["max_step"] == 1


def test_build_snapshot_marks_stale(tmp_path):
    from src.gated_mem.schema import EdgeType, MemoryEdge, MemoryStatus

    s = Store(":memory:")
    s.insert_memory(MemoryNode(memory_id="P", content="父", memory_type=MemoryType.DECISION,
                               subject="p", predicate="p", created_step=1, last_cited_step=1))
    s.insert_memory(MemoryNode(memory_id="C", content="子", memory_type=MemoryType.DECISION,
                               subject="c", predicate="p", created_step=2, last_cited_step=2))
    s.insert_edge(MemoryEdge(edge_id="E1", source_id="C", target_id="P",
                             edge_type=EdgeType.BELONGS_TO, created_step=2))
    s.set_status("P", MemoryStatus.SUPERSEDED, 3)
    snap = build_snapshot(s)
    child = [n for n in snap["nodes"] if n["id"] == "C"][0]
    assert child["stale"] is True
    assert "P" in child["stale_ancestors"]


def test_render_html_contains_no_external_refs():
    html = render_html({"nodes": [], "edges": [], "max_step": 0})
    assert "http://" not in html.split("<script")[0].replace("https://www.w3.org", "")
    assert "innerHTML" not in html


def test_export_html_creates_parent_dirs(tmp_path):
    s = Store(":memory:")
    out = tmp_path / "deep" / "nested" / "g.html"
    export_html(s, out)
    assert out.exists()
