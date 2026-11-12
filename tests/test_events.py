"""事件溯源、状态机与 undo 原子性测试。"""
from __future__ import annotations

import json

import pytest

from src.gated_mem.events import EventLog
from src.gated_mem.schema import (
    EdgeType,
    EventType,
    MemoryEdge,
    MemoryEvent,
    MemoryNode,
    MemoryStatus,
    MemoryType,
    is_transition_allowed,
)
from src.gated_mem.storage import StorageError, Store


def _node(mid, step=1, content=None, **kw):
    return MemoryNode(
        memory_id=mid,
        content=content or ("记忆 %s 的内容" % mid),
        memory_type=kw.pop("memory_type", MemoryType.DECISION),
        subject=kw.pop("subject", "db"),
        predicate=kw.pop("predicate", "engine"),
        scope=kw.pop("scope", "global"),
        created_step=step,
        last_cited_step=step,
        **kw
    )


def test_state_matrix_blocks_revival():
    """superseded / killed 不得被普通写入复活。"""
    assert not is_transition_allowed(MemoryStatus.SUPERSEDED.value, MemoryStatus.ACTIVE.value)
    assert not is_transition_allowed(MemoryStatus.KILLED.value, MemoryStatus.ACTIVE.value)
    assert is_transition_allowed(MemoryStatus.ACTIVE.value, MemoryStatus.SUPERSEDED.value)
    assert is_transition_allowed(MemoryStatus.CANDIDATE_CONFLICT.value, MemoryStatus.ACTIVE.value)


def test_set_status_rejects_illegal_transition():
    s = Store(":memory:")
    s.insert_memory(_node("M1"))
    s.set_status("M1", MemoryStatus.SUPERSEDED, 2)
    with pytest.raises(StorageError):
        s.set_status("M1", MemoryStatus.ACTIVE, 3)


def test_killed_cannot_be_revived_by_normal_write():
    s = Store(":memory:")
    s.insert_memory(_node("M1"))
    s.set_status("M1", MemoryStatus.KILLED, 2)
    with pytest.raises(StorageError):
        s.set_status("M1", MemoryStatus.ACTIVE, 3)


def test_event_carries_causation_and_correlation():
    s = Store(":memory:")
    s.insert_memory(_node("M1"))
    ev = s.get_event(s.get_memory("M1").source_event_id)
    assert ev.correlation_id
    assert ev.event_type == EventType.MEMORY_CREATED


def test_edge_direction_is_child_to_parent():
    s = Store(":memory:")
    s.insert_memory(_node("M1"))
    s.insert_memory(_node("M2", subject="test", predicate="iso"))
    s.insert_edge(
        MemoryEdge(
            edge_id="E1", source_id="M2", target_id="M1",
            edge_type=EdgeType.BELONGS_TO, created_step=2,
        )
    )
    # M2 是子，M1 是父
    assert s.parents_of("M2") == ["M1"]
    assert s.children_of("M1") == ["M2"]


def test_self_loop_edge_rejected():
    with pytest.raises(Exception):
        MemoryEdge(edge_id="E1", source_id="M1", target_id="M1", created_step=1)


def test_undo_restores_creation():
    s = Store(":memory:")
    s.insert_memory(_node("M1"))
    ev_id = s.get_memory("M1").source_event_id
    assert s.get_memory("M1") is not None
    s.undo(ev_id)
    assert s.get_memory("M1") is None


def test_undo_restores_supersede_status():
    s = Store(":memory:")
    s.insert_memory(_node("M1"))
    s.set_status("M1", MemoryStatus.SUPERSEDED, 2)
    assert s.get_memory("M1").status == MemoryStatus.SUPERSEDED
    sup_event = s.conn.execute(
        "SELECT event_id FROM memory_events WHERE event_type=? ORDER BY step DESC LIMIT 1",
        (EventType.MEMORY_SUPERSEDED.value,),
    ).fetchone()["event_id"]
    s.undo(sup_event)
    assert s.get_memory("M1").status == MemoryStatus.ACTIVE


def test_undo_restores_fts_index():
    """undo 必须同步回滚 FTS5，不能留下幽灵索引条目。"""
    s = Store(":memory:")
    s.insert_memory(_node("M1", content="主数据库选用 MySQL 8.0"))
    assert s.fts_search("mysql")
    ev_id = s.get_memory("M1").source_event_id
    s.undo(ev_id)
    assert s.fts_search("mysql") == []


def test_undo_is_atomic_across_tables():
    """跨表原子性：undo 边创建事件后，边表与 FTS 必须同步回滚。"""
    s = Store(":memory:")
    s.insert_memory(_node("M1", content="主数据库选用 MySQL 8.0"))
    s.insert_memory(_node("M2", subject="test", predicate="iso", content="单元测试必须 mock 数据库"))
    before = s.snapshot()

    s.insert_edge(
        MemoryEdge(
            edge_id="E1", source_id="M2", target_id="M1",
            edge_type=EdgeType.BELONGS_TO, created_step=2,
        )
    )
    after = s.snapshot()
    assert len(after["edges"]) == len(before["edges"]) + 1
    assert s.parents_of("M2") == ["M1"]

    edge_ev = s.conn.execute(
        "SELECT event_id FROM memory_events WHERE event_type=? ORDER BY rowid DESC LIMIT 1",
        (EventType.EDGE_CREATED.value,),
    ).fetchone()
    s.undo(edge_ev["event_id"])

    restored = s.snapshot()
    assert restored["edges"] == before["edges"], "边表未回滚干净"
    assert restored["fts"] == before["fts"], "FTS5 索引未同步回滚"
    assert s.parents_of("M2") == []


def test_undo_10_steps_any_middle_point():
    """连续 10 步增删改后，任意中间步 undo 都必须精确可逆。"""
    s = Store(":memory:")
    log = EventLog(s)
    created = {}
    for i in range(1, 11):
        n = _node("M%d" % i, step=i, content="第 %d 步的决策内容" % i)
        s.insert_memory(n)
        created[i] = s.get_memory("M%d" % i).source_event_id

    # 撤销第 5 步
    s.undo(created[5])
    assert s.get_memory("M5") is None
    # 其余 9 个必须完好
    for i in [1, 2, 3, 4, 6, 7, 8, 9, 10]:
        assert s.get_memory("M%d" % i) is not None


def test_causation_chain_no_loop():
    s = Store(":memory:")
    log = EventLog(s)
    s.insert_memory(_node("M1"))
    e1 = s.get_memory("M1").source_event_id
    chain = log.causation_chain(e1)
    assert chain[0].event_id == e1


def test_record_batch_links_causation():
    s = Store(":memory:")
    log = EventLog(s)
    cid = log.record_batch(
        [
            {"event_type": EventType.MEMORY_PINNED, "payload": {"memory_id": "X"}},
            {"event_type": EventType.MEMORY_PINNED, "payload": {"memory_id": "Y"}},
        ],
        step=1,
    )
    evs = s.events_of_correlation(cid)
    assert len(evs) == 2
    # 链序由写入顺序决定：后写入的事件 causation_id 指向前一条
    by_payload = {json.loads(e.payload_json)["memory_id"]: e for e in evs}
    assert by_payload["Y"].causation_id == by_payload["X"].event_id
    assert by_payload["X"].causation_id is None
