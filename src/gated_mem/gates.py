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

# --- 有界校准融合常数（GM-DIRECTIVE-P3-v2.2.0 §3.1）---
# alpha 是向量通道权重；1-alpha 给 FTS 通道。默认 0.60 略偏向量。
ALPHA_DEFAULT = 0.60
# 米氏饱和常数：bm25 原始正分达到 5.0 时映射到 0.5。
KB_DEFAULT = 5.0
# 槽位精确命中奖励。
BETA_SLOT_DEFAULT = 0.15
# FTS 单通道保底系数：防止专有名词精确命中被向量平均稀释。
FTS_FLOOR_RATIO = 0.85


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


def saturate_bm25(raw_score: float, kb: float = KB_DEFAULT) -> float:
    """米氏饱和函数：s = b / (b + kb)，把 b>=0 映射到 [0, 1)。

    性质（这是它优于 Min-Max 的关键）：
      - b=0 时 s=0，绝不会把微弱噪音放大到 1.0
      - b 单调递增、有上界，批次内无「相对拉伸」语义
      - 不需要知道整批候选的分布，因此天然支持单条打分与增量更新
    """
    if raw_score <= 0.0:
        return 0.0
    return raw_score / (raw_score + kb)


def bm25_to_positive(bm25_value: float) -> float:
    """FTS5 的 bm25() 返回负数且越负越相关，转成非负原始分。"""
    v = -float(bm25_value)
    return v if v > 0.0 else 0.0


def calibrated_fusion(
    s_vec: float,
    s_fts: float,
    slot_hit: bool = False,
    alpha: float = ALPHA_DEFAULT,
    beta_slot: float = BETA_SLOT_DEFAULT,
) -> float:
    """有界校准融合，返回 rel(q, v) ∈ [0, 1]。

    公式（终审钦定闭式解）：
        blended = alpha * s_vec + (1 - alpha) * s_fts
        floored = max(blended, 0.85 * s_fts)        # FTS 保底，防专名被稀释
        rel     = min(1.0, floored + beta_slot * I(slot_hit))

    为什么不用 RRF：标准 RRF 的第 1 名与第 10 名分差仅 1.14 倍，
    而生命力门控 [F]^0.3 的动态范围可达 5.5 倍，相乘会把相关性差异抹平。
    有界校准融合保持绝对可比性，且有硬上界 1.0。
    """
    a = alpha if 0.0 <= alpha <= 1.0 else ALPHA_DEFAULT
    sv = s_vec if s_vec > 0.0 else 0.0
    sf = s_fts if s_fts > 0.0 else 0.0
    blended = a * sv + (1.0 - a) * sf
    floored = blended if blended > FTS_FLOOR_RATIO * sf else FTS_FLOOR_RATIO * sf
    rel = floored + (beta_slot if slot_hit else 0.0)
    return 1.0 if rel > 1.0 else rel


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
