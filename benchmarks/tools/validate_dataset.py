#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""benchmarks/tools/validate_dataset.py — Gated-Mem 阶段一数据集校验器。

用法（CONTRACT.md §8.2）:
    python benchmarks/tools/validate_dataset.py --dataset benchmarks/data/eval_cases_40.json

逐条检查 CONTRACT.md §3.5 的九条硬约束，每条打印 OK/FAIL 并给出精确定位
（scenario_id / event id / probe_index）；另做额外自检（前向引用 / 自引用 / 环、
memory_type 合法性、input_weight 范围、scope 非空、probe 三类各一、scenario_id 连续唯一）
与 WARN 警告（current_state 建议同时提及新旧技术名）。

有 FAIL 退出码 1；全 OK 退出码 0。纯标准库，Python 3.9 兼容。
"""
import argparse
import json
import os
import re
import sys

TARGET_CASES = 40
VALID_TYPES = ("DECISION", "CONSTRAINT", "PREFERENCE", "EPHEMERAL")
VALID_PROBES = ("current_state", "anti_trap", "evolution_why")
ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]*")
CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")


class Report(object):
    """收集九条硬约束的 OK/FAIL 与 WARN，最后统一打印。"""

    def __init__(self):
        self.failures = []          # [(constraint_no, message)]
        self.warnings = []          # [message]

    def fail(self, no, msg):
        self.failures.append((no, msg))
        print("  [FAIL] " + msg)

    def warn(self, msg):
        self.warnings.append(msg)
        print("  [WARN] " + msg)

    def ok(self, no, summary):
        print("  [OK]   约束 %d: %s" % (no, summary))

    @property
    def has_fail(self):
        return len(self.failures) > 0


def _probe_by_type(case, ptype):
    for i, p in enumerate(case.get("probes", [])):
        if p.get("probe_type") == ptype:
            return i, p
    return None, None


def _coverage_pairs(events):
    """按 CONTRACT §2.1 槽位规则逐事件模拟覆盖，返回 [(new_ev, old_ev), ...]。"""
    active = []
    pairs = []

    def slot_of(e):
        return (e.get("subject"), e.get("predicate"), e.get("scope"))

    for e in events:
        slot = slot_of(e)
        olds = [a for a in active if slot_of(a) == slot]
        if olds:
            old = min(olds, key=lambda x: x.get("id", ""))
            pairs.append((e, old))
            active = [a for a in active if slot_of(a) != slot]
        active.append(e)
    return pairs


def _tech_keywords(text):
    """契约判据：旧 content 中长度>=3 的 ASCII 单词；无则取最后一个中文二元组。"""
    words = [w for w in ASCII_WORD_RE.findall(text or "") if len(w) >= 3]
    if words:
        return words
    runs = CJK_RUN_RE.findall(text or "")
    if runs and len(runs[-1]) >= 2:
        return [runs[-1][-2:]]
    return []


def _descendants(events):
    """返回 {event_id: 传递闭包子孙 id 集合}（基于 parent_ids 有向边）。"""
    children = {}
    ids = [e.get("id") for e in events]
    for e in events:
        for pid in e.get("parent_ids", []):
            children.setdefault(pid, []).append(e.get("id"))
    desc = {}
    for start in ids:
        seen = set()
        stack = list(children.get(start, []))
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(children.get(n, []))
        desc[start] = seen
    return desc


def check_constraint_1(dataset, rep):
    cases = dataset.get("cases", [])
    problems = []
    if dataset.get("case_count") != TARGET_CASES:
        problems.append("顶层 case_count=%r != 40" % (dataset.get("case_count"),))
    if len(cases) != TARGET_CASES:
        problems.append("len(cases)=%d != 40" % len(cases))
    for i, c in enumerate(cases, start=1):
        want = "S%02d" % i
        if c.get("scenario_id") != want:
            problems.append("第 %d 个 case 的 scenario_id=%r，期望 %r" % (i, c.get("scenario_id"), want))
    ids = [c.get("scenario_id") for c in cases]
    dup = sorted(set(x for x in ids if ids.count(x) > 1))
    if dup:
        problems.append("scenario_id 重复: " + ", ".join(dup))
    if problems:
        for p in problems:
            rep.fail(1, p)
    else:
        rep.ok(1, "case_count=len(cases)=40，scenario_id=S01..S40 连续唯一零填充")


def check_constraint_2(cases, rep):
    bad = [(c.get("scenario_id"), len(c.get("session_events", [])))
           for c in cases if not (6 <= len(c.get("session_events", [])) <= 8)]
    if bad:
        for sid, n in bad:
            rep.fail(2, "%s: session_events 长度 %d 不在 [6,8]" % (sid, n))
    else:
        rep.ok(2, "全部 40 组 session_events 长度均在 [6,8]")


def check_constraint_3(cases, rep):
    bad = []
    for c in cases:
        probes = c.get("probes", [])
        types = [p.get("probe_type") for p in probes]
        if len(probes) != 3 or sorted(types) != sorted(VALID_PROBES):
            bad.append("%s: %d 条 probes，类型=%s" % (c.get("scenario_id"), len(probes), types))
    if bad:
        for b in bad:
            rep.fail(3, b)
    else:
        rep.ok(3, "每组恰好 3 条 probes 且 current_state/anti_trap/evolution_why 各一")


def check_constraint_4(cases, rep):
    domains = sorted(set(c.get("domain", "") for c in cases))
    if len(domains) < 6:
        rep.fail(4, "domain 去重仅 %d 种（<6）: %s" % (len(domains), ", ".join(domains)))
    else:
        rep.ok(4, "domain 去重 %d 种 >= 6: %s" % (len(domains), ", ".join(domains)))


def check_constraint_5(cases, rep):
    tagged = [c for c in cases if "multi_parent" in c.get("tags", [])]
    if len(tagged) < 3:
        rep.fail(5, "multi_parent 用例仅 %d 组（<3）" % len(tagged))
        return
    bad = []
    for c in tagged:
        evs = c.get("session_events", [])
        multi = [e.get("id") for e in evs if len(e.get("parent_ids", [])) >= 2]
        if not multi:
            bad.append("%s: 打了 multi_parent 标签但没有任何 event 的 parent_ids 长度>=2" % c.get("scenario_id"))
    if bad:
        for b in bad:
            rep.fail(5, b)
    else:
        detail = "; ".join(
            "%s(%s)" % (c["scenario_id"], ",".join(e["id"] for e in c["session_events"] if len(e.get("parent_ids", [])) >= 2))
            for c in tagged)
        rep.ok(5, "multi_parent 用例 %d 组 >= 3: %s" % (len(tagged), detail))


def check_constraint_6(cases, rep):
    tagged = [c for c in cases if "scope_isolation" in c.get("tags", [])]
    if len(tagged) < 4:
        rep.fail(6, "scope_isolation 用例仅 %d 组（<4）" % len(tagged))
        return
    bad = []
    for c in tagged:
        sid = c.get("scenario_id")
        evs = c.get("session_events", [])
        has_branch = any(str(e.get("scope", "")).startswith("branch:") for e in evs)
        if not has_branch:
            bad.append("%s: 打了 scope_isolation 标签但无 branch:* scope 事件" % sid)
            continue
        # 同 subject+predicate 但不同 scope 的节点对
        pairs_ok = False
        for i in range(len(evs)):
            for j in range(len(evs)):
                if i == j:
                    continue
                a, b = evs[i], evs[j]
                if (a.get("subject") == b.get("subject")
                        and a.get("predicate") == b.get("predicate")
                        and a.get("scope") != b.get("scope")):
                    pairs_ok = True
        if not pairs_ok:
            bad.append("%s: 无同 subject+predicate 不同 scope 的节点对" % sid)
            continue
        # 该类 case 的 current_state 探针必须验证跨 scope 共存（机械代理：query 提及分支名）
        pi, p = _probe_by_type(c, "current_state")
        branch_short = ""
        for e in evs:
            sc = str(e.get("scope", ""))
            if sc.startswith("branch:"):
                branch_short = sc.split(":", 1)[1]
                break
        if p is None or branch_short not in (p.get("query") or ""):
            bad.append("%s: current_state 探针(第 %s 条)未在 query 中验证跨 scope 共存（缺分支名 %r）"
                       % (sid, pi, branch_short))
    if bad:
        for b in bad:
            rep.fail(6, b)
    else:
        rep.ok(6, "scope_isolation 用例 %d 组 >= 4: %s" % (len(tagged), ", ".join(c["scenario_id"] for c in tagged)))


def check_constraint_7(cases, rep):
    tagged = [c for c in cases if "fake_conflict" in c.get("tags", [])]
    if len(tagged) < 2:
        rep.fail(7, "fake_conflict 用例仅 %d 组（<2）" % len(tagged))
        return
    bad = []
    for c in tagged:
        sid = c.get("scenario_id")
        evs = c.get("session_events", [])
        found = None
        for i in range(len(evs)):
            for j in range(i + 1, len(evs)):
                a, b = evs[i], evs[j]
                if a.get("subject") == b.get("subject") and a.get("predicate") != b.get("predicate"):
                    found = (a.get("id"), b.get("id"))
                    break
            if found:
                break
        if not found:
            bad.append("%s: 打了 fake_conflict 标签但无同 subject 不同 predicate 的节点对" % sid)
    if bad:
        for b in bad:
            rep.fail(7, b)
    else:
        rep.ok(7, "fake_conflict 用例 %d 组 >= 2: %s" % (len(tagged), ", ".join(c["scenario_id"] for c in tagged)))


def check_constraint_8(cases, rep):
    ctrls = [c for c in cases if c.get("is_control") is True]
    if len(ctrls) < 8:
        rep.fail(8, "is_control=true 的负控制组仅 %d 组（<8）" % len(ctrls))
    bad = []
    for c in ctrls:
        sid = c.get("scenario_id")
        note = c.get("construction_note") or ""
        if len(note) < 10:
            bad.append("%s: construction_note 过短（%d 字），未说明控制目的" % (sid, len(note)))
        evs = c.get("session_events", [])
        cov = _coverage_pairs(evs)
        if not cov:
            continue  # 无覆盖的控制组合法
        # 有覆盖：覆盖不得涉及 anti_trap 靶子（靶子不得在被覆盖旧节点的传递子孙集内）
        pi, p = _probe_by_type(c, "anti_trap")
        targets = (p or {}).get("expect_survive") or []
        if not targets:
            bad.append("%s: 控制组含覆盖但 anti_trap 探针缺 expect_survive 靶子" % sid)
            continue
        desc = _descendants(evs)
        for t in targets:
            for new_e, old_e in cov:
                if t in desc.get(old_e.get("id"), set()):
                    bad.append("%s: anti_trap 靶子 %s 是被覆盖节点 %s 的子孙，分支 B 会误杀（违反控制组设计）"
                               % (sid, t, old_e.get("id")))
    for b in bad:
        rep.fail(8, b)
    if not bad and len(ctrls) >= 8:
        rep.ok(8, "负控制组 %d 组 >= 8: %s；含覆盖的控制组其覆盖均不涉及 anti_trap 靶子"
               % (len(ctrls), ", ".join(c["scenario_id"] for c in ctrls)))


def check_constraint_9(cases, rep):
    bad = []

    for c in cases:
        sid = c.get("scenario_id")
        evs = c.get("session_events", [])

        # 9a. parent_ids 引用完整性（更早出现；禁止前向引用 / 自引用 / 环）
        earlier = []
        for e in evs:
            eid = e.get("id")
            for pid in e.get("parent_ids", []):
                if pid == eid:
                    bad.append("%s/%s: parent_ids 自引用" % (sid, eid))
                elif pid not in earlier:
                    kind = "前向引用" if pid in [x.get("id") for x in evs] else "引用不存在的 id"
                    bad.append("%s/%s: parent_ids %s（%s）" % (sid, eid, kind, pid))
            earlier.append(eid)

        # 9b. 字段合法性
        for e in evs:
            eid = e.get("id")
            if e.get("memory_type") not in VALID_TYPES:
                bad.append("%s/%s: 非法 memory_type=%r" % (sid, eid, e.get("memory_type")))
            w = e.get("input_weight")
            if not isinstance(w, (int, float)) or not (0.1 <= w <= 1.0):
                bad.append("%s/%s: input_weight=%r 越界 [0.1,1.0]" % (sid, eid, w))
            if not e.get("scope"):
                bad.append("%s/%s: scope 为空" % (sid, eid))

        # 9c. 覆盖事件必须带 residual_diff 且含旧节点技术关键词；diff 不得带 [Replaced 前缀
        diffs = []
        for e in evs:
            d = e.get("residual_diff")
            if d:
                diffs.append(d)
                if "[Replaced" in d:
                    bad.append("%s/%s: residual_diff 带 [Replaced 前缀（应由运行时拼装）" % (sid, e.get("id")))
        for new_e, old_e in _coverage_pairs(evs):
            d = new_e.get("residual_diff")
            if not d:
                bad.append("%s/%s: 同槽覆盖事件缺 residual_diff（被覆盖旧节点 %s）"
                           % (sid, new_e.get("id"), old_e.get("id")))
                continue
            kws = _tech_keywords(old_e.get("content") or "")
            low = d.lower()
            if not any(k.lower() in low for k in kws):
                bad.append("%s/%s: residual_diff 未含旧节点 %s content 的技术关键词（候选=%r）"
                           % (sid, new_e.get("id"), old_e.get("id"), kws))

        # 9d. evolution_why 必须带 old_keyword，且出现在某条 residual_diff 中
        for idx, p in enumerate(c.get("probes", [])):
            if p.get("probe_type") != "evolution_why":
                continue
            ok_kw = p.get("old_keyword")
            if not ok_kw:
                bad.append("%s/probe[%d]: evolution_why 缺 old_keyword" % (sid, idx))
            elif not any(ok_kw.lower() in d.lower() for d in diffs):
                bad.append("%s/probe[%d]: old_keyword=%r 未出现在任何 residual_diff 中"
                           % (sid, idx, ok_kw))

    if bad:
        for b in bad:
            rep.fail(9, b)
    else:
        n_diff = sum(1 for c in cases for e in c.get("session_events", []) if e.get("residual_diff"))
        rep.ok(9, "引用完整性/字段合法性/覆盖事件 residual_diff 及关键词/old_keyword 全部通过"
               "（含 residual_diff 事件共 %d 个）" % n_diff)


def check_warnings(cases, rep):
    """WARN：current_state 的 query 建议同时提及新旧两个技术名。"""
    n_warn = 0
    for c in cases:
        pi, p = _probe_by_type(c, "current_state")
        if p is None:
            continue
        q = (p.get("query") or "")
        for w in (p.get("must_exclude") or []):
            if w.lower() not in q.lower():
                rep.warn("%s/probe[%d]: current_state 的 query 未提及 must_exclude 中的旧技术名 %r"
                         % (c.get("scenario_id"), pi, w))
                n_warn += 1
    if n_warn == 0:
        print("  [OK]   WARN 项: 所有非控制组 current_state 的 query 均同时提及新旧技术名（无警告）")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Gated-Mem 阶段一数据集校验器：逐条检查 CONTRACT.md §3.5 九条硬约束（纯标准库）")
    ap.add_argument("--dataset", default=os.path.join("benchmarks", "data", "eval_cases_40.json"),
                    help="待校验的数据集 JSON 路径（默认 benchmarks/data/eval_cases_40.json）")
    args = ap.parse_args(argv)

    try:
        with open(args.dataset, "r", encoding="utf-8") as f:
            dataset = json.load(f)
    except (IOError, OSError) as e:
        print("[validate] 无法读取数据集: %s (%s)" % (args.dataset, e))
        return 1
    except ValueError as e:
        print("[validate] 数据集不是合法 JSON: %s" % e)
        return 1

    cases = dataset.get("cases", [])
    rep = Report()
    print("[validate] 数据集: %s" % os.path.abspath(args.dataset))
    print("[validate] ===== CONTRACT.md §3.5 九条硬约束 =====")
    check_constraint_1(dataset, rep)
    check_constraint_2(cases, rep)
    check_constraint_3(cases, rep)
    check_constraint_4(cases, rep)
    check_constraint_5(cases, rep)
    check_constraint_6(cases, rep)
    check_constraint_7(cases, rep)
    check_constraint_8(cases, rep)
    check_constraint_9(cases, rep)
    print("[validate] ===== 附加 WARN（不参与退出码） =====")
    check_warnings(cases, rep)
    print("[validate] ===== 结果 =====")
    if rep.has_fail:
        print("[validate] FAIL: 共 %d 条失败" % len(rep.failures))
        for no, msg in rep.failures:
            print("  - 约束 %d: %s" % (no, msg))
        return 1
    print("[validate] OK: 九条硬约束全部通过，警告 %d 条" % len(rep.warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
