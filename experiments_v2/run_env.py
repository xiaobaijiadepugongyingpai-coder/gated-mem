"""E0 · 环境探测 + 真实 token 实测。

目的：
  1. 确认 datasets / 模型 / src.gated_mem 是否可用
  2. 打印 MemoryAgentBench Conflict_Resolution 的真实规模
  3. 产出一张真实 token 表，替换所有估算

用法：
    python experiments_v2/run_env.py                 # 只探测，不调模型
    python experiments_v2/run_env.py --probe-model   # 额外用 3 道题实测 token

不做任何写入，不改既有文件。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback


def hr(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


# ---------------------------------------------------------------------------
def check_python() -> dict:
    info = {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "cwd": os.getcwd(),
    }
    print("python      :", info["python"])
    print("executable  :", info["executable"])
    print("cwd         :", info["cwd"])
    return info


def check_deps() -> dict:
    hr("1. 依赖探测")
    out = {}
    for mod in ("datasets", "sqlite3", "numpy"):
        try:
            if mod == "sqlite3":
                import sqlite3
                out[mod] = sqlite3.sqlite_version
                print("  %-10s : OK (sqlite %s)" % (mod, out[mod]))
            else:
                m = __import__(mod)
                out[mod] = getattr(m, "__version__", "?")
                print("  %-10s : OK (%s)" % (mod, out[mod]))
        except Exception as exc:
            out[mod] = None
            print("  %-10s : MISSING (%s)" % (mod, exc))
    return out


def check_src() -> dict:
    hr("2. src/gated_mem 可用性")
    out = {"importable": False}
    try:
        sys.path.insert(0, os.path.abspath("src"))
        import gated_mem

        out["importable"] = True
        out["version"] = getattr(gated_mem, "__version__", "?")
        out["path"] = getattr(gated_mem, "__file__", "?")
        print("  import gated_mem : OK  version=%s" % out["version"])
        print("  path             : %s" % out["path"])

        # 关键接口存在性
        from gated_mem import gates, retrieval, storage  # noqa: F401

        checks = [
            ("gates.compute_retention", hasattr(gates, "compute_retention")),
            ("gates.compute_vitality", hasattr(gates, "compute_vitality")),
            ("gates.compute_retrieval_score",
             hasattr(gates, "compute_retrieval_score")),
            ("retrieval.Retriever", hasattr(retrieval, "Retriever")),
            ("storage.Store", hasattr(storage, "Store")),
        ]
        for name, ok in checks:
            print("  %-28s : %s" % (name, "OK" if ok else "MISSING"))
            out[name] = ok
    except Exception:
        print("  FAIL:")
        traceback.print_exc()
    return out


def check_dataset() -> dict:
    hr("3. MemoryAgentBench Conflict_Resolution 真实规模")
    out = {}
    try:
        from datasets import load_dataset
    except Exception as exc:
        print("  datasets 不可用，跳过（pip install datasets）:", exc)
        return out

    try:
        ds = load_dataset("ai-hyz/MemoryAgentBench", split="Conflict_Resolution")
    except Exception as exc:
        print("  加载失败:", exc)
        print("  可尝试离线：先在能联网处 export，再 datasets.load_from_disk")
        return out

    n_ex = len(ds)
    total_q = 0
    total_sessions = 0
    total_turns = 0
    total_ctx_chars = 0
    qtypes: dict[str, int] = {}
    multi_answer = 0

    for ex in ds:
        qs = ex["questions"]
        total_q += len(qs)
        ctx = ex.get("context") or ""
        total_ctx_chars += len(ctx)
        md = ex.get("metadata") or {}
        sess = md.get("haystack_sessions") or []
        total_sessions += len(sess)
        total_turns += sum(len(s) for s in sess)
        for qt in (md.get("question_types") or []):
            qtypes[qt] = qtypes.get(qt, 0) + 1
        for ans in ex["answers"]:
            if isinstance(ans, (list, tuple)) and len(ans) > 1:
                multi_answer += 1

    out = {
        "examples": n_ex,
        "questions": total_q,
        "sessions": total_sessions,
        "turns": total_turns,
        "ctx_chars": total_ctx_chars,
        "qtypes": qtypes,
        "multi_answer": multi_answer,
    }
    print("  样本数 examples      :", n_ex)
    print("  题目数 questions     :", total_q,
          "  ← 这是 E1 的调用量基数")
    print("  会话数 sessions      :", total_sessions)
    print("  轮数   turns         :", total_turns)
    print("  正文总字符           :", total_ctx_chars)
    print("  多选题(可接受多答案) :", multi_answer)
    if qtypes:
        print("  题型分布             :", qtypes)

    # 单样本解剖
    ex0 = ds[0]
    print("\n  --- 样本[0] 解剖 ---")
    print("  questions        :", len(ex0["questions"]))
    print("  answers[0]       :", ex0["answers"][0])
    print("  question[0][:120]:", str(ex0["questions"][0])[:120])
    md = ex0.get("metadata") or {}
    print("  metadata keys    :", sorted(md.keys()))
    sess = md.get("haystack_sessions") or []
    print("  haystack_sessions:", len(sess))

    return out


def check_models(probe: bool) -> dict:
    hr("4. 模型可用性")
    out = {}
    env_keys = {
        "deepseek": ["DEEPSEEK_API_KEY"],
        "glm": ["GLM_API_KEY", "ZHIPU_API_KEY", "BIGMODEL_API_KEY"],
        "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "openai": ["OPENAI_API_KEY"],
    }
    for name, keys in env_keys.items():
        found = [k for k in keys if os.environ.get(k)]
        out[name] = found
        if found:
            print("  %-10s : key present (%s)" % (name, ", ".join(found)))
        else:
            print("  %-10s : no env key" % name)

    if probe:
        print("\n  [--probe-model] 实测 token 需要具体 provider，")
        print("  请在 experiments_v2/adapters/llm.py 里配置后调用。")
        print("  当前先记录：未实测。E0 的出口条件要求补上这张表。")
    return out


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-model", action="store_true",
                    help="额外用少量题实测 token（需要模型配置）")
    args = ap.parse_args()

    hr("E0 · 环境探测")
    report = {"python": check_python()}
    report["deps"] = check_deps()
    report["src"] = check_src()
    report["dataset"] = check_dataset()
    report["models"] = check_models(args.probe_model)

    hr("5. E0 出口检查清单")
    items = [
        ("python 可用", True),
        ("src.gated_mem 可导入", report["src"].get("importable", False)),
        ("MemoryAgentBench 可加载", bool(report["dataset"].get("examples"))),
        ("至少一个模型 key 就绪",
         any(report["models"].get(k) for k in
             ("deepseek", "glm", "gemini", "openai"))),
        ("真实 token 表已产出", False),   # 需 --probe-model 后人工补
    ]
    for name, ok in items:
        print("  [%s] %s" % ("x" if ok else " ", name))

    out_dir = os.path.join("experiments_v2", "results")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "e0_env.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("\n已写入:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
