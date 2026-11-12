"""events.py 门面层补齐测试（提升覆盖率到 Gate 2 门槛）。"""
from __future__ import annotations

import json

import pytest

from src.gated_mem.events import EventLog, read_only_guard
from src.gated_mem.schema import EventType, MemoryEdge, MemoryNode, MemoryStatus, MemoryType
from src.gated_mem.storage import Store


def _node(mid, step=1, **kw):
    return MemoryNode(
        memory_id=mid, content=kw.pop("content", "内容 %s" % mid),
        memory_type=kw.pop("memory_type", MemoryType.DECISION),
        subject=kw.pop("subject", "db"), predicate=kw.pop("predicate", "engine"),
        created_step=step, last_cited_step=step, **kw
    )


def test_new_correlation_unique():
    s = Store(":memory:")
    log = EventLog(s)
    a, b = log.new_correlation(), log.new_correlation()
    assert a != b


def test_record_batch_empty():
    s = Store(":memory:")
    log = EventLog(s)
    cid = log.record_batch([], step=1)
    assert cid
    assert s.events_of_correlation(cid) == []


def test_record_batch_rolls_back_on_error():
    s = Store(":memory:")
    log = EventLog(s)
    with pytest.raises(Exception):
        log.record_batch(
            [
                {"event_type": EventType.MEMORY_PINNED, "payload": {}},
                {"event_type": "NOT_A_REAL_TYPE", "payload": {}},
            ],
            step=1,
        )
    # 事务必须回滚干净，不留半条事件
    cnt = s.conn.execute("SELECT COUNT(*) AS c FROM memory_events").fetchone()["c"]
    assert cnt == 0


def test_history_ordered():
    s = Store(":memory:")
    log = EventLog(s)
    for i in range(1, 5):
        s.insert_memory(_node("M%d" % i, step=i))
    hist = log.history(limit=100)
    steps = [e.step for e in hist]
    assert steps == sorted(steps)


def test_causation_chain_depth_bounded():
    s = Store(":memory:")
    log = EventLog(s)
    s.insert_memory(_node("M1"))
    eid = s.get_memory("M1").source_event_id
    chain = log.causation_chain(eid, max_depth=1)
    assert len(chain) == 1


def test_undo_via_eventlog():
    s = Store(":memory:")
    log = EventLog(s)
    s.insert_memory(_node("M1"))
    eid = s.get_memory("M1").source_event_id
    res = log.undo(eid)
    assert "undone_event_ids" in res
    assert s.get_memory("M1") is None


def test_rebuild_projection_tracks_status_changes():
    s = Store(":memory:")
    log = EventLog(s)
    s.insert_memory(_node("M1", step=1))
    s.set_status("M1", MemoryStatus.SUPERSEDED, step=2)
    proj = log.rebuild_projection()
    assert proj["M1"].status == MemoryStatus.SUPERSEDED


def test_rebuild_projection_restores_after_undo():
    s = Store(":memory:")
    log = EventLog(s)
    s.insert_memory(_node("M1", step=1))
    sup_ev = s.set_status("M1", MemoryStatus.SUPERSEDED, step=2)
    assert log.rebuild_projection()["M1"].status == MemoryStatus.SUPERSEDED
    s.undo(sup_ev)
    assert log.rebuild_projection()["M1"].status == MemoryStatus.ACTIVE


def test_read_only_guard_is_silent(capsys):
    read_only_guard()
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""
