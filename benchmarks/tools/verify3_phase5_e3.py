# -*- coding: utf-8 -*-
"""对指定数据集做四通道全量核验（含互补性、模块/版本判别率、平局性质）。"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from src.gated_mem.embeddings import FastEmbedProvider, non_negative_cosine
from src.gated_mem.gates import bm25_to_positive, calibrated_fusion, saturate_bm25
from src.gated_mem.schema import MemoryNode, MemoryType
from src.gated_mem.storage import Store
from src.gated_mem.retrieval import _fts_query

path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
p = FastEmbedProvider()
MODES = (("A1_vec", "vec"), ("A2_fts", "fts"), ("A3_slot", "slot"), ("A4_fusion", "fusion"))
hit = {m: set() for m, _ in MODES}
hit3 = {m: 0 for m, _ in MODES}
mod_ok = {m: 0 for m, _ in MODES}
ver_ok = {m: 0 for m, _ in MODES}
tie = {m: 0 for m, _ in MODES}
luck = {m: 0 for m, _ in MODES}
by_side = {m: {"A": 0, "B": 0} for m, _ in MODES}
fail = []

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
    q = case["query"]; qv = p.embed_one(q)
    raw = dict(st.fts_search(_fts_query(q), limit=500))
    rows = []
    for node in st.all_memories():
        sv = non_negative_cosine(qv, node.embedding)
        sf = saturate_bm25(bm25_to_positive(raw.get(node.memory_id, 0.0)))
        slot = any(s and s.lower() in q.lower() for s in (node.subject, node.predicate))
        rows.append({"id": node.memory_id, "vec": sv, "fts": sf,
                     "slot": 1.0 if slot else 0.0, "fusion": calibrated_fusion(sv, sf, slot)})
    st.close()
    exp = case["expected_id"]
    meta = {m["id"]: m for m in case["memories"]}
    side = case.get("target_module") or meta[exp]["module"]
    for mode, key in MODES:
        ordered = sorted(rows, key=lambda r: (-r[key], r["id"]))
        best = ordered[0][key]
        tied = [r["id"] for r in ordered if abs(r[key] - best) < 1e-12]
        t1 = ordered[0]["id"]
        if t1 == exp:
            hit[mode].add(case["case_id"]); by_side[mode][side] += 1
            if len(tied) > 1:
                tie[mode] += 1
                if exp == min(tied):
                    luck[mode] += 1
        if exp in [r["id"] for r in ordered[:3]]:
            hit3[mode] += 1
        if meta[t1]["module"] == meta[exp]["module"]:
            mod_ok[mode] += 1
        if meta[t1]["version"] == meta[exp]["version"]:
            ver_ok[mode] += 1
    if sorted(rows, key=lambda r: (-r["fusion"], r["id"]))[0]["id"] != exp:
        fail.append((case["case_id"], exp, side,
                     [r["id"] for r in sorted(rows, key=lambda r: -r["fusion"])][:3]))

n = len(data["cases"])
allids = set(c["case_id"] for c in data["cases"])
print("dataset=%s cases=%d" % (os.path.basename(path), n))
print()
print("通道        Top1    Top3    模块对    版本对   平局侥幸")
for mode, _ in MODES:
    print("  %-9s %2d/%d(%.0f%%) %2d/%d(%.0f%%) %2d/%d(%.0f%%) %2d/%d(%.0f%%) %d"
          % (mode, len(hit[mode]), n, 100.0*len(hit[mode])/n, hit3[mode], n,
             100.0*hit3[mode]/n, mod_ok[mode], n, 100.0*mod_ok[mode]/n,
             ver_ok[mode], n, 100.0*ver_ok[mode]/n, luck[mode]))
print()
print("分目标模块 Top1:", {m: by_side[m] for m, _ in MODES})
a1, a2, a3, a4 = hit["A1_vec"], hit["A2_fts"], hit["A3_slot"], hit["A4_fusion"]
print()
print("互补性: 仅A1=%d 仅A2=%d 都赢=%d 都输=%d 并集=%d/%d"
      % (len(a1-a2), len(a2-a1), len(a1&a2), len(allids-a1-a2), len(a1|a2), n))
print("A4=%d  三通道全错的题=%d 其中A4救回=%d %s"
      % (len(a4), len(allids-a1-a2-a3), len(a4-a1-a2-a3), sorted(a4-a1-a2-a3)))
print("融合失败题:", fail)
