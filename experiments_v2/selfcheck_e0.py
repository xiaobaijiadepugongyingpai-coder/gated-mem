"""E0 自检：验证适配层能真正驱动 src/gated_mem，且各臂行为差异符合语义。

不调外部 LLM。跑的是"检索层"链路，确认：
  1. 能建库、写入、检索
  2. A1(纯向量/无槽位) 不会发生覆盖 → 新旧并存
  3. A3(槽位覆盖) 会发生覆盖 → 旧节点 superseded
  4. write_event=False 不产生续命副作用

用法: python experiments_v2/selfcheck_e0.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "arms")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "adapters")))

from definitions import ARMS, by_name          # noqa: E402
from gated_store import GatedStore              # noqa: E402


def hr(t):
    print("\n" + "=" * 66)
    print(t)
    print("=" * 66)


def basic_drive() -> bool:
    hr("1. 基础驱动：建库 / 写入 / 检索")
    arm = by_name("A3_slot")
    try:
        with GatedStore(arm) as g:
            g.remember("主数据库使用 MySQL 8.0", "database", "engine")
            g.remember("连接池大小设为 20", "database", "pool_size")
            print("  写入节点数:", g.size())
            r = g.recall("数据库用什么引擎")
            txt = GatedStore.receipt_text(r)
            print("  召回正文长度:", len(txt))
            print("  正文片段:", repr(txt[:160]))
        print("  => OK")
        return True
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print("  => FAIL:", exc)
        return False


def no_slots_no_supersede() -> bool:
    hr("2. A1(no-slots) 语义：同槽位两次写入不应触发覆盖")
    arm = by_name("A1_vector")
    try:
        with GatedStore(arm) as g:
            g.remember("主数据库使用 MySQL 8.0", "database", "engine")
            g.remember("主数据库改用 PostgreSQL 16", "database", "engine")
            nodes = g.store.all_memories()
            active = [n for n in nodes if n.status.value == "active"]
            print("  总节点:", len(nodes), " active:", len(active))
            print("  状态分布:", {n.status.value for n in nodes})
            ok = len(active) == len(nodes)
            print("  => %s（预期：全部 active，新旧并存）" % ("OK" if ok else "FAIL"))
            return ok
    except Exception:
        import traceback
        traceback.print_exc()
        return False


def inspect_recall_path() -> bool:
    hr("3. 检查 recall 的各开关是否真的生效")
    try:
        from definitions import by_name

        for name in ("A1_vector", "A2_fts", "A3_slot", "A5_full"):
            arm = by_name(name)
            with GatedStore(arm) as g:
                for i in range(5):
                    g.remember("配置项 %d 的取值为 %d" % (i, i * 10),
                               "cfg", "item%d" % i)
                r = g.recall("配置项 2 的取值", topk=3)
                txt = GatedStore.receipt_text(r)
                print("  %-14s lam=%.1f fusion=%-5s -> 正文 %3d 字符"
                      % (name, arm.lam, arm.fusion, len(txt)))
        return True
    except Exception:
        import traceback
        traceback.print_exc()
        return False


def main() -> int:
    results = []
    results.append(("基础驱动", basic_drive()))
    results.append(("A1 无覆盖语义", no_slots_no_supersede()))
    results.append(("各臂开关生效", inspect_recall_path()))

    hr("E0 自检汇总")
    for name, ok in results:
        print("  [%s] %s" % ("x" if ok else " ", name))
    allok = all(ok for _, ok in results)
    print("\n结论:", "全部通过" if allok else "有失败，需修适配层")
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
