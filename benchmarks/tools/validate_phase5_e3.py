# -*- coding: utf-8 -*-
"""E3 跨模块同符号碰撞消歧基准集独立校验器 (phase5)。

与 phase1 的 benchmarks/tools/validate_dataset.py 同等的定位：结构契约 + 实验
命门双重校验。仅在标准库 + gated_mem.schema.tokenize（src 在 sys.path 中）下运行：

  1. JSON 可解析；case_count / memories_per_case / dataset 元信息一致；
  2. 每 case 恰 6 条记忆，id 为中性编号 <case_id>_M01..M06 且按序；
  3. A/B 两模块版本号集合完全相等且 == version_family（3 个互异版本）；
  4. 同版本号跨模块超时值不同（正确答案唯一，且每 case 期望答案唯一）；
  5. 目标模块 A/B 各半（12:12）；模块落位 AB/BA 各 12 题；FTS 平局字典序兜底
     命中期望答案恰 12/24（无系统性偏差）；
  6. 版本 token 碰撞对校验：query identifier 的全部版本 token 同时出现在
     content 的记忆恰为 {expected, twin} 两节点（A2 纯 FTS5 的候选锁定点）；
  7. 改写词二元组不得泄漏进任何记忆正文（保证 A1 需依赖语义桥、A2 无法凭改写
     词消歧）；查询不得包含任一模块全称。

用法：python benchmarks/tools/validate_phase5_e3.py [JSON路径]
退出码：0 = 全部通过；1 = 任一校验失败。
"""
from __future__ import print_function

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

DEFAULT = os.path.join(ROOT, "benchmarks", "data", "phase5_e3_collision_disambiguation.json")
MODULE_A = u"分布式账务清算服务"
MODULE_B = u"边缘网关流控中间件"


def cjk_bigrams(text):
    import re as _re
    out = set()
    for run in _re.findall(u"[\u4e00-\u9fff]+", text):
        out.update(run)
        if len(run) >= 2:
            for i in range(len(run) - 1):
                out.add(run[i:i + 2])
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    blob = open(path, "rb").read()
    try:
        text = blob.decode("utf-8")
        d = json.loads(text)
    except Exception as e:  # noqa
        print("FAIL: JSON 解析失败(%s): %s" % (path, e))
        return 1

    problems = []
    cases = d.get("cases", [])
    cc = d.get("case_count")
    if cc != len(cases) or len(cases) < 20:
        problems.append("case_count(%s) 与 len(cases)(%d) 不一致或不足 20" % (cc, len(cases)))
    if d.get("memories_per_case") != 6:
        problems.append("memories_per_case 应为 6")
    if d.get("dataset") != "phase5_e3_collision_disambiguation":
        problems.append("dataset 标识不符")

    sur_a = {t for t in cjk_bigrams(d.get("surrogates", {}).get("A", u"")) if len(t) >= 2}
    sur_b = {t for t in cjk_bigrams(d.get("surrogates", {}).get("B", u"")) if len(t) >= 2}

    a_t, b_t, ab_o, fav = 0, 0, 0, 0
    all_ids = set()
    for c in cases:
        cid = c["case_id"]
        mems = c.get("memories", [])
        if len(mems) != 6:
            problems.append("%s: 记忆数 != 6" % cid)
        ids = [m["id"] for m in mems]
        if ids != ["%s_M%02d" % (cid, i) for i in range(1, 7)]:
            problems.append("%s: id 非连续中性编号 M01..M06" % cid)
        if len(set(ids)) != 6:
            problems.append("%s: id 重复" % cid)
        all_ids.update(ids)
        # 版本集合相等
        a_vers = sorted(m["version"] for m in mems if m["module"] == "A")
        b_vers = sorted(m["version"] for m in mems if m["module"] == "B")
        fam = sorted(c["version_family"])
        if a_vers != b_vers or a_vers != fam or len(set(a_vers)) != 3:
            problems.append("%s: 版本集合A/B不等或与family不符" % cid)
        # 跨模块同版本超时不同
        for v in fam:
            ta = [m for m in mems if m["module"] == "A" and m["version"] == v]
            tb = [m for m in mems if m["module"] == "B" and m["version"] == v]
            if len(ta) != 1 or len(tb) != 1 or ta[0]["timeout_ms"] == tb[0]["timeout_ms"]:
                problems.append("%s: 版本 %s 跨模块超时须存在且不同" % (cid, v))
        # 期望唯一
        hits = [m for m in mems if m["module"] == c["target_module"] and m["version"] == c["identifier"]]
        if len(hits) != 1 or hits[0]["id"] != c["expected_id"]:
            problems.append("%s: 期望答案不唯一或错位" % cid)
        if c["expected_top3"] != [c["expected_id"]]:
            problems.append("%s: expected_top3 != [expected_id]" % cid)
        # 查询约束
        if c["surrogate"] not in c["query"] or c["identifier"] not in c["query"]:
            problems.append("%s: 查询缺改写或缺精确版本符号" % cid)
        if MODULE_A in c["query"] or MODULE_B in c["query"]:
            problems.append("%s: 查询泄漏模块全称" % cid)
        # 模块落位
        order = c["module_order_in_ids"]
        fm = [m["module"] for m in mems]
        expect_fm = (["A"] * 3 + ["B"] * 3) if order == "AB" else (["B"] * 3 + ["A"] * 3)
        if fm != expect_fm:
            problems.append("%s: 模块落位与声明 %s 不符" % (cid, order))
        ab_o += 1 if order == "AB" else 0
        tf = (order == "AB") == (c["target_module"] == "A")
        if tf != c["tiebreak_favors_expected"]:
            problems.append("%s: tiebreak 属性不一致" % cid)
        fav += 1 if tf else 0
        a_t += 1 if c["target_module"] == "A" else 0
        b_t += 1 if c["target_module"] == "B" else 0
        # 改写词泄漏 + 碰撞对（version tokens）
        from gated_mem.schema import tokenize
        vt = tokenize(c["identifier"])
        coll = [m for m in mems if all(t in tokenize(m["content"]) for t in vt)]
        if len(coll) != 2 or sorted(m["id"] for m in coll) != sorted([c["expected_id"], c["collision_twin"]]):
            problems.append("%s: 版本token碰撞对非 {expected, twin}" % cid)
        for m in mems:
            for t in (sur_a | sur_b):
                if t in m["content"]:
                    problems.append("%s/%s: 改写词 %s 泄漏" % (cid, m["id"], t))
    if a_t != b_t:
        problems.append("目标模块不均衡 A=%d B=%d" % (a_t, b_t))
    if ab_o != 12:
        problems.append("AB-first 应 12，实得 %d" % ab_o)
    if fav != 12:
        problems.append("tiebreak 兜底命中期望应 12，实得 %d" % fav)

    if problems:
        print("FAIL: %d 项问题" % len(problems))
        for p in problems:
            print("  -", p)
        return 1

    print("VALIDATE_OK cases=%d memories_per_case=6 targets_A=%d targets_B=%d order_AB=%d order_BA=%d tiebreak_favors=%d" % (
        len(cases), a_t, b_t, ab_o, len(cases) - ab_o, fav))
    print("file_bytes=%d utf8_parsed=%s sha256=%s" % (len(blob), "yes", hashlib.sha256(blob).hexdigest()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
