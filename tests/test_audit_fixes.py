"""阶段三审计发现的缺陷回归测试（P1/P2 全量覆盖）。"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from src.gated_mem.retrieval import _fts_query
from src.gated_mem.schema import MemoryNode, MemoryType
from src.gated_mem.storage import Store


# ---------------------------------------------------------------------------
# P1-1: _fts_query 必须确定性，且优先保留高价值专有 token
# ---------------------------------------------------------------------------
def test_fts_query_is_deterministic_across_hash_seeds():
    """frozenset 迭代顺序随 PYTHONHASHSEED 变化，必须 sorted 后再切片。

    这是真实缺陷：不排序时同一个 query 在不同进程里会丢掉不同的 token，
    导致 ERR_PG_42P01 这类精确错误码随机消失。
    """
    q = "ERR_PG_42P01 是什么错误，max_wal_size 该怎么配才能避免连接池打满"
    outs = set()
    for seed in ("0", "1", "2", "3", "7"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        code = (
            "import sys; sys.path.insert(0,'src');"
            "from gated_mem.retrieval import _fts_query;"
            "print(_fts_query(%r))" % q
        )
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           env=env, timeout=120)
        outs.add(r.stdout.strip())
    assert len(outs) == 1, "不同 hash seed 产出不同 FTS 查询串：%r" % outs


def test_fts_query_prioritizes_proprietary_tokens():
    """长查询截断到 20 个 token 时，复合 ASCII 专有名词必须保留。"""
    q = ("ERR_PG_42P01 这个错误到底是什么意思，我们在 max_wal_size 配置上"
         "纠结了很久，还讨论了连接池大小、主库并发瓶颈、读写分离、"
         "事务隔离级别、索引策略、慢查询日志、以及备份恢复窗口等一堆话题")
    out = _fts_query(q)
    assert "err_pg_42p01" in out, "精确错误码被丢弃：%s" % out
    assert "max_wal_size" in out, "配置键被丢弃：%s" % out


def test_fts_query_escapes_syntax_chars():
    out = _fts_query('a "b" c:d *e* (f)')
    for ch in '"\':*()':
        assert ch not in out


# ---------------------------------------------------------------------------
# P1-2: project_id 作用域
# ---------------------------------------------------------------------------
def test_insert_memory_uses_store_project_id(tmp_path):
    """节点的 project_id 必须以 Store 为准，否则跨实例读不到。"""
    db = str(tmp_path / "p.db")
    s1 = Store(db, project_id="proj-a")
    s1.insert_memory(MemoryNode(
        memory_id="M1", content="x", memory_type=MemoryType.DECISION,
        subject="s", predicate="p", created_step=1, last_cited_step=1,
    ))
    s2 = Store(db, project_id="proj-a")
    assert s2.get_memory("M1") is not None, "同一 project_id 的另一个实例读不到节点"
    s1.close()
    s2.close()


def test_touch_citation_is_project_scoped(tmp_path):
    """touch_citation 不能误改其他项目的同名节点。"""
    db = str(tmp_path / "p.db")
    a = Store(db, project_id="A")
    a.insert_memory(MemoryNode(memory_id="M1", content="x",
                               memory_type=MemoryType.DECISION, subject="s",
                               predicate="p", created_step=1, last_cited_step=1))
    a.touch_citation("M1", 9)
    assert a.get_memory("M1").last_cited_step == 9

    b = Store(db, project_id="B")
    b.touch_citation("M1", 100)
    assert a.get_memory("M1").last_cited_step == 9, "跨项目误改"
    a.close()
    b.close()


def test_touch_citation_persists_across_connections(tmp_path):
    """连接是 autocommit，写后必须能被另一个连接读到。"""
    db = str(tmp_path / "p.db")
    s1 = Store(db, project_id="P")
    s1.insert_memory(MemoryNode(memory_id="M1", content="x",
                                memory_type=MemoryType.DECISION, subject="s",
                                predicate="p", created_step=1, last_cited_step=1))
    s1.touch_citation("M1", 42)
    s2 = Store(db, project_id="P")
    n = s2.get_memory("M1")
    assert n is not None and n.last_cited_step == 42
    assert n.citation_count == 1
    s1.close()
    s2.close()


# ---------------------------------------------------------------------------
# P2-1 / P2-2: CLI 行为
# ---------------------------------------------------------------------------
def test_cli_query_records_event_so_explain_works(tmp_path, monkeypatch, capsys):
    """query 默认必须落盘 RECALL_DELIVERED，否则 explain 查不到。"""
    db = tmp_path / "m.db"
    monkeypatch.setenv("GATED_MEM_DB", str(db))
    from src.gated_mem import cli

    assert cli.main(["remember", "主数据库选用 PostgreSQL 16",
                     "--subject", "db", "--predicate", "engine"]) == 0
    assert cli.main(["query", "数据库选型"]) == 0
    out = capsys.readouterr().out
    assert "回执事件:" in out

    store = Store(str(db))
    n = store.conn.execute(
        "SELECT COUNT(*) c FROM memory_events WHERE event_type='RECALL_DELIVERED'"
    ).fetchone()["c"]
    store.close()
    assert n == 1


def test_cli_query_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    db = tmp_path / "m.db"
    monkeypatch.setenv("GATED_MEM_DB", str(db))
    from src.gated_mem import cli

    cli.main(["remember", "主数据库选用 PostgreSQL 16",
              "--subject", "db", "--predicate", "engine"])
    before = _count_events(db)
    assert cli.main(["query", "数据库选型", "--dry-run"]) == 0
    assert _count_events(db) == before


def test_cli_explain_renders_evolution_traces(tmp_path, monkeypatch, capsys):
    """explain 必须把 [Replaced: ...] 演进轨迹打出来。"""
    db = tmp_path / "m.db"
    monkeypatch.setenv("GATED_MEM_DB", str(db))
    from src.gated_mem import cli

    cli.main(["remember", "主数据库选用 MySQL 8.0 作为生产存储方案",
              "--subject", "db", "--predicate", "engine"])
    cli.main(["remember", "主数据库选用 MySQL 8.0 作为生产存储方案的替代：PostgreSQL 16",
              "--subject", "db", "--predicate", "engine",
              "--residual-diff", "因需支持 JSONB 高并发索引查询"])

    capsys.readouterr()
    cli.main(["query", "数据库选型"])
    out = capsys.readouterr().out
    rid = [ln.split(":")[-1].strip() for ln in out.splitlines() if "回执事件" in ln][0]

    assert cli.main(["explain", rid]) == 0
    exp = capsys.readouterr().out
    assert "演进轨迹" in exp
    assert "JSONB" in exp


def test_cli_remember_triggers_supersede(tmp_path, monkeypatch, capsys):
    """CLI 写入必须走两阶段裁决，不能绕过覆盖直接插入。"""
    db = tmp_path / "m.db"
    monkeypatch.setenv("GATED_MEM_DB", str(db))
    from src.gated_mem import cli
    from src.gated_mem.schema import MemoryStatus

    cli.main(["remember", "主数据库选用 MySQL 8.0 作为生产存储方案",
              "--subject", "db", "--predicate", "engine"])
    capsys.readouterr()
    cli.main(["remember",
              "主数据库选用 MySQL 8.0 作为生产存储方案的替代：PostgreSQL 16",
              "--subject", "db", "--predicate", "engine",
              "--residual-diff", "因需支持 JSONB"])
    out = capsys.readouterr().out
    assert "SUPERSEDED" in out
    assert "[Replaced: MySQL]" in out

    store = Store(str(db))
    nodes = store.all_memories()
    active = [n for n in nodes if n.status == MemoryStatus.ACTIVE]
    superseded = [n for n in nodes if n.status == MemoryStatus.SUPERSEDED]
    store.close()
    assert len(active) == 1 and len(superseded) == 1, "旧决策未被覆盖"


def _count_events(db):
    s = Store(str(db))
    c = s.conn.execute("SELECT COUNT(*) c FROM memory_events").fetchone()["c"]
    s.close()
    return c
