"""生成阶段五 E3 跨模块同符号碰撞评测集。

设计铁律（任何一条被破坏，整张对照表作废）：

  1. **目标模块随机化**：一半题目的正确答案落在模块 A 侧，另一半落在模块 B 侧。
  2. **记忆 id 中性化**：每题统一 M01..M06，且「目标模块的 id 是否字典序更小」
     逐题交替，与「目标模块是 A 还是 B」**正交**。
  3. **同版本号集合**：每题模块 A 与模块 B 拥有完全相同的版本号集合
     v2.14.37 / .38 / .39，只有超时参数值不同。
  4. **题量 >= 20**。
  5. **查询用语义改写表达模块名 + 精确符号表达版本号**。
  6. **正文绝不出现模块正面名**。

第 2 条与第 6 条的理由要写清楚，它们直接决定这张表有没有意义：

  * 关于 id：FTS5 精确命中 v2.14.38 时，两个模块的那条记忆拿到的是**完全相同**的
    bm25 分（队长实测 0.1052 == 0.1052）。同分下排序退化为 memory_id 字典序。
    如果目标 id 系统性地落在字典序最小处，A2 纯 FTS5 就会白捡高准确率，整张对照表
    作废。这里让 (目标侧, id 极性) 两两组合各出现 5 次，A2 的平局胜率被压到纯抛硬币
    的 50%，且可在报告里逐题复核。

  * 关于正文：模块正面名（如「分布式账务清算服务」）一旦出现在正文里，纯向量通道与
    FTS 通道就会靠**字面重合**命中模块，掩盖掉「版本号消歧」这个真正的考点。队长
    实测过这种偶然（A 模块正文重复模块名导致 VEC/FTS 的 Top-1 都恰好是 A38）。
    所以正文只用参数键名与业务描述词区分模块，不写模块名。

确定性：本脚本不使用随机数。所有「随机化」都是可复现的轮转：
    目标侧   = i % 2
    id 极性  = (i // 2) % 2
    版本轮换 = i % 3
任何机器重跑得到逐字节相同的文件。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

VERSIONS = ("v2.14.37", "v2.14.38", "v2.14.39")
DEFAULT_OUT = "benchmarks/data/phase5_e3_collision_disambiguation.json"

# (模块代号, 模块正面名, 语义改写说法 list, 超时参数键, 基值, 业务描述词)
MODULES = [
    (
        "A",
        "分布式账务清算服务",
        ["支付对账系统", "交易对账平台", "清结算后台"],
        "settle_timeout_ms",
        3000,
        "跨机房清算批次",
    ),
    (
        "B",
        "边缘网关流控中间件",
        ["网关限流层", "API 流量网关", "边缘接入代理"],
        "upstream_timeout_ms",
        800,
        "边缘节点上游转发",
    ),
]

TOPICS = [
    "联调复盘", "灰度发布", "容量压测", "故障演练", "季度巡检",
    "版本升级评审", "线上事故复盘", "配置基线审计", "跨团队契约对齐", "灾备切换演练",
]

QUERY_TEMPLATES = [
    "当{alias}升级到 {version} 时，超时参数应该配成多少？",
    "{alias} 这次要升到 {version}，请确认那时的超时配置。",
    "{version} 版本的{alias}，超时到底该取哪个值？",
    "我们要把{alias}的版本钉到 {version}，超时参数随之改成多少？",
    "关于{alias}在 {version} 下的超时设置，最终结论是什么？",
]


def _content(extra: str, key: str, value: int, topic: str, version: str) -> str:
    """构造正文。

    **刻意不写模块正面名**（见模块级 docstring 第 6 条）。模块之间只靠
    「业务描述词 + 参数键名」区分，版本之间只靠版本号字面区分。
    """
    return (
        "在%s的结论里，%s这条配置被正式固化：%s 取 %d 毫秒，"
        "并要求与同批次的其它参数一起纳入变更单逐项核对；"
        "该取值与 %s 这个版本号严格绑定，换版本必须重新评估，"
        "严禁套用相邻版本的数值。"
        % (topic, extra, key, value, version)
    )


def build() -> dict:
    cases = []
    for i in range(20):
        topic = TOPICS[i % len(TOPICS)]
        target_side = i % 2          # 0 -> A 侧, 1 -> B 侧（各 10 题）
        id_polarity = (i // 2) % 2   # 0 -> A 模块拿小 id, 1 -> B 模块拿小 id
        version = VERSIONS[i % len(VERSIONS)]
        query = QUERY_TEMPLATES[i % len(QUERY_TEMPLATES)]

        memories = []
        cursor = 1
        # 先决定每个模块分到的 id 段
        small_mod_idx = 0 if id_polarity == 0 else 1
        for side_idx, (code, name, aliases, key, base, extra) in enumerate(MODULES):
            first = 1 if side_idx == small_mod_idx else 4
            for j, ver in enumerate(VERSIONS):
                mid = "M%02d" % (first + j)
                if ver == version:
                    value = base + (i * 137) % 500
                else:
                    value = base + 111 * (j + 1) + (i * 71) % 300
                memories.append({
                    "id": mid,
                    "content": _content(extra, key, value, topic, ver),
                    "subject": name,
                    "predicate": key,
                    "scope": "global",
                    "memory_type": "DECISION",
                    "input_weight": 0.5,
                    "step": cursor,
                    "module": code,
                    "module_name": name,
                    "version": ver,
                    "value": str(value),
                })
                cursor += 1

        target_code = "A" if target_side == 0 else "B"
        expected = [m for m in memories
                    if m["module"] == target_code and m["version"] == version]
        expected_id = expected[0]["id"]
        alias = MODULES[target_side][2][i % len(MODULES[target_side][2])]

        # 在平局集合（两条同版本记忆）里，目标是否字典序最小 —— 供报告审计
        tie_pair = sorted([m["id"] for m in memories if m["version"] == version])
        target_is_lex_min = expected_id == tie_pair[0]

        cases.append({
            "case_id": "E3_%02d" % (i + 1),
            "query_tag": "q1",
            "query": query.format(alias=alias, version=version),
            "expected_id": expected_id,
            "expected_top3": [expected_id],
            "expected_value": expected[0]["value"],
            "target_module": target_code,
            "target_module_name": MODULES[target_side][1],
            "target_alias": alias,
            "version": version,
            "id_polarity": id_polarity,
            "target_is_lex_min_in_tie": target_is_lex_min,
            "memories": memories,
        })

    return {
        "dataset_version": "1.0.0",
        "case_count": len(cases),
        "generator": "benchmarks/tools/build_phase5_e3.py",
        "design_notes": {
            "target_module_balanced": "target_side = i % 2，A 侧 10 题 / B 侧 10 题",
            "neutral_memory_ids": "每题 M01..M06；(目标侧, id 极性) 两两组合各 5 次，正交",
            "same_version_set": "A 与 B 拥有完全相同的版本号集合 v2.14.37/.38/.39",
            "no_module_name_in_content": "正文不出现模块正面名，只靠参数键名与业务描述词区分",
            "version_rotation": "版本 = VERSIONS[i % 3]，避免答案恒为中间版本",
            "deterministic": "无随机数；全部为 i 的轮转，重跑逐字节一致",
        },
        "cases": cases,
    }


def audit(data: dict) -> dict:
    """数据集自检：目标侧 / id 极性 / 平局字典序 三项平衡性。"""
    cases = data["cases"]
    n = len(cases)
    by_side = {"A": 0, "B": 0}
    by_polarity = {0: 0, 1: 0}
    lex_min = 0
    for c in cases:
        by_side[c["target_module"]] += 1
        by_polarity[c["id_polarity"]] += 1
        if c["target_is_lex_min_in_tie"]:
            lex_min += 1
    # A2 的历史性偏差：若目标恒为字典序最小，A2 会白捡
    return {
        "cases": n,
        "target_side": by_side,
        "id_polarity": {str(k): v for k, v in by_polarity.items()},
        "target_is_lex_min_in_tie": lex_min,
        "expected_lex_min_rate": round(lex_min / float(n), 4),
        "no_module_name_in_content": not any(
            m["module_name"] in m["content"]
            for c in cases for m in c["memories"]
        ),
        "alias_absent_from_content": not any(
            c["target_alias"] in m["content"]
            for c in cases for m in c["memories"]
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 E3 碰撞消歧评测集")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()
    data = build()
    a = audit(data)
    data["audit"] = a
    out_dir = os.path.dirname(args.out)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(payload)
    print("wrote %s" % args.out)
    print("cases=%d  sha256=%s" % (data["case_count"],
                                   hashlib.sha256(payload.encode("utf-8")).hexdigest()))
    print(json.dumps(a, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
