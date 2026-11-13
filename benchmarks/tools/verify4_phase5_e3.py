# -*- coding: utf-8 -*-
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from src.gated_mem.embeddings import FastEmbedProvider, non_negative_cosine
from src.gated_mem.gates import bm25_to_positive, calibrated_fusion, saturate_bm25
from src.gated_mem.schema import MemoryNode, MemoryType
from src.gated_mem.storage import Store
from src.gated_mem.retrieval import _fts_query
data = json.load(open(os.path.join(ROOT, "benchmarks/results/_e3_frozen20.json"), encoding="utf-8"))
p = FastEmbedProvider()
MODES = (("A1_vec","vec"),("A2_fts","fts"),("A3_slot","slot"),("A4_fusion","fusion"))
hit = {m:set() for m,_ in MODES}
for case in data["cases"]:
    st = Store(":memory:")
    for m in case["memories"]:
        st.insert_memory(MemoryNode(memory_id=m["id"], content=m["content"],
            memory_type=MemoryType(m["memory_type"]), subject=m["subject"],
            predicate=m["predicate"], scope="global",
            input_weight=float(m.get("input_weight",0.5)), pinned=False,
            embedding=p.embed_one(m["content"]), embedding_model=p.model_id,
            created_step=int(m["step"]), last_cited_step=int(m["step"])))
    q=case["query"]; qv=p.embed_one(q)
    raw=dict(st.fts_search(_fts_query(q), limit=500))
    rows=[]
    for node in st.all_memories():
        sv=non_negative_cosine(qv,node.embedding)
        sf=saturate_bm25(bm25_to_positive(raw.get(node.memory_id,0.0)))
        slot=any(s and s.lower() in q.lower() for s in (node.subject,node.predicate))
        rows.append({"id":node.memory_id,"vec":sv,"fts":sf,"slot":1.0 if slot else 0.0,
                     "fusion":calibrated_fusion(sv,sf,slot)})
    st.close()
    exp=case["expected_id"]
    for mode,key in MODES:
        if sorted(rows,key=lambda r:(-r[key],r["id"]))[0]["id"]==exp:
            hit[mode].add(case["case_id"])
a1,a2,a3,a4=hit["A1_vec"],hit["A2_fts"],hit["A3_slot"],hit["A4_fusion"]
allids=set(c["case_id"] for c in data["cases"])
print("A3 命中题:", sorted(a3))
print("A1∪A2:", sorted(a1|a2))
print("A3 ⊆ (A1∪A2) ?", a3 <= (a1|a2))
print()
tri = allids - a1 - a2 - a3
print("三通道全错:", sorted(tri), "=", len(tri))
print("其中 A4 救回:", sorted(a4 - a1 - a2 - a3), "=", len(a4-a1-a2-a3))
print("A4 仍未救回:", sorted(tri - a4))
