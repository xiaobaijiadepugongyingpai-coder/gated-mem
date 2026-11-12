"""两阶段槽位冲突裁决测试。"""
from __future__ import annotations

import pytest

from src.gated_mem import conflicts
from src.gated_mem.schema import MemoryNode, MemoryStatus, MemoryType
from src.gated_mem.storage import Store


def _node(mid, content, subject="db", predicate="engine", scope="global", step=1, **kw):
    return MemoryNode(
        memory_id=mid, content=content, memory_type=kw.pop("memory_type", MemoryType.DECISION),
        subject=subject, predicate=predicate, scope=scope,
        created_step=step, last_cited_step=step, **kw
    )


def test_extract_entity_keyword_prefers_ascii_tech_word():
    assert conflicts.extract_entity_keyword("主数据库选用 MySQL 8.0") == "MySQL"
    assert conflicts.extract_entity_keyword("前端构建器使用 webpack 5") == "webpack"


def test_extract_entity_keyword_falls_back_to_cjk():
    kw = conflicts.extract_entity_keyword("全量使用中文描述无技术名词")
    assert kw and len(kw) <= 6


def test_format_residual_diff_shape():
    old = _node("M1", "主数据库选用 MySQL 8.0")
    diff = conflicts.format_residual_diff(old, "因需支持 JSONB 改用 PostgreSQL")
    assert diff.startswith("[Replaced: MySQL]")
    assert "JSONB" in diff


def test_format_residual_diff_idempotent():
    old = _node("M1", "主数据库选用 MySQL 8.0")
    once = conflicts.format_residual_diff(old, "换成 PG")
    twice = conflicts.format_residual_diff(old, once)
    assert once == twice
    assert twice.count("[Replaced:") == 1


def test_slot_normalization_via_alias():
    s = Store(":memory:")
    s.upsert_alias("db.primary", "主数据库")
    s.upsert_alias("primary_database", "主数据库")
    assert s.resolve_alias("db.primary") == "主数据库"
    assert s.resolve_alias("primary_database") == "主数据库"
    assert s.resolve_alias("unmapped") == "unmapped"


def test_alias_enables_slot_match():
    """别名归一化后，两条不同写法的同槽节点必须能触发覆盖。"""
    s = Store(":memory:")
    s.upsert_alias("db.primary", "主数据库")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0", subject="主数据库"))
    norm = conflicts.normalize_slot(s, "db.primary", "engine", "global")
    assert norm[0] == "主数据库"
    olds = s.find_active_by_slot(*norm)
    assert [o.memory_id for o in olds] == ["M1"]


def test_decide_supersedes_on_clear_replacement():
    s = Store(":memory:")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0 作为生产环境存储"))
    decision, olds = conflicts.decide(
        s,
        {"content": "主数据库选用 MySQL 8.0 作为生产环境存储的替代品 PostgreSQL 16"},
        "db", "engine", "global",
    )
    assert decision in (conflicts.SUPERSEDES, conflicts.EXACT_MATCH)
    assert olds


def test_decide_no_conflict_when_slot_differs():
    s = Store(":memory:")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0"))
    decision, olds = conflicts.decide(s, {"content": "前端构建器改用 Vite"}, "frontend", "bundler", "global")
    assert decision == conflicts.NO_CONFLICT
    assert olds == []


def test_decide_candidate_conflict_on_ambiguous():
    """同槽但内容既不重述也不明确替换 → 必须挂起，绝不自动覆盖。"""
    s = Store(":memory:")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0 集群三节点"))
    decision, olds = conflicts.decide(
        s, {"content": "缓存层完全无关的另一件事"}, "db", "engine", "global"
    )
    assert decision == conflicts.CANDIDATE_CONFLICT
    assert olds


def test_apply_supersede_does_not_touch_descendants():
    """P0-3 铁律：覆盖旧节点时，其子孙状态与生命力绝不受影响。"""
    s = Store(":memory:")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0"))
    s.insert_memory(_node("M2", "单元测试必须 mock 数据库", subject="test", predicate="iso"))
    from src.gated_mem.schema import MemoryEdge, EdgeType

    s.insert_edge(
        MemoryEdge(edge_id="E_M2_M1", source_id="M2", target_id="M1",
                   edge_type=EdgeType.BELONGS_TO, created_step=2)
    )
    old = s.get_memory("M1")
    new = _node("M4", "主数据库切换为 PostgreSQL 16", step=3)
    s.insert_memory(new)
    updated = conflicts.apply_supersede(s, new, [old], step=3, reason="因需支持 JSONB")

    assert s.get_memory("M1").status == MemoryStatus.SUPERSEDED
    # 子节点必须仍是 active
    assert s.get_memory("M2").status == MemoryStatus.ACTIVE
    assert updated.residual_diff.startswith("[Replaced: MySQL]")


def test_apply_supersede_creates_supersedes_edge():
    s = Store(":memory:")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0"))
    old = s.get_memory("M1")
    new = _node("M4", "主数据库切换为 PostgreSQL 16", step=3)
    s.insert_memory(new)
    conflicts.apply_supersede(s, new, [old], step=3, reason="因需支持 JSONB")
    rows = s.conn.execute(
        "SELECT source_id,target_id FROM memory_edges WHERE edge_type='SUPERSEDES'"
    ).fetchall()
    # source=child(新), target=parent(旧)
    assert (rows[0]["source_id"], rows[0]["target_id"]) == ("M4", "M1")


def test_mark_candidate_conflict_does_not_supersede_old():
    s = Store(":memory:")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0"))
    old = s.get_memory("M1")
    new = _node("M9", "数据库层有些模糊的想法", step=4)
    conflicted = conflicts.mark_candidate_conflict(s, new, [old], step=4)
    assert conflicted.status == MemoryStatus.CANDIDATE_CONFLICT
    assert s.get_memory("M1").status == MemoryStatus.ACTIVE, "挂起时不得覆盖旧节点"
