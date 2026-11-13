"""宽松匹配。

MemoryAgentBench 官方判分用的是 substring_exact_match / exact_match，
极其严格：真值是 "43" 时，模型输出 "label: 43" 会被判错。

MAB README 原话：
    "For exact_match, the parsing is strict — e.g., if the ground-truth label
     is "43" but the model returns "label: 43", it will be counted as incorrect.
     We recommend flexible parsing when adapting the benchmark to your own pipeline."

所以适配到自己的 pipeline 时必须加宽松解析，否则分数会系统性虚低。
"""

from __future__ import annotations

import re
import unicodedata

_ANSWER_PREFIX = re.compile(
    r"^\s*(?:ANSWER|答案|最终答案)\s*[:：]\s*", re.IGNORECASE
)
_LABEL_PREFIX = re.compile(
    r"^\s*(?:label|答案|选项|choice|option)\s*[:：]?\s*", re.IGNORECASE
)
_QUOTES = "\"'`“”‘’"
_PUNCT_TAIL = re.compile(r"[\s。．.、,，;；:：!！?？]+$")


def normalize(text: str) -> str:
    """NFKC + 去首尾空白/引号/句末标点 + 小写。"""
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).strip()
    s = s.strip(_QUOTES).strip()
    s = _PUNCT_TAIL.sub("", s)
    return s.lower()


def strip_prefixes(text: str) -> str:
    """剥掉 ANSWER: / label: 之类的前缀，可能有多层。"""
    s = text
    for _ in range(3):  # 最多剥三层，防死循环
        before = s
        s = _ANSWER_PREFIX.sub("", s)
        s = _LABEL_PREFIX.sub("", s)
        if s == before:
            break
    return s.strip()


def match(prediction: str, golds) -> bool:
    """宽松匹配。

    golds 可以是 str，也可以是 list[str]（MAB 的 answers 是 list[list[str]]，
    每个题可能有多个可接受答案）。任一命中即算对。
    """
    if prediction is None:
        return False
    if isinstance(golds, str):
        golds = [golds]

    cand = strip_prefixes(str(prediction))
    cand_n = normalize(cand)
    if not cand_n:
        return False

    for g in golds:
        g_n = normalize(g)
        if not g_n:
            continue
        # 1) 完全相等
        if cand_n == g_n:
            return True
        # 2) 真值被答案包含（答案更长，如 "the answer is 43"）
        if g_n in cand_n:
            # 防 "4" 命中 "43" 这类子串误判：仅当真值长度 >= 2 或边界匹配
            if len(g_n) >= 2:
                return True
            if re.search(r"(?:^|\D)%s(?:\D|$)" % re.escape(g_n), cand_n):
                return True
        # 3) 答案是真值的一部分（答案更短，如真值 "the answer is 43"，答案 "43"）
        if cand_n in g_n and len(cand_n) >= 2:
            return True

    return False


def is_in_pool(prediction: str, golds, distractor_pool=None) -> bool:
    """输出是否落在候选集合内（in-pool）。

    这一项必须和准确率一起报：否则"大量拒答/输出格式错误"会伪装成
    "低污染率"。StateMem 论文 §6.3 明确警告过这个陷阱——
    LightMem drift-rate 仅 14.9%，但 accuracy 只有 0.012，因为它 84% 的
    回答落在候选池之外，根本没在回答问题。
    """
    if prediction is None:
        return False
    cand_n = normalize(strip_prefixes(str(prediction)))
    if not cand_n:
        return False
    if match(prediction, golds):
        return True
    for d in (distractor_pool or []):
        d_n = normalize(d)
        if d_n and (cand_n == d_n or d_n in cand_n):
            return True
    return False


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    cases = [
        ("43", ["43"], True),
        ("label: 43", ["43"], True),
        ("ANSWER: 43", ["43"], True),
        ("答案：43。", ["43"], True),
        ('"43"', ["43"], True),
        ("the answer is 43", ["43"], True),
        # 宽松匹配的设计目标就是容忍这类格式差异，故判 True
        ("43.0", ["43"], True),
        ("43 秒", ["43"], True),
        # 真正的错答案必须判 False
        ("42", ["43"], False),
        ("MySQL", ["PostgreSQL 16"], False),
        ("", ["43"], False),
        (None, ["43"], False),
        ("PostgreSQL 16", ["PostgreSQL 16", "pg16"], True),
        ("pg16", ["PostgreSQL 16", "pg16"], True),
    ]
    ok = 0
    for pred, golds, expect in cases:
        got = match(pred, golds)
        flag = "ok " if got == expect else "FAIL"
        if got == expect:
            ok += 1
        print("%s match(%r, %r) = %s (expect %s)" % (flag, pred, golds, got, expect))
    print("\n%d/%d passed" % (ok, len(cases)))
