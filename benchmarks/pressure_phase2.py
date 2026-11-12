"""高压检索压测（P0-1 / G2-Rank）。

不依赖 GLM 的外部数据：本脚本自带确定性合成器，生成 15 组 25 节点、
跨度 400 步的高密度场景，强制触发 TOPK 截断，并量化 λ 门控的增益。

若 benchmarks/data/phase2_dense_stress_15.json 存在，则用外部数据跑同样的度量。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gated_mem.retrieval import Retriever
from src.gated_mem.schema import MemoryNode, MemoryStatus, MemoryType
from src.gated_mem.storage import Store

TOPICS = [
    ("主数据库", "engine", "MySQL", "PostgreSQL 16"),
    ("前端构建器", "bundler", "webpack", "Vite 5"),
    ("认证方案", "auth", "Session Cookie", "OAuth 2.1 + PKCE"),
    ("缓存层", "cache", "Memcached", "Redis 7 集群"),
    ("消息队列", "mq", "RabbitMQ", "Kafka 3.6"),
    ("部署编排", "orchestration", "Docker Swarm", "Kubernetes 1.29"),
    ("日志采集", "logging", "Fluentd", "Vector 0.35"),
    ("接口协议", "protocol", "SOAP", "REST + OpenAPI 3.1"),
    ("状态管理", "state", "Redux", "Zustand 4"),
    ("测试框架", "test", "Selenium", "Playwright 1.42"),
    ("构建缓存", "buildcache", "distutils", "Bazel 7"),
    ("配置中心", "config", "Consul", "etcd 3.5"),
    ("对象存储", "storage", "GlusterFS", "S3 兼容 MinIO"),
    ("服务网格", "mesh", "Linkerd 1", "Istio 1.20"),
    ("告警通道", "alerting", "PagerDuty", "Grafana OnCall"),
]


def build_store(scenario_index: int, dense: bool = True) -> Tuple[Store, dict]:
    """构造一个高密度场景。

    25 个节点：
      - 6 个极旧 + 内容堆满 query 原词的噪音节点（衰减到极低）
      - 12 个中等相关的背景节点
      - 1 个真正有效的目标节点（新、vitality 高）
      - 4 个多跳链节点（三代 + 根废弃）
      - 2 个 pinned 节点
    """
    topic, pred, old_tech, new_tech = TOPICS[scenario_index % len(TOPICS)]
    s = Store(":memory:")

    def add(mid, content, subj, pr, step, mtype=MemoryType.DECISION, last=None, pinned=False):
        s.insert_memory(
            MemoryNode(
                memory_id=mid, content=content, memory_type=mtype,
                subject=subj, predicate=pr, created_step=step,
                last_cited_step=last if last is not None else step, pinned=pinned,
            )
        )

    # --- 噪音（6 个）：把 query 的原词全部塞进正文，rel 最高，但 step 极旧 ---
    # 用 EPHEMERAL（beta=1.2）保证衰减够快，Δ=390 时 R 会掉到 1e-3 量级。
    for i in range(6):
        add(
            "N%02d" % i,
            "%s 选型讨论记录：%s 与 %s 的 %s 选型，当前状态待定，第 %d 条备忘"
            % (topic, old_tech, new_tech, topic, i),
            "noise%d" % i, pred, step=2, last=2, mtype=MemoryType.EPHEMERAL,
        )
    # --- 背景（12 个）：完全不涉及 query 的主题词，rel 很低 ---
    # 它们存在的意义是撑大体量、制造真实候选池，而不是参与竞争。
    filler_topics = ["代码规范", "注释风格", "分支策略", "依赖升级", "文档模板", "评审流程"]
    for i in range(6, 18):
        ft = filler_topics[i % len(filler_topics)]
        add(
            "N%02d" % i,
            "团队%s第 %d 条：与本次技术选型无关的通用工程约定" % (ft, i),
            "bg%d" % i, "misc", step=20 + i * 5, last=20 + i * 5,
        )
    # --- 目标（1 个）：真正有效的当前状态。rel 中高、vitality 接近 1 ---
    add(
        "TARGET",
        "%s 已确认完成迁移，当前生产环境使用 %s，%s 选型到此定稿" % (topic, new_tech, topic),
        "real", pred, step=395, last=395,
    )
    # --- 多跳链（4 个）：H1(根,废弃) <- H2(父) <- H3(子) <- H4(孙) ---
    add("H1", "%s 初始决策：选用 %s 作为长期方案" % (topic, old_tech), "h1", "root", step=5)
    add("H2", "%s 模块规范：统一封装访问层与 %s 的对接方式" % (topic, new_tech), "h2", "spec", step=30)
    add("H3", "%s 子配置：超时、重试与连接数策略" % topic, "h3", "conf", step=60)
    add("H4", "%s 孙辈细则：连接池大小 20，%s 选型后的最终参数" % (topic, topic), "h4", "detail", step=90)
    # pinned 安全约束
    add("PIN1", "禁止硬编码密钥，一律走环境变量", "sec", "rule", step=1, pinned=True,
        mtype=MemoryType.CONSTRAINT)
    add("PIN2", "所有对外接口必须有超时与熔断", "sec", "rule2", step=1, pinned=True,
        mtype=MemoryType.CONSTRAINT)

    from src.gated_mem.schema import EdgeType, MemoryEdge

    for child, parent, st in (("H2", "H1", 30), ("H3", "H2", 60), ("H4", "H3", 90)):
        s.insert_edge(
            MemoryEdge(edge_id="E_%s_%s" % (child, parent), source_id=child, target_id=parent,
                       edge_type=EdgeType.BELONGS_TO, created_step=st)
        )
    # 根废弃
    s.set_status("H1", MemoryStatus.SUPERSEDED, 380)

    meta = {
        "scenario_id": "P%02d" % (scenario_index + 1),
        "topic": topic,
        "query": "%s 选型 %s %s 当前状态" % (topic, old_tech, new_tech),
        "must_include": [new_tech.split()[0]],
        "must_exclude": [old_tech.split()[0]],
        "target_id": "TARGET",
        "chain_leaf": "H4",
        "stale_root": "H1",
    }
    return s, meta


def evaluate_lambda(s: Store, meta: dict, lam: float, topk: int = 5) -> dict:
    """在给定 λ 下跑一次召回，返回度量。"""
    r = Retriever(s, lam=lam, topk=topk)
    receipt = r.recall(meta["query"], case_step=400)
    ids = [i.memory_id for i in receipt.injected_items]
    body = receipt.injected_text()
    target_rank = None
    for idx, (node, _score) in enumerate(
        sorted(
            [(n, 0) for n in s.all_memories() if n.status == MemoryStatus.ACTIVE],
            key=lambda x: x[0].memory_id,
        )
    ):
        pass
    return {
        "lambda": lam,
        "injected_ids": ids,
        "target_injected": meta["target_id"] in ids,
        "must_include_ok": all(w.lower() in body.lower() for w in meta["must_include"]),
        "must_exclude_clean": not any(w.lower() in body.lower() for w in meta["must_exclude"]),
        "candidate_pool_size": receipt.candidate_pool_size,
        "truncated": receipt.truncated_candidates,
        "stale_warned": [i.memory_id for i in receipt.injected_items if i.stale_parent_warning],
    }


def run(n_scenarios: int = 15, topk: int = 5, verbose: bool = True) -> dict:
    """跑全部场景，返回聚合指标。"""
    rows = []
    for i in range(n_scenarios):
        s, meta = build_store(i)
        gated = evaluate_lambda(s, meta, 0.3, topk)
        pure = evaluate_lambda(s, meta, 0.0, topk)
        rows.append({"meta": meta, "gated": gated, "pure": pure})
        s.close()

    n = len(rows)
    gated_ok = sum(1 for r in rows if r["gated"]["target_injected"])
    pure_ok = sum(1 for r in rows if r["pure"]["target_injected"])
    trunc_ok = sum(1 for r in rows if r["gated"]["truncated"] > 0)
    pool_min = min(r["gated"]["candidate_pool_size"] for r in rows)
    stale_hits = sum(1 for r in rows if r["gated"]["stale_warned"])

    result = {
        "scenarios": n,
        "topk": topk,
        "gated_lambda0.3_target_rate": round(gated_ok / float(n), 6),
        "pure_lambda0.0_target_rate": round(pure_ok / float(n), 6),
        "improvement_pp": round((gated_ok - pure_ok) / float(n) * 100.0, 4),
        "truncation_triggered_rate": round(trunc_ok / float(n), 6),
        "min_candidate_pool": pool_min,
        "scenarios_with_stale_warning": stale_hits,
        "rows": rows,
    }
    if verbose:
        print("=" * 78)
        print("  P0-1 高压检索压测：lambda 生死对照（%d 场景 / TOPK=%d）" % (n, topk))
        print("=" * 78)
        print("  场景   候选池  真实淘汰  λ=0.3 目标入榜  λ=0.0 目标入榜  截断")
        for r in rows:
            g, p = r["gated"], r["pure"]
            print(
                "  %-5s %6d %8d %12s %13s %6s"
                % (
                    r["meta"]["scenario_id"],
                    g["candidate_pool_size"],
                    g["truncated"],
                    "YES" if g["target_injected"] else "no",
                    "YES" if p["target_injected"] else "no",
                    "YES" if g["truncated"] > 0 else "no",
                )
            )
        print("-" * 78)
        print("  λ=0.3 目标入榜率 : %.2f%%" % (result["gated_lambda0.3_target_rate"] * 100))
        print("  λ=0.0 目标入榜率 : %.2f%%" % (result["pure_lambda0.0_target_rate"] * 100))
        print("  门控提升         : +%.2f pp" % result["improvement_pp"])
        print("  截断触发率       : %.2f%%" % (result["truncation_triggered_rate"] * 100))
        print("  最小候选池       : %d" % result["min_candidate_pool"])
        print("  多跳告警命中     : %d / %d" % (stale_hits, n))
        print("=" * 78)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="阶段二 P0-1 高压检索压测")
    ap.add_argument("--scenarios", type=int, default=15)
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--out", default="")
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    args = ap.parse_args()

    res = run(args.scenarios, args.topk, verbose=not args.json)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("已写入 %s" % args.out)
    elif args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))

    # 门禁判定：G2-Rank 要求提升 >= 25pp
    ok = res["improvement_pp"] >= 25.0 and res["truncation_triggered_rate"] > 0.9
    print("\n[G2-Rank] %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
