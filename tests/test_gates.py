"""gates 数学闭式解与连坐封印测试。"""
from __future__ import annotations

import math

import pytest

from src.gated_mem.gates import (
    compute_half_life,
    compute_retention,
    compute_retention_2h,
    compute_retrieval_score,
    compute_t0,
    compute_vitality,
)
from src.gated_mem.schema import MemoryNode, MemoryType

EXPECTED_R2H = {
    MemoryType.DECISION: 0.466539,
    MemoryType.CONSTRAINT: 0.482968,
    MemoryType.PREFERENCE: 0.450959,
    MemoryType.EPHEMERAL: 0.323133,
}


def test_r0_equals_one():
    for mt in MemoryType:
        assert compute_retention(0, 100.0, mt.beta) == 1.0


def test_rh_equals_half():
    for mt in MemoryType:
        t0 = compute_t0(mt, 0.5)
        h = compute_half_life(t0, mt.beta)
        assert abs(compute_retention(h, t0, mt.beta) - 0.5) < 1e-9


def test_r2h_closed_form_and_above_quarter():
    """R(2H) 必须等于闭式解，且严格大于 0.25（幂律长尾优势）。"""
    for mt in MemoryType:
        beta = mt.beta
        expected = (2.0 * (2.0 ** (1.0 / beta)) - 1.0) ** (-beta)
        t0 = compute_t0(mt, 0.5)
        h = compute_half_life(t0, beta)
        got = compute_retention(2 * h, t0, beta)
        assert math.isclose(got, expected, rel_tol=1e-9), (mt, got, expected)
        assert got > 0.25, (mt, got)
        assert compute_retention_2h(mt) == pytest.approx(expected, rel=1e-9)


def test_r2h_matches_phase1_measured_values():
    """阶段一实测定值，防止常数表被抄错。"""
    for mt, exp in EXPECTED_R2H.items():
        assert compute_retention_2h(mt) == pytest.approx(exp, abs=1e-3)


def test_t0_scales_with_input_weight():
    low = compute_t0(MemoryType.DECISION, 0.1)
    high = compute_t0(MemoryType.DECISION, 1.0)
    assert high > low


def test_pinned_is_immune_to_decay():
    node = MemoryNode(
        memory_id="N1", content="x", memory_type=MemoryType.EPHEMERAL,
        subject="s", predicate="p", pinned=True, created_step=0, last_cited_step=0,
    )
    assert compute_vitality(node, [], case_step=100000) == 1.0


def test_parent_decay_never_subtracts_vitality():
    """P0-3 铁律：父节点废弃不得扣减子节点 F。

    传入空父列表（相当于父节点全部失效）时，F 必须等于纯 R，
    而不是被乘以任何 psi 因子。
    """
    node = MemoryNode(
        memory_id="N2", content="x", memory_type=MemoryType.CONSTRAINT,
        subject="s", predicate="p", input_weight=0.5, created_step=0, last_cited_step=0,
    )
    t0 = compute_t0(node.memory_type, node.input_weight)
    pure_r = compute_retention(50, t0, node.memory_type.beta)
    f_no_parent = compute_vitality(node, [], case_step=50)
    assert f_no_parent == pytest.approx(pure_r, rel=1e-12)
    assert f_no_parent > 0.0


def test_gamma_gain_is_capped_at_one():
    node = MemoryNode(
        memory_id="N3", content="x", memory_type=MemoryType.DECISION,
        subject="s", predicate="p", created_step=0, last_cited_step=0,
    )
    assert compute_vitality(node, [1.0], case_step=0) == 1.0


def test_score_monotonic_in_vitality():
    low = compute_retrieval_score(0.5, 0.1, lam=0.3)
    high = compute_retrieval_score(0.5, 0.9, lam=0.3)
    assert high > low


def test_lambda_zero_ignores_vitality():
    """lambda=0 时分数退化为纯相关度（消融基线）。"""
    a = compute_retrieval_score(0.7, 0.01, lam=0.0)
    b = compute_retrieval_score(0.7, 1.0, lam=0.0)
    assert a == b == pytest.approx(0.7)


def test_no_connotation_constants_in_module():
    """物理封印：代码里不得存在 psi 常数或连坐乘子（注释提及不算）。

    用 AST 扫描名字节点，而不是文本搜索——文档里解释"不存在 psi"是合法的。
    """
    import ast
    import src.gated_mem.gates as g

    tree = ast.parse(open(g.__file__, "r", encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
    lowered = {n.lower() for n in names}
    assert "psi" not in lowered, "gates.py 不得出现 psi 连坐符号"
    # 也不得出现连坐乘子语义的常数名
    for bad in ("connotation_factor", "cascade_multiplier"):
        assert bad not in lowered
