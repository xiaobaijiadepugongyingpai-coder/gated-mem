"""E3 · 自然语言改写集的检索层评测（零 LLM 调用）。

## 这一层在测什么

只测「**检索排序**」：给定 query，正确记忆能否进 Top-1 / Top-3。
不需要答案生成、不需要 judge —— 所以**成本为 0，且完全确定性可复现**。

## 为什么这是本方案性价比最高的一步

现有 phase4 报告的 +40pp 是「fusion vs vec」，而 fts 单通道已达 100%。
在那种「query 内嵌唯一精确标识符」的分布上，融合**不可能**超过 fts。

本脚本用 4 种查询形态做同一批 100 条记忆的检索，直接量出：
    - 有标识符时：fts 是否确实 100%
    - 去掉标识符后：fts 掉到多少，vec / fusion 各是多少

**如果 fts 在改写形态上大幅掉分而融合保持，就第一次证明了融合严格优于任何单通道。**

## 用法

    # 内置哈希向量器（零依赖，立即可跑）
    python experiments_v2/runners/e3_naturalized.py --provider builtin

    # 真实语义模型（需 conda 环境已装 fastembed）
    python experiments_v2/runners/e3_naturalized.py --provider fastembed
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

_HERE = os.path.abspath(os.path.dirname(__file__))
_EXP = os.path.abspath(os.path.join(_HERE, ".."))
for p in (_EXP, os.path.join(_EXP, "arms"), os.path.join(_EXP, "adapters")):
    if p not in sys.path:
        sys.path.insert(0, p)
_SRC = os.path.abspath(os.path.join(_EXP, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from definitions import by_name            # noqa: E402
from gated_store import GatedStore          # noqa: E402

DATA = os.path.join(_EXP, "data", "e3_naturalized.json")
RAW = os.path.abspath(os.path.join(_EXP, "..",
                                   "benchmarks/data/phase4_hard_negatives_20.json"))


def load_memories() -> dict[str, list[dict]]:
    """case_id -> 5 条候选记忆。

    已核实原始结构（benchmarks/data/phase4_hard_negatives_20.json）：
      case keys: case_id / entity_kind / expected_id / expected_top3 /
                 identifier / memories / module / query
      memories[i] keys: content / id / identifier / input_weight /
                        memory_type / predicate / step / subject / value
    注意：记忆的 ID 字段名是 **`id`**，不是 `memory_id`。
    """
    with open(RAW, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    cases = data if isinstance(data, list) else data.get("cases", [])
    out = {}
    for c in cases:
        mems = c.get("memories") or []
        out[c["case_id"]] = [
            {
                "memory_id": m.get("id") or m.get("memory_id"),
                "content": m.get("content", ""),
                "subject": m.get("subject") or c.get("module", "mod"),
                "predicate": m.get("predicate") or "p",
                "memory_type": m.get("memory_type") or "DECISION",
            }
            for m in mems
        ]
    return out


def load_rows() -> list[dict]:
    with open(DATA, "r", encoding="utf-8") as fh:
        return json.load(fh)["rows"]


def build_provider(name: str):
    """返回 provider 实例。

    已核实（src/gated_mem/retrieval.py:150）：
      向量通道只在 `q_vec is not None and node.embedding` 时计算，
      而 q_vec 只在 self.provider 非 None 时产生。
      ⇒ 不注入 provider，s_vec 恒为 0，各臂会退化成同一结果。
    """
    if name == "builtin":
        try:
            from gated_mem.embeddings import BuiltinHashEmbedder
            prov = BuiltinHashEmbedder()
            print("provider: BuiltinHashEmbedder dim=%s"
                  % getattr(prov, "dim", "?"))
            return prov
        except Exception as exc:
            print("BuiltinHashEmbedder 不可用:", exc)
            return None
    try:
        from gated_mem.embeddings import FastEmbedProvider
        prov = FastEmbedProvider()
        print("provider: FastEmbed %s dim=%s"
              % (getattr(prov, "model_id", "?"), getattr(prov, "dim", "?")))
        return prov
    except Exception as exc:
        print("FastEmbed 不可用（%s），尝试退回内置哈希器" % exc)
        try:
            from gated_mem.embeddings import BuiltinHashEmbedder
            prov = BuiltinHashEmbedder()
            print("provider: BuiltinHashEmbedder dim=%s"
                  % getattr(prov, "dim", "?"))
            return prov
        except Exception:
            return None


def eval_arm(arm_name: str, provider, rows: list[dict],
             memories: dict[str, list[dict]], topk: int = 3) -> dict:
    """按 case 分组，每个 case 建一个库（5 条候选），再跑 4 种形态。"""
    arm = by_name(arm_name)
    by_case: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_case[r["case_id"]].append(r)

    hits = defaultdict(lambda: {"t1": 0, "t3": 0, "n": 0})

    for case_id, case_rows in sorted(by_case.items()):
        mems = memories.get(case_id) or []
        if not mems:
            continue
        # 每个 case 独立建库，避免 20×5=100 条互相干扰
        with GatedStore(arm, provider=provider) as g:
            id_map = {}
            for m in mems:
                mid = g.remember(
                    content=m["content"],
                    subject=m["subject"],
                    predicate=m["predicate"],
                    scope=case_id,
                    memory_type=m.get("memory_type") or "DECISION",
                )
                id_map[m["memory_id"]] = mid

            for r in case_rows:
                form = r["form"]
                receipt = g.recall(r["query"], topk=topk)
                ids = []
                try:
                    ids = [it.memory_id for it in (receipt.injected_items or [])]
                except Exception:
                    ids = []

                expect = r.get("expected_id")
                expect_internal = id_map.get(expect)

                hits[form]["n"] += 1
                if expect_internal and ids:
                    if ids[0] == expect_internal:
                        hits[form]["t1"] += 1
                    if expect_internal in ids:
                        hits[form]["t3"] += 1
                elif expect:
                    # 退化：内容里包含答案标识符
                    text = GatedStore.receipt_text(receipt)
                    if expect in text:
                        hits[form]["t1"] += 1
                        hits[form]["t3"] += 1

    res = {}
    for form, h in hits.items():
        n = max(1, h["n"])
        res[form] = {
            "n": h["n"],
            "top1": h["t1"] / n,
            "top3": h["t3"] / n,
        }
    return res


FORM_ORDER = ["q0_original", "q1_synonym", "q2_pronoun", "q3_colloquial"]
FORM_LABEL = {
    "q0_original": "含精确标识符",
    "q1_synonym": "同义改写",
    "q2_pronoun": "指代改写",
    "q3_colloquial": "口语改写",
}


def render(results: dict) -> str:
    arms = list(results.keys())
    lines = []
    lines.append("# E3 · 自然语言改写集 · 检索层评测\n")
    lines.append("零 LLM 调用，纯检索排序，完全确定性。\n")
    lines.append("## Top-1 命中率（%d case × 4 形态）\n" % 20)
    head = "| 查询形态 | " + " | ".join(arms) + " |"
    sep = "|---" * (len(arms) + 1) + "|"
    lines.append(head)
    lines.append(sep)
    for form in FORM_ORDER:
        cells = []
        for a in arms:
            v = results[a].get(form)
            cells.append("%.1f%%" % (v["top1"] * 100) if v else "-")
        lines.append("| %s | %s |" % (FORM_LABEL.get(form, form), " | ".join(cells)))

    lines.append("\n## Top-3 命中率\n")
    lines.append(head)
    lines.append(sep)
    for form in FORM_ORDER:
        cells = []
        for a in arms:
            v = results[a].get(form)
            cells.append("%.1f%%" % (v["top3"] * 100) if v else "-")
        lines.append("| %s | %s |" % (FORM_LABEL.get(form, form), " | ".join(cells)))

    # 落差表
    lines.append("\n## 落差（含标识符 → 口语改写）\n")
    lines.append("| 臂 | q0 | q3 | 落差(pp) |")
    lines.append("|---|---:|---:|---:|")
    for a in arms:
        q0 = results[a].get("q0_original", {}).get("top1")
        q3 = results[a].get("q3_colloquial", {}).get("top1")
        if q0 is None or q3 is None:
            continue
        lines.append("| %s | %.1f%% | %.1f%% | %+.1f |"
                     % (a, q0 * 100, q3 * 100, (q3 - q0) * 100))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="builtin",
                    choices=["builtin", "fastembed"])
    ap.add_argument("--arms", default="A1_vector,A2_fts,A4_slot_fusion")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not os.path.exists(DATA):
        print("缺数据，请先运行：")
        print("  python experiments_v2/data_gen/build_naturalized.py")
        return 2

    rows = load_rows()
    memories = load_memories()
    print("查询行数:", len(rows), " case 数:", len(memories))

    provider = build_provider(args.provider)

    arm_list = [a.strip() for a in args.arms.split(",") if a.strip()]
    results = {}
    for name in arm_list:
        print("\n--- 评测 %s ---" % name)
        results[name] = eval_arm(name, provider, rows, memories)
        for form in FORM_ORDER:
            v = results[name].get(form)
            if v:
                print("  %-14s Top1 %5.1f%%  Top3 %5.1f%%  (n=%d)"
                      % (FORM_LABEL.get(form, form),
                         v["top1"] * 100, v["top3"] * 100, v["n"]))

    md = render(results)
    out_path = args.out or os.path.join(
        _EXP, "results", "e3_naturalized_%s.md" % args.provider)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(md + "\n")

    jpath = os.path.splitext(out_path)[0] + ".json"
    with open(jpath, "w", encoding="utf-8") as fh:
        json.dump({"provider": args.provider, "results": results},
                  fh, ensure_ascii=False, indent=2)

    print("\n已写出:", out_path)
    print("已写出:", jpath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
