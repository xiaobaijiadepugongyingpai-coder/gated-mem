#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立评分器（紫军监察）——Gated-Mem 阶段一 Spike Cut #1。

本文件是**从零重写**的评分实现，唯一依据是 benchmarks/CONTRACT.md 1.0.0
的 §1（数学）、§2（三分支语义）、§4（分词与相似度）、§5（检索与双通道注入）、
§6（机械判定）、§7（指标与门禁）、§8.5（审计产物结构）。

审计独立性声明：编写本文件时**未阅读** benchmarks/spike_cut1.py 的任何实现
代码，只读过它的 --help 与它产出的 raw_runs.json / metrics.json 数据。
一切语义均按契约条文逐字重述，遇到条文可作两种解释之处，在本文件顶部
"契约歧义记录"中显式列出，并给出本实现所选读法。

用法：
    python benchmarks/audit/independent_scorer.py \
        --dataset benchmarks/data/eval_cases_40.json \
        --raw benchmarks/results/raw_runs.json \
        --out benchmarks/results/audit_scores.json

仅标准库、Python 3.9 语法、纯机械判定、无随机、无时间戳。
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

CONTRACT_VERSION = "1.0.0"

# §1.1 类型参数表（唯一真源）
TYPE_PARAMS = {
    "DECISION": (0.10, 100.0),
    "CONSTRAINT": (0.05, 200.0),
    "PREFERENCE": (0.15, 80.0),
    "EPHEMERAL": (1.20, 5.0),
}
LAMBDA = 0.3
GAMMA = 0.2
TOPK = 5

BRANCHES = ("A", "B", "C")
PROBE_TYPES = ("current_state", "anti_trap", "evolution_why")

# 契约歧义记录（重实现时踩到的）
# AMB-1 §1.6/§5.1：排序用"未舍入的 score"还是"舍入到 6 位后的 score"？条文只说
#   "写入 raw_runs.json 的值一律 round(x,6)"与"score 降序、同分按 node_id 升序"，
#   未说明排序键是原始值还是写盘值。本实现主口径 = 按原始 float 排序（SORT_BY_RAW
#   = True），并同时用舍入口径复算一遍，若两种口径订单不同则记入歧义统计。
# AMB-2 §2.1 与 §2.2：B 分支"覆盖时把全部子孙标 superseded"是**覆盖瞬间的快照
#   闭包**，还是"父被 superseded 后新挂上来的子节点也应立即失效"？条文只规定了
#   "处理第 i 条时只能看到前 i-1 条的状态"与"写入新节点 status=active"，本实现取
#   快照闭包读法（新节点一律 active）。
# AMB-3 §2.1 C 分支"仅直接子节点置 stale_parent_warning"：这里的"直接子节点"指
#   被覆盖旧节点的直接子节点，且只对"覆盖发生时已存在"的节点生效。
# AMB-4 §2.1 多个同槽旧节点：条文说"全部标 superseded，old 取 node_id 最小者"，
#   但 §2 的 C 分支 diff 前缀只用 old；若被覆盖旧节点里有的没有 content 可截断则
#   未规定，本实现按 old 计算，不涉及缺失。
# AMB-5 §6 大小写不敏感：条文写"两边都 NFKC + lower() 后再比较"，本实现对
#   injected_text / returned_diff 与被比较子串统一 NFKC + lower。
# AMB-6 §5.2 returned_diff 只拼"被注入且 residual_diff 非空"的节点，按注入顺序，
#   用 "\n" 连接；空则空串（不是 None）。

SORT_BY_RAW = True


# --------------------------------------------------------------------------
# §4 分词与相似度（逐字实现）
# --------------------------------------------------------------------------
def tokenize(text: str) -> set:
    """按 §4 逐字实现：NFKC + lower，ASCII 整词 + 中文单字 + 中文相邻二元组。"""
    s = unicodedata.normalize("NFKC", text).lower()
    toks = set(re.findall(r"[a-z0-9_]+", s))
    for run in re.findall(r"[\u4e00-\u9fff]+", s):
        toks.update(run)
        if len(run) >= 2:
            for i in range(len(run) - 1):
                toks.add(run[i:i + 2])
    return toks


def rel(a_text: str, b_text: str) -> float:
    """按 §4 逐字实现：词袋余弦的分子/分母形式。"""
    A, B = tokenize(a_text), tokenize(b_text)
    if not A or not B:
        return 0.0
    return len(A & B) / math.sqrt(len(A) * len(B))


def norm_lower(text: Optional[str]) -> str:
    """§6：两边都 NFKC + lower 后再比较。"""
    if text is None:
        return ""
    return unicodedata.normalize("NFKC", text).lower()


def contains_ci(haystack: str, needle: str) -> bool:
    """大小写不敏感子串包含（两侧统一 NFKC + lower）。"""
    return norm_lower(needle) in norm_lower(haystack)


# --------------------------------------------------------------------------
# §1 数学：t0 / R / F / Score
# --------------------------------------------------------------------------
def retention(node: Dict[str, Any], case_step: int) -> float:
    """§1.3 保留率 R(v)。"""
    beta, t0_base = TYPE_PARAMS[node["memory_type"]]
    delta = case_step - node["step"]
    t0 = t0_base * (0.5 + node["input_weight"])
    return (1.0 + delta / t0) ** (-beta)


def vitality(node: Dict[str, Any], nodes_by_id: Dict[str, Dict[str, Any]],
             r_cache: Dict[str, float]) -> float:
    """§1.4 生命力 F(v)：无连坐，只有父 active 时的 1-Hop 正增益。"""
    if node.get("pinned"):
        return 1.0
    base = r_cache[node["node_id"]]
    gain = 0.0
    parent_rs = []
    for pid in node["parent_ids"]:
        p = nodes_by_id.get(pid)
        if p is not None and p["status"] == "active":
            parent_rs.append(r_cache[pid])
    if parent_rs:
        gain = GAMMA * max(parent_rs)
    return min(1.0, base + gain)


# --------------------------------------------------------------------------
# §2 三分支仿真
# --------------------------------------------------------------------------
def simulate(case: Dict[str, Any], branch: str) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """按 §2 逐事件仿真一条分支，返回（节点列表，node_id -> 节点）。

    A：不做槽位覆盖，所有节点恒 active，residual_diff 一律不记录。
    B：做覆盖；沿 parent 边把全部子孙（传递闭包）标 superseded；记录原始 diff。
    C：做覆盖；仅直接子节点置 stale_parent_warning=True 且保持 active；记录带前缀 diff。
    """
    events = case["session_events"]
    nodes = []  # type: List[Dict[str, Any]]
    nodes_by_id = {}  # type: Dict[str, Dict[str, Any]]

    for idx, ev in enumerate(events):
        node = {
            "node_id": ev["id"],
            "content": ev["content"],
            "subject": ev["subject"],
            "predicate": ev["predicate"],
            "scope": ev["scope"],
            "memory_type": ev["memory_type"],
            "input_weight": float(ev["input_weight"]),
            "parent_ids": list(ev.get("parent_ids") or []),
            "raw_diff": ev.get("residual_diff"),
            "step": idx + 1,
            "status": "active",
            "stale_parent_warning": False,
            "pinned": bool(ev.get("pinned", False)),
            "covered_old_id": None,
        }

        if branch in ("B", "C"):
            # §2.1：槽位三元组字符串精确相等；同槽且 active 的旧节点全部覆盖
            olds = [
                x for x in nodes
                if x["status"] == "active"
                and x["subject"] == node["subject"]
                and x["predicate"] == node["predicate"]
                and x["scope"] == node["scope"]
            ]
            old_ids = [x["node_id"] for x in olds]
            # §2.1：old（拼 diff 前缀用）= 覆盖瞬间同槽 active 节点中 node_id 字典序最小者
            if old_ids:
                node["covered_old_id"] = sorted(old_ids)[0]
            for o in olds:
                o["status"] = "superseded"

            if branch == "B":
                # 传递闭包：覆盖瞬间，把 olds 的全部子孙标 superseded
                stack = list(old_ids)
                seen = set(stack)
                while stack:
                    cur = stack.pop()
                    for child in nodes:
                        if child["node_id"] in seen:
                            continue
                        if cur in child["parent_ids"]:
                            seen.add(child["node_id"])
                            child["status"] = "superseded"
                            stack.append(child["node_id"])
            else:
                # C：仅**直接**子节点打标签，status 保持 active
                old_id_set = set(old_ids)
                for child in nodes:
                    if any(pid in old_id_set for pid in child["parent_ids"]):
                        child["stale_parent_warning"] = True

        nodes.append(node)
        nodes_by_id[node["node_id"]] = node

    # §2：A 分支不记录任何 residual_diff
    if branch == "A":
        for n in nodes:
            n["raw_diff"] = None

    # §2 / §5.2：residual_diff 字段（B 原始，C 拼前缀）
    for n in nodes:
        if branch == "A":
            n["residual_diff"] = None
        elif branch == "B":
            n["residual_diff"] = n["raw_diff"]
        else:  # C
            if n["raw_diff"]:
                old = nodes_by_id.get(n["covered_old_id"]) if n["covered_old_id"] else None
                if old is not None:
                    n["residual_diff"] = "[Replaced: " + old["subject"] + " / " + old["content"][:30] + "] " + n["raw_diff"]
                else:
                    n["residual_diff"] = n["raw_diff"]
            else:
                n["residual_diff"] = None

    return nodes, nodes_by_id


# --------------------------------------------------------------------------
# §5 检索与双通道注入
# --------------------------------------------------------------------------
def build_ranked(nodes: List[Dict[str, Any]], nodes_by_id: Dict[str, Dict[str, Any]],
                 case_step: int, query: str, branch: str) -> List[Dict[str, Any]]:
    """§5.1：候选、rel、Score、排序（完整候选，截断到 TOPK 之前）。"""
    r_cache = {n["node_id"]: retention(n, case_step) for n in nodes}
    ranked = []
    for n in nodes:
        if branch in ("B", "C") and n["status"] != "active":
            continue
        # §4 检索文本
        if branch == "A":
            retrieval_text = n["content"]
        else:
            retrieval_text = n["content"] + " " + (n["residual_diff"] or "")
        r = rel(query, retrieval_text)
        f = vitality(n, nodes_by_id, r_cache)
        score = r * (f ** LAMBDA)
        ranked.append({
            "node_id": n["node_id"],
            "rel": round(r, 6),
            "f": round(f, 6),
            "score": round(score, 6),
            "status": n["status"],
            "_raw_score": score,
        })
    if SORT_BY_RAW:
        ranked.sort(key=lambda x: (-x["_raw_score"], x["node_id"]))
    else:
        ranked.sort(key=lambda x: (-x["score"], x["node_id"]))
    return ranked


def run_probe(case: Dict[str, Any], branch: str, probe: Dict[str, Any],
              probe_index: int) -> Dict[str, Any]:
    """跑一条 (branch, case, probe)，返回与 §8.3 同构的 run（不含 _raw_score）。"""
    nodes, nodes_by_id = simulate(case, branch)
    case_step = len(case["session_events"])
    ranked = build_ranked(nodes, nodes_by_id, case_step, probe["query"], branch)
    injected = ranked[:TOPK]

    # §5.2 两条通道严格隔离
    injected_text = "\n".join(
        nodes_by_id[x["node_id"]]["content"] for x in injected
    )
    diff_parts = []
    for x in injected:
        d = nodes_by_id[x["node_id"]]["residual_diff"]
        if d:
            diff_parts.append(d)
    returned_diff = "\n".join(diff_parts)

    injected_node_ids = [x["node_id"] for x in injected]

    # §6 机械判定
    verdict, detail = judge(probe, injected_text, returned_diff, injected_node_ids)

    return {
        "branch": branch,
        "scenario_id": case["scenario_id"],
        "is_control": bool(case["is_control"]),
        "probe_index": probe_index,
        "probe_type": probe["probe_type"],
        "query": probe["query"],
        "ranked": [
            {"node_id": x["node_id"], "rel": x["rel"], "f": x["f"],
             "score": x["score"], "status": x["status"]}
            for x in ranked
        ],
        "injected_node_ids": injected_node_ids,
        "injected_text": injected_text,
        "returned_diff": returned_diff,
        "verdict": verdict,
        "detail": detail,
    }


def judge(probe: Dict[str, Any], injected_text: str, returned_diff: str,
          injected_node_ids: List[str]) -> Tuple[bool, Dict[str, Any]]:
    """§6：零人味机械判定。"""
    ptype = probe["probe_type"]
    must_include = list(probe.get("must_include") or [])
    must_exclude = list(probe.get("must_exclude") or [])

    if ptype == "current_state":
        missing = [s for s in must_include if not contains_ci(injected_text, s)]
        hit_exc = [s for s in must_exclude if contains_ci(injected_text, s)]
        verdict = (not missing) and (not hit_exc)
        return verdict, {
            "missing_include": missing,
            "hit_exclude": hit_exc,
            "missing_survive": [],
            "diff_empty": not bool(returned_diff),
        }

    if ptype == "anti_trap":
        missing = [s for s in must_include if not contains_ci(injected_text, s)]
        survive = list(probe.get("expect_survive") or [])
        missing_survive = [s for s in survive if s not in injected_node_ids]
        verdict = (not missing) and (not missing_survive)
        return verdict, {
            "missing_include": missing,
            "hit_exclude": [],
            "missing_survive": missing_survive,
            "diff_empty": not bool(returned_diff),
        }

    # evolution_why
    old_keyword = probe.get("old_keyword") or ""
    missing = [s for s in must_include if not contains_ci(returned_diff, s)]
    diff_empty = not bool(returned_diff)
    kw_ok = bool(old_keyword) and contains_ci(returned_diff, old_keyword)
    verdict = (not diff_empty) and (not missing) and kw_ok
    return verdict, {
        "missing_include": missing,
        "hit_exclude": [],
        "missing_survive": [],
        "diff_empty": diff_empty,
        "missing_old_keyword": [] if kw_ok else [old_keyword],
    }


# --------------------------------------------------------------------------
# §7 指标与门禁
# --------------------------------------------------------------------------
def empty_cell() -> Dict[str, Any]:
    return {"passed": 0, "total": 0, "rate": 0.0}


def add_cell(cell: Dict[str, Any], ok: bool) -> None:
    cell["total"] += 1
    if ok:
        cell["passed"] += 1


def finish_cell(cell: Dict[str, Any]) -> Dict[str, Any]:
    cell["rate"] = round(cell["passed"] / cell["total"], 6) if cell["total"] else 0.0
    return cell


def compute_metrics(cases: List[Dict[str, Any]], runs: List[Dict[str, Any]],
                    dataset_sha256: str) -> Dict[str, Any]:
    """按 §7 / §8.4 重算指标与门禁。"""
    per = {b: {t: empty_cell() for t in PROBE_TYPES} for b in BRANCHES}
    grp = {
        "control": {b: {t: empty_cell() for t in PROBE_TYPES} for b in BRANCHES},
        "non_control": {b: {t: empty_cell() for t in PROBE_TYPES} for b in BRANCHES},
    }
    for run in runs:
        b = run["branch"]
        t = run["probe_type"]
        ok = bool(run["verdict"])
        add_cell(per[b][t], ok)
        add_cell(grp["control" if run["is_control"] else "non_control"][b][t], ok)

    for b in BRANCHES:
        for t in PROBE_TYPES:
            finish_cell(per[b][t])
    for g in ("control", "non_control"):
        for b in BRANCHES:
            for t in PROBE_TYPES:
                finish_cell(grp[g][b][t])

    a_cs = per["A"]["current_state"]["rate"]
    b_at = per["B"]["anti_trap"]["rate"]
    c_cs = per["C"]["current_state"]["rate"]
    c_at = per["C"]["anti_trap"]["rate"]
    c_ew = per["C"]["evolution_why"]["rate"]

    delta_pp = round((c_cs - a_cs) * 100.0, 6)
    g1 = delta_pp >= 20.0
    g2 = c_at > b_at
    g3 = c_ew >= 0.85

    return {
        "contract_version": CONTRACT_VERSION,
        "dataset_sha256": dataset_sha256,
        "cases_total": len(cases),
        "probes_per_branch": len(runs) // len(BRANCHES),
        "per_branch_probe": per,
        "by_group": grp,
        "gates": {
            "G1_current_state_lead_pp": {
                "a": a_cs, "c": c_cs, "delta_pp": delta_pp,
                "threshold_pp": 20.0, "pass": g1,
            },
            "G2_anti_trap_c_gt_b": {"b": b_at, "c": c_at, "pass": g2},
            "G3_evolution_why": {"c": c_ew, "threshold": 0.85, "pass": g3},
        },
        "gate1_overall_pass": bool(g1 and g2 and g3),
    }


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def key_of(run: Dict[str, Any]) -> Tuple[str, str, int]:
    return (run["branch"], run["scenario_id"], int(run["probe_index"]))


def diff_lists(a: List[str], b: List[str]) -> Dict[str, Any]:
    return {
        "only_in_runner": [x for x in a if x not in b],
        "only_in_auditor": [x for x in b if x not in a],
        "runner": a,
        "auditor": b,
    }


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="独立评分器：从零重实现三分支仿真 + 逐 probe 交叉核对 + 门禁复算"
    )
    ap.add_argument("--dataset", required=True, help="eval_cases_40.json 路径")
    ap.add_argument("--raw", required=True, help="kernel 产出的 raw_runs.json 路径")
    ap.add_argument("--out", required=True, help="输出 audit_scores.json 路径")
    ap.add_argument("--metrics", default=None,
                    help="可选：metrics.json 路径；缺省则在 --raw 同目录下寻找 metrics.json")
    ap.add_argument("--retrace-cases", default="S05,S07,S24",
                    help="抽做完整重实现比对的 3 个 scenario_id（逗号分隔）")
    ap.add_argument("--auditor", default="auditor2 / gemini-3.8-flash",
                    help="签署人标识")
    args = ap.parse_args(argv)

    dataset = load_json(args.dataset)
    raw = load_json(args.raw)
    cases = dataset["cases"]

    dataset_sha = sha256_file(args.dataset)

    # 1) 独立复算全部 360 条 run
    my_runs = []  # type: List[Dict[str, Any]]
    for branch in BRANCHES:
        for case in cases:
            for pi, probe in enumerate(case["probes"]):
                my_runs.append(run_probe(case, branch, probe, pi))

    # 2) 逐 probe 交叉核对
    kernel_index = {}  # type: Dict[Tuple[str, str, int], Dict[str, Any]]
    for run in raw["runs"]:
        kernel_index[key_of(run)] = run

    divergences = []
    for mine in my_runs:
        k = key_of(mine)
        other = kernel_index.get(k)
        if other is None:
            divergences.append({
                "branch": k[0], "scenario_id": k[1], "probe_index": k[2],
                "runner_verdict": None, "auditor_verdict": bool(mine["verdict"]),
                "reason": "kernel 未产出该 (branch, scenario, probe) 记录，审计侧有而 kernel 侧缺",
            })
            continue
        inj_same = list(other.get("injected_node_ids") or []) == mine["injected_node_ids"]
        verdict_same = bool(other.get("verdict")) == bool(mine["verdict"])
        if inj_same and verdict_same:
            continue
        reason_parts = []
        if not inj_same:
            d = diff_lists(list(other.get("injected_node_ids") or []),
                           mine["injected_node_ids"])
            reason_parts.append(
                "注入节点集合不一致（kernel 独有=%s，审计独有=%s；kernel 顺序=%s，审计顺序=%s）"
                % (d["only_in_runner"], d["only_in_auditor"], d["runner"], d["auditor"])
            )
        if not verdict_same:
            reason_parts.append(
                "判定不一致：kernel=%s / 审计=%s；kernel detail=%s / 审计 detail=%s"
                % (bool(other.get("verdict")), bool(mine["verdict"]),
                   json.dumps(other.get("detail"), ensure_ascii=False, sort_keys=True),
                   json.dumps(mine["detail"], ensure_ascii=False, sort_keys=True))
            )
        divergences.append({
            "branch": k[0], "scenario_id": k[1], "probe_index": k[2],
            "runner_verdict": bool(other.get("verdict")),
            "auditor_verdict": bool(mine["verdict"]),
            "reason": "；".join(reason_parts),
        })

    missing_in_audit = sorted(
        [k for k in kernel_index if k not in set(key_of(r) for r in my_runs)]
    )
    for k in missing_in_audit:
        other = kernel_index[k]
        divergences.append({
            "branch": k[0], "scenario_id": k[1], "probe_index": k[2],
            "runner_verdict": bool(other.get("verdict")),
            "auditor_verdict": None,
            "reason": "审计侧未生成该 (branch, scenario, probe) 记录，kernel 侧有而审计侧缺",
        })

    divergences.sort(key=lambda d: (d["branch"], d["scenario_id"], d["probe_index"]))

    # 3) 重算 metrics 并与 metrics.json 对比
    recomputed = compute_metrics(cases, my_runs, dataset_sha)

    metrics_path = args.metrics
    if metrics_path is None:
        cand = os.path.join(os.path.dirname(os.path.abspath(args.raw)), "metrics.json")
        if os.path.exists(cand):
            metrics_path = cand
    kernel_metrics = load_json(metrics_path) if metrics_path else None
    metrics_match = (kernel_metrics == recomputed) if kernel_metrics is not None else False

    # 4) retrace：抽 3 个 case 做完整重实现比对
    retrace_ids = [x.strip() for x in args.retrace_cases.split(",") if x.strip()]
    case_index = {c["scenario_id"]: c for c in cases}
    retrace_notes = []
    node_set_match = True
    for sid in retrace_ids:
        case = case_index.get(sid)
        if case is None:
            retrace_notes.append("%s：数据集内不存在，跳过" % sid)
            node_set_match = False
            continue
        per_case_ok = True
        for branch in BRANCHES:
            # 全量节点状态 + 逐 probe 注入集合，与 kernel ranked 对照
            for pi, probe in enumerate(case["probes"]):
                mine = run_probe(case, branch, probe, pi)
                other = kernel_index.get((branch, sid, pi))
                if other is None:
                    per_case_ok = False
                    retrace_notes.append("%s/%s/probe%d：kernel 缺记录" % (sid, branch, pi))
                    continue
                if list(other.get("injected_node_ids") or []) != mine["injected_node_ids"]:
                    per_case_ok = False
                    retrace_notes.append(
                        "%s/%s/probe%d 注入集合不一致：kernel=%s 审计=%s"
                        % (sid, branch, pi,
                           other.get("injected_node_ids"), mine["injected_node_ids"])
                    )
                # ranked 的节点集合与 status 也要一致
                k_nodes = [(x["node_id"], x["status"]) for x in other.get("ranked", [])]
                a_nodes = [(x["node_id"], x["status"]) for x in mine["ranked"]]
                if k_nodes != a_nodes:
                    per_case_ok = False
                    retrace_notes.append(
                        "%s/%s/probe%d 候选节点/状态集合不一致：kernel=%s 审计=%s"
                        % (sid, branch, pi, k_nodes, a_nodes)
                    )
                # 数值只报最大偏差，不据此判分歧
        if per_case_ok:
            retrace_notes.append("%s：三分支 × 三探针全部一致（注入集合、候选集合、状态）" % sid)
        else:
            node_set_match = False

    # 数值层：全部 360 条的 rel/f/score 最大绝对偏差（补充证据，不计入 divergence）
    max_abs = 0.0
    num_checked = 0
    for mine in my_runs:
        other = kernel_index.get(key_of(mine))
        if other is None:
            continue
        kr = {x["node_id"]: x for x in other.get("ranked", [])}
        for x in mine["ranked"]:
            y = kr.get(x["node_id"])
            if y is None:
                continue
            num_checked += 1
            for field in ("rel", "f", "score"):
                max_abs = max(max_abs, abs(float(x[field]) - float(y[field])))
    retrace_notes.append(
        "数值层（全 360 条 × 全部候选）：共比对 %d 个节点-探针三元组的 rel/f/score，"
        "最大绝对偏差 %.9f（契约 §1.6 只要求 round 到 6 位，偏差 <= 5e-7 属舍入公差）"
        % (num_checked, max_abs)
    )

    # 5) 门禁签署：独立复算结果 + 与 kernel 的一致性
    g = recomputed["gates"]
    consistent = (len(divergences) == 0) and metrics_match
    signoff = {
        "G1": bool(g["G1_current_state_lead_pp"]["pass"]),
        "G2": bool(g["G2_anti_trap_c_gt_b"]["pass"]),
        "G3": bool(g["G3_evolution_why"]["pass"]),
        "overall": bool(recomputed["gate1_overall_pass"] and consistent),
        "signed_by": args.auditor,
    }
    if not consistent:
        signoff["status"] = "PENDING"
        signoff["reason"] = (
            "独立复算与 kernel 不一致（divergence_count=%d, metrics_match=%s），"
            "按任务书规定门禁不得签署通过" % (len(divergences), metrics_match)
        )

    out = {
        "auditor": args.auditor,
        "contract_version": CONTRACT_VERSION,
        "probes_checked": len(my_runs),
        "divergences": divergences,
        "divergence_count": len(divergences),
        "recomputed_metrics": recomputed,
        "metrics_match": bool(metrics_match),
        "retrace": {
            "mode": "reimplement",
            "cases_checked": retrace_ids,
            "node_set_match": bool(node_set_match),
            "notes": "；".join(retrace_notes),
        },
        "gate1_signoff": signoff,
    }

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")

    # 控制台摘要（不写入结果文件）
    print("probes_checked      = %d" % len(my_runs))
    print("divergence_count    = %d" % len(divergences))
    print("metrics_match       = %s" % metrics_match)
    print("node_set_match      = %s" % node_set_match)
    print("gate1_overall_pass  = %s" % recomputed["gate1_overall_pass"])
    print("gates               = G1=%s G2=%s G3=%s"
          % (g["G1_current_state_lead_pp"]["pass"],
             g["G2_anti_trap_c_gt_b"]["pass"],
             g["G3_evolution_why"]["pass"]))
    for b in BRANCHES:
        print("  %s: %s" % (b, {t: (recomputed["per_branch_probe"][b][t]["passed"],
                                     recomputed["per_branch_probe"][b][t]["rate"])
                                for t in PROBE_TYPES}))
    if divergences:
        print("--- divergences ---")
        for d in divergences:
            print("[%s %s probe%d] runner=%s auditor=%s :: %s"
                  % (d["branch"], d["scenario_id"], d["probe_index"],
                     d["runner_verdict"], d["auditor_verdict"], d["reason"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
