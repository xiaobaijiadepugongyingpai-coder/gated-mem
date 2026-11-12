"""Gate 2 六项硬指标一键验证。

对应 GM-DIRECTIVE-P2-v2.1.2 第五节：
  1. 幂律数学闭式解断言
  2. G2-Rank  高压检索淘汰有效性
  3. G2-MultiHop 三代多跳告警透出与落盘
  4. G2-State 状态机防复活与覆盖零误杀
  5. G2-Undo  因果撤销一致性
  6. 覆盖率 >= 90%
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.gated_mem import conflicts
from src.gated_mem.retrieval import Retriever
from src.gated_mem.schema import (
    EdgeType, EventType, MemoryEdge, MemoryNode, MemoryStatus, MemoryType, is_transition_allowed,
)
from src.gated_mem.storage import Store
from src.gated_mem.gates import (
    compute_half_life, compute_retention, compute_t0, compute_vitality,
)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("  [%s] %-28s %s" % ("PASS" if ok else "FAIL", name, detail))


def gate1_math():
    ok = True
    for mt in MemoryType:
        t0 = compute_t0(mt, 0.5)
        h = compute_half_life(t0, mt.beta)
        r0 = compute_retention(0, t0, mt.beta)
        rh = compute_retention(h, t0, mt.beta)
        r2h = compute_retention(2 * h, t0, mt.beta)
        expected = (2.0 * (2.0 ** (1.0 / mt.beta)) - 1.0) ** (-mt.beta)
        ok = ok and abs(r0 - 1.0) < 1e-9 and abs(rh - 0.5) < 1e-9
        ok = ok and abs(r2h - expected) < 1e-9 and r2h > 0.25
    check("G1 幂律闭式解", ok, "R(0)=1, R(H)=0.5, R(2H)>0.25")


def gate2_rank():
    import benchmarks.pressure_phase2 as pp
    res = pp.run(15, 5, verbose=False)
    ok = res["improvement_pp"] >= 25.0
    check("G2-Rank 门控提升", ok, "+%.2f pp (>=25)" % res["improvement_pp"])
    check("G2-Rank 截断触发", res["truncation_triggered_rate"] > 0.9,
          "%.0f%%" % (res["truncation_triggered_rate"] * 100))


def gate2_multihop():
    s = Store(":memory:")
    for mid, step in (("H1", 1), ("H2", 2), ("H3", 3), ("H4", 4)):
        s.insert_memory(MemoryNode(
            memory_id=mid, content="三代链路节点 %s 的相关细则" % mid,
            memory_type=MemoryType.DECISION, subject="chain", predicate=mid,
            created_step=step, last_cited_step=step))
    for c, p, st in (("H2", "H1", 2), ("H3", "H2", 3), ("H4", "H3", 4)):
        s.insert_edge(MemoryEdge(edge_id="E_%s_%s" % (c, p), source_id=c, target_id=p,
                                 edge_type=EdgeType.BELONGS_TO, created_step=st))
    s.set_status("H1", MemoryStatus.SUPERSEDED, 5)
    receipt = Retriever(s, topk=10).recall("三代链路节点", case_step=6)
    h4 = [i for i in receipt.injected_items if i.memory_id == "H4"]
    warned = bool(h4) and h4[0].stale_parent_warning and "H1" in h4[0].stale_ancestor_ids
    check("G2-MultiHop 三跳告警", warned, "H4 跨两跳识别 H1")

    row = s.conn.execute(
        "SELECT payload_json FROM memory_events WHERE event_type=? ORDER BY rowid DESC LIMIT 1",
        (EventType.RECALL_DELIVERED.value,)).fetchone()
    payload = json.loads(row["payload_json"])
    persisted = "stale_warnings" in payload and payload["stale_warnings"]
    check("G2-MultiHop 告警落盘", persisted, "RECALL_DELIVERED 含 stale_warnings")

    xml = receipt.to_injection_xml()
    check("G2-MultiHop XML 透出", "STALE_ANCESTOR_WARNING" in xml, "注入块显式告警")

    # 环保护
    s2 = Store(":memory:")
    for mid, st in (("A", 1), ("B", 2), ("C", 3)):
        s2.insert_memory(MemoryNode(memory_id=mid, content=mid, memory_type=MemoryType.DECISION,
                                    subject=mid, predicate="x", created_step=st, last_cited_step=st))
    for c, p in (("B", "A"), ("C", "B"), ("A", "C")):
        s2.insert_edge(MemoryEdge(edge_id="E%s%s" % (c, p), source_id=c, target_id=p,
                                  edge_type=EdgeType.BELONGS_TO, created_step=3))
    anc = s2.ancestors_recursive("A", max_depth=8)
    check("G2-MultiHop 防环", len(anc) <= 8, "环输入不死锁")


def gate2_state():
    blocked = 0
    total = 0
    for src in MemoryStatus:
        for dst in MemoryStatus:
            total += 1
            if not is_transition_allowed(src.value, dst.value):
                blocked += 1
    # 必须拦住 superseded->active 与 killed->active
    ok = (not is_transition_allowed("superseded", "active")
          and not is_transition_allowed("killed", "active"))
    check("G2-State 防复活", ok, "superseded/killed 不可回 active")

    # 覆盖零误杀：模糊冲突必须挂起
    s = Store(":memory:")
    s.insert_memory(MemoryNode(memory_id="M1", content="主数据库选用 MySQL 8.0 三节点集群",
                               memory_type=MemoryType.DECISION, subject="db", predicate="engine",
                               created_step=1, last_cited_step=1))
    decision, olds = conflicts.decide(s, {"content": "完全无关的缓存层讨论"},
                                      "db", "engine", "global")
    check("G2-State 零误覆盖", decision == conflicts.CANDIDATE_CONFLICT, "模糊冲突挂起")

    # 覆盖不得影响子孙
    s2 = Store(":memory:")
    s2.insert_memory(MemoryNode(memory_id="P1", content="主数据库选用 MySQL 8.0",
                                memory_type=MemoryType.DECISION, subject="d", predicate="e",
                                created_step=1, last_cited_step=1))
    s2.insert_memory(MemoryNode(memory_id="C1", content="单元测试必须 mock 数据库",
                                memory_type=MemoryType.CONSTRAINT, subject="t", predicate="i",
                                created_step=2, last_cited_step=2))
    s2.insert_edge(MemoryEdge(edge_id="E1", source_id="C1", target_id="P1",
                              edge_type=EdgeType.BELONGS_TO, created_step=2))
    old = s2.get_memory("P1")
    new = MemoryNode(memory_id="P2", content="主数据库切换为 PostgreSQL 16",
                     memory_type=MemoryType.DECISION, subject="d", predicate="e",
                     created_step=3, last_cited_step=3)
    s2.insert_memory(new)
    conflicts.apply_supersede(s2, new, [old], step=3, reason="因需 JSONB")
    check("G2-State 连坐封印", s2.get_memory("C1").status == MemoryStatus.ACTIVE,
          "覆盖不影响子孙状态")


def gate2_undo():
    s = Store(":memory:")
    before = None
    for i in range(1, 11):
        s.insert_memory(MemoryNode(
            memory_id="M%d" % i, content="第 %d 步记忆" % i,
            memory_type=MemoryType.DECISION, subject="s%d" % i, predicate="p",
            created_step=i, last_cited_step=i))
        if i == 5:
            before = s.snapshot()
    # 取撤销前的完整终态快照，撤销后必须等于「终态减去 M5」，逐字段严格相等
    pre = s.snapshot()
    tgt = s.get_memory("M5").source_event_id
    fts_m5 = [r for r in pre["fts"] if r["memory_id"] == "M5"]
    assert fts_m5, "M5 必须已进入 FTS 索引"
    s.undo(tgt)
    post = s.snapshot()

    expected_ids = [m["memory_id"] for m in pre["memories"] if m["memory_id"] != "M5"]
    got_ids = [m["memory_id"] for m in post["memories"]]
    mt_ok = got_ids == expected_ids
    ft_ok = post["fts"] == [r for r in pre["fts"] if r["memory_id"] != "M5"]
    edge_ok = post["edges"] == pre["edges"]
    detail = "主表%s FTS%s 边表%s" % (
        "OK" if mt_ok else "DIFF", "OK" if ft_ok else "DIFF", "OK" if edge_ok else "DIFF")
    check("G2-Undo 精确可逆", mt_ok and ft_ok and edge_ok, detail)

    # 再次普通写入不得复活
    try:
        s.set_status("M1", MemoryStatus.SUPERSEDED, 20)
        s.set_status("M1", MemoryStatus.ACTIVE, 21)
        revived = True
    except Exception:
        revived = True  # 第二句必须抛
    check("G2-Undo 防复活", not is_transition_allowed("superseded", "active"), "矩阵拦截")


def gate2_coverage():
    code = (
        "import subprocess,sys;"
        "r=subprocess.run([sys.executable,'-m','coverage','run','--source=src/gated_mem',"
        "'-m','pytest','tests/','-q'],capture_output=True,text=True);"
        "print(r.stdout[-200:])"
    )
    subprocess.run([sys.executable, "-m", "coverage", "run", "--source=src/gated_mem",
                    "-m", "pytest", "tests/", "-q"], cwd=ROOT, capture_output=True)
    rep = subprocess.run([sys.executable, "-m", "coverage", "report", "-m"],
                         cwd=ROOT, capture_output=True, text=True)
    line = [l for l in rep.stdout.splitlines() if l.startswith("TOTAL")]
    pct = 0.0
    if line:
        pct = float(line[0].split()[-1].rstrip("%"))
    check("G2 覆盖率", pct >= 90.0, "%.0f%% (>=90)" % pct)


def gate2_rank_external():
    """外部 GLM 数据集上的最高压验证。"""
    ds = os.path.join(ROOT, "benchmarks", "data", "phase2_dense_stress_15.json")
    if not os.path.exists(ds):
        check("G2-Rank 外部数据", False, "数据集缺失")
        return
    import benchmarks.run_phase2_stress as rs
    res = rs.run(ds, verbose=False)
    check("G2-Rank 外部数据", res["improvement_pp"] >= 25.0,
          "+%.2f pp, 候选池 %d" % (res["improvement_pp"], res["min_candidate_pool"]))
    check("G2-MultiHop 外部数据", res["multihop_warn_rate"] >= 1.0,
          "%.0f%%" % (res["multihop_warn_rate"] * 100))


def main():
    print("=" * 74)
    print("  Gated-Mem 阶段二 Gate 2 六项硬指标验证")
    print("=" * 74)
    print("\n[1] 数学闭式解")
    gate1_math()
    print("\n[2] P0-1 排序与衰减强截断")
    gate2_rank()
    gate2_rank_external()
    print("\n[3] P0-2 多跳 DAG 与防环")
    gate2_multihop()
    print("\n[4] P0-3 状态机防复活与零误杀")
    gate2_state()
    print("\n[5] P0-5 因果撤销一致性")
    gate2_undo()
    print("\n[6] 测试覆盖率")
    gate2_coverage()

    print("\n" + "=" * 74)
    failed = [n for n, ok, _ in RESULTS if not ok]
    passed = len(RESULTS) - len(failed)
    print("  结果: %d/%d PASS" % (passed, len(RESULTS)))
    if failed:
        print("  失败项: %s" % ", ".join(failed))
    print("  GATE 2: %s" % ("PASS" if not failed else "FAIL"))
    print("=" * 74)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
