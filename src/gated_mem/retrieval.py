"""混合检索与输出门。

P0-4 双通道物理隔离：
  injected_items     — 只含 status==active 的节点正文，绝不含 residual_diff
  evolution_traces   — 只含 SUPSERSEDES 边与 residual_diff，绝不混入正文

P0-2 多跳告警：
  沿 BELONGS_TO 向上追溯祖先（递归 CTE + visited 防环，MAX_DEPTH=8）；
  任一祖先为 superseded/killed 即置 stale_parent_warning=True 并记录祖先 id。
  这里绝不修改任何节点的 F 或 status。

P0-3 全链路透出：
  RecallItem 携带告警 -> RECALL_DELIVERED 事件载荷落盘 -> to_injection_xml 显式透出。
"""
from __future__ import annotations

import json
import math
import uuid
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .gates import (
    GAMMA_DEFAULT,
    LAMBDA_DEFAULT,
    MAX_DEPTH_DEFAULT,
    TOPK_DEFAULT,
    compute_relevance,
    compute_retrieval_score,
    compute_retention,
    compute_t0,
    compute_vitality,
    rank_by_score,
)
from .schema import (
    EdgeType,
    EventType,
    EvolutionTrace,
    MemoryNode,
    MemoryStatus,
    RecallItem,
    RecallReceipt,
    tokenize,
)
from .storage import Store

STALE_STATUSES = frozenset({MemoryStatus.SUPERSEDED.value, MemoryStatus.KILLED.value})


class Retriever(object):
    """混合检索器：FTS5 + 向量余弦 + 生命力门控。"""

    def __init__(
        self,
        store: Store,
        lam: float = LAMBDA_DEFAULT,
        gamma: float = GAMMA_DEFAULT,
        topk: int = TOPK_DEFAULT,
        max_depth: int = MAX_DEPTH_DEFAULT,
    ) -> None:
        self.store = store
        self.lam = lam
        self.gamma = gamma
        self.topk = topk
        self.max_depth = max_depth

    # -- 候选池 ---------------------------------------------------------
    def _candidate_ids(self, query: str, use_fts: bool = True) -> List[str]:
        """候选池 = FTS5 命中 ∪ 全部 active 节点。

        高密度场景下候选池可达 20-30，从而真正触发 TOPK 截断。
        """
        ids: List[str] = []
        seen = set()
        for node in self.store.all_memories():
            if node.memory_id not in seen:
                seen.add(node.memory_id)
                ids.append(node.memory_id)
        if use_fts:
            fts_hits = self.store.fts_search(_fts_query(query), limit=200)
            for mid, _score in fts_hits:
                if mid not in seen:
                    seen.add(mid)
                    ids.append(mid)
        return ids

    # -- 回执 -----------------------------------------------------------
    def recall(
        self,
        query: str,
        case_step: Optional[int] = None,
        topk: Optional[int] = None,
        max_tokens: Optional[int] = None,
        write_event: bool = True,
        use_fts: bool = True,
        use_vitality: bool = True,
    ) -> RecallReceipt:
        """执行一次召回，返回双通道回执并落盘 RECALL_DELIVERED。"""
        k = topk if topk is not None else self.topk
        all_nodes = {n.memory_id: n for n in self.store.all_memories()}
        if case_step is None:
            case_step = max([n.created_step for n in all_nodes.values()] or [0])

        q_tokens = tokenize(query)
        candidate_ids = self._candidate_ids(query, use_fts=use_fts)

        # 1. 只把 active 节点放进候选（被 superseded/killed 的绝不注入正文）
        scored: List[Tuple[MemoryNode, float]] = []
        for mid in candidate_ids:
            node = all_nodes.get(mid)
            if node is None:
                continue
            if node.status != MemoryStatus.ACTIVE:
                continue
            rel = compute_relevance(q_tokens, tokenize(_doc_text(node)))
            if use_vitality:
                parent_rs = self._parent_retentions(node, all_nodes, case_step)
                f = compute_vitality(node, parent_rs, gamma=self.gamma, case_step=case_step)
            else:
                f = 1.0
            s = compute_retrieval_score(rel, f, lam=self.lam)
            scored.append((node, s))

        pool_size = len(scored)
        ordered = rank_by_score(scored, topk=None)

        # 2. 多跳告警（绝不改 F）
        warnings: Dict[str, List[str]] = {}
        for node, _s in ordered:
            anc = self._stale_ancestors(node.memory_id)
            if anc:
                warnings[node.memory_id] = anc

        # 3. TOPK 截断
        chosen = ordered[:k] if (k and k > 0) else list(ordered)

        items: List[RecallItem] = []
        tokens_used = 0
        for node, score in chosen:
            item_tokens = _approx_tokens(node.content)
            if max_tokens is not None and tokens_used + item_tokens > max_tokens and items:
                break
            t0 = compute_t0(node.memory_type, node.input_weight)
            rel = compute_relevance(q_tokens, tokenize(_doc_text(node)))
            f = compute_vitality(node, [], gamma=self.gamma, case_step=case_step)
            items.append(
                RecallItem(
                    memory_id=node.memory_id,
                    content=node.content,
                    memory_type=node.memory_type,
                    subject=node.subject,
                    predicate=node.predicate,
                    scope=node.scope,
                    trust_tier=node.trust_tier,
                    relevance=round(rel, 6),
                    vitality=round(f, 6),
                    score=round(score, 6),
                    stale_parent_warning=node.memory_id in warnings,
                    stale_ancestor_ids=warnings.get(node.memory_id, []),
                )
            )
            tokens_used += item_tokens

        # 4. 演进轨迹通道（只取被注入节点上的 SUPERSEDES 边与 residual_diff）
        traces = self._collect_traces([i.memory_id for i in items], all_nodes)

        excluded = [
            mid
            for mid, n in all_nodes.items()
            if n.status in STALE_STATUSES
            and compute_relevance(q_tokens, tokenize(_doc_text(n))) > 0.0
        ]

        recall_event_id = ""
        if write_event:
            recall_event_id = str(uuid.uuid4())
            self.store.append_event(
                EventType.RECALL_DELIVERED,
                case_step,
                {
                    "recall_event_id": recall_event_id,
                    "query": query,
                    "injected_ids": [i.memory_id for i in items],
                    "excluded_stale_ids": sorted(excluded),
                    "stale_warnings": [
                        {"memory_id": i.memory_id, "stale_ancestor_ids": i.stale_ancestor_ids}
                        for i in items
                        if i.stale_parent_warning
                    ],
                    "evolution_trace_ids": [t.memory_id for t in traces],
                    "tokens_used": tokens_used,
                    "candidate_pool_size": pool_size,
                    "truncated_candidates": max(0, pool_size - len(items)),
                },
                correlation_id=str(uuid.uuid4()),
            )
            # 刷新被引用节点的 last_cited_step
            for i in items:
                self.store.touch_citation(i.memory_id, case_step)

        return RecallReceipt(
            recall_event_id=recall_event_id,
            query=query,
            injected_items=items,
            evolution_traces=traces,
            excluded_stale_ids=sorted(excluded),
            stale_warning_ids=[i.memory_id for i in items if i.stale_parent_warning],
            tokens_used=tokens_used,
            truncated_candidates=max(0, pool_size - len(items)),
            candidate_pool_size=pool_size,
        )

    # -- 内部 -----------------------------------------------------------
    def _parent_retentions(
        self, node: MemoryNode, all_nodes: Dict[str, MemoryNode], case_step: int
    ) -> List[float]:
        """只统计「本轮被激活（active）的父节点」的 R。

        父节点被废弃时返回空列表——即不产生任何惩罚，仅不产生增益。
        """
        out: List[float] = []
        for pid in self.store.parents_of(node.memory_id, EdgeType.BELONGS_TO):
            parent = all_nodes.get(pid)
            if parent is None or parent.status != MemoryStatus.ACTIVE:
                continue
            t0 = compute_t0(parent.memory_type, parent.input_weight)
            out.append(
                compute_retention(case_step - parent.last_cited_step, t0, parent.memory_type.beta)
            )
        return out

    def _stale_ancestors(self, memory_id: str) -> List[str]:
        """跨多跳追溯失效祖先，visited 防环，深度上限 MAX_DEPTH。"""
        visited = set()
        stack = [(memory_id, 0)]
        stale: List[str] = []
        while stack:
            cur, depth = stack.pop()
            if depth >= self.max_depth:
                continue
            for pid in self.store.parents_of(cur, EdgeType.BELONGS_TO):
                if pid in visited:
                    continue
                visited.add(pid)
                parent = self.store.get_memory(pid)
                if parent is None:
                    continue
                if parent.status.value in STALE_STATUSES:
                    stale.append(pid)
                stack.append((pid, depth + 1))
        return sorted(stale)

    def _collect_traces(
        self, injected_ids: Sequence[str], all_nodes: Dict[str, MemoryNode]
    ) -> List[EvolutionTrace]:
        """从被注入节点出发，收集 SUPERSEDES 边承载的演进轨迹。

        同时收集「被注入节点自身 residual_diff」（C 分支语义：新节点记录为何替换旧的）。
        """
        traces: List[EvolutionTrace] = []
        seen = set()
        for mid in injected_ids:
            node = all_nodes.get(mid)
            if node is None:
                continue
            # 自身带 diff 的（它是某次覆盖的产物）
            if node.residual_diff and mid not in seen:
                seen.add(mid)
                traces.append(
                    EvolutionTrace(
                        memory_id=mid,
                        subject=node.subject,
                        residual_diff=node.residual_diff,
                        replaced_entity=_parse_replaced(node.residual_diff),
                    )
                )
            # 它 SUPERSEDES 了谁
            for old_id in self.store.children_of(mid) or []:
                pass
        # 沿 SUPERSEDES 边找出被覆盖节点，把它们的 diff 也纳入
        for mid in injected_ids:
            rows = self.store.conn.execute(
                "SELECT target_id, residual_diff FROM memory_edges"
                " WHERE project_id=? AND source_id=? AND edge_type=? ORDER BY target_id ASC",
                (self.store.project_id, mid, EdgeType.SUPERSEDES.value),
            ).fetchall()
            for r in rows:
                old = all_nodes.get(r["target_id"])
                key = "edge:%s:%s" % (mid, r["target_id"])
                if key in seen:
                    continue
                seen.add(key)
                diff = r["residual_diff"] or (old.residual_diff if old else "")
                if not diff:
                    continue
                traces.append(
                    EvolutionTrace(
                        memory_id=mid,
                        subject=old.subject if old else "",
                        residual_diff=diff,
                        replaced_entity=_parse_replaced(diff),
                    )
                )
        return traces


def _doc_text(node: MemoryNode) -> str:
    """检索文本：正文 + 残差（残差参与匹配，但绝不进注入正文）。"""
    if node.residual_diff:
        return node.content + " " + node.residual_diff
    return node.content


def _fts_query(query: str) -> str:
    """把自然语言 query 转成 FTS5 安全查询串（去掉 FTS 语法字符）。"""
    tokens = [t for t in tokenize(query) if t.isalnum() or len(t) > 1]
    safe = [t for t in tokens if not any(ch in t for ch in '"\':*^()-')]
    return " OR ".join(safe[:20])


def _approx_tokens(text: str) -> int:
    """粗略 token 估算：中文按字、英文按 4 字符。"""
    import re as _re

    cjk = len(_re.findall(r"[\u4e00-\u9fff]", text))
    others = len(text) - cjk
    return cjk + max(1, others // 4)


def _parse_replaced(diff: str) -> str:
    """从 [Replaced: X] 里解析出 X。"""
    import re as _re

    m = _re.match(r"^\[Replaced:\s*([^\]]*)\]", diff)
    return m.group(1).strip() if m else ""
