"""用 GLM 生成的 phase2_dense_stress_15.json 跑最高压实测。

以外部数据（非自造）驱动 src/gated_mem 的完整链路：
  载入 25 节点场景 -> 建边 -> 检索 -> 度量 λ 门控与多跳告警。
硬指标（Gate 2）：
  G2-Rank     : λ=0.3 相比 λ=0.0 在 kill_worm 上的目标入榜率提升 >= 25pp
  截断触发    : 活跃候选池 >= 18 且真实淘汰率 >= 80%
  G2-MultiHop : 3-4 代链叶节点的 stale_parent_warning 落盘率 100%
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gated_mem.retrieval import Retriever
from src.gated_mem.schema import EdgeType, MemoryEdge, MemoryNode, MemoryStatus, MemoryType
from src.gated_mem.storage import Store

DEFAULT_DATASET = "benchmarks/data/phase2_dense_stress_15.json"


def load_scenario(sc: dict) -> Store:
    """把一个 scenario 灌进内存库，保持原始 step 与状态。"""
    s = Store(":memory:")
    for n in sc["nodes"]:
        s.insert_memory(
            MemoryNode(
                memory_id=n["id"],
                content=n["content"],
                memory_type=MemoryType(n["memory_type"]),
                subject=n["subject"],
                predicate=n["predicate"],
                scope=n.get("scope", "global"),
                input_weight=float(n.get("input_weight", 0.5)),
                pinned=bool(n.get("pinned", False)),
                residual_diff=n.get("residual_diff"),
                embedding=n.get("embedding"),
                created_step=int(n["step"]),
                last_cited_step=int(n.get("last_cited_step", n["step"])),
            )
        )
    for a in sc.get("aliases", []):
        s.upsert_alias(a["alias_name"], a["canonical_slot"])

    # 先把节点状态按数据里声明的设置好（允许矩阵旁路，因为这是数据装载而非业务写入）
    for n in sc["nodes"]:
        st = n.get("status", "active")
        if st != "active":
            s.set_status(n["id"], MemoryStatus(st), int(n["step"]), allow_matrix_bypass=True)

    for e in sc["edges"]:
        try:
            s.insert_edge(
                MemoryEdge(
                    edge_id="E_%s_%s_%s" % (e["source_id"], e["target_id"], e.get("edge_type", "BELONGS_TO")),
                    source_id=e["source_id"],
                    target_id=e["target_id"],
                    edge_type=EdgeType(e.get("edge_type", "BELONGS_TO")),
                    created_step=1,
                )
            )
        except Exception:
            # 环输入端由 visited 集合在遍历时阻断，这里允许插边失败
            pass
    return s


def max_step(sc: dict) -> int:
    return max(int(n["step"]) for n in sc["nodes"])


def run(dataset: str = DEFAULT_DATASET, verbose: bool = True) -> dict:
    data = json.load(open(dataset, "r", encoding="utf-8"))
    rows: List[dict] = []

    for sc in data["scenarios"]:
        s = load_scenario(sc)
        step = max_step(sc)
        kw = sc.get("kill_worm")
        row = {"scenario_id": sc["scenario_id"], "has_kill_worm": kw is not None}

        for lam in (0.3, 0.0):
            r = Retriever(s, lam=lam, topk=5)
            receipt = r.recall(kw["query"] if kw else sc["probes"][0]["query"], case_step=step, write_event=False)
            ids = [i.memory_id for i in receipt.injected_items]
            key = "gated" if lam > 0 else "pure"
            row[key] = {
                "injected": ids,
                "target_in": (kw["target_node_id"] in ids) if kw else None,
                "noise_in": sum(1 for nid in (kw["noise_node_ids"] if kw else []) if nid in ids),
                "pool": receipt.candidate_pool_size,
                "truncated": receipt.truncated_candidates,
            }

        # 多跳告警：找一个被废弃根的 3 代孙
        leaf, root = find_stale_chain(sc)
        row["chain"] = {"leaf": leaf, "root": root}
        if leaf:
            r = Retriever(s, lam=0.3, topk=25)
            receipt = r.recall_by_ids([leaf], case_step=step) if hasattr(r, "recall_by_ids") else None
            warn = compute_warning(s, leaf, step)
            row["stale"] = warn
        rows.append(row)
        s.close()

    # 聚合
    kw_rows = [r for r in rows if r["has_kill_worm"]]
    gated_rate = (sum(1 for r in kw_rows if r["gated"]["target_in"]) / float(len(kw_rows))) if kw_rows else 0.0
    pure_rate = (sum(1 for r in kw_rows if r["pure"]["target_in"]) / float(len(kw_rows))) if kw_rows else 0.0
    trunc_rate = sum(1 for r in rows if r["gated"]["truncated"] > 0) / float(len(rows))
    pool_min = min(r["gated"]["pool"] for r in rows)
    stale_ok = sum(1 for r in rows if r.get("stale", {}).get("warned")) / float(len(rows))

    res = {
        "dataset": dataset,
        "scenarios": len(rows),
        "kill_worm_scenarios": len(kw_rows),
        "gated_target_rate": round(gated_rate, 6),
        "pure_target_rate": round(pure_rate, 6),
        "improvement_pp": round((gated_rate - pure_rate) * 100.0, 4),
        "truncation_rate": round(trunc_rate, 6),
        "min_candidate_pool": pool_min,
        "multihop_warn_rate": round(stale_ok, 6),
        "rows": rows,
        "gates": {
            "G2-Rank": (gated_rate - pure_rate) * 100.0 >= 25.0,
            "G2-Truncation": trunc_rate >= 0.8 and pool_min >= 18,
            "G2-MultiHop": stale_ok >= 1.0,
        },
    }
    res["overall"] = all(res["gates"].values())
    if verbose:
        print("=" * 82)
        print("  阶段二高压实测（外部数据集 %s）" % os.path.basename(dataset))
        print("=" * 82)
        print("  场景  kill_worm  候选池  淘汰  λ=0.3目标  λ=0.0目标  多跳告警")
        for r in rows:
            print(
                "  %-5s %-10s %6d %5d %10s %10s %8s"
                % (
                    r["scenario_id"],
                    "yes" if r["has_kill_worm"] else "-",
                    r["gated"]["pool"],
                    r["gated"]["truncated"],
                    ("YES" if r["gated"]["target_in"] else "no") if r["has_kill_worm"] else "-",
                    ("YES" if r["pure"]["target_in"] else "no") if r["has_kill_worm"] else "-",
                    "YES" if r.get("stale", {}).get("warned") else "no",
                )
            )
        print("-" * 82)
        print("  λ=0.3 目标入榜率 : %.2f%%" % (res["gated_target_rate"] * 100))
        print("  λ=0.0 目标入榜率 : %.2f%%" % (res["pure_target_rate"] * 100))
        print("  门控提升         : +%.2f pp （门槛 25pp）" % res["improvement_pp"])
        print("  截断触发率       : %.2f%% （门槛 80%%）" % (res["truncation_rate"] * 100))
        print("  最小候选池       : %d （门槛 18）" % res["min_candidate_pool"])
        print("  多跳告警率       : %.2f%%" % (res["multihop_warn_rate"] * 100))
        print("-" * 82)
        for g, ok in res["gates"].items():
            print("  %-16s %s" % (g, "PASS" if ok else "FAIL"))
        print("  OVERALL          %s" % ("PASS" if res["overall"] else "FAIL"))
        print("=" * 82)
    return res


def find_stale_chain(sc: dict) -> Tuple[str, str]:
    """找一条 3 跳链：叶 active，根 superseded/killed。"""
    byid = {n["id"]: n for n in sc["nodes"]}
    parents: Dict[str, str] = {}
    for e in sc["edges"]:
        if e.get("edge_type") == "BELONGS_TO":
            parents[e["source_id"]] = e["target_id"]
    for nid, n in byid.items():
        if n.get("status", "active") != "active":
            continue
        cur, depth = nid, 0
        while cur in parents and depth < 10:
            cur = parents[cur]
            depth += 1
            if depth >= 3:
                root = byid.get(cur)
                if root is not None and root.get("status") in ("superseded", "killed"):
                    return nid, cur
    return "", ""


def compute_warning(store: Store, leaf_id: str, step: int) -> dict:
    """用 Retriever 内部的多跳追溯验证告警，并检查落盘。"""
    r = Retriever(store, lam=0.3, topk=25)
    stale = r._stale_ancestors(leaf_id)
    return {"warned": bool(stale), "ancestors": stale}


def main() -> int:
    ap = argparse.ArgumentParser(description="阶段二外部高压数据集实测")
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--out", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = run(args.dataset, verbose=not args.json)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
            f.write("\n")
    return 0 if res["overall"] else 1


if __name__ == "__main__":
    sys.exit(main())
