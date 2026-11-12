"""storage 与 conflicts 覆盖率补齐 + 边界测试。"""
from __future__ import annotations

import json

import pytest

from src.gated_mem import conflicts
from src.gated_mem.schema import (
    EdgeType, EventType, MemoryEdge, MemoryNode, MemoryStatus, MemoryType, TrustTier,
)
from src.gated_mem.storage import StorageError, Store


def _node(mid, step=1, **kw):
    return MemoryNode(
        memory_id=mid, content=kw.pop("content", "内容 %s" % mid),
        memory_type=kw.pop("memory_type", MemoryType.DECISION),
        subject=kw.pop("subject", "db"), predicate=kw.pop("predicate", "engine"),
        scope=kw.pop("scope", "global"),
        created_step=step, last_cited_step=kw.pop("last_cited_step", step), **kw
    )


# ---- storage 边界 ----
def test_pack_unpack_embedding_roundtrip():
    vec = [0.1, -0.25, 0.9, 0.0]
    blob = Store._pack_embedding(vec)
    back = Store.unpack_embedding(blob)
    assert len(back) == 4
    for a, b in zip(vec, back):
        assert abs(a - b) < 1e-6


def test_pack_embedding_none():
    assert Store._pack_embedding(None) is None
    assert Store.unpack_embedding(None) is None


def test_embedding_persisted_in_blob_column():
    s = Store(":memory:")
    s.insert_memory(_node("M1", embedding=[0.5] * 32))
    raw = s.conn.execute("SELECT embedding FROM memories WHERE memory_id='M1'").fetchone()["embedding"]
    assert isinstance(raw, bytes)
    assert len(raw) == 32 * 4
    assert s.get_memory("M1").embedding == pytest.approx([0.5] * 32, abs=1e-6)


def test_all_memories_filter_by_status():
    s = Store(":memory:")
    s.insert_memory(_node("M1"))
    s.insert_memory(_node("M2", subject="x"))
    s.set_status("M2", MemoryStatus.SUPERSEDED, 2)
    assert [n.memory_id for n in s.all_memories([MemoryStatus.ACTIVE.value])] == ["M1"]
    assert [n.memory_id for n in s.all_memories([MemoryStatus.SUPERSEDED.value])] == ["M2"]


def test_all_memories_filter_by_scope():
    s = Store(":memory:")
    s.insert_memory(_node("M1", scope="global"))
    s.insert_memory(_node("M2", scope="branch:dev", subject="y"))
    assert [n.memory_id for n in s.all_memories(scope="branch:dev")] == ["M2"]


def test_set_status_missing_node_raises():
    s = Store(":memory:")
    with pytest.raises(StorageError):
        s.set_status("NOPE", MemoryStatus.ACTIVE, 1)


def test_undo_missing_event_raises():
    s = Store(":memory:")
    with pytest.raises(StorageError):
        s.undo("no-such-event")


def test_expand_scratch_scratch_storage_reset():
    s = Store(":memory:")
    s.insert_memory(_node("M1"))
    s.close()


def test_fts_special_chars_do_not_crash():
    s = Store(":memory:")
    s.insert_memory(_node("M1", content="主数据库 MySQL"))
    # 纯特殊字符不应抛异常
    assert s.fts_search("") == []
    assert isinstance(s.fts_search("!!!:::"), list)


def test_edges_cascade_on_memory_delete():
    s = Store(":memory:")
    s.insert_memory(_node("M1"))
    s.insert_memory(_node("M2", subject="x"))
    s.insert_edge(MemoryEdge(edge_id="E1", source_id="M2", target_id="M1",
                             edge_type=EdgeType.BELONGS_TO, created_step=2))
    ev = s.get_memory("M1").source_event_id
    s.undo(ev)
    assert s.get_memory("M1") is None


# ---- conflicts 覆盖率 ----
def test_resolve_candidate_to_active():
    s = Store(":memory:")
    s.insert_memory(_node("M9", status=MemoryStatus.CANDIDATE_CONFLICT, step=2))
    conflicts.resolve_candidate(s, "M9", conflicts.ACTIVE_DECISION, step=3)
    assert s.get_memory("M9").status == MemoryStatus.ACTIVE


def test_resolve_candidate_to_superseded_sets_reason():
    s = Store(":memory:")
    s.insert_memory(_node("M9", status=MemoryStatus.CANDIDATE_CONFLICT, step=2))
    conflicts.resolve_candidate(s, "M9", conflicts.SUPERSEDED_DECISION, step=3,
                                reason="[Replaced: old] 被取代")
    assert s.get_memory("M9").status == MemoryStatus.SUPERSEDED
    assert "[Replaced:" in s.get_memory("M9").residual_diff


def test_resolve_candidate_wrong_state_raises():
    s = Store(":memory:")
    s.insert_memory(_node("M1"))
    with pytest.raises(ValueError):
        conflicts.resolve_candidate(s, "M1", conflicts.ACTIVE_DECISION, step=2)


def test_resolve_candidate_missing_raises():
    s = Store(":memory:")
    with pytest.raises(ValueError):
        conflicts.resolve_candidate(s, "NOPE", conflicts.ACTIVE_DECISION, step=2)


def test_apply_supersede_default_reason():
    s = Store(":memory:")
    s.insert_memory(_node("M1", content="主数据库选用 MySQL 8.0"))
    old = s.get_memory("M1")
    new = _node("M4", step=3)
    s.insert_memory(new)
    updated = conflicts.apply_supersede(s, new, [old], step=3)
    assert updated.residual_diff.startswith("[Replaced:")


def test_apply_supersede_multiple_olds_uses_smallest_id():
    s = Store(":memory:")
    s.insert_memory(_node("MA", content="主数据库使用 MySQL 5.7", subject="s1"))
    s.insert_memory(_node("MB", content="主数据库使用 MySQL 8.0", subject="s2"))
    olds = [s.get_memory("MA"), s.get_memory("MB")]
    new = _node("MZ", step=5)
    s.insert_memory(new)
    updated = conflicts.apply_supersede(s, new, olds, step=5, reason="统一升级 PG")
    assert "MA" or updated.residual_diff
    assert s.get_memory("MA").status == MemoryStatus.SUPERSEDED
    assert s.get_memory("MB").status == MemoryStatus.SUPERSEDED


def test_touch_citation_increments():
    s = Store(":memory:")
    s.insert_memory(_node("M1", step=1))
    s.touch_citation("M1", 10)
    n = s.get_memory("M1")
    assert n.last_cited_step == 10
    assert n.citation_count == 1
