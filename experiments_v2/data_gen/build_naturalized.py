"""E3 · 从 phase4 难负例派生「自然语言改写」查询集。

## 为什么必须做这个

现有 `phase4_hard_negatives_20.json` 的 20 条 query 全部形如：
    "配置中心热更新模块里，错误码 CFG_HOT_SYNC_FAIL_34 的对账参数记录在哪一条？"
                ↑ 模块名（5 条候选共享）        ↑ 唯一精确标识符

这是 **FTS 的主场**：唯一标识符产生高 IDF 爆发。
实测结果 FTS 单通道已 100%，融合无法超越它。

但真实开发者不会这样提问。他们会说：
    "配置中心热更新老失败，当时定的对账间隔是多少？"
                              ↑ 没有标识符

## 本脚本产出什么

对同一批 100 条记忆、同样的 expected_id，生成 4 种查询形态：

  q0_original   含精确标识符（原样，作为对照基线）
  q1_synonym    同义改写（标识符换成描述性说法）
  q2_pronoun    指代改写（"那个错误码"）
  q3_colloquial 口语改写（更自然、更口语）

这样能得到一张 **落差表**：
    含标识符时 FTS=100%，去掉标识符后 FTS=?，融合=?

如果 FTS 在改写形态上大幅掉分而融合保持，就第一次证明了
「融合确实优于任何单通道」—— 且是在不符合人工构造偏好的分布上。

## 生成方式

两种模式：
  --mode manual  只按规则做确定性改写（无需 LLM，可立即跑，质量中等）
  --mode llm     调用 LLM 生成改写（质量高，需模型配置）

默认 manual，因为它零成本、确定性、可复现。
LLM 模式留作后续增强。

用法：
    python experiments_v2/data_gen/build_naturalized.py --mode manual
    python experiments_v2/data_gen/build_naturalized.py --mode manual --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys

SRC = "benchmarks/data/phase4_hard_negatives_20.json"
OUT = "experiments_v2/data/e3_naturalized.json"

# 标识符前缀 -> 中文描述。用于把 "CFG_HOT_SYNC_FAIL_34" 这种
# 转成 "同步失败" 这类可读描述，保证改写后语义仍在但标识符消失。
PREFIX_HINTS = {
    "ERR": "报错", "CFG": "配置", "MQ": "消息队列", "PG": "数据库",
    "IDEM": "幂等", "read_buffer_size": "读缓冲大小",
    "session_gc_interval": "会话回收间隔",
    "tls_handshake_timeout": "TLS 握手超时",
    "log_rotate_max_size": "日志轮转上限",
    "rate_limit_burst": "限流突发值",
    "v2.14": "网关版本", "fw_1.8": "网卡固件", "sdk_3.4": "SDK 版本",
    "img_1.21": "镜像版本", "kmod_6.2": "内核模块",
    "reconcile_ledger": "账务对账函数",
    "parse_wire": "报文解析函数",
    "drain_flush": "刷写队列函数",
    "scrape_target": "指标抓取函数",
    "compact_sst": "SST 压实函数",
}

# entity_kind -> 该类别合适的指代说法（必须类型匹配，否则改写不自然）
PRONOUN_BY_KIND = {
    "error_code":    "那个错误码",
    "config_key":    "那个配置项",
    "version":       "那个版本号",
    "function_name": "那个函数",
}

# entity_kind -> 该类别在口语里怎么说
WHAT_BY_KIND = {
    "error_code":    "那个报错码",
    "config_key":    "那个配置值",
    "version":       "那个版本",
    "function_name": "那个函数",
}

# 口语化模板（保留模块名，去掉标识符）
COLLOQUIAL = [
    "{module}那块儿，上次{what}定成多少来着？",
    "{module}里{what}的取值，帮忙查一下记录。",
    "{module}当时{what}，是配的多少？",
]


def _hint(ident: str, kind: str = "") -> str:
    """从一个标识符猜出它的中文类别描述。

    优先用 entity_kind（最可靠），其次用前缀表，最后退化。
    """
    if kind in WHAT_BY_KIND:
        return WHAT_BY_KIND[kind]
    best = None
    best_len = -1
    for pre, hint in PREFIX_HINTS.items():
        if ident.startswith(pre) and len(pre) > best_len:
            best, best_len = hint, len(pre)
    if best:
        return best
    m = re.match(r"^([A-Za-z_]+)", ident)
    return (m.group(1) if m else "那个字段")


def _module_of(query: str) -> str:
    """从原 query 里抽出"XX模块"。"""
    m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]+模块)", query)
    return m.group(1) if m else "这个模块"


KIND_WORD = {
    "error_code": "错误码", "config_key": "配置项",
    "version": "版本", "function_name": "函数",
}
KIND_REPL = {
    "error_code": "那次报错", "config_key": "那个配置",
    "version": "那个版本", "function_name": "那个函数",
}


def _tidy(text: str) -> str:
    """清理标识符被删/替换后留下的悬空空格与重复词。"""
    s = text
    # 删掉中文字符与"的/中/里"之间的空格
    s = re.sub(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])", "", s)
    s = re.sub(r"(?<=[\u4e00-\u9fa5])\s+(?=[，。？、])", "", s)
    s = re.sub(r"(?<=[，。？、])\s+", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    # 连续重复的词（"错误码 那个错误码" -> "那个错误码"）
    s = re.sub(r"([\u4e00-\u9fa5]{2,4})\s+\1", r"\1", s)
    return s.strip()


def make_variants(case: dict) -> list[dict]:
    """对一条 case 生成 4 种查询形态。"""
    q0 = case["query"]
    kind = case.get("entity_kind", "")
    ident = case.get("identifier") or case.get("query_identifier") or ""
    module = case.get("module") or _module_of(q0)
    hint = _hint(ident, kind)
    expected = case.get("expected_id")
    rng = random.Random(hash(case.get("case_id", "")) & 0xFFFF)

    out = [{"form": "q0_original", "query": q0,
            "has_identifier": True, "expected_id": expected}]

    kind_word = KIND_WORD.get(kind)
    kind_repl = KIND_REPL.get(kind, hint)

    # q1 同义改写：整段"错误码 XXX"替换成"那次报错"，标识符消失且语法自然
    q1 = q0
    if ident:
        if kind_word:
            q1 = re.sub(re.escape(kind_word) + r"\s*" + re.escape(ident),
                        kind_repl, q1)
        q1 = q1.replace(ident, "")
        q1 = _tidy(q1)
    if len(q1) < 8:
        q1 = "%s里%s相关的那条记录是什么？" % (module, hint)
    out.append({"form": "q1_synonym", "query": q1,
                "has_identifier": False, "expected_id": expected})

    # q2 指代改写：整段"错误码 XXX"替换成"那个错误码"
    pron = PRONOUN_BY_KIND.get(kind, "那个字段")
    q2 = q0
    if ident:
        if kind_word:
            q2 = re.sub(re.escape(kind_word) + r"\s*" + re.escape(ident),
                        pron, q2)
        else:
            q2 = q2.replace(ident, pron)
        q2 = _tidy(q2)
    else:
        q2 = "%s里%s的记录是哪一条？" % (module, pron)
    out.append({"form": "q2_pronoun", "query": q2,
                "has_identifier": False, "expected_id": expected})

    # q3 口语改写
    tpl = rng.choice(COLLOQUIAL)
    q3 = _tidy(tpl.format(module=module, what=hint))
    out.append({"form": "q3_colloquial", "query": q3,
                "has_identifier": False, "expected_id": expected})

    return out


def load_cases(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        for key in ("cases", "data", "items"):
            if key in data:
                return data[key]
        raise SystemExit("无法从 %s 找到 case 列表" % path)
    return data


def build(cases: list[dict]) -> dict:
    rows = []
    for case in cases:
        cid = case.get("case_id", "?")
        memories = case.get("memories") or case.get("candidates") or []
        for v in make_variants(case):
            rows.append({
                "case_id": cid,
                "form": v["form"],
                "query": v["query"],
                "has_identifier": v["has_identifier"],
                "expected_id": v["expected_id"],
                "memory_ids": [m.get("memory_id") or m.get("id")
                               for m in memories],
            })
    payload = {"rows": rows}
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    payload["sha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        print("源数据不存在:", args.src)
        return 2

    cases = load_cases(args.src)
    print("载入 case 数:", len(cases))

    # 检查源数据里标识符字段叫什么
    sample = cases[0]
    keys = sorted(sample.keys())
    print("case 字段:", keys)
    ident_field = None
    for k in ("query_identifier", "identifier", "target_identifier"):
        if k in sample:
            ident_field = k
            break
    print("标识符字段:", ident_field or "(未找到，将用文本匹配退路)")

    payload = build(cases)
    n_rows = len(payload["rows"])
    print("生成查询条数:", n_rows, "（%d case × 4 form）" % len(cases))

    print("\n--- 样例（前 4 条 form） ---")
    shown = set()
    for r in payload["rows"]:
        if r["case_id"] == cases[0].get("case_id"):
            print("  [%s] %s" % (r["form"], r["query"]))
            shown.add(r["form"])

    if args.dry_run:
        print("\n[dry-run] 未写文件")
        return 0

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print("\n已写出:", args.out)
    print("sha256:", payload["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
