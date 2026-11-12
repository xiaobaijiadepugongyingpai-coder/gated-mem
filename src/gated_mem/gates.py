"""Gated-Mem 生命力与检索评分：无状态纯函数。

数学闭式解（阶段一已验证，实测值 0.4665 / 0.4830 / 0.4510 / 0.3231）：
    t0(v)  = t0_base(type) * (0.5 + input_weight)
    H      = t0 * (2 ** (1/beta) - 1)
    R(d)   = (1 + d / t0) ** (-beta)
    F(v)   = 1.0                                若 pinned
           = min(1.0, R + GAMMA * max(R of cited active parents))  否则
    Score  = rel * (F ** LAMBDA)

铁律（P0-3 / 议题 2 选项 A）：连坐机制永久物理封印。
本模块不存在任何因祖先废弃而扣减 F 的代码路径，也不存在 psi 常数。
祖先废弃的唯一合法表达是只读告警 stale_parent_warning（在 retrieval 中产生）。
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence

from .schema import MemoryType, MemoryNode

# 全局常数。不得由调用方随意覆盖默认值，但允许显式传参做消融。
LAMBDA_DEFAULT = 0.3
GAMMA_DEFAULT = 0.2
TOPK_DEFAULT = 5
MAX_DEPTH_DEFAULT = 8


def compute_t0(mem_type: MemoryType, input_weight: float) -> float:
    """t0 = t0_base(type) * (0.5 + input_weight)。

    input_weight 是输入门重要度，重要度越高初始时间尺度越长（衰减越慢）。
    """
    if not (0.0 < input_weight <= 1.0):
        raise ValueError("input_weight 必须落在 (0, 1]：%r" % (input_weight,))
    return mem_type.t0_base * (0.5 + input_weight)


def compute_half_life(t0: float, beta: float) -> float:
    """半衰期 H = t0 * (2 ** (1/beta) - 1)。"""
    if t0 <= 0:
        raise ValueError("t0 必须为正：%r" % (t0,))
    if beta <= 0:
        raise ValueError("beta 必须为正：%r" % (beta,))
    return t0 * (2.0 ** (1.0 / beta) - 1.0)


def compute_retention(delta_steps: float, t0: float, beta: float) -> float:
    """幂律保留率 R = (1 + delta/t0) ** (-beta)。delta<0 按 0 处理。"""
    if t0 <= 0:
        raise ValueError("t0 必须为正：%r" % (t0,))
    if beta <= 0:
        raise ValueError("beta 必须为正：%r" % (beta,))
    d = delta_steps if delta_steps > 0 else 0.0
    return (1.0 + d / t0) ** (-beta)


def compute_retention_2h(mem_type: MemoryType, input_weight: float = 0.5) -> float:
    """R(2H) 的闭式解，用于自检断言。

    R(2H) = (2 * 2**(1/beta) - 1) ** (-beta)
    """
    beta = mem_type.beta
    return (2.0 * (2.0 ** (1.0 / beta)) - 1.0) ** (-beta)


def compute_vitality(
    node: MemoryNode,
    parent_retentions_cited: Sequence[float] = (),
    gamma: float = GAMMA_DEFAULT,
    case_step: Optional[int] = None,
) -> float:
    """生命力 F(v)。

    pinned 节点恒为 1.0（免疫时间衰减与覆盖连坐）。
    否则 F = min(1.0, R + gamma * max(已引用父节点的 R))。

    parent_retentions_cited 只应传入「本轮被激活的父节点」的 R 值。
    祖先被废弃时不得传入任何惩罚项——这是 P0-3 的物理保证。
    """
    if node.pinned:
        return 1.0
    if case_step is None:
        case_step = max(node.created_step, node.last_cited_step)
    delta = case_step - node.last_cited_step
    t0 = compute_t0(node.memory_type, node.input_weight)
    r = compute_retention(delta, t0, node.memory_type.beta)
    gain = 0.0
    if parent_retentions_cited:
        gain = gamma * max(parent_retentions_cited)
    f = r + gain
    return 1.0 if f > 1.0 else f


def compute_retrieval_score(rel: float, vitality: float, lam: float = LAMBDA_DEFAULT) -> float:
    """Score = rel * (F ** lambda)。

    lam=0 时退化为纯相关度检索（消融基线）。
    """
    if rel < 0.0:
        rel = 0.0
    if vitality < 0.0:
        vitality = 0.0
    return rel * (vitality ** lam)


def compute_relevance(query_tokens: frozenset, doc_tokens: frozenset) -> float:
    """rel = |A ∩ B| / sqrt(|A| * |B|)，空集返回 0.0。"""
    if not query_tokens or not doc_tokens:
        return 0.0
    overlap = len(query_tokens & doc_tokens)
    if overlap == 0:
        return 0.0
    return overlap / math.sqrt(len(query_tokens) * len(doc_tokens))


def rank_by_score(
    scored: Sequence,
    topk: int = TOPK_DEFAULT,
    sort_by_raw: bool = True,
) -> List:
    """按 score 降序、同分按 memory_id 升序排序并截断。

    sort_by_raw=True 时用未舍入的原始浮点做排序键（阶段一 AMB-1 的结论）。
    """
    if sort_by_raw:
        ordered = sorted(scored, key=lambda x: (-x[1], x[0].memory_id))
    else:
        ordered = sorted(scored, key=lambda x: (-round(x[1], 6), x[0].memory_id))
    if topk is None or topk <= 0:
        return list(ordered)
    return list(ordered[:topk])
