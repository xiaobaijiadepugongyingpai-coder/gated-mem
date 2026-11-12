"""两阶段槽位冲突裁决。

铁律（P0-3 / 议题 2）：连坐永久物理封印。
  旧节点被覆盖时，只做两件事：
    1. 旧节点自身 status -> superseded；
    2. 沿 BELONGS_TO 向上追溯它的子孙时，不做任何递归状态修改；
       子孙的生命力 F 不受任何影响，只在检索时透出只读告警 stale_parent_warning。
  生产代码中不存在 psi、也不存在任何因子孙/祖先废弃而扣减 F 的分支。
"""
from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

from .schema import (
    EdgeType,
    MemoryEdge,
    MemoryNode,
    MemoryStatus,
    MemoryType,
    tokenize,
)
from .storage import Store

REPLACED_PREFIX_RE = re.compile(r"^\[Replaced:\s*(?P<entity>[^\]]*)\]\s*")

# 内容等价判定阈值：槽位相同且 rel >= 该值视为同一事实的重述。
EXACT_MATCH_THRESHOLD = 0.92
# 明确覆盖阈值：达到该值认定为对旧事实的替换。
SUPERSEDE_THRESHOLD = 0.55


class ConflictDecision(str):
    """裁决结果常量。"""


EXACT_MATCH = "EXACT_MATCH"
SUPERSEDES = "SUPERSEDES"
CANDIDATE_CONFLICT = "CANDIDATE_CONFLICT"
NO_CONFLICT = "NO_CONFLICT"


def normalize_slot(store: Store, subject: str, predicate: str, scope: str) -> Tuple[str, str, str]:
    """经 slot_aliases 归一化槽位三元组。"""
    return (
        store.resolve_alias(subject),
        store.resolve_alias(predicate),
        store.resolve_alias(scope),
    )


def _rel(a: str, b: str) -> float:
    """内部相似度，口径与 retrieval 一致。"""
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    import math

    return len(ta & tb) / math.sqrt(len(ta) * len(tb))


def extract_entity_keyword(content: str) -> str:
    """从旧节点正文中提取被替换实体的关键词。

    优先取长度 >= 3 的 ASCII 技术名词（MySQL / PostgreSQL / React）；
    没有则回退到首个中文片段的前 6 字。
    """
    words = re.findall(r"[A-Za-z][A-Za-z0-9_.\-]*", content)
    long_words = [w for w in words if len(w) >= 3]
    if long_words:
        return long_words[0]
    cjk = re.findall(r"[\u4e00-\u9fff]+", content)
    if cjk:
        return cjk[0][:6]
    return content[:6]


def format_residual_diff(old_node: MemoryNode, reason: str) -> str:
    """拼装 [Replaced: <旧实体>] <原因>。

    若 reason 已带前缀则原样返回（幂等，避免双重前缀）。
    """
    if reason and REPLACED_PREFIX_RE.match(reason):
        return reason
    entity = extract_entity_keyword(old_node.content)
    return "[Replaced: %s] %s" % (entity, reason)


def decide(
    store: Store,
    new_node_draft: dict,
    normalized_subject: str,
    normalized_predicate: str,
    normalized_scope: str,
) -> Tuple[str, List[MemoryNode]]:
    """两阶段裁决。返回 (decision, old_nodes)。

    阶段一：槽位归一化后查同槽活跃节点；
    阶段二：比对内容，决定 EXACT_MATCH / SUPERSEDES / CANDIDATE_CONFLICT。
    """
    olds = store.find_active_by_slot(normalized_subject, normalized_predicate, normalized_scope)
    if not olds:
        return NO_CONFLICT, []

    content = new_node_draft.get("content", "")
    best_rel = 0.0
    for old in olds:
        r = _rel(content, old.content)
        if r > best_rel:
            best_rel = r

    if best_rel >= EXACT_MATCH_THRESHOLD:
        return EXACT_MATCH, olds
    if best_rel >= SUPERSEDE_THRESHOLD:
        return SUPERSEDES, olds
    # 槽位相同但内容既不重述也不明确替换 —— 挂起待决，绝不自动覆盖
    return CANDIDATE_CONFLICT, olds


def apply_supersede(
    store: Store,
    new_node: MemoryNode,
    old_nodes: Sequence[MemoryNode],
    step: int,
    reason: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> MemoryNode:
    """执行覆盖：旧节点标 superseded，返回带格式化 residual_diff 的新节点。

    关键：这里既不递归改子孙状态，也不触碰任何生命力计算。
    """
    ordered = sorted(old_nodes, key=lambda n: n.memory_id)
    primary = ordered[0]

    if reason is None or not reason.strip():
        # 未给原因时用默认模板，仍保持 [Replaced: ...] 格式
        reason = "该决策已被 %s 替代" % new_node.memory_id
    diff = format_residual_diff(primary, reason)

    for old in ordered:
        store.set_status(
            old.memory_id,
            MemoryStatus.SUPERSEDED,
            step,
            correlation_id=correlation_id,
        )
        # 覆盖边：新节点 SUPERSEDES 旧节点（source=child(new) -> target=parent(old)）
        store.insert_edge(
            MemoryEdge(
                edge_id="E_SUP_%s_%s" % (new_node.memory_id, old.memory_id),
                project_id=store.project_id,
                source_id=new_node.memory_id,
                target_id=old.memory_id,
                edge_type=EdgeType.SUPERSEDES,
                residual_diff=diff,
                created_step=step,
            )
        )

    return new_node.model_copy(update={"residual_diff": diff})


def mark_candidate_conflict(
    store: Store,
    new_node: MemoryNode,
    old_nodes: Sequence[MemoryNode],
    step: int,
    correlation_id: Optional[str] = None,
) -> MemoryNode:
    """把新节点挂起为 candidate_conflict，等待人工或规则裁决。

    绝不自动覆盖旧节点——这是「零误覆盖」的物理保证。
    """
    conflicted = new_node.model_copy(update={"status": MemoryStatus.CANDIDATE_CONFLICT})
    store.insert_memory(conflicted)
    return conflicted


def resolve_candidate(
    store: Store,
    memory_id: str,
    decision: str,
    step: int,
    reason: Optional[str] = None,
) -> None:
    """人工裁决一个 candidate_conflict 节点。

    decision 只能是 ACTIVE 或 SUPERSEDED（不允许直接 KILLED 绕过审计）。
    """
    node = store.get_memory(memory_id)
    if node is None:
        raise ValueError("节点不存在：%s" % memory_id)
    if node.status != MemoryStatus.CANDIDATE_CONFLICT:
        raise ValueError("节点 %s 不处于 candidate_conflict（当前 %s）" % (memory_id, node.status.value))
    target = MemoryStatus.ACTIVE if decision == ACTIVE_DECISION else MemoryStatus.SUPERSEDED
    store.set_status(memory_id, target, step)
    if target == MemoryStatus.SUPERSEDED and reason:
        store.conn.execute(
            "UPDATE memories SET residual_diff=? WHERE memory_id=?", (reason, memory_id)
        )


ACTIVE_DECISION = "ACTIVE"
SUPERSEDED_DECISION = "SUPERSEDED"
