# -*- coding: utf-8 -*-
"""核对报告里的派生数字：互补性拆分、A1 模块/版本判别率、A3 平局性质。"""
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
hit = {m: set() for m, _ in MODES}
mod_ok = {m: 0 for m, _ in MODES}
ver_ok = {m: 0 for m, _ in MODES}
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
    for mode, key in MODES:
        ordered = sorted(rows, key=lambda r: (-r[key], r["id"]))
        t1 = ordered[0]["id"]
        if t1 == exp:
            hit[mode].add(case["case_id"])
        if meta[t1]["module"] == meta[exp]["module"]:
            mod_ok[mode] += 1
        if meta[t1]["version"] == meta[exp]["version"]:
            ver_ok[mode] += 1

n = len(data["cases"])
a1, a2, a3, a4 = hit["A1_vec"], hit["A2_fts"], hit["A3_slot"], hit["A4_fusion"]
allids = set(c["case_id"] for c in data["cases"])
print("=== 互补性拆分（A1 vs A2）===")
print("  仅 A1 答对 :", len(a1 - a2), sorted(a1 - a2))
print("  仅 A2 答对 :", len(a2 - a1), sorted(a2 - a1))
print("  两者都答对 :", len(a1 & a2), sorted(a1 & a2))
print("  两者都答错 :", len(allids - a1 - a2), sorted(allids - a1 - a2))
print("  并集       :", len(a1 | a2), "/%d" % n)
print()
print("  A4 答对总数:", len(a4))
print("  A4 在『三个单通道全错』的题里救回的:", sorted(a4 - a1 - a2 - a3),
      "=", len(a4 - a1 - a2 - a3), "题")
print("  『三个单通道全错』的题总数:", sorted(allids - a1 - a2 - a3),
      "=", len(allids - a1 - a2 - a3), "题")
print()
print("=== 模块 / 版本判别率 ===")
for mode, _ in MODES:
    print("  %-10s 模块对=%2d/%d (%.0f%%)  版本对=%2d/%d (%.0f%%)"
          % (mode, mod_ok[mode], n, 100.0 * mod_ok[mode] / n,
             ver_ok[mode], n, 100.0 * ver_ok[mode] / n))
print()
print("=== A3 命中的性质 ===")
print("  A3 命中题:", sorted(a3))
print("  A3 命中是否全部落在 A1/A2 的并集里:", a3 <= (a1 | a2))
