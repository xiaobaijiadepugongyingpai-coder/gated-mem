"""阶段三混合检索评测（Gate 3 第 1 项）。

对比三种通道在 GLM 生成的 20 组 E2E 集上的 Top-3 命中率：
  1. 单独 FTS/BM25
  2. 单独向量
  3. 有界校准融合（P3 §3.1）

门禁：融合 Top-3 命中率 >= 90%，且严格高于两个单通道。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gated_mem.embeddings import BuiltinHashEmbedder, non_negative_cosine
from src.gated_mem.gates import (
    bm25_to_positive,
    calibrated_fusion,
    saturate_bm25,
)
from src.gated_mem.schema import MemoryNode, MemoryType, tokenize
from src.gated_mem.storage import Store

DEFAULT_DATASET = "benchmarks/data/phase3_hybrid_e2e_20.json"
TOPK = 3


def load_case(store: Store, case: Dict[str, Any], provider) -> None:
    """把一个 case 的记忆灌进 store。"""
    for m in case["memories"]:
        store.insert_memory(
            MemoryNode(
                memory_id=m["id"],
                content=m["content"],
                memory_type=MemoryType(m["memory_type"]),
                subject=m["subject"],
                predicate=m["predicate"],
                scope=m.get("scope", "global"),
                input_weight=float(m.get("input_weight", 0.5)),
                pinned=bool(m.get("pinned", False)),
                residual_diff=m.get("residual_diff"),
                embedding=provider.embed_one(m["content"]),
                embedding_model=provider.model_id,
                created_step=int(m["step"]),
                last_cited_step=int(m.get("last_cited_step", m["step"])),
            )
        )


def score_case(store: Store, case: Dict[str, Any], provider, mode: str) -> List[str]:
    """按指定通道给候选打分，返回 Top-3 的 memory_id。

    mode: "fts" | "vec" | "fusion"
    """
    query = case["query"]
    qv = provider.embed_one(query)

    # FTS 通道
    from src.gated_mem.retrieval import _fts_query

    bm25 = {}
    for mid, raw in store.fts_search(_fts_query(query), limit=500):
        bm25[mid] = saturate_bm25(bm25_to_positive(raw))

    scored: List[Tuple[str, float]] = []
    for node in store.all_memories():
        if node.status.value != "active":
            continue
        sf = bm25.get(node.memory_id, 0.0)
        sv = non_negative_cosine(qv, node.embedding) if node.embedding else 0.0
        if mode == "fts":
            s = sf
        elif mode == "vec":
            s = sv
        else:
            slot_hit = _slot_hit(query, node)
            s = calibrated_fusion(sv, sf, slot_hit)
        scored.append((node.memory_id, s))

    scored.sort(key=lambda x: (-x[1], x[0]))
    return [mid for mid, _s in scored[:TOPK]]


def _slot_hit(query: str, node) -> bool:
    q = query.lower()
    for slot in (node.subject, node.predicate):
        if slot and slot.lower() in q:
            return True
    return False


def run(dataset: str = DEFAULT_DATASET, verbose: bool = True,
        provider_name: str = "builtin") -> Dict[str, Any]:
    """跑全部 case，返回三通道对比结果。

    provider_name: "builtin"（零依赖回退）| "fastembed"（本地 ONNX 语义模型）
    """
    data = json.load(open(dataset, "r", encoding="utf-8"))
    if provider_name == "fastembed":
        from src.gated_mem.embeddings import FastEmbedProvider

        provider = FastEmbedProvider()
    else:
        provider = BuiltinHashEmbedder()

    results: Dict[str, List[bool]] = {"fts": [], "vec": [], "fusion": []}
    rows: List[Dict[str, Any]] = []

    for case in data["cases"]:
        store = Store(":memory:")
        load_case(store, case, provider)
        expected = set(case["expected_top3"])
        row = {"case_id": case["case_id"], "category": case["category"]}
        for mode in ("fts", "vec", "fusion"):
            top3 = score_case(store, case, provider, mode)
            hit = bool(expected & set(top3))
            results[mode].append(hit)
            row[mode] = {"top3": top3, "hit": hit}
        rows.append(row)
        store.close()

    summary = {}
    for mode, hits in results.items():
        n = len(hits)
        summary[mode] = {
            "passed": sum(1 for h in hits if h),
            "total": n,
            "rate": round(sum(1 for h in hits if h) / float(n), 6) if n else 0.0,
        }

    # 分组（lexical / semantic）
    by_cat: Dict[str, Dict[str, Any]] = {}
    for cat in ("lexical", "semantic"):
        cat_rows = [r for r in rows if r["category"] == cat]
        by_cat[cat] = {
            mode: {
                "passed": sum(1 for r in cat_rows if r[mode]["hit"]),
                "total": len(cat_rows),
            }
            for mode in ("fts", "vec", "fusion")
        }

    out = {
        "dataset": dataset,
        "topk": TOPK,
        "cases": len(rows),
        "by_mode": summary,
        "by_category": by_cat,
        "rows": rows,
        "gates": {
            "G3-Hybrid": (
                summary["fusion"]["rate"] >= 0.90
                and summary["fusion"]["rate"] > summary["fts"]["rate"]
                and summary["fusion"]["rate"] > summary["vec"]["rate"]
            )
        },
    }
    out["overall"] = all(out["gates"].values())

    if verbose:
        print("=" * 78)
        print("  阶段三混合检索评测（%d 组 / Top-%d）" % (len(rows), TOPK))
        print("=" * 78)
        print("  通道         命中    总数    命中率")
        for mode in ("fts", "vec", "fusion"):
            s = summary[mode]
            print("  %-10s %6d %7d %9.2f%%" % (mode.upper(), s["passed"], s["total"], s["rate"] * 100))
        print("-" * 78)
        for cat, d in by_cat.items():
            print("  [%s]" % cat)
            for mode in ("fts", "vec", "fusion"):
                print("      %-8s %d/%d" % (mode, d[mode]["passed"], d[mode]["total"]))
        print("-" * 78)
        for g, ok in out["gates"].items():
            print("  %-14s %s" % (g, "PASS" if ok else "FAIL"))
        print("  OVERALL        %s" % ("PASS" if out["overall"] else "FAIL"))
        print("=" * 78)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="阶段三混合检索评测")
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--out", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--provider", default="builtin", choices=["builtin", "fastembed"])
    args = ap.parse_args()
    res = run(args.dataset, verbose=not args.json, provider_name=args.provider)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
            f.write("\n")
    return 0 if res["overall"] else 1


if __name__ == "__main__":
    sys.exit(main())
