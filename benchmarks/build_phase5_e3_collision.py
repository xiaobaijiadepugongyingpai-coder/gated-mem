# -*- coding: utf-8 -*-
"""阶段五 E3 跨模块同符号碰撞消歧基准集生成器 (GM-DIRECTIVE-P5 v5.0.0 §2.2)。

场景（本实验命门）：
  - 模块 A「分布式账务清算服务」与模块 B「边缘网关流控中间件」在**每个 case 内
    共享完全相同的一组版本号**（同符号碰撞），同一版本号在 A/B 两模块中的超时
    配置值**不同**（正确答案唯一）；
  - 查询只含「语义改写」（与模块名零/近零字面重叠）+ 精确版本符号：
      A 侧改写：「支付对账系统」
      B 侧改写：「设备接入限速决策器」
  - 因此：A1 单向量能凭 FastEmbed 语义桥认模块、却无法区分微差版本（≈33%）；
    A2 纯 FTS5 能凭版本 token 锁死目标版本、却无法区分模块 A/B（≈50%）；
    唯有混合融合能同时锁定 {模块, 版本}。

★ memory_id 平局陷阱规避（Captain 实测：FTS 给 A38 与 B38 完全同分 0.1052，
  排序回退到 memory_id 字典序兜底；若 A 侧 id 永远靠前，A2 会被字典序假性抬高）：
  - 记忆 id 采用中性编号 "<case_id>_M01..M06"，不含模块字母；
  - 每 case 的模块落位顺序（AB = A 三节点在前 / BA = B 三节点在前）按确定性集合
    分配：24 题中 AB-first 12 题、BA-first 12 题；A-target 题 6 题 AB + 6 题 BA，
    B-target 题同理，使 FTS 平局时字典序兜底「恰好帮到期望答案」的比例在每题、
    每模块口径下都精确 = 12/24 = 50%，与蓝图 A2≈50% 的统计期望一致，无系统性偏差。

结构约束（与 phase4_hard_negatives_20.json 同构）：
  顶层 {case_count, cases, dataset, version, generator, determinism, ...}
  case {case_id, entity_kind, identifier, expected_id, expected_top3,
        module, memories[], query, ...}；memory 含 content/id/subject/predicate
        /memory_type/input_weight/step/value 等 phase4 既有字段。

纯标准库、确定性生成（无 random/time/env，连跑两次逐字节相同）；脚本尾部原位
自校验，任何一条失败立即非零退出并打印失败原因。

用法：python benchmarks/build_phase5_e3_collision.py
"""
from __future__ import print_function

import hashlib
import json
import os
import re as _re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "benchmarks", "data", "phase5_e3_collision_disambiguation.json")

MODULE_A = u"分布式账务清算服务"
MODULE_B = u"边缘网关流控中间件"
PARAM_A = "settlement_timeout_ms"
PARAM_B = "flow_control_timeout_ms"
SURROGATE_A = u"支付对账系统"              # 语义改写：与「分布式账务清算」零字面重叠
SURROGATE_B = u"设备接入限速决策器"        # 语义改写：与「边缘网关流控中间件」零字面重叠
PREDICATE = u"超时参数配置记录"

TEMPLATE_A = (
    u"在分布式账务清算服务上线{V}的变更评审里，清算治理组把账期结算请求的超时参数固化为一条配置记忆："
    u"结算链路超时阈值 settlement_timeout_ms 调整为 {T} 毫秒，同时保留幂等去重窗口与清算补偿回退开关，"
    u"并把该取值登记进当次发布基线；该配置上线后运转平稳，未再出现清算超时误判或重复结算，"
    u"同模块各小版本共用同一配置模板，仅版本号与取值不同，评审时按版本逐条核对即可。"
)
TEMPLATE_B = (
    u"在边缘网关流控中间件上线{V}的变更评审里，边缘侧维护组把南向请求的超时参数固化为一条配置记忆："
    u"网关侧超时阈值 flow_control_timeout_ms 调整为 {T} 毫秒，同时保留令牌桶平滑整形与降级回退开关，"
    u"并把该取值登记进当次发布基线；该配置上线后运转平稳，未再出现链路超时误判或请求积压，"
    u"同模块各小版本共用同一配置模板，仅版本号与取值不同，评审时按版本逐条核对即可。"
)

# 6 个同符号版本族：每族三个版本号，A/B 两模块部署完全相同的集合（实验命门）；
# 同一版本号在 A/B 中的超时值不同；同模块内各版本超时值亦互不相同。
FAMILIES = [
    {"id": "F1", "versions": ["v2.14.37", "v2.14.38", "v2.14.39"],
     "timeouts": {"A": ["25000", "30000", "36000"], "B": ["1200", "1500", "1800"]}},
    {"id": "F2", "versions": ["v3.9.4", "v3.9.5", "v3.9.6"],
     "timeouts": {"A": ["20000", "24000", "28000"], "B": ["900", "1000", "1200"]}},
    {"id": "F3", "versions": ["v1.8.2", "v1.8.3", "v1.8.4"],
     "timeouts": {"A": ["15000", "18000", "22000"], "B": ["700", "800", "950"]}},
    {"id": "F4", "versions": ["v2.4.10", "v2.4.11", "v2.4.12"],
     "timeouts": {"A": ["30000", "35000", "40000"], "B": ["1500", "1800", "2000"]}},
    {"id": "F5", "versions": ["v0.7.3", "v0.7.4", "v0.7.5"],
     "timeouts": {"A": ["12000", "15000", "19000"], "B": ["500", "650", "800"]}},
    {"id": "F6", "versions": ["v4.2.0", "v4.2.1", "v4.2.2"],
     "timeouts": {"A": ["22000", "26000", "31000"], "B": ["1000", "1300", "1500"]}},
]

# 每族的出题槽位：A 首版 / A 中版 / B 中版 / B 末版（目标模块均衡 12:12）
TARGET_SLOTS = [("A", 0), ("A", 1), ("B", 1), ("B", 2)]

# memory_id 模块落位顺序：AB = 模块A 三节点取 M01..M03、模块B 取 M04..M06；
# BA = 反之。确定性集合（case 编号 1..24），AB-first 12 题 / BA-first 12 题，
# 且 A-target 与 B-target 各 6 AB + 6 BA → FTS 平局字典序兜底恰好在 A/B 各半
# 的题目上命中期望答案（12/24），A2 不会被 id 方案系统性抬高或压低。
AB_FIRST_CASES = frozenset({1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 15})

re_cjk = _re.compile(u"[\u4e00-\u9fff]+")

def cjk_bigrams(text):
    """与 gated_mem.schema.tokenize 相同的 CJK 单字+相邻二元组切分（泄漏自检用）。"""
    out = set()
    s = unicodedata.normalize("NFKC", text)
    for run in re_cjk.findall(s):
        out.update(run)
        if len(run) >= 2:
            for i in range(len(run) - 1):
                out.add(run[i:i + 2])
    return out


def make_case(case_no, fam, target_mod, ver_idx):
    cid = "E3%02d" % case_no
    vers = fam["versions"]
    target_ver = vers[ver_idx]
    order = "AB" if case_no in AB_FIRST_CASES else "BA"
    mods = ["A", "B"] if order == "AB" else ["B", "A"]

    mems = []
    mem_no = 1
    for mod in mods:
        named = MODULE_A if mod == "A" else MODULE_B
        param = PARAM_A if mod == "A" else PARAM_B
        tmpl = TEMPLATE_A if mod == "A" else TEMPLATE_B
        for vi in range(3):
            ver = vers[vi]
            timeout = fam["timeouts"][mod][vi]
            mems.append({
                "content": tmpl.format(V=ver, T=timeout),
                "id": "%s_M%02d" % (cid, mem_no),
                "identifier": ver,
                "input_weight": 0.5,
                "memory_type": "DECISION",
                "module": mod,
                "param": param,
                "predicate": PREDICATE,
                "step": mem_no,
                "subject": named,
                "timeout_ms": int(timeout),
                "value": timeout,
                "version": ver,
            })
            mem_no += 1

    expected = [m for m in mems if m["module"] == target_mod and m["version"] == target_ver]
    assert len(expected) == 1, "期望答案必须唯一"
    expected = expected[0]
    twin = [m for m in mems if m["module"] != target_mod and m["version"] == target_ver]
    assert len(twin) == 1, "碰撞孪生（另一模块同版本）必须唯一"
    twin = twin[0]

    surrogate = SURROGATE_A if target_mod == "A" else SURROGATE_B
    query = u"当%s升级到 %s 时，超时参数应配置为多少？" % (surrogate, target_ver)
    named_target = MODULE_A if target_mod == "A" else MODULE_B
    param_target = PARAM_A if target_mod == "A" else PARAM_B

    # FTS 平局（A38/B38 同分）时按 id 字典序兜底：本 case 兜底是否帮到期望答案
    tiebreak_favors = (order == "AB") == (target_mod == "A")

    return {
        "case_id": cid,
        "entity_kind": "config_version",
        "identifier": target_ver,
        "expected_id": expected["id"],
        "expected_top3": [expected["id"]],
        "module": named_target,
        "target_module": target_mod,
        "module_a": MODULE_A,
        "module_b": MODULE_B,
        "surrogate": surrogate,
        "version_family": list(vers),
        "module_order_in_ids": order,
        "collision_twin": twin["id"],
        "tiebreak_favors_expected": tiebreak_favors,
        "expected_value": expected["value"],
        "expected_param": param_target,
        "memories": mems,
        "query": query,
        "description": u"「%s」升级到 %s 时超时配置的跨模块同符号消歧（目标模块 %s）" % (
            surrogate, target_ver, target_mod),
        "construction_note": (
            u"同版本号集合 %s 在模块 A（%s）与模块 B（%s）中完全相同，A2 纯 FTS5 仅能"
            u"靠版本 token 把候选锁到 %s 的 {期望, 孪生} 两节点（实测两节点 FTS 同分，"
            u"排序退化为 id 字典序兜底）；模块名只以语义改写「%s」出现在查询中（与模块"
            u"原文零字面重叠），A1 单向量需依赖 FastEmbed 语义桥认模块、在微差版本上坍缩。"
            u"记忆 id 为中性编号 M01..M06，本 case 模块落位 %s（%s三节点在前），"
            u"字典序兜底%s期望答案。期望答案唯一：%s 的 %s = %s 毫秒（%s）。"
            % ("/".join(vers), MODULE_A, MODULE_B, target_ver, surrogate, order,
               MODULE_A if order == "AB" else MODULE_B,
               u"命中" if tiebreak_favors else u"不命中",
               named_target, param_target, expected["value"], expected["id"])
        ),
    }


def build():
    cases = []
    idx = 1
    for fam in FAMILIES:
        for (mod, vi) in TARGET_SLOTS:
            cases.append(make_case(idx, fam, mod, vi))
            idx += 1

    dataset = {
        "dataset": "phase5_e3_collision_disambiguation",
        "version": "1.0.0",
        "case_count": len(cases),
        "memories_per_case": 6,
        "generator": "benchmarks/build_phase5_e3_collision.py",
        "determinism": u"纯字面模板生成；无 random/time/env；连跑两次逐字节相同",
        "description": (
            u"E3 跨模块同符号碰撞消歧基准：模块 A（分布式账务清算服务）与模块 B（边缘网关流控中间件）"
            u"在每一 case 内共享完全相同的版本号集合（v2.14.37/.38/.39 等 6 个同符号版本族），"
            u"同一版本号在两模块中的超时配置值不同；查询 = 语义改写（支付对账系统 / 设备接入限速决策器，"
            u"与模块全称零字面重叠）+ 精确版本符号。单向量 A1 能认模块认不出微差版本（≈33%），"
            u"单 FTS5 A2 能锁版本认不出模块（≈50%），唯有混合融合同时锁定{模块, 版本}。"
            u"每题期望答案唯一。记忆 id 为中性编号（M01..M06），模块落位顺序 AB/BA 各 12 题，"
            u"FTS 平局的字典序兜底精确抵销，无系统性偏差。"
        ),
        "modules": {"A": MODULE_A, "B": MODULE_B},
        "surrogates": {"A": SURROGATE_A, "B": SURROGATE_B},
        "cases": cases,
    }
    return dataset


def self_check(dataset):
    problems = []
    cases = dataset["cases"]
    all_ids = set()
    sur_a_bg = {t for t in cjk_bigrams(SURROGATE_A) if len(t) >= 2}
    sur_b_bg = {t for t in cjk_bigrams(SURROGATE_B) if len(t) >= 2}

    if dataset["case_count"] != len(cases) or len(cases) < 20:
        problems.append("case_count != len(cases) 或不足 20")
    ab_ids = 0
    fav_count = 0
    for c in cases:
        mems = c["memories"]
        cid = c["case_id"]
        if len(mems) != 6:
            problems.append("%s: 记忆数 != 6" % cid)
        a_vers = sorted(m["version"] for m in mems if m["module"] == "A")
        b_vers = sorted(m["version"] for m in mems if m["module"] == "B")
        if a_vers != b_vers or a_vers != sorted(c["version_family"]):
            problems.append("%s: 版本集合A/B不一致或与family不符" % cid)
        if len(set(a_vers)) != 3:
            problems.append("%s: 版本号集合须为3个不同版本" % cid)
        got = [m["id"] for m in mems]
        if got != ["%s_M%02d" % (cid, i) for i in range(1, 7)]:
            problems.append("%s: 记忆 id 非连续中性编号 M01..M06" % cid)
        first_mods = [m["module"] for m in mems]
        if c["module_order_in_ids"] == "AB":
            if first_mods != ["A", "A", "A", "B", "B", "B"]:
                problems.append("%s: module_order_in_ids=AB 但落位不符" % cid)
        else:
            if first_mods != ["B", "B", "B", "A", "A", "A"]:
                problems.append("%s: module_order_in_ids=BA 但落位不符" % cid)
        ab_ids += 1 if c["module_order_in_ids"] == "AB" else 0
        # 同版本号跨模块必须不同超时值
        for v in c["version_family"]:
            ta = [m["timeout_ms"] for m in mems if m["module"] == "A" and m["version"] == v]
            tb = [m["timeout_ms"] for m in mems if m["module"] == "B" and m["version"] == v]
            if not (len(ta) == 1 and len(tb) == 1 and ta[0] != tb[0]):
                problems.append("%s: 版本 %s 跨模块超时值须存在且不同" % (cid, v))
        # 期望唯一性
        hits = [m for m in mems if m["module"] == c["target_module"] and m["version"] == c["identifier"]]
        if len(hits) != 1 or hits[0]["id"] != c["expected_id"]:
            problems.append("%s: 期望答案不唯一或 expected_id 错位" % cid)
        if c["expected_top3"] != [c["expected_id"]]:
            problems.append("%s: expected_top3 应为 [expected_id]" % cid)
        # 查询：含改写+精确符号，不含模块全称
        if c["surrogate"] not in c["query"]:
            problems.append("%s: 查询缺少语义改写" % cid)
        if c["identifier"] not in c["query"]:
            problems.append("%s: 查询缺少精确版本符号" % cid)
        if MODULE_A in c["query"] or MODULE_B in c["query"]:
            problems.append("%s: 查询泄漏模块全称" % cid)
        # 碰撞孪生 + tiebreak 属性
        tw = [m for m in mems if m["module"] != c["target_module"] and m["version"] == c["identifier"]]
        if len(tw) != 1 or tw[0]["id"] != c["collision_twin"]:
            problems.append("%s: collision_twin 错位" % cid)
        tiebreak_favors = (c["module_order_in_ids"] == "AB") == (c["target_module"] == "A")
        if tiebreak_favors != c["tiebreak_favors_expected"]:
            problems.append("%s: tiebreak_favors_expected 计算不一致" % cid)
        if tiebreak_favors:
            fav_count += 1
        # 改写词不得泄漏进任意记忆正文（二元组级）
        for m in mems:
            for t in (sur_a_bg | sur_b_bg):
                if t in m["content"]:
                    problems.append("%s/%s: 改写词 token %s 泄漏进记忆正文" % (cid, m["id"], t))
        # 逐记忆基础字段
        for m in mems:
            if m["id"] in all_ids:
                problems.append("%s: id 全局重复" % m["id"])
            all_ids.add(m["id"])
            if m["memory_type"] not in ("DECISION", "CONSTRAINT", "PREFERENCE", "EPHEMERAL"):
                problems.append("%s: 非法 memory_type" % m["id"])
            if not (0.1 <= m["input_weight"] <= 1.0):
                problems.append("%s: input_weight 越界" % m["id"])
            if m["step"] != int(m["id"].split("_M")[1]):
                problems.append("%s: step 与 id 序号不一致" % m["id"])
            if m["value"] != str(m["timeout_ms"]):
                problems.append("%s: value/timeout_ms 不一致" % m["id"])
    # 全局均衡：目标模块 A/B 各半；AB-first 12 题；tiebreak 兜底命中期望 12 题
    a_targets = sum(1 for c in cases if c["target_module"] == "A")
    b_targets = sum(1 for c in cases if c["target_module"] == "B")
    if a_targets != b_targets:
        problems.append("目标模块不均衡: A=%d B=%d" % (a_targets, b_targets))
    if ab_ids != 12:
        problems.append("AB-first 应为 12 题, 实得 %d" % ab_ids)
    if fav_count != 12:
        problems.append("tiebreak 兜底命中期望应是 12/24, 实得 %d" % fav_count)
    return problems


def main():
    dataset = build()
    problems = self_check(dataset)
    if problems:
        print("FAIL %d 项自检问题:" % len(problems))
        for p in problems:
            print("  -", p)
        sys.exit(1)

    text = json.dumps(dataset, ensure_ascii=False, indent=2) + "\n"
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    a_count = sum(1 for c in dataset["cases"] if c["target_module"] == "A")
    b_count = sum(1 for c in dataset["cases"] if c["target_module"] == "B")
    ab_ids = sum(1 for c in dataset["cases"] if c["module_order_in_ids"] == "AB")
    fams = sorted(set("/".join(c["version_family"]) for c in dataset["cases"]))
    print("OK 自检通过：%d cases（目标 A=%d, B=%d），memory_id 中性编号 M01..M06，AB-first %d 题 / BA-first %d 题"
          % (len(dataset["cases"]), a_count, b_count, ab_ids, len(dataset["cases"]) - ab_ids))
    print("  同符号版本族 %d 个：" % len(fams))
    for f in fams:
        print("    ", f)
    print("字节数:", len(text.encode("utf-8")))
    print("sha256:", hashlib.sha256(text.encode("utf-8")).hexdigest())

    # 样例输出（任务要求：贴 1 个样例）
    for c in dataset["cases"]:
        if c["case_id"] == "E302":
            print("=== 样例 case " + c["case_id"] + " ===")
            print("  query:", c["query"])
            print("  expected_id:", c["expected_id"], " expected_value:", c["expected_value"],
                  " collision_twin:", c["collision_twin"], " module_order_in_ids:", c["module_order_in_ids"],
                  " tiebreak_favors_expected:", c["tiebreak_favors_expected"])
            for m in c["memories"]:
                print("  mem %s module=%s version=%s timeout_ms=%s" % (m["id"], m["module"], m["version"], m["timeout_ms"]))
            break
    print("OUT:", os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    main()
