# -*- coding: utf-8 -*-
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from src.gated_mem.embeddings import FastEmbedProvider, non_negative_cosine
from src.gated_mem.gates import bm25_to_positive, calibrated_fusion, saturate_bm25
from src.gated_mem.schema import MemoryNode, MemoryType
from src.gated_mem.storage import Store
from src.gated_mem.retrieval import _fts_query

data = json.load(open(os.path.join(ROOT, "benchmarks", "data",
                                   "phase5_e3_collision_disambiguation.json"), encoding="utf-8"))
p = FastEmbedProvider()
MODES = (("A1_vec", "vec"), ("A2_fts", "fts"), ("A3_slot", "slot"), ("A4_fusion", "fusion"))
hit1 = {m: 0 for m, _ in MODES}
tie = {m: 0 for m, _ in MODES}
luck = {m: 0 for m, _ in MODES}
lexmin_by_side = {"A": 0, "B": 0}
a_always_low = 0
diffs_fts = []
for case in data["cases"]:
    mem = case["memories"]
    bymod = {}
    for m in mem:
        bymod.setdefault(m["module"], []).append(m["id"])
    # 检查 A 模块是否恒为字典序更小
    if min(bymod["A"]) < min(bymod["B"]):
        a_always_low += 1
    st = Store(":memory:")
    for m in mem:
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
    vals = [r["fts"] for r in rows]
    if max(vals) - min(vals) < 1e-12:
        diffs_fts.append(case["case_id"])
    for mode, key in MODES:
        ordered = sorted(rows, key=lambda r: (-r[key], r["id"]))
        best = ordered[0][key]
        tied = [r["id"] for r in ordered if abs(r[key] - best) < 1e-12]
        if ordered[0]["id"] == exp:
            hit1[mode] += 1
            if len(tied) > 1:
                tie[mode] += 1
                if exp == min(tied):
                    luck[mode] += 1
                    lexmin_by_side[case["target_module"]] += 1

n = len(data["cases"])
print("cases=%d" % n)
print("A 模块恒为字典序更小的题数: %d/%d" % (a_always_low, n))
print("FTS 六候选完全同分（无任何区分度）的题数: %d/%d" % (len(diffs_fts), n))
print()
for mode, _ in MODES:
    print("%-10s Top1=%2d/%d (%.2f%%)  其中平局赢=%d  字典序侥幸=%d"
          % (mode, hit1[mode], n, 100.0 * hit1[mode] / n, tie[mode], luck[mode]))
print()
print("A2 的平局侥幸命中按目标模块分布: A侧=%d  B侧=%d" % (lexmin_by_side["A"], lexmin_by_side["B"]))
print("A1 与 A4 是否同分同序: ", end="")
a1 = [sorted((r["id"] for r in [0]), key=str) for _ in ()]
print("见下")
