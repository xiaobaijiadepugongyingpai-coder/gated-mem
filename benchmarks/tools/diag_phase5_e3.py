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
print("cases=%d" % len(data["cases"]))
for cid in ("E301", "E302", "E305"):
    case = next(c for c in data["cases"] if c["case_id"] == cid)
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
    fq = _fts_query(q)
    raw = st.fts_search(fq, limit=500)
    print()
    print("=== %s  expected=%s (%s)" % (cid, case["expected_id"], case.get("target_module")))
    print("   query :", q)
    print("   fts_q :", fq[:120])
    print("   fts raw hits:", [(mid, round(r, 6)) for mid, r in raw])
    for node in st.all_memories():
        sv = non_negative_cosine(qv, node.embedding)
        sf = saturate_bm25(bm25_to_positive(dict(raw).get(node.memory_id, 0.0)))
        slot = any(s and s.lower() in q.lower() for s in (node.subject, node.predicate))
        print("     %s ver=%-9s vec=%.4f fts=%.8f slot=%d fusion=%.4f"
              % (node.memory_id, node.content[10:20], sv, sf, slot,
                 calibrated_fusion(sv, sf, slot)))
    st.close()
