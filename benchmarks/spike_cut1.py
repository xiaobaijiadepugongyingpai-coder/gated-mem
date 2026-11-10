#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gated-Mem 阶段一 · Spike Cut #1 三分支仿真运行器 + 自检。

唯一真源：benchmarks/CONTRACT.md v1.0.0。
- 纯标准库，Python 3.9 语法（无 match 语句，无运行期 X | Y 联合类型标注）。
- 三分支：A 纯向量基线（不做槽位覆盖）/ B v2.0 强连坐对照组（传递闭包）/
  C v2.1.1 终审机制（仅直接子节点打 stale_parent_warning，孙辈不受影响）。
- 确定性硬约束（§9）：不用 random / time / os.environ 影响输出；
  任何 set 迭代前必须 sorted()；JSON 落盘统一 indent=2 + 结尾换行。
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import unicodedata

CONTRACT_VERSION = "1.0.0"

# ---------------------------------------------------------------- §1 数学常数

# §1.1 类型参数表（唯一真源，禁止改动）
TYPE_PARAMS = {
    "DECISION": {"beta": 0.10, "t0_base": 100.0},
    "CONSTRAINT": {"beta": 0.05, "t0_base": 200.0},
    "PREFERENCE": {"beta": 0.15, "t0_base": 80.0},
    "EPHEMERAL": {"beta": 1.20, "t0_base": 5.0},
}

LAMBDA = 0.3      # §1.1 得分指数
GAMMA = 0.2       # §1.1 父节点 1-Hop 正增益系数
TOPK = 5          # §5.1 注入条数

BRANCHES = ["A", "B", "C"]
PROBE_TYPES = ["current_state", "anti_trap", "evolution_why"]
MEMORY_TYPES = ["DECISION", "CONSTRAINT", "PREFERENCE", "EPHEMERAL"]


def round6(x):
    """§1.6 数值输出约定：一律 round(x, 6)。"""
    return round(float(x), 6)


def t0_of(memory_type, input_weight):
    """§1.3 t0(v) = t0_base * (0.5 + input_weight)。"""
    p = TYPE_PARAMS[memory_type]
    return p["t0_base"] * (0.5 + float(input_weight))


def retention(memory_type, input_weight, delta):
    """§1.3 R(v) = (1 + Delta / t0) ** (-beta)。"""
    p = TYPE_PARAMS[memory_type]
    t0 = t0_of(memory_type, input_weight)
    return (1.0 + float(delta) / t0) ** (-p["beta"])


# ---------------------------------------------------------------- §4 分词与相似度

def tokenize(text):
    """§4 分词器：NFKC + lower；ASCII 整词；中文片段取全部单字 + 全部相邻二元组。"""
    s = unicodedata.normalize("NFKC", text).lower()
    toks = set()
    for word in re.findall(r"[a-z0-9_]+", s):      # ASCII 整词，不做词干化
        toks.add(word)
    for run in re.findall(r"[\u4e00-\u9fff]+", s):  # 连续中文片段
        for ch in run:
            toks.add(ch)                            # 全部单字
        for i in range(len(run) - 1):
            toks.add(run[i:i + 2])                  # 全部相邻二元组
    return toks


def rel(a_text, b_text):
    """§4 rel = |A ∩ B| / sqrt(|A| * |B|)，空集返回 0.0。"""
    A = tokenize(a_text)
    B = tokenize(b_text)
    if not A or not B:
        return 0.0
    return len(A & B) / math.sqrt(len(A) * len(B))


def nfkc_lower(text):
    """§6 判定比较前：两边都 NFKC + lower。"""
    return unicodedata.normalize("NFKC", text).lower()


# ---------------------------------------------------------------- 节点

class Node(object):
    """一条入库记忆节点（仿真状态）。"""

    __slots__ = (
        "node_id", "content", "subject", "predicate", "scope",
        "memory_type", "input_weight", "step", "parent_ids",
        "residual_diff", "status", "stale_parent_warning", "pinned",
    )

    def __init__(self, node_id, content, subject, predicate, scope,
                 memory_type, input_weight, step, parent_ids,
                 residual_diff, pinned):
        self.node_id = node_id
        self.content = content
        self.subject = subject
        self.predicate = predicate
        self.scope = scope
        self.memory_type = memory_type
        self.input_weight = float(input_weight)
        self.step = int(step)
        self.parent_ids = list(parent_ids)
        self.residual_diff = residual_diff
        self.status = "active"           # active / superseded
        self.stale_parent_warning = False
        self.pinned = bool(pinned)


# ---------------------------------------------------------------- §2 三分支语义

def _children_map(nodes_by_id):
    """按 parent 边建子节点索引（node_id 升序遍历，保证确定性）。"""
    children = {}
    for nid in sorted(nodes_by_id.keys()):
        node = nodes_by_id[nid]
        for pid in node.parent_ids:
            children.setdefault(pid, []).append(nid)
    return children


def _supersede_descendants(nodes_by_id, seed_ids):
    """B 分支：沿 parent 边把全部子孙（传递闭包）标 superseded。"""
    children = _children_map(nodes_by_id)
    queue = []
    for sid in seed_ids:
        queue.extend(children.get(sid, []))
    seen = set()
    while queue:
        nid = queue.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        node = nodes_by_id.get(nid)
        if node is None:
            continue
        node.status = "superseded"
        queue.extend(children.get(nid, []))


def _mark_direct_children_stale(nodes_by_id, seed_ids):
    """C 分支：仅直接子节点置 stale_parent_warning=True，status 保持 active。"""
    seed_set = set(seed_ids)
    for nid in sorted(nodes_by_id.keys()):
        node = nodes_by_id[nid]
        for pid in node.parent_ids:
            if pid in seed_set:
                node.stale_parent_warning = True
                break


class Simulation(object):
    """单个 case 在单个分支上的仿真结果。"""

    __slots__ = ("nodes_by_id", "order", "case_step")

    def __init__(self, nodes_by_id, order, case_step):
        self.nodes_by_id = nodes_by_id
        self.order = order
        self.case_step = case_step


def simulate_case(case, branch):
    """§2.2 严格按 session_events 数组顺序逐条处理。

    处理第 i 条时只能看到前 i-1 条的状态：禁止先全量建图再统一算状态。
    """
    events = case["session_events"]
    case_step = len(events)                  # §1.2 CASE_STEP = N
    nodes_by_id = {}
    order = []

    for idx in range(len(events)):
        ev = events[idx]
        step = idx + 1                       # §1.2 step = 1..N
        node_id = ev["id"]

        orig_diff = ev.get("residual_diff")
        if orig_diff is not None:
            orig_diff = str(orig_diff)
            if orig_diff == "":
                orig_diff = None

        residual_diff = None

        if branch == "A":
            # §2 A 分支：不做槽位覆盖、所有节点恒 active、residual_diff 一律不记录。
            pass
        else:
            olds = []
            for nid in sorted(nodes_by_id.keys()):
                cand = nodes_by_id[nid]
                if cand.status != "active":
                    continue
                if (cand.subject == ev["subject"]
                        and cand.predicate == ev["predicate"]
                        and cand.scope == ev["scope"]):
                    olds.append(cand)
            if olds:
                # §2.1 同槽且 active 的旧节点全部标 superseded；
                # old（拼 diff 用）取 node_id 字典序最小者。
                old = olds[0]
                for cand in olds:
                    cand.status = "superseded"
                seed_ids = [cand.node_id for cand in olds]
                if branch == "B":
                    _supersede_descendants(nodes_by_id, seed_ids)
                else:  # C
                    _mark_direct_children_stale(nodes_by_id, seed_ids)
                if orig_diff is not None:
                    if branch == "C":
                        # §2 C 分支 + §11 D4：前缀由运行时拼装。
                        residual_diff = ("[Replaced: " + old.subject + " / "
                                         + old.content[:30] + "] " + orig_diff)
                    else:
                        # B 分支：只记录原始原因，不拼前缀。
                        residual_diff = orig_diff

        node = Node(
            node_id=node_id,
            content=str(ev["content"]),
            subject=str(ev["subject"]),
            predicate=str(ev["predicate"]),
            scope=str(ev["scope"]),
            memory_type=str(ev["memory_type"]),
            input_weight=ev["input_weight"],
            step=step,
            parent_ids=ev.get("parent_ids") or [],
            residual_diff=residual_diff,
            pinned=ev.get("pinned", False),
        )
        nodes_by_id[node_id] = node
        order.append(node_id)

    return Simulation(nodes_by_id, order, case_step)


# ---------------------------------------------------------------- §1.4 / §1.5 得分

def node_r(node, case_step):
    """§1.3 Delta(v) = CASE_STEP - v.step。"""
    return retention(node.memory_type, node.input_weight, case_step - node.step)


def node_f(node, nodes_by_id, case_step):
    """§1.4 F(v)：pinned → 1.0；否则 min(1.0, R + GAMMA * max(active 父的 R))。

    连坐系数 ψ 已物理砍除：父被覆盖时不对子节点做任何扣减。
    """
    if node.pinned:
        return 1.0
    base = node_r(node, case_step)
    best = 0.0
    has_active_parent = False
    for pid in node.parent_ids:
        parent = nodes_by_id.get(pid)
        if parent is None:
            continue
        if parent.status != "active":
            continue
        r = node_r(parent, case_step)
        if (not has_active_parent) or r > best:
            best = r
            has_active_parent = True
    gain = GAMMA * best if has_active_parent else 0.0
    return min(1.0, base + gain)


def retrieval_text(node, branch):
    """§4 检索文本：A 只用 content；B/C 用 content + 空格 + residual_diff。"""
    if branch == "A":
        return node.content
    return node.content + " " + (node.residual_diff or "")


def rank_candidates(sim, branch, query):
    """§5.1 候选集 + 排序（score 降序，同分按 node_id 升序）。返回截断前的全量排序。"""
    candidates = []
    for nid in sorted(sim.nodes_by_id.keys()):
        node = sim.nodes_by_id[nid]
        if branch != "A" and node.status != "active":
            continue                     # B/C 只取 active
        rel_value = rel(query, retrieval_text(node, branch))
        f_value = node_f(node, sim.nodes_by_id, sim.case_step)
        score = rel_value * (f_value ** LAMBDA)
        candidates.append({
            "node": node,
            "rel": rel_value,
            "f": f_value,
            "score": score,
        })
    candidates.sort(key=lambda item: (-item["score"], item["node"].node_id))
    return candidates


# ---------------------------------------------------------------- §6 机械判定

def judge(probe, injected_text, injected_node_ids, returned_diff):
    """§6 判定规则（零人味）。返回 (verdict, detail)。"""
    probe_type = probe["probe_type"]
    must_include = list(probe.get("must_include") or [])
    must_exclude = list(probe.get("must_exclude") or [])

    text_lc = nfkc_lower(injected_text)
    diff_lc = nfkc_lower(returned_diff)

    detail = {
        "missing_include": [],
        "hit_exclude": [],
        "missing_survive": [],
        "diff_empty": False,
    }

    if probe_type == "current_state":
        # 只扫 injected_text，绝不扫 returned_diff。
        for item in must_include:
            if nfkc_lower(item) not in text_lc:
                detail["missing_include"].append(item)
        for item in must_exclude:
            if nfkc_lower(item) in text_lc:
                detail["hit_exclude"].append(item)
        verdict = (not detail["missing_include"]) and (not detail["hit_exclude"])
        return verdict, detail

    if probe_type == "anti_trap":
        for item in must_include:
            if nfkc_lower(item) not in text_lc:
                detail["missing_include"].append(item)
        for node_id in (probe.get("expect_survive") or []):
            if node_id not in injected_node_ids:
                detail["missing_survive"].append(node_id)
        verdict = (not detail["missing_include"]) and (not detail["missing_survive"])
        return verdict, detail

    if probe_type == "evolution_why":
        detail["diff_empty"] = (returned_diff.strip() == "")
        for item in must_include:
            if nfkc_lower(item) not in diff_lc:
                detail["missing_include"].append(item)
        old_keyword = probe.get("old_keyword")
        keyword_ok = True
        if old_keyword is None or str(old_keyword) == "":
            keyword_ok = False
        elif nfkc_lower(str(old_keyword)) not in diff_lc:
            keyword_ok = False
        verdict = (not detail["diff_empty"]) and (not detail["missing_include"]) and keyword_ok
        return verdict, detail

    raise ValueError("未知 probe_type: " + str(probe_type))


# ---------------------------------------------------------------- 单 probe 评估

def evaluate_probe(case, branch, probe_index, probe):
    """跑一次完整流程：仿真 → 检索 → 双通道注入 → 判定。"""
    return _evaluate_with_sim(case, simulate_case(case, branch), branch,
                              probe_index, probe)


def _evaluate_with_sim(case, sim, branch, probe_index, probe):
    query = str(probe["query"])
    ranked_items = rank_candidates(sim, branch, query)

    # §5.1 ranked 记录截断前的全部候选，供复核。
    ranked = []
    for item in ranked_items:
        node = item["node"]
        ranked.append({
            "node_id": node.node_id,
            "rel": round6(item["rel"]),
            "f": round6(item["f"]),
            "score": round6(item["score"]),
            "status": node.status,
        })

    injected_items = ranked_items[:TOPK]

    # §5.2 两条通道，严禁混流。
    injected_text = "\n".join(item["node"].content for item in injected_items)
    injected_node_ids = [item["node"].node_id for item in injected_items]
    returned_diff = "\n".join(
        item["node"].residual_diff for item in injected_items
        if item["node"].residual_diff
    )

    verdict, detail = judge(probe, injected_text, injected_node_ids, returned_diff)

    return {
        "branch": branch,
        "scenario_id": case["scenario_id"],
        "is_control": bool(case.get("is_control", False)),
        "probe_index": int(probe_index),
        "probe_type": probe["probe_type"],
        "query": query,
        "ranked": ranked,
        "injected_node_ids": injected_node_ids,
        "injected_text": injected_text,
        "returned_diff": returned_diff,
        "verdict": bool(verdict),
        "detail": detail,
    }


def build_runs(dataset):
    """§8.3 runs 顺序：branch 外层(A,B,C) → scenario_id 升序 → probe_index 升序。"""
    cases = sorted(dataset["cases"], key=lambda c: c["scenario_id"])
    runs = []
    for branch in BRANCHES:
        for case in cases:
            sim = simulate_case(case, branch)
            for probe_index in range(len(case["probes"])):
                probe = case["probes"][probe_index]
                runs.append(_evaluate_with_sim(case, sim, branch, probe_index, probe))
    return runs


# ---------------------------------------------------------------- §7 指标

def _empty_type_bucket():
    return {"passed": 0, "total": 0, "rate": 0.0}


def _empty_branch_bucket():
    return {ptype: _empty_type_bucket() for ptype in PROBE_TYPES}


def _finish_bucket(bucket):
    for ptype in PROBE_TYPES:
        cell = bucket[ptype]
        total = cell["total"]
        cell["rate"] = round6(cell["passed"] / total) if total else 0.0
    return bucket


def build_metrics(dataset, runs):
    case_count = len(dataset["cases"])

    per_branch_probe = {branch: _empty_branch_bucket() for branch in BRANCHES}
    by_group = {
        "control": {branch: _empty_branch_bucket() for branch in BRANCHES},
        "non_control": {branch: _empty_branch_bucket() for branch in BRANCHES},
    }

    for run in runs:
        branch = run["branch"]
        ptype = run["probe_type"]
        group = "control" if run["is_control"] else "non_control"
        passed = 1 if run["verdict"] else 0
        for bucket in (per_branch_probe[branch], by_group[group][branch]):
            bucket[ptype]["total"] += 1
            bucket[ptype]["passed"] += passed

    for branch in BRANCHES:
        _finish_bucket(per_branch_probe[branch])
        _finish_bucket(by_group["control"][branch])
        _finish_bucket(by_group["non_control"][branch])

    rate_a = per_branch_probe["A"]["current_state"]["rate"]
    rate_b_anti = per_branch_probe["B"]["anti_trap"]["rate"]
    rate_c_current = per_branch_probe["C"]["current_state"]["rate"]
    rate_c_anti = per_branch_probe["C"]["anti_trap"]["rate"]
    rate_c_evo = per_branch_probe["C"]["evolution_why"]["rate"]

    delta_pp = round((rate_c_current - rate_a) * 100.0, 6)
    g1_pass = delta_pp >= 20.0                       # §7 G1 ≥ 20pp
    g2_pass = rate_c_anti > rate_b_anti              # §7 G2 严格大于
    g3_pass = rate_c_evo >= 0.85                     # §7 G3 ≥ 0.85

    gates = {
        "G1_current_state_lead_pp": {
            "a": rate_a,
            "c": rate_c_current,
            "delta_pp": delta_pp,
            "threshold_pp": 20.0,
            "pass": bool(g1_pass),
        },
        "G2_anti_trap_c_gt_b": {
            "b": rate_b_anti,
            "c": rate_c_anti,
            "pass": bool(g2_pass),
        },
        "G3_evolution_why": {
            "c": rate_c_evo,
            "threshold": 0.85,
            "pass": bool(g3_pass),
        },
    }

    return {
        "contract_version": CONTRACT_VERSION,
        "dataset_sha256": dataset["__sha256__"],
        "cases_total": case_count,
        "probes_per_branch": case_count * len(PROBE_TYPES),
        "per_branch_probe": per_branch_probe,
        "by_group": by_group,
        "gates": gates,
        "gate1_overall_pass": bool(g1_pass and g2_pass and g3_pass),
    }


# ---------------------------------------------------------------- IO

def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def load_dataset(path):
    """读数据集；dataset_sha256 对文件原始字节计算。"""
    digest = sha256_of_file(path)
    with open(path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    dataset["__sha256__"] = digest
    return dataset


def dumps_json(obj):
    """§9.4 唯一的序列化实现：ensure_ascii=False, indent=2, sort_keys=False + 结尾换行。

    落盘与自检的字节比对都走这里，保证「文件内容」与「被断言的字节」同源。
    """
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def write_json(path, obj):
    """§9.4 统一落盘（内容由 dumps_json 唯一决定）。"""
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    payload = dumps_json(obj)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(payload)


def build_raw(dataset, runs):
    return {
        "contract_version": CONTRACT_VERSION,
        "dataset_sha256": dataset["__sha256__"],
        "case_count": len(dataset["cases"]),
        "branches": list(BRANCHES),
        "runs": runs,
    }


def run_pipeline(dataset_path, out_raw_path, out_metrics_path):
    """完整跑分：读数据集 → 三分支仿真 → 落盘。返回 (raw, metrics)。"""
    dataset = load_dataset(dataset_path)
    runs = build_runs(dataset)
    metrics = build_metrics(dataset, runs)
    raw = build_raw(dataset, runs)
    if out_raw_path:
        write_json(out_raw_path, raw)
    if out_metrics_path:
        write_json(out_metrics_path, metrics)
    return raw, metrics


# ---------------------------------------------------------------- 自检内置微用例

MICRO_CASE = {
    "scenario_id": "T01",
    "domain": "db",
    "description": "内置微用例：MySQL 迁移 PostgreSQL，且存在挂载规范子节点",
    "is_control": False,
    "construction_note": "自检专用微用例，用于验证 §2 三分支在直接子节点上的差异",
    "tags": ["multi_parent"],
    "session_events": [
        {
            "id": "M1",
            "content": "数据库引擎选定 MySQL 8.0",
            "subject": "db",
            "predicate": "engine",
            "scope": "global",
            "memory_type": "DECISION",
            "input_weight": 0.8,
        },
        {
            "id": "M2",
            "content": "挂载规范要求 PVC 只读挂载",
            "subject": "mount",
            "predicate": "spec",
            "scope": "global",
            "memory_type": "CONSTRAINT",
            "input_weight": 0.7,
            "parent_ids": ["M1"],
        },
        {
            "id": "M3",
            "content": "挂载规范补充要求 fsGroup 设为 1000",
            "subject": "mount",
            "predicate": "spec_extra",
            "scope": "global",
            "memory_type": "CONSTRAINT",
            "input_weight": 0.6,
            "parent_ids": ["M2"],
        },
        {
            "id": "M4",
            "content": "数据库引擎迁移到 PostgreSQL 16",
            "subject": "db",
            "predicate": "engine",
            "scope": "global",
            "memory_type": "DECISION",
            "input_weight": 0.9,
            "residual_diff": "因为许可证与 JSON 能力，替换掉 MySQL",
        },
    ],
    "probes": [
        {
            "probe_type": "current_state",
            "query": "数据库引擎现在用 PostgreSQL 还是 MySQL？挂载规范是什么？",
            "must_include": ["PostgreSQL"],
            "must_exclude": ["MySQL"],
            "expect_nodes": ["M4"],
        },
        {
            "probe_type": "anti_trap",
            "query": "挂载规范要求什么？数据库引擎是什么？",
            "must_include": ["挂载规范"],
            "must_exclude": [],
            "expect_survive": ["M2"],
        },
        {
            "probe_type": "evolution_why",
            "query": "为什么数据库引擎发生了变化？",
            "must_include": ["许可证"],
            "must_exclude": [],
            "old_keyword": "MySQL",
        },
    ],
}

MICRO_CASE_2 = {
    "scenario_id": "T02",
    "domain": "deploy",
    "description": "内置微用例二：scope 隔离 + 覆盖链上的 EPHEMERAL 节点",
    "is_control": False,
    "construction_note": "自检专用微用例，用于覆盖 scope 隔离与多类型混合场景",
    "tags": ["scope_isolation"],
    "session_events": [
        {
            "id": "N1",
            "content": "缓存 TTL 偏好 60 秒",
            "subject": "cache",
            "predicate": "ttl",
            "scope": "global",
            "memory_type": "PREFERENCE",
            "input_weight": 0.3,
        },
        {
            "id": "N2",
            "content": "热点缓存 TTL 改为 10 秒",
            "subject": "cache",
            "predicate": "ttl",
            "scope": "branch:hot",
            "memory_type": "PREFERENCE",
            "input_weight": 0.4,
        },
        {
            "id": "N3",
            "content": "发布窗口限定在周二凌晨，使用 Kubernetes",
            "subject": "deploy",
            "predicate": "window",
            "scope": "global",
            "memory_type": "CONSTRAINT",
            "input_weight": 0.9,
        },
        {
            "id": "N4",
            "content": "发布窗口改为周四凌晨，改用 Argo CD",
            "subject": "deploy",
            "predicate": "window",
            "scope": "global",
            "memory_type": "DECISION",
            "input_weight": 0.9,
            "residual_diff": "因为 Kubernetes 滚动更新回滚太慢，换掉 Kubernetes",
        },
        {
            "id": "N5",
            "content": "临时观察 Argo CD 同步延迟",
            "subject": "deploy",
            "predicate": "observe",
            "scope": "global",
            "memory_type": "EPHEMERAL",
            "input_weight": 0.2,
            "parent_ids": ["N4"],
        },
        {
            "id": "N6",
            "content": "回滚策略要求保留两个版本",
            "subject": "rollback",
            "predicate": "policy",
            "scope": "global",
            "memory_type": "CONSTRAINT",
            "input_weight": 0.5,
            "parent_ids": ["N3", "N4"],
        },
    ],
    "probes": [
        {
            "probe_type": "current_state",
            "query": "发布窗口现在是什么？缓存 TTL 是多少？",
            "must_include": ["周四"],
            "must_exclude": ["Kubernetes"],
            "expect_nodes": ["N4"],
        },
        {
            "probe_type": "anti_trap",
            "query": "回滚策略要求什么？发布窗口是什么？",
            "must_include": ["回滚策略"],
            "must_exclude": [],
            "expect_survive": ["N6"],
        },
        {
            "probe_type": "evolution_why",
            "query": "为什么发布窗口变了？",
            "must_include": ["回滚"],
            "must_exclude": [],
            "old_keyword": "Kubernetes",
        },
    ],
}


def selfcheck_dataset():
    """自检内部构造的小数据集（不落仓库）。"""
    return {
        "dataset_version": "0.0.0-selfcheck",
        "case_count": 2,
        "cases": [MICRO_CASE, MICRO_CASE_2],
    }


# ---------------------------------------------------------------- 自检输出工具

def _disp_width(text):
    width = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def _pad(text, width):
    return text + " " * max(0, width - _disp_width(text))


def _print_table(rows):
    headers = ["序号", "断言（CONTRACT §12）", "结果", "实测 / 说明"]
    widths = [4, 40, 6, 60]
    for row in rows:
        for i in range(len(row)):
            widths[i] = max(widths[i], _disp_width(row[i]))
    line = "-+-".join("-" * widths[i] for i in range(len(headers)))

    print("  ".join(_pad(headers[i], widths[i]) for i in range(len(headers))))
    print(line)
    for row in rows:
        print("  ".join(_pad(row[i], widths[i]) for i in range(len(row))))


def _close(a, b, rel_tol):
    return abs(a - b) <= rel_tol * max(abs(a), abs(b))


# ---------------------------------------------------------------- 自检 8 条

def run_self_test():
    """§12 自检清单，全部断言；任何一条不过返回非 0。"""
    rows = []
    failures = []

    def record(index, title, ok, note):
        rows.append((str(index), title, "PASS" if ok else "FAIL", note))
        if not ok:
            failures.append(index)
        return ok

    print("=" * 118)
    print("  spike_cut1.py 自检 —— CONTRACT v" + CONTRACT_VERSION + " §12（共 8 条断言）")
    print("=" * 118)

    # ---- 1) R(0) == 1.0（四种类型）
    ok1 = True
    notes1 = []
    for mtype in MEMORY_TYPES:
        value = retention(mtype, 0.5, 0)
        if value != 1.0:
            ok1 = False
        notes1.append(mtype + "=" + repr(value))
    record(1, "R(0) == 1.0（四种类型）", ok1, " ".join(notes1))

    # ---- 2) R(H) ≈ 0.5，H = t0 * (2**(1/beta) - 1)
    ok2 = True
    notes2 = []
    h_values = {}
    for mtype in MEMORY_TYPES:
        beta = TYPE_PARAMS[mtype]["beta"]
        t0 = t0_of(mtype, 0.5)
        H = t0 * (2.0 ** (1.0 / beta) - 1.0)
        h_values[mtype] = H
        value = retention(mtype, 0.5, H)
        if not _close(value, 0.5, 1e-9):
            ok2 = False
        notes2.append(mtype + "=" + format(value, ".12f"))
    record(2, "R(H) ≈ 0.5，H = t0*(2^(1/beta)-1)", ok2, " ".join(notes2))

    # ---- 3) R(2H) == (2*2**(1/beta)-1)**(-beta) 且 R(2H) > 0.25
    ok3 = True
    notes3 = []
    for mtype in MEMORY_TYPES:
        beta = TYPE_PARAMS[mtype]["beta"]
        expected = (2.0 * 2.0 ** (1.0 / beta) - 1.0) ** (-beta)
        value = retention(mtype, 0.5, 2.0 * h_values[mtype])
        good = _close(value, expected, 1e-6) and value > 0.25
        if not good:
            ok3 = False
        notes3.append(mtype + "=" + format(value, ".6f")
                      + "(期望 " + format(expected, ".6f") + ")")
    record(3, "R(2H) 符公式（rel_tol 1e-6）且 > 0.25", ok3, " ".join(notes3))

    # ---- 4) 四类型 input_weight=0.5, Delta=2H 实测值
    expected4 = {
        "DECISION": 0.4665,
        "CONSTRAINT": 0.4830,
        "PREFERENCE": 0.4510,
        "EPHEMERAL": 0.3231,
    }
    ok4 = True
    notes4 = []
    for mtype in MEMORY_TYPES:
        value = retention(mtype, 0.5, 2.0 * h_values[mtype])
        target = expected4[mtype]
        if not _close(value, target, 1e-3):
            ok4 = False
        notes4.append(mtype + "=" + format(value, ".4f") + "(≈" + format(target, ".4f") + ")")
    record(4, "四类型实测 0.4665/0.4830/0.4510/0.3231（1e-3）", ok4, " ".join(notes4))

    # ---- 5) 内置微用例（MySQL→PG + 挂载规范）
    sim_a = simulate_case(MICRO_CASE, "A")
    sim_b = simulate_case(MICRO_CASE, "B")
    sim_c = simulate_case(MICRO_CASE, "C")
    probe_micro = MICRO_CASE["probes"][1]      # anti_trap，expect_survive = M3

    run_a = _evaluate_with_sim(MICRO_CASE, sim_a, "A", 1, probe_micro)
    run_b = _evaluate_with_sim(MICRO_CASE, sim_b, "B", 1, probe_micro)
    run_c = _evaluate_with_sim(MICRO_CASE, sim_c, "C", 1, probe_micro)

    text_a_lc = nfkc_lower(run_a["injected_text"])
    a_coexist = ("mysql" in text_a_lc) and ("postgresql" in text_a_lc)
    b_kills_m2 = "M2" not in run_b["injected_node_ids"]
    b_kills_m3 = "M3" not in run_b["injected_node_ids"]   # 传递闭包：孙辈也一并误杀
    c_keeps_m2 = "M2" in run_c["injected_node_ids"]
    c_keeps_m3 = "M3" in run_c["injected_node_ids"]       # 孙辈不受影响
    c_diff_has_mysql = "mysql" in nfkc_lower(run_c["returned_diff"])
    c_m2_stale = sim_c.nodes_by_id["M2"].stale_parent_warning
    c_m3_stale = sim_c.nodes_by_id["M3"].stale_parent_warning
    # 双通道隔离：MySQL 只许出现在 returned_diff，不得出现在 injected_text。
    c_text_pure = "mysql" not in nfkc_lower(run_c["injected_text"])
    ok5 = (a_coexist and b_kills_m2 and b_kills_m3 and c_keeps_m2 and c_keeps_m3
           and c_diff_has_mysql and c_m2_stale and (not c_m3_stale) and c_text_pure)
    notes5 = ("A新旧并存=" + str(a_coexist)
              + " B误杀M2=" + str(b_kills_m2)
              + " B连坐杀M3=" + str(b_kills_m3)
              + " C存M2=" + str(c_keeps_m2)
              + " C存M3=" + str(c_keeps_m3)
              + " C_diff含MySQL=" + str(c_diff_has_mysql)
              + " C_M2.stale=" + str(c_m2_stale)
              + " C_M3.stale=" + str(c_m3_stale)
              + " C正文无MySQL=" + str(c_text_pure))
    record(5, "微用例：A 并存 / B 误杀规范 / C 存活且 diff 含 MySQL", ok5, notes5)

    # ---- 6) 分词器
    toks = tokenize("MySQL 8.0 主数据库")
    required = ["mysql", "8", "0", "主", "数据", "据库"]
    missing = [item for item in required if item not in toks]
    ok6 = not missing
    record(6, "tokenize 含 ASCII 词 / 单字 / 二元组", ok6,
           "缺失=" + repr(missing) + " 样例=" + repr(sorted(toks))[:160])

    # ---- 7) rel 对称性 + 空集 0.0
    a_text = "MySQL 8.0 主数据库"
    b_text = "PostgreSQL 16 主数据库"
    rel_ab = rel(a_text, b_text)
    rel_ba = rel(b_text, a_text)
    symmetric = (rel_ab == rel_ba)
    empty_ok = (rel("", "任意文本") == 0.0
                and rel("任意文本", "") == 0.0
                and rel("", "") == 0.0
                and rel("！！！", "???") == 0.0)
    ok7 = symmetric and empty_ok
    record(7, "rel 对称性，空集返回 0.0", ok7,
           "rel(a,b)=" + repr(rel_ab) + " rel(b,a)=" + repr(rel_ba)
           + " 空集=" + str(empty_ok))

    # ---- 8) 内置小数据集连跑两次，输出字节完全相同
    tmp_dir = tempfile.mkdtemp(prefix="spike_cut1_selftest_")
    ok8 = False
    note8 = ""
    try:
        dataset_path = os.path.join(tmp_dir, "selfcheck_dataset.json")
        with open(dataset_path, "w", encoding="utf-8", newline="") as f:
            f.write(dumps_json(selfcheck_dataset()))

        raw1 = os.path.join(tmp_dir, "raw_1.json")
        met1 = os.path.join(tmp_dir, "metrics_1.json")
        raw2 = os.path.join(tmp_dir, "raw_2.json")
        met2 = os.path.join(tmp_dir, "metrics_2.json")

        obj_raw1, obj_met1 = run_pipeline(dataset_path, raw1, met1)
        obj_raw2, obj_met2 = run_pipeline(dataset_path, raw2, met2)

        def _bytes(path):
            with open(path, "rb") as fh:
                return fh.read()

        # 双重断言：内存序列化字节 + 真实落盘字节，都必须逐字节相同。
        mem_same_raw = (dumps_json(obj_raw1) == dumps_json(obj_raw2))
        mem_same_met = (dumps_json(obj_met1) == dumps_json(obj_met2))
        disk_same_raw = (_bytes(raw1) == _bytes(raw2))
        disk_same_met = (_bytes(met1) == _bytes(met2))
        ok8 = mem_same_raw and mem_same_met and disk_same_raw and disk_same_met
        note8 = ("raw 字节一致=" + str(disk_same_raw)
                 + " metrics 字节一致=" + str(disk_same_met)
                 + " 内存序列化一致=" + str(mem_same_raw and mem_same_met)
                 + " raw sha256=" + hashlib.sha256(_bytes(raw1)).hexdigest()[:16])
    except Exception as exc:                       # 自检内部异常一律判负
        ok8 = False
        note8 = "异常: " + repr(exc)
    finally:
        try:
            if os.path.isdir(tmp_dir):
                for name in sorted(os.listdir(tmp_dir)):
                    os.remove(os.path.join(tmp_dir, name))
                os.rmdir(tmp_dir)
        except OSError:
            pass
    record(8, "小数据集连跑两次输出字节相同", ok8, note8)

    print("")
    _print_table(rows)
    print("")

    if failures:
        print("自检失败：" + str(len(failures)) + " 条断言未通过 -> " + repr(failures))
        return 1
    print("自检通过：8/8 条断言全部 PASS。")
    return 0


# ---------------------------------------------------------------- CLI (§8.2)

def build_parser():
    parser = argparse.ArgumentParser(
        prog="spike_cut1.py",
        description="Gated-Mem 阶段一 Spike Cut #1：A/B/C 三分支仿真运行器 + 自检。",
        epilog="示例：python benchmarks/spike_cut1.py --self-test",
    )
    parser.add_argument("--dataset", metavar="PATH",
                        help="数据集 JSON 路径（benchmarks/data/eval_cases_40.json）")
    parser.add_argument("--out-raw", metavar="PATH", dest="out_raw",
                        help="原始证据输出路径（benchmarks/results/raw_runs.json）")
    parser.add_argument("--out-metrics", metavar="PATH", dest="out_metrics",
                        help="聚合指标输出路径（benchmarks/results/metrics.json）")
    parser.add_argument("--self-test", action="store_true", dest="self_test",
                        help="运行 §12 自检 8 条断言，退出码 0 = 全部通过")
    return parser


def _force_utf8_console():
    """Windows 控制台默认 GBK，中文表格会乱码；这里把 stdout/stderr 切到 UTF-8。

    注意：此项只影响屏幕编码，绝不参与任何结果计算（§9 确定性不受影响）。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def main(argv):
    _force_utf8_console()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if not args.dataset:
        sys.stderr.write("错误：未指定 --dataset（或使用 --self-test 运行自检）。\n")
        return 2
    if not os.path.isfile(args.dataset):
        sys.stderr.write("错误：数据集不存在：" + args.dataset + "\n")
        return 2

    dataset = load_dataset(args.dataset)
    if "cases" not in dataset or not isinstance(dataset["cases"], list):
        sys.stderr.write("错误：数据集缺少 cases 数组。\n")
        return 2

    runs = build_runs(dataset)
    metrics = build_metrics(dataset, runs)
    raw = build_raw(dataset, runs)

    if args.out_raw:
        write_json(args.out_raw, raw)
    if args.out_metrics:
        write_json(args.out_metrics, metrics)

    gates = metrics["gates"]
    print("cases_total=" + str(metrics["cases_total"])
          + " runs=" + str(len(runs))
          + " gate1_overall_pass=" + str(metrics["gate1_overall_pass"]))
    print("G1 delta_pp=" + str(gates["G1_current_state_lead_pp"]["delta_pp"])
          + " pass=" + str(gates["G1_current_state_lead_pp"]["pass"]))
    print("G2 b=" + str(gates["G2_anti_trap_c_gt_b"]["b"])
          + " c=" + str(gates["G2_anti_trap_c_gt_b"]["c"])
          + " pass=" + str(gates["G2_anti_trap_c_gt_b"]["pass"]))
    print("G3 c=" + str(gates["G3_evolution_why"]["c"])
          + " pass=" + str(gates["G3_evolution_why"]["pass"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
