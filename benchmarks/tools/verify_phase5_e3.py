# -*- coding: utf-8 -*-
"""独立交叉验证：不复用 eval 脚本的聚合逻辑，逐题重算四通道与平局统计。"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from src.gated_mem.embeddings import FastEmbedProvider, non_negative_cosine
from src.gated_mem.gates import bm25_to_positive, calibrated_fusion, saturate_bm25
from src.gated_mem.schema import MemoryNode, MemoryType
from src.gated_mem.storage import Store
from src.gated_mem.retrieval import _fts_query

MODES = (("A1_vec", "vec"), ("A2_fts", "fts"), ("A3_slot", "slot"), ("A4_fusion", "fusion"))
data = json.load(open(os.path.join(ROOT, "benchmarks", "data",
                                   "phase5_e3_collision_disambiguation.json"), encoding="utf-8"))
p = FastEmbedProvider()
print("provider=%s dim=%d cases=%d" % (p.model_id, p.dim, len(data["cases"])))

tie_cnt = {m: 0 for m, _ in MODES}
tie_luck = {m: 0 for m, _ in MODES}
hit1 = {m: 0 for m, _ in MODES}
hit3 = {m: 0 for m, _ in MODES}
by_mod = {m: {"A": 0, "B": 0} for m, _ in MODES}
fail_rows = []
tie_detail = {}

for case in data["cases"]:
    st = Store(":memory:")
    for m in case["memories"]:
        st.insert_memory(MemoryNode(
            memory_id=m["id"], content=m["content"],
            memory_type=MemoryType(m["memory_type"]),
            subject=m["subject"], predicate=m["predicate"], scope="global",
            input_weight=float(m.get("input_weight", 0.5)), pinned=False,
            embedding=p.embed_one(m["content"]), embedding_model=p.model_id,
            created_step=int(m["step"]), last_cited_step=int(m["step"])))
    q = case["query"]
    qv = p.embed_one(q)
    bm = {mid: saturate_bm25(bm25_to_positive(r))
          for mid, r in st.fts_search(_fts_query(q), limit=500)}
    rows = []
    for node in st.all_memories():
        sv = non_negative_cosine(qv, node.embedding) if node.embedding else 0.0
        sf = bm.get(node.memory_id, 0.0)
        slot = any(s and s.lower() in q.lower() for s in (node.subject, node.predicate))
        rows.append({"id": node.memory_id, "vec": sv, "fts": sf,
                     "slot": 1.0 if slot else 0.0,
                     "fusion": calibrated_fusion(sv, sf, slot)})
    st.close()
    exp = case["expected_id"]
    for mode, key in MODES:
        ordered = sorted(rows, key=lambda r: (-r[key], r["id"]))
        best = ordered[0][key]
        tied = [r["id"] for r in ordered if abs(r[key] - best) < 1e-12]
        top1 = ordered[0]["id"]
        if top1 == exp:
            hit1[mode] += 1
            by_mod[mode][case["target_module"]] += 1
        if exp in [r["id"] for r in ordered[:3]]:
            hit3[mode] += 1
        if len(tied) > 1:
            tie_cnt[mode] += 1
            if exp in tied and exp == min(tied):
                tie_luck[mode] += 1
            if mode in ("A2_fts", "A4_fusion"):
                tie_detail.setdefault(case["case_id"], {})[mode] = {
                    "tied": tied, "expected": exp, "top1": top1,
                    "is_luck": exp in tied and exp == min(tied)}
    if hit1["A4_fusion"] == 0:  # placeholder, recomputed below
        pass
    if sorted(rows, key=lambda r: (-r["fusion"], r["id"]))[0]["id"] != exp:
        fail_rows.append({
            "case_id": case["case_id"], "expected": exp,
            "target_module": case["target_module"],
            "rows": sorted(rows, key=lambda r: -r["fusion"]),
        })

n = len(data["cases"])
print("\n== 四通道 ==")
for mode, _ in MODES:
    print("  %-10s Top1=%2d/%d (%.2f%%)  Top3=%2d/%d (%.2f%%)  A侧=%d B侧=%d"
          % (mode, hit1[mode], n, 100.0 * hit1[mode] / n, hit3[mode], n,
             100.0 * hit3[mode] / n, by_mod[mode]["A"], by_mod[mode]["B"]))

print("\n== 平局统计 ==")
for mode, _ in MODES:
    print("  %-10s 榜首平局=%d  其中字典序侥幸赢=%d" % (mode, tie_cnt[mode], tie_luck[mode]))

print("\n== 融合失败题 ==")
for f in fail_rows:
    print("  %s expected=%s target_module=%s" % (f["case_id"], f["expected"], f["target_module"]))
    for r in f["rows"]:
        print("     %s vec=%.4f fts=%.4f slot=%.0f fusion=%.4f"
              % (r["id"], r["vec"], r["fts"], r["slot"], r["fusion"]))

print("\n== A2/A4 平局明细 ==")
for cid in sorted(tie_detail):
    print("  %s -> %s" % (cid, json.dumps(tie_detail[cid], ensure_ascii=False)))

print("\n== 逐题 Top-1 ==")
