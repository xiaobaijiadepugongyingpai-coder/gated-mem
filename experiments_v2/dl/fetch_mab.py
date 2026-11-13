"""MemoryAgentBench 获取与切分。

两条路径：
  A. HuggingFace（需要 `pip install datasets` + 网络）
  B. 手动 parquet（离线可用，适合网络受限或避免反复下载）

数据事实（2026-11 核实）：
  - 仓库：https://huggingface.co/datasets/ai-hyz/MemoryAgentBench
  - 协议：MIT
  - split：Accurate_Retrieval(22) / Test_Time_Learning(6) /
           Long_Range_Understanding(110) / Conflict_Resolution(8)
  - 本实验只用 Conflict_Resolution（8 样本，但每样本带 60–100 题）
  - 字段：context / questions / answers / metadata
      metadata.haystack_sessions : 分块会话（有则用它做 ingest）
      metadata.question_types    : 题型（用于单跳/多跳分组）
      metadata.qa_pair_ids       : 题目标识

注意：本脚本只读，不修改任何既有文件。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

SPLIT = "Conflict_Resolution"
HF_NAME = "ai-hyz/MemoryAgentBench"


def load_via_hf(split: str = SPLIT):
    from datasets import load_dataset

    ds = load_dataset(HF_NAME, split=split)
    return ds


def load_via_parquet(path: str):
    """从本地 parquet 目录/文件加载。"""
    from datasets import load_dataset

    return load_dataset("parquet", data_files=path, split="train")


def iter_examples(ds):
    """统一成纯 dict 迭代，避免依赖 datasets 类型的细节。"""
    for i in range(len(ds)):
        yield i, ds[i]


def describe(ds) -> dict:
    n = len(ds)
    total_q = sum(len(ds[i]["questions"]) for i in range(n))
    qtypes: dict[str, int] = {}
    turns = 0
    for i in range(n):
        md = ds[i].get("metadata") or {}
        turns += sum(len(s) for s in (md.get("haystack_sessions") or []))
        for qt in (md.get("question_types") or []):
            qtypes[qt] = qtypes.get(qt, 0) + 1
    return {
        "split": SPLIT,
        "examples": n,
        "questions": total_q,
        "turns": turns,
        "qtypes": qtypes,
    }


def dump_normalized(ds, out_path: str) -> int:
    """落成 JSONL，方便后续 runner 不依赖 datasets 库。"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    n = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for i, ex in iter_examples(ds):
            md = ex.get("metadata") or {}
            sessions = md.get("haystack_sessions")
            if not sessions:
                # 无分块会话时，把整段 context 当成单一 session
                sessions = [[{"role": "user", "content": ex.get("context") or ""}]]
            rec = {
                "idx": i,
                "context": ex.get("context") or "",
                "sessions": sessions,
                "questions": ex.get("questions") or [],
                "answers": ex.get("answers") or [],
                "question_types": md.get("question_types") or [],
                "qa_pair_ids": md.get("qa_pair_ids") or [],
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default=SPLIT)
    ap.add_argument("--parquet", default=None,
                    help="本地 parquet 路径（离线时用）")
    ap.add_argument("--out", default="experiments_v2/data/mab_cr.jsonl")
    ap.add_argument("--dry-run", action="store_true", help="只打印规模")
    args = ap.parse_args()

    global SPLIT
    SPLIT = args.split

    try:
        ds = load_via_parquet(args.parquet) if args.parquet else load_via_hf(SPLIT)
    except ImportError:
        print("缺少 datasets 库。请先 `pip install datasets`，")
        print("或用 --parquet 指向本地已下载的 parquet 文件。")
        return 2
    except Exception as exc:
        print("加载失败:", exc)
        print("\n离线方案：")
        print("  1) 在能联网的机器上:")
        print("     huggingface-cli download ai-hyz/MemoryAgentBench "
              "--repo-type dataset --local-dir ./mab")
        print("  2) 把 ./mab 拷回本机")
        print("  3) python experiments_v2/dl/fetch_mab.py "
              "--parquet ./mab/data/Conflict_Resolution-*.parquet")
        return 3

    info = describe(ds)
    print(json.dumps(info, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0

    n = dump_normalized(ds, args.out)
    print("\n已写出 %d 条 -> %s" % (n, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
