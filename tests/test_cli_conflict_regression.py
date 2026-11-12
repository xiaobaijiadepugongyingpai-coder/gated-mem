"""CLI 冲突路径回归测试（Gemini 复核抓到的崩溃）。"""
from __future__ import annotations

import pytest

from src.gated_mem import cli
from src.gated_mem.schema import MemoryStatus
from src.gated_mem.storage import Store


@pytest.fixture()
def db(tmp_path, monkeypatch):
    p = tmp_path / "m.db"
    monkeypatch.setenv("GATED_MEM_DB", str(p))
    return p


def test_cli_remember_conflict_path_does_not_crash(db, capsys):
    """CANDIDATE_CONFLICT 分支曾因 p = Paint() 位置错误抛 UnboundLocalError。"""
    cli.main(["remember", "主数据库选用 MySQL 8.0 三节点集群部署方案",
              "--subject", "db", "--predicate", "engine"])
    capsys.readouterr()

    rc = cli.main(["remember", "完全无关的缓存层讨论内容",
                   "--subject", "db", "--predicate", "engine"])
    assert rc == 0, "冲突路径不得崩溃"
    out = capsys.readouterr().out
    assert "候选冲突" in out
    assert "resolve" in out


def test_cli_remember_conflict_creates_pending_node(db, capsys):
    cli.main(["remember", "主数据库选用 MySQL 8.0 三节点集群部署方案",
              "--subject", "db", "--predicate", "engine"])
    cli.main(["remember", "完全无关的缓存层讨论内容",
              "--subject", "db", "--predicate", "engine"])
    store = Store(str(db))
    pending = store.all_memories([MemoryStatus.CANDIDATE_CONFLICT.value])
    store.close()
    assert len(pending) == 1


def test_all_cli_print_helpers_defined_before_use():
    """静态扫描：cmd_* 函数里若使用 p(...) 作为调用，必须先有 p = Paint()。"""
    import ast

    src = open(cli.__file__, "r", encoding="utf-8").read()
    tree = ast.parse(src)
    problems = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        uses = []
        assigns = []
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "p":
                uses.append(node.lineno)
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "p":
                        assigns.append(node.lineno)
        if uses and assigns and min(uses) < min(assigns):
            problems.append((fn.name, min(uses), min(assigns)))
    assert not problems, "存在 p() 早于赋值：%r" % problems
