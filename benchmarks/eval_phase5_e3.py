# -*- coding: utf-8 -*-
"""阶段五 E3：跨模块同符号碰撞与语义改写消歧评测（GM-DIRECTIVE-P5 v5.0.0 §2.2）。

四通道对照（每条通道单独排名，互不共享候选集）：
  A1 纯向量       —— FastEmbed 语义余弦（零依赖环境下退化为 BuiltinHashEmbedder 字面哈希）
  A2 纯 FTS5      —— BM25 饱和分（米氏饱和，与融合通道同一映射）
  A3 纯槽位       —— subject/predicate 是否作为子串出现在 query 中
  A4 混合融合     —— calibrated_fusion(s_vec, s_fts, slot_hit)

为什么必须显式保留 A2 独立列：
  阶段四的对照表里融合相对纯 FTS5 净增益为 +0.00pp，被质疑"何必融合"。
  E3 的设计目标就是让 A1 与 A2 都无法单独完成任务，只有 A4 能同时锁定
  {模块, 版本}。因此 A2 必须是可见的独立基线，而不是被折叠进"单通道"。

诚实性约定（本脚本的硬约束）：
  - 所有数字来自真实打分，脚本不做任何按题调参。
  - 同时报告 Top-1 与 Top-3 两个口径。Top-1 是主口径；Top-3 用于观察
    通道是否至少把正确答案排进了候选区。
  - 平局按 memory_id 升序兜底（与生产代码 rank_by_score 一致）。
    数据集已把记忆 id 中性化并随机化目标模块，避免字典序给某通道制造假性满分。

用法：
  python benchmarks/eval_phase5_e3.py
  python benchmarks/eval_phase5_e3.py --provider builtin   # 零依赖字面模式
"""
from __future__ import print_function

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from src.gated_mem.embeddings import BuiltinHashEmbedder, non_negative_cosine
from src.gated_mem.gates import bm25_to_positive, calibrated_fusion, saturate_bm25
from src.gated_mem.schema import MemoryNode, MemoryType
from src.gated_mem.storage import Store

DEFAULT_DATASET = os.path.join(ROOT, "benchmarks", "data",
                               "phase5_e3_collision_disambiguation.json")
MODES = ("A1_vec", "A2_fts", "A3_slot", "A4_fusion")


def _fts_query(query):
    """直接复用生产实现，保证评测与线上检索同源。"""
    from src.gated_mem.retrieval import _fts_query as prod_fts_query
    return prod_fts_query(query)


def build_store(case, provider):
    """把一个 case 的记忆灌进内存库，返回 store。"""
    store = Store(":memory:")
    for m in case["memories"]:
        store.insert_memory(
            MemoryNode(
                memory_id=m["id"],
                content=m["content"],
                memory_type=MemoryType(m["memory_type"]),
                subject=m["subject"],
                predicate=m["predicate"],
                scope="global",
                input_weight=float(m.get("input_weight", 0.5)),
                pinned=False,
                embedding=provider.embed_one(m["content"]),
                embedding_model=provider.model_id,
                created_step=int(m["step"]),
                last_cited_step=int(m["step"]),
            )
        )
    return store


def score_case(case, provider):
    """返回 {mode: 排序后的 memory_id 列表}。"""
    store = build_store(case, provider)
    query = case["query"]
    qv = provider.embed_one(query)

    bm25 = {}
    for mid, raw in store.fts_search(_fts_query(query), limit=500):
        bm25[mid] = saturate_bm25(bm25_to_positive(raw))

    rows = []
    for node in store.all_memories():
        sv = non_negative_cosine(qv, node.embedding) if node.embedding else 0.0
        sf = bm25.get(node.memory_id, 0.0)
        slot = any(
            s and s.lower() in query.lower()
            for s in (node.subject, node.predicate)
        )
        rows.append({
            "id": node.memory_id,
            "vec": sv,
            "fts": sf,
            "slot": 1.0 if slot else 0.0,
            "fusion": calibrated_fusion(sv, sf, slot),
        })
    store.close()

    rankings = {}
    for mode, key in zip(MODES, ("vec", "fts", "slot", "fusion")):
        # 平局按 id 升序兜底，与生产代码 rank_by_score 完全一致
        ordered = sorted(rows, key=lambda r: (-r[key], r["id"]))
        rankings[mode] = [r["id"] for r in ordered]
    return rankings, rows


def run(dataset=DEFAULT_DATASET, provider_name="fastembed", verbose=True):
    with open(dataset, "r", encoding="utf-8") as f:
        data = json.load(f)

    if provider_name == "builtin":
        provider = BuiltinHashEmbedder()
    else:
        from src.gated_mem.embeddings import FastEmbedProvider
        provider = FastEmbedProvider()

    per_case = []
    for case in data["cases"]:
        rankings, rows = score_case(case, provider)
        expected = case["expected_id"]
        rec = {
            "case_id": case["case_id"],
            "target_module": case["target_module"],
            "expected_id": expected,
            "collision_twin": case.get("collision_twin"),
            "query": case["query"],
        }
        for mode in MODES:
            rank = rankings[mode]
            rec[mode] = {
                "top1": rank[0],
                "top3": rank[:3],
                "hit1": rank[0] == expected,
                "hit3": expected in rank[:3],
            }
        per_case.append(rec)

    summary = {}
    for mode in MODES:
        n = len(per_case)
        h1 = sum(1 for r in per_case if r[mode]["hit1"])
        h3 = sum(1 for r in per_case if r[mode]["hit3"])
        summary[mode] = {
            "top1_passed": h1,
            "top3_passed": h3,
            "total": n,
            "top1_rate": round(h1 / float(n), 6) if n else 0.0,
            "top3_rate": round(h3 / float(n), 6) if n else 0.0,
        }

    # 分模块看：确认不存在"某通道只赢一半"的假象
    by_module = {}
    for mod in ("A", "B"):
        sub = [r for r in per_case if r["target_module"] == mod]
        by_module[mod] = {
            mode: {
                "top1_passed": sum(1 for r in sub if r[mode]["hit1"]),
                "total": len(sub),
            }
            for mode in MODES
        }

    singles = ("A1_vec", "A2_fts", "A3_slot")
    best_single = max(singles, key=lambda m: summary[m]["top1_rate"])
    best_rate = summary[best_single]["top1_rate"]
    fusion_rate = summary["A4_fusion"]["top1_rate"]

    out = {
        "dataset": os.path.basename(dataset),
        "provider": provider.model_id,
        "cases": len(per_case),
        "by_mode": summary,
        "by_target_module": by_module,
        "best_single_channel": best_single,
        "best_single_top1_rate": best_rate,
        "fusion_top1_rate": fusion_rate,
        "net_gain_pp": round((fusion_rate - best_rate) * 100.0, 2),
        "rows": per_case,
    }

    if verbose:
        print("=" * 84)
        print("  阶段五 E3 跨模块同符号碰撞消歧（%d 题 / provider=%s）"
              % (len(per_case), provider.model_id))
        print("=" * 84)
        print("  %-12s %8s %8s %10s %10s" % ("通道", "Top1命中", "Top3命中", "Top1率", "Top3率"))
        print("  " + "-" * 80)
        labels = {
            "A1_vec": "A1 纯向量",
            "A2_fts": "A2 纯FTS5",
            "A3_slot": "A3 纯槽位",
            "A4_fusion": "A4 混合融合",
        }
        for mode in MODES:
            s = summary[mode]
            print("  %-12s %8d %8d %9.2f%% %9.2f%%" % (
                labels[mode], s["top1_passed"], s["top3_passed"],
                s["top1_rate"] * 100, s["top3_rate"] * 100))
        print("  " + "-" * 80)
        print("  最强单通道: %s  Top1=%.2f%%" % (best_single, best_rate * 100))
        print("  融合 Top1 : %.2f%%   净增益 = %+.2fpp" % (fusion_rate * 100, out["net_gain_pp"]))
        print("  " + "-" * 80)
        for mod in ("A", "B"):
            cells = "  ".join("%s %d/%d" % (m, by_module[mod][m]["top1_passed"],
                                            by_module[mod][m]["total"]) for m in MODES)
            print("  目标模块 %s: %s" % (mod, cells))
        print("=" * 84)

    return out


def main():
    ap = argparse.ArgumentParser(description="阶段五 E3 碰撞消歧评测")
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--out", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--provider", default="fastembed", choices=["fastembed", "builtin"])
    args = ap.parse_args()
    res = run(args.dataset, provider_name=args.provider, verbose=not args.json)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
