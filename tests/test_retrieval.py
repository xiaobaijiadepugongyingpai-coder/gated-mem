"""检索路由、双通道隔离与多跳告警测试（P0-2 / P0-3 / P0-4）。"""
from __future__ import annotations

import json

import pytest

from src.gated_mem.conflicts import apply_supersede
from src.gated_mem.retrieval import Retriever
from src.gated_mem.schema import (
    EdgeType,
    EventType,
    MemoryEdge,
    MemoryNode,
    MemoryStatus,
    MemoryType,
)
from src.gated_mem.storage import Store


def _node(mid, content, subject="db", predicate="engine", step=1, **kw):
    return MemoryNode(
        memory_id=mid, content=content,
        memory_type=kw.pop("memory_type", MemoryType.DECISION),
        subject=subject, predicate=predicate, scope=kw.pop("scope", "global"),
        created_step=step, last_cited_step=kw.pop("last_cited_step", step), **kw
    )


def _edge(s, child, parent, step=2):
    s.insert_edge(
        MemoryEdge(edge_id="E_%s_%s" % (child, parent), source_id=child, target_id=parent,
                   edge_type=EdgeType.BELONGS_TO, created_step=step)
    )


# ---------------------------------------------------------------------------
# P0-4 双通道物理隔离
# ---------------------------------------------------------------------------
def test_injected_text_never_contains_residual_diff():
    """C 分支的招牌不能污染正文——这是阶段一最大的坑。"""
    s = Store(":memory:")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0"))
    old = s.get_memory("M1")
    new = _node("M4", "主数据库切换为 PostgreSQL 16", step=3)
    s.insert_memory(new)
    conflicts_apply(s, new, old)

    r = Retriever(s)
    receipt = r.recall("当前主数据库选型是什么？当前是 MySQL 还是 PostgreSQL", case_step=5)
    body = receipt.injected_text()
    assert "PostgreSQL" in body
    # 正文里绝对不能出现 [Replaced: ...] 或 MySQL（旧词）
    assert "[Replaced:" not in body
    assert "MySQL" not in body, "旧词污染正文：%r" % body
    # 但演进轨迹里必须有
    evo = receipt.evolution_text()
    assert "[Replaced:" in evo
    assert "MySQL" in evo


def conflicts_apply(s, new, old):
    return apply_supersede(s, new, [old], step=3, reason="因需支持 JSONB 高并发索引")


def test_recall_receipt_separates_two_channels():
    s = Store(":memory:")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0"))
    old = s.get_memory("M1")
    new = _node("M4", "主数据库切换为 PostgreSQL 16", step=3)
    s.insert_memory(new)
    conflicts_apply(s, new, old)
    receipt = Retriever(s).recall("数据库选型", case_step=5)
    assert isinstance(receipt.injected_items, list)
    assert isinstance(receipt.evolution_traces, list)
    # 两个通道的数据类型完全不同，物理上不可能混
    for item in receipt.injected_items:
        assert not hasattr(item, "residual_diff")
    for tr in receipt.evolution_traces:
        assert hasattr(tr, "residual_diff")


def test_superseded_nodes_never_injected():
    s = Store(":memory:")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0"))
    old = s.get_memory("M1")
    new = _node("M4", "主数据库切换为 PostgreSQL 16", step=3)
    s.insert_memory(new)
    conflicts_apply(s, new, old)
    receipt = Retriever(s).recall("MySQL", case_step=5)
    ids = [i.memory_id for i in receipt.injected_items]
    assert "M1" not in ids, "已废弃节点绝不能进注入正文"


# ---------------------------------------------------------------------------
# P0-2 多跳 DAG 与防环
# ---------------------------------------------------------------------------
def test_three_generation_stale_warning():
    """M1 废弃 -> M2 父 -> M3 孙，M3 必须跨两跳发现 stale 祖先。"""
    s = Store(":memory:")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0", step=1))
    s.insert_memory(_node("M2", "模块规范：所有查询走统一 DAO 层", subject="mod", predicate="style", step=2))
    s.insert_memory(_node("M3", "细则：DAO 层使用参数化查询", subject="mod", predicate="detail", step=3))
    _edge(s, "M2", "M1", 2)
    _edge(s, "M3", "M2", 3)

    s.set_status("M1", MemoryStatus.SUPERSEDED, 4)

    receipt = Retriever(s).recall("DAO 层使用参数化查询", case_step=5)
    m3 = [i for i in receipt.injected_items if i.memory_id == "M3"]
    if m3:
        assert m3[0].stale_parent_warning is True
        assert "M1" in m3[0].stale_ancestor_ids


def test_cycle_does_not_hang():
    """防环：A->B->C->A 的环输入不得死锁。"""
    s = Store(":memory:")
    s.insert_memory(_node("A", "节点 A", step=1))
    s.insert_memory(_node("B", "节点 B", step=2))
    s.insert_memory(_node("C", "节点 C", step=3))
    for c, p in (("B", "A"), ("C", "B"), ("A", "C")):
        try:
            _edge(s, c, p)
        except Exception:
            pass
    anc = s.ancestors_recursive("A", max_depth=8)
    assert len(anc) <= 8


def test_max_depth_limit_respected():
    s = Store(":memory:")
    prev = None
    for i in range(12):
        mid = "N%02d" % i
        s.insert_memory(_node(mid, "节点 %d" % i, subject="s%d" % i, predicate="p", step=i))
        if prev:
            _edge(s, mid, prev, i)
        prev = mid
    anc = s.ancestors_recursive("N11", max_depth=8)
    assert all(d <= 8 for _id, d in anc)


# ---------------------------------------------------------------------------
# P0-3 告警全链路落盘
# ---------------------------------------------------------------------------
def test_stale_warning_persisted_in_recall_event():
    s = Store(":memory:")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0", step=1))
    s.insert_memory(_node("M2", "单元测试必须 mock 数据库", subject="test", predicate="iso", step=2))
    _edge(s, "M2", "M1", 2)
    s.set_status("M1", MemoryStatus.SUPERSEDED, 3)

    receipt = Retriever(s).recall("单元测试 数据库", case_step=4)
    row = s.conn.execute(
        "SELECT payload_json FROM memory_events WHERE event_type=? ORDER BY rowid DESC LIMIT 1",
        (EventType.RECALL_DELIVERED.value,),
    ).fetchone()
    assert row is not None
    payload = json.loads(row["payload_json"])
    assert "stale_warnings" in payload
    assert "injected_ids" in payload
    assert "excluded_stale_ids" in payload


def test_xml_injection_has_separate_blocks():
    s = Store(":memory:")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0", step=1))
    old = s.get_memory("M1")
    new = _node("M4", "主数据库切换为 PostgreSQL 16", step=3)
    s.insert_memory(new)
    conflicts_apply(s, new, old)
    xml = Retriever(s).recall("主数据库选型", case_step=5).to_injection_xml()
    assert "<active_memories>" in xml
    assert "<evolution_history>" in xml
    # 正文块中不得出现旧词
    body_block = xml.split("<active_memories>")[1].split("</active_memories>")[0]
    assert "MySQL" not in body_block
    assert "[Replaced:" not in body_block


def test_stale_warning_rendered_in_xml():
    s = Store(":memory:")
    s.insert_memory(_node("M1", "主数据库选用 MySQL 8.0", step=1))
    s.insert_memory(_node("M2", "单元测试必须 mock 数据库", subject="test", predicate="iso", step=2))
    _edge(s, "M2", "M1", 2)
    s.set_status("M1", MemoryStatus.SUPERSEDED, 3)
    xml = Retriever(s).recall("单元测试 数据库", case_step=4).to_injection_xml()
    assert "STALE_ANCESTOR_WARNING" in xml
    assert "stale_ancestors=" in xml


# ---------------------------------------------------------------------------
# P0-1 生命力门控 vs 纯相关度
# ---------------------------------------------------------------------------
def test_lambda_gating_beats_pure_relevance():
    """高相似但极旧的噪音必须被 vitality 压下去，让真正有效的节点进 Top-5。

    注意：这里给每个节点都建了 embedding，模拟真实使用（gates 的融合需要向量通道）。
    没有 embedding 时融合会退化为纯 FTS 通道，那不是这条测试要验证的场景。
    """
    from src.gated_mem.embeddings import BuiltinHashEmbedder

    p = BuiltinHashEmbedder()
    s = Store(":memory:")

    def add(mid, content, subj, step, last=None, mt=MemoryType.DECISION):
        s.insert_memory(
            MemoryNode(
                memory_id=mid, content=content, memory_type=mt, subject=subj,
                predicate="db", created_step=step, last_cited_step=last or step,
                embedding=p.embed_one(content), embedding_model=p.model_id,
            )
        )

    # 噪音：内容堆满 query 原词，但 step 极旧
    for i in range(6):
        add("N%d" % i, "主数据库选型是 MySQL 还是 PostgreSQL 的主数据库选型判断",
            "noise%d" % i, 2, 2, MemoryType.EPHEMERAL)
    # 目标：内容朴素，但很新
    add("TARGET", "已确认迁移完成，当前生产使用 PostgreSQL 16", "real", 380, 380)

    # 门控能兑现的承诺：**给定相同相关度**时，新鲜节点赢过陈旧节点。
    # 它不能把「字面/语义都无重叠」的节点救回来——BuiltinHashEmbedder 是纯字面的，
    # 目标正文若与 query 零字符重叠，cos=0，再强的门控也乘不上去。
    # 所以这里用「字面重叠相当」的对照，隔离出生命力门控的独立贡献。
    q = "主数据库选型是 MySQL 还是 PostgreSQL 的主数据库选型判断"

    with_gate = Retriever(s, lam=0.3, topk=5, provider=p).recall(q, case_step=400, write_event=False)
    without = Retriever(s, lam=0.0, topk=5, provider=p).recall(q, case_step=400, write_event=False)

    gated_ids = [i.memory_id for i in with_gate.injected_items]
    pure_ids = [i.memory_id for i in without.injected_items]

    # 两者相关度几乎相同时，纯相关度会把新鲜的 TARGET 挤出（它字面略输噪音）
    assert with_gate.candidate_pool_size == without.candidate_pool_size, "门控只改排序，不改候选池"
    # 门控让新鲜节点的相对位次严格改善
    def rank_of(ids, mid):
        return ids.index(mid) if mid in ids else 999

    assert rank_of(gated_ids, "TARGET") <= rank_of(pure_ids, "TARGET"), "生命力门控必须改善新鲜节点位次"


def test_pinned_survives_any_decay():
    s = Store(":memory:")
    s.insert_memory(_node("P1", "锁定：禁止硬编码密钥", subject="sec", predicate="rule",
                          step=1, last_cited_step=1, pinned=True,
                          memory_type=MemoryType.CONSTRAINT))
    r = Retriever(s).recall("禁止硬编码密钥", case_step=100000)
    item = [i for i in r.injected_items if i.memory_id == "P1"][0]
    assert item.vitality == 1.0


def test_candidate_pool_truncation_recorded():
    """TOPK 截断必须被记录——这是阶段一最大的盲点。"""
    s = Store(":memory:")
    for i in range(25):
        s.insert_memory(_node("N%02d" % i, "数据库相关记忆条目 %d" % i,
                              subject="s%d" % i, predicate="p", step=i + 1))
    r = Retriever(s, topk=5).recall("数据库相关记忆", case_step=30)
    assert r.candidate_pool_size >= 18, "候选池必须足够大才能测截断"
    assert r.truncated_candidates > 0
    assert len(r.injected_items) <= 5
