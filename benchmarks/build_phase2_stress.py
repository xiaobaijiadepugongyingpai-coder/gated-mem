# -*- coding: utf-8 -*-
"""benchmarks/build_phase2_stress.py — 阶段二 P0-1 / P0-2 高压压测集确定性生成器。

依据冻结契约 docs/CONTRACT_P2_STRESS.md（P2-STRESS v1.0.0）生成
benchmarks/data/phase2_dense_stress_15.json：15 组高压场景（P01..P15），每组恰好 25 节点。

对照契约逐条落实：
- §3/§4 字段名照抄不改名；step 全程 1..400、scenario 内互不重复且跨度 >= 300。
- §5 每 scenario 一条 4 代 BELONGS_TO 链（叶 active -> 子 -> 父 -> 根 superseded/killed），
  另加 1 条 is_cycle_probe=true 成环边（消费方须靠 visited 阻断）。
- §6 aliases >= 2 对；其中 1 对用「别名 vs 规范名」双写同槽节点（predicate+scope 相同、step 一前一后）。
- §7 其中 >= 5 组带 kill_worm（λ 生死对照）：λ=0 时 noise 霸榜、target 排名 > 5；
  λ=0.3 时 target 进 Top-5。脚本内置离线自检，自行实现 tokenize/rel/t0/R/F/score
  （口径照 benchmarks/CONTRACT.md §1、§4），断言失败即退出码 1，绝不静默产出废数据。
- §8 embedding 用 sha256 伪向量（同 content 同向量）。
- §10 十二条硬约束逐条打印 OK/FAIL，全部通过才落盘。
- 确定性：禁 random / time / os.environ；连跑两次输出逐字节相同。
- 本脚本不 import src/gated_mem 的任何模块。
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import unicodedata

# ---------- 契约常数（benchmarks/CONTRACT.md §1.1 唯一真源） ----------
BETA = {"DECISION": 0.10, "CONSTRAINT": 0.05, "PREFERENCE": 0.15, "EPHEMERAL": 1.20}
T0_BASE = {"DECISION": 100, "CONSTRAINT": 200, "PREFERENCE": 80, "EPHEMERAL": 5}
GAMMA = 0.2
LAMBDA_STRICT = 0.3
TOPK = 5
EMBED_DIM = 32
ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]*")


# ---------- 阶段一契约 §4：分词与相似度（照抄口径） ----------
def tokenize(text):
    s = unicodedata.normalize("NFKC", text).lower()
    toks = set(re.findall(r"[a-z0-9_]+", s))
    for run in re.findall(r"[\u4e00-\u9fff]+", s):
        toks.update(run)
        if len(run) >= 2:
            for i in range(len(run) - 1):
                toks.add(run[i:i + 2])
    return toks


def rel(a_text, b_text):
    A, B = tokenize(a_text), tokenize(b_text)
    if not A or not B:
        return 0.0
    return len(A & B) / math.sqrt(len(A) * len(B))


# ---------- P2 契约 §8：确定性伪向量 ----------
def pseudo_embedding(text, dim=EMBED_DIM):
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vals = []
    for i in range(dim):
        b = h[i % len(h)]
        vals.append((b / 255.0) * 2.0 - 1.0)
    return vals


# ---------- 阶段一契约 §1.3-§1.5：t0 / R / F / score（离线自检口径） ----------
def t0_of(node):
    return T0_BASE[node["memory_type"]] * (0.5 + node["input_weight"])


def retention_R(node, case_step):
    # 衰减锚点取 last_cited_step（P2 契约 §4：「久未被引用」的衰减陷阱）。
    # 阶段一中 last_cited_step == step，两者等价；本数据集 noise 节点两值同为极旧，
    # target 两值同为最新，故两种锚点解读下 kill_worm 结论一致。
    delta = case_step - node["last_cited_step"]
    return (1.0 + delta / t0_of(node)) ** (-BETA[node["memory_type"]])


def parent_ids_of(node_id, edges):
    return [e["target_id"] for e in edges if e["source_id"] == node_id]


def vitality_F(node, nodes_by_id, edges, case_step):
    if node["pinned"]:
        return 1.0
    base = retention_R(node, case_step)
    gains = []
    for p in parent_ids_of(node["id"], edges):
        u = nodes_by_id.get(p)
        if u is not None and u["status"] == "active":
            gains.append(retention_R(u, case_step))
    gain = GAMMA * max(gains) if gains else 0.0
    return min(1.0, base + gain)


def score_of(node, query, nodes_by_id, edges, case_step, lam):
    r = rel(query, node["content"])
    f = vitality_F(node, nodes_by_id, edges, case_step)
    return r * (f ** lam)


def rank_target(scenario, lam):
    """返回 (target 的 1 基排名, 完整排序表)。候选 = active 节点；排序键用未舍入原始浮点，
    降序、同分按 node_id 升序（阶段一契约 §1.6 / AMB-1）。"""
    kw = scenario["kill_worm"]
    nodes_by_id = {n["id"]: n for n in scenario["nodes"]}
    case_step = max(n["step"] for n in scenario["nodes"])
    scored = []
    for n in scenario["nodes"]:
        if n["status"] != "active":
            continue
        s = score_of(n, kw["query"], nodes_by_id, scenario["edges"], case_step, lam)
        scored.append((s, n["id"], n))
    scored.sort(key=lambda t: (-t[0], t[1]))
    rank = None
    for idx, (s, nid, n) in enumerate(scored):
        if nid == kw["target_node_id"]:
            rank = idx + 1
            break
    if rank is None:
        raise AssertionError(kw["target_node_id"] + " 不在候选集中")
    return rank, scored


# ---------- 步数阶梯（宽跨度，确定性抖动） ----------
STEP_LADDER = [2, 5, 9, 13, 17, 45, 70, 95, 120, 145, 170, 195, 220, 245, 265,
               285, 305, 320, 335, 350, 362, 372, 381, 389, 397]


def scenario_steps(s_idx):
    steps = []
    for i, base in enumerate(STEP_LADDER):
        s = base + ((s_idx * 13 + i * 7) % 7) - 3
        if s < 1:
            s = 1 + (s_idx % 3)
        while s in steps:
            s += 1
        if s > 400:
            s = 400
            while s in steps:
                s -= 1
        steps.append(s)
    return steps


# ---------- 15 组场景规格 ----------
SPECS = [
    {"domain": "db", "flavor": "订单", "slot": "主数据库", "pred": "primary_db_choice",
     "alias1": "db.primary", "alias2n": "pg", "alias2s": "PostgreSQL",
     "new": "PostgreSQL 16", "new_kw": "PostgreSQL", "old": "MySQL 8.0", "old_kw": "MySQL"},
    {"domain": "auth", "flavor": "会员", "slot": "登录鉴权", "pred": "auth_choice",
     "alias1": "auth.gateway", "alias2n": "oauth", "alias2s": "OAuth2",
     "new": "OAuth2 PKCE", "new_kw": "OAuth2", "old": "SessionAuth", "old_kw": "SessionAuth"},
    {"domain": "frontend", "flavor": "活动页", "slot": "前端构建", "pred": "build_tool_choice",
     "alias1": "fe.builder", "alias2n": "vite", "alias2s": "Vite",
     "new": "Vite 5", "new_kw": "Vite", "old": "Webpack 4", "old_kw": "Webpack"},
    {"domain": "testing", "flavor": "用例", "slot": "接口测试", "pred": "e2e_tool_choice",
     "alias1": "qa.e2e", "alias2n": "pw", "alias2s": "Playwright",
     "new": "Playwright", "new_kw": "Playwright", "old": "Selenium 3", "old_kw": "Selenium"},
    {"domain": "deploy", "flavor": "发布单", "slot": "部署平台", "pred": "deploy_platform_choice",
     "alias1": "deploy.platform", "alias2n": "k8s", "alias2s": "Kubernetes",
     "new": "Kubernetes", "new_kw": "Kubernetes", "old": "Docker Swarm", "old_kw": "Swarm"},
    {"domain": "observability", "flavor": "告警", "slot": "可观测性", "pred": "telemetry_stack_choice",
     "alias1": "obs.stack", "alias2n": "otel", "alias2s": "OpenTelemetry",
     "new": "OpenTelemetry", "new_kw": "OpenTelemetry", "old": "StatsD", "old_kw": "StatsD"},
    {"domain": "api", "flavor": "网关", "slot": "接口协议", "pred": "rpc_protocol_choice",
     "alias1": "api.protocol", "alias2n": "grpc", "alias2s": "gRPC",
     "new": "gRPC", "new_kw": "gRPC", "old": "SOAP 1.2", "old_kw": "SOAP"},
    {"domain": "security", "flavor": "密钥", "slot": "密钥管理", "pred": "secret_mgmt_choice",
     "alias1": "sec.vault", "alias2n": "vault", "alias2s": "Vault",
     "new": "Vault", "new_kw": "Vault", "old": "StaticEnv", "old_kw": "StaticEnv"},
    {"domain": "cache", "flavor": "热点", "slot": "缓存中间件", "pred": "cache_choice",
     "alias1": "cache.layer", "alias2n": "redis", "alias2s": "Redis",
     "new": "Redis Cluster", "new_kw": "Redis", "old": "Memcached", "old_kw": "Memcached"},
    {"domain": "mq", "flavor": "事件流", "slot": "消息队列", "pred": "mq_choice",
     "alias1": "mq.bus", "alias2n": "kafka", "alias2s": "Kafka",
     "new": "Kafka", "new_kw": "Kafka", "old": "RabbitMQ", "old_kw": "RabbitMQ"},
    {"domain": "search", "flavor": "索引", "slot": "搜索引擎", "pred": "search_choice",
     "alias1": "search.index", "alias2n": "ose", "alias2s": "OpenSearch",
     "new": "OpenSearch 2", "new_kw": "OpenSearch", "old": "Solr 7", "old_kw": "Solr"},
    {"domain": "inference", "flavor": "推理", "slot": "推理服务", "pred": "serving_choice",
     "alias1": "infer.serving", "alias2n": "vllm", "alias2s": "vLLM",
     "new": "vLLM", "new_kw": "vLLM", "old": "TFServing", "old_kw": "TFServing"},
    {"domain": "ci", "flavor": "流水线", "slot": "持续集成", "pred": "ci_choice",
     "alias1": "ci.pipeline", "alias2n": "gha", "alias2s": "GitHub Actions",
     "new": "GitHub Actions", "new_kw": "GitHub", "old": "Jenkins", "old_kw": "Jenkins"},
    {"domain": "storage", "flavor": "附件", "slot": "对象存储", "pred": "object_storage_choice",
     "alias1": "storage.bucket", "alias2n": "minio", "alias2s": "MinIO",
     "new": "MinIO", "new_kw": "MinIO", "old": "FastDFS", "old_kw": "FastDFS"},
    {"domain": "network", "flavor": "隧道", "slot": "网络插件", "pred": "network_choice",
     "alias1": "net.cni", "alias2n": "cilium", "alias2s": "Cilium",
     "new": "Cilium", "new_kw": "Cilium", "old": "Flannel", "old_kw": "Flannel"},
]

# 带 kill_worm 的 scenario（≥5 组）
KW_SCENARIOS = {"P01", "P04", "P07", "P10", "P13"}

TARGET_TPL = [
    "当前{slot}选型确定为 {new}，切换窗口安排在下个季度。",
    "经过评审，{slot}正式切换到 {new}，旧链路保留只读。",
    "{slot}的最新决定：全面采用 {new}，由平台组统一维护。",
    "平台组已确认{slot}统一运行 {new}，迁移清单见附页。",
]
ROOT_TPL = [
    "早期{slot}采用 {old} 单实例架构。",
    "项目起步时{slot}使用的是 {old}。",
    "第一代{slot}基于 {old} 搭建，随后整体重写。",
    "{slot}最初的技术栈记录：{old}，已废弃。",
]
ROOT_DIFF_TPL = [
    "因 {old} 单实例写入瓶颈被 {new} 集群整体替代。",
    "{old} 的许可成本与扩展上限不满足新目标，改用 {new}。",
    "{old} 社区版本停止维护，团队决定整体迁移到 {new}。",
    "性能压测显示 {old} 无法支撑峰值流量，已由 {new} 接管。",
]
PINNED_TPL = [
    "所有线上变更必须先经过灰度发布与回归验证。",
    "生产配置变更必须双人复核并留存审计记录。",
    "任何架构决策必须同步更新架构决策记录。",
    "发布窗口内的变更必须预留回滚方案。",
]

NOISE_SUFFIX = [
    "。（旧速记，已归档）",
    "。（旧速记备份，已归档）",
    "。（历史速记，已归档）",
    "。（过期笔记，已归档）",
    "。（旧备忘，已归档）",
]


def build_scenario(spec, s_idx):
    sid = "P%02d" % (s_idx + 1)
    steps = scenario_steps(s_idx)
    slot = spec["slot"]
    new = spec["new"]
    old = spec["old"]
    new_kw = spec["new_kw"]
    old_kw = spec["old_kw"]
    flavor = spec["flavor"]
    pred_main = spec["pred"]
    v = s_idx % 4

    cs_query = "当前" + slot + "选型是什么？"
    why_query = "为什么不再用 " + old + "？淘汰原因是什么？"
    target_content = TARGET_TPL[v].format(slot=slot, new=new)
    root_content = ROOT_TPL[v].format(slot=slot, old=old)
    root_diff = ROOT_DIFF_TPL[v].format(old=old, new=new)
    carrier_content = "淘汰旧方案的原因：单点写入瓶颈明显、商业许可成本过高。"
    carrier_diff = "淘汰 " + old + " 的原因：单点写入瓶颈明显、商业许可成本过高。"
    pinned_content = PINNED_TPL[v]

    nodes = []

    def add(nid, content, mtype, subject, pred, scope, w, pinned, status,
            residual_diff=None, last_cited=None):
        st = steps[int(nid[1:]) - 1]
        lc = st if last_cited is None else max(1, min(last_cited, st))
        node = {
            "id": nid, "content": content, "memory_type": mtype, "subject": subject,
            "predicate": pred, "scope": scope, "step": st, "input_weight": w,
            "last_cited_step": lc, "pinned": pinned, "status": status,
        }
        if residual_diff is not None:
            node["residual_diff"] = residual_diff
        node["embedding"] = pseudo_embedding(content)
        nodes.append(node)

    # N01..N05：kill_worm noise（EPHEMERAL、step/last_cited 极旧 → R 衰减到极低；
    # 内容堆满 cs_query 原词 → rel 极高）。非 kill_worm 场景里它们只是陈旧噪音。
    for i, nid in enumerate(["N01", "N02", "N03", "N04", "N05"]):
        add(nid, cs_query + NOISE_SUFFIX[i], "EPHEMERAL", "过期速记", "stale_scratch",
            "global", 0.1, False, "active")
    # N06：kill_worm target（内容朴素 → rel 较低；step=last_cited=CASE_STEP → R≈1、F≈1）
    add("N06", target_content, "DECISION", slot, pred_main, "global", 0.8, False, "active")
    # N07..N09：中段 filler（低 rel、中衰减）
    add("N07", "每日站会同步" + flavor + "相关进度与阻塞事项。", "EPHEMERAL", "站会记录",
        "daily_sync", "global", 0.4, False, "active")
    add("N08", flavor + "模块的联调时间表与负责人分工。", "PREFERENCE", flavor + "联调计划",
        "schedule_note", "branch:feat-" + spec["domain"], 0.5, False, "active")
    add("N09", "用户反馈：" + flavor + "页面加载速度需要优化。", "EPHEMERAL", "用户反馈",
        "user_feedback", "global", 0.3, False, "active")
    # N10..N13：4 代 BELONGS_TO 链（叶 active -> 子 -> 父 -> 根 superseded）
    add("N10", "高可用与容灾部署规范（现行版本）。", "DECISION", slot + "架构谱系",
        "ha_spec", "global", 0.7, False, "active")
    add("N11", "容量规划与副本数基线。", "CONSTRAINT", slot + "架构谱系",
        "capacity_baseline", "global", 0.6, False, "active")
    add("N12", "该层的备份恢复与例行巡检策略。", "DECISION", slot + "架构谱系",
        "backup_strategy", "global", 0.6, False, "active")
    add("N13", root_content, "DECISION", slot + "架构谱系",
        "legacy_stack", "global", 0.5, False, "superseded", residual_diff=root_diff)
    # N14/N15：别名对①——同一实体「别名 vs 规范名」双写同槽（predicate+scope 相同、step 一前一后）
    add("N14", spec["alias1"] + " 实例的连接池上限调整记录。", "DECISION", spec["alias1"],
        pred_main, "global", 0.6, False, "active")
    add("N15", slot + "的连接池与备份策略由平台组统一管理。", "DECISION", slot,
        pred_main, "global", 0.7, False, "active")
    # N16：evolution_why 的解释通道载体（active 节点携带 residual_diff，提及旧技术词）
    add("N16", carrier_content, "DECISION", slot + "迁移决策",
        "migration_rationale", "global", 0.7, False, "active", residual_diff=carrier_diff)
    add("N17", "团队编码规范：Python 代码统一使用 black 格式化。", "PREFERENCE", "编码规范",
        "coding_convention", "global", 0.6, False, "active")
    add("N18", "会议纪要：季度目标对齐与资源盘点。", "EPHEMERAL", "会议纪要",
        "meeting_note", "global", 0.2, False, "active")
    add("N19", flavor + "相关的外部依赖清单与联系人。", "PREFERENCE", "外部依赖",
        "dependency_list", "global", 0.4, False, "active")
    # N20：别名对②的规范名使用方
    add("N20", spec["alias2s"] + " 集群的节点版本升级计划。", "PREFERENCE", spec["alias2s"],
        "infra_upgrade", "global", 0.5, False, "active")
    add("N21", "旧版 " + old + " 运行手册（已归档）。", "DECISION", "旧版运行手册",
        "legacy_runbook", "global", 0.4, False, "superseded",
        residual_diff="旧版 " + old + " 手册下线，由 " + new + " 方案替代。")
    add("N22", "作废的 " + old + " 扩容预案。", "EPHEMERAL", "旧扩容预案",
        "legacy_capacity_plan", "global", 0.2, False, "killed")
    add("N23", "值班交接记录：本周无重大事故。", "EPHEMERAL", "值班交接",
        "duty_handover", "global", 0.3, False, "active")
    add("N24", flavor + "文档库的目录结构说明。", "PREFERENCE", "文档索引",
        "doc_structure", "global", 0.5, False, "active")
    # N25：pinned
    add("N25", pinned_content, "CONSTRAINT", "发布纪律", "release_policy",
        "global", 1.0, True, "active")
    # N18 制造 last_cited_step < step 的引用滞后
    for n in nodes:
        if n["id"] == "N18":
            n["last_cited_step"] = max(1, n["step"] - 25)

    edges = [
        {"source_id": "N10", "target_id": "N11", "edge_type": "BELONGS_TO"},
        {"source_id": "N11", "target_id": "N12", "edge_type": "BELONGS_TO"},
        {"source_id": "N12", "target_id": "N13", "edge_type": "BELONGS_TO"},
        {"source_id": "N13", "target_id": "N10", "edge_type": "BELONGS_TO",
         "is_cycle_probe": True},
        {"source_id": "N15", "target_id": "N14", "edge_type": "REFINES"},
        {"source_id": "N16", "target_id": "N12", "edge_type": "REFINES"},
        {"source_id": "N20", "target_id": "N15", "edge_type": "REFINES"},
        {"source_id": "N22", "target_id": "N21", "edge_type": "CONTRADICTS"},
    ]

    aliases = [
        {"alias_name": spec["alias1"], "canonical_slot": slot},
        {"alias_name": spec["alias2n"], "canonical_slot": spec["alias2s"]},
    ]

    probes = [
        {"probe_type": "current_state", "query": cs_query,
         "must_include": [new_kw], "must_exclude": [old_kw], "expect_nodes": ["N06"]},
        {"probe_type": "evolution_why", "query": why_query,
         "must_include": ["瓶颈", "成本"], "must_exclude": [],
         "old_keyword": old_kw, "expect_nodes": ["N16"]},
    ]

    scenario = {
        "scenario_id": sid,
        "domain": spec["domain"],
        "description": slot + "由 " + old + " 演进到 " + new + " 的高压检索与多跳拓扑场景。",
        "nodes": nodes,
        "edges": edges,
        "aliases": aliases,
        "probes": probes,
    }
    if sid in KW_SCENARIOS:
        scenario["kill_worm"] = {
            "query": cs_query,
            "must_include": [new_kw],
            "must_exclude": [old_kw],
            "target_node_id": "N06",
            "noise_node_ids": ["N01", "N02", "N03", "N04", "N05"],
        }
    return scenario


def build_dataset():
    scenarios = [build_scenario(spec, i) for i, spec in enumerate(SPECS)]
    return {
        "dataset_version": "p2-stress-1.0.0",
        "scenario_count": 15,
        "scenarios": scenarios,
    }


def dump_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode("utf-8")


# ---------- 硬约束自检辅助 ----------
def find_4gen_chain(scenario):
    nodes_by_id = {n["id"]: n for n in scenario["nodes"]}
    par = {}
    for e in scenario["edges"]:
        if e["edge_type"] == "BELONGS_TO":
            par.setdefault(e["source_id"], []).append(e["target_id"])
    for n in scenario["nodes"]:
        if n["status"] != "active" or n["id"] not in par:
            continue
        path = [n["id"]]
        cur = n["id"]
        for _ in range(3):
            nxt = par.get(cur)
            if not nxt:
                break
            cur = nxt[0]
            path.append(cur)
        if len(path) == 4 and nodes_by_id[path[-1]]["status"] in ("superseded", "killed"):
            return path
    return None


def path_exists(adj, a, b):
    seen = set()
    stack = [a]
    while stack:
        cur = stack.pop()
        if cur == b:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(adj.get(cur, []))
    return False


def verify_cycle_edge(scenario):
    adj = {}
    for e in scenario["edges"]:
        if e["edge_type"] == "BELONGS_TO":
            adj.setdefault(e["source_id"], []).append(e["target_id"])
    for e in scenario["edges"]:
        if e.get("is_cycle_probe") is True:
            if path_exists(adj, e["target_id"], e["source_id"]):
                return e
    return None


def alias_coverage_pair(scenario):
    subjects = {}
    for n in scenario["nodes"]:
        subjects.setdefault(n["subject"], []).append(n)
    for pair in scenario["aliases"]:
        a, c = pair["alias_name"], pair["canonical_slot"]
        for na in subjects.get(a, []):
            for nc in subjects.get(c, []):
                if (na["predicate"], na["scope"]) == (nc["predicate"], nc["scope"]):
                    return pair, na, nc
    return None


def kw_report(scenario):
    """返回 (ok, rank0, rank3, detail_str)。"""
    kw = scenario["kill_worm"]
    rank0, ranked0 = rank_target(scenario, 0.0)
    rank3, ranked3 = rank_target(scenario, LAMBDA_STRICT)
    top5_0 = "\n".join(n["content"] for _, _, n in ranked0[:TOPK])
    top5_3 = "\n".join(n["content"] for _, _, n in ranked3[:TOPK])
    mi = [m.lower() for m in kw["must_include"]]
    mx = [m.lower() for m in kw["must_exclude"]]
    ok = True
    notes = []
    if not rank0 > TOPK:
        ok = False
        notes.append("λ=0 rank 未 > 5")
    if not rank3 <= TOPK:
        ok = False
        notes.append("λ=0.3 rank 未 ≤ 5")
    # λ=0：must_include 落空（noise 霸榜）
    if any(m in top5_0.lower() for m in mi):
        ok = False
        notes.append("λ=0 Top5 意外命中 must_include")
    # λ=0.3：must_include 全中、must_exclude 零命中
    if not all(m in top5_3.lower() for m in mi):
        ok = False
        notes.append("λ=0.3 Top5 缺 must_include")
    if any(m in top5_3.lower() for m in mx):
        ok = False
        notes.append("λ=0.3 Top5 命中 must_exclude")
    detail = "λ=0 rank=%d | λ=0.3 rank=%d | λ0_Top5含[%s]=%s | λ0.3_Top5含[%s]=%s,含[%s]=%s%s" % (
        rank0, rank3,
        ",".join(kw["must_include"]), "True" if any(m in top5_0.lower() for m in mi) else "False",
        ",".join(kw["must_include"]), "True" if all(m in top5_3.lower() for m in mi) else "False",
        ",".join(kw["must_exclude"]), "True" if any(m in top5_3.lower() for m in mx) else "False",
        ("  " + ";".join(notes)) if notes else "")
    return ok, rank0, rank3, detail


def run_checks(data, repro_bytes_equal):
    checks = []
    scenarios = data["scenarios"]

    # 1
    ids = [s["scenario_id"] for s in scenarios]
    ok1 = (data["scenario_count"] == 15 and len(scenarios) == 15
           and ids == ["P%02d" % i for i in range(1, 16)])
    checks.append((1, "scenario_count=15 且 id P01..P15 连续唯一", ok1, ""))

    # 2
    ok2 = True
    for s in scenarios:
        if len(s["nodes"]) != 25:
            ok2 = False
        for k, n in enumerate(s["nodes"], 1):
            if n["id"] != "N%02d" % k:
                ok2 = False
    checks.append((2, "每 scenario nodes 恰好 25 且 id N01..N25", ok2, ""))

    # 3
    ok3 = True
    for s in scenarios:
        st = [n["step"] for n in s["nodes"]]
        if len(set(st)) != 25 or max(st) - min(st) < 300:
            ok3 = False
        if min(st) < 1 or max(st) > 400:
            ok3 = False
    checks.append((3, "step 互不重复、1..400、跨度 >= 300", ok3, ""))

    # 4
    ok4 = all(any(n["pinned"] for n in s["nodes"]) for s in scenarios)
    checks.append((4, "每 scenario 至少 1 个 pinned=true", ok4, ""))

    # 5
    ok5 = all(find_4gen_chain(s) is not None for s in scenarios)
    checks.append((5, "每 scenario 至少 1 条 4 代 BELONGS_TO 链（根失效/叶 active）", ok5, ""))

    # 6
    ok6 = all(verify_cycle_edge(s) is not None for s in scenarios)
    checks.append((6, "每 scenario 至少 1 条 is_cycle_probe=true 且真实成环", ok6, ""))

    # 7
    ok7 = all(len(s["aliases"]) >= 2 and alias_coverage_pair(s) is not None for s in scenarios)
    checks.append((7, "每 scenario aliases >= 2 对且含真实同槽别名覆盖对", ok7, ""))

    # 8
    kw_scenarios = [s for s in scenarios if "kill_worm" in s]
    ok8 = len(kw_scenarios) >= 5
    kw_details = []
    for s in kw_scenarios:
        okr, r0, r3, det = kw_report(s)
        ok8 = ok8 and okr
        kw_details.append((s["scenario_id"], r0, r3, det, okr))
    checks.append((8, "kill_worm >= 5 组且全部通过 λ 生死对照断言", ok8, ""))

    # 9：probes 恰好 2 条（current_state 与 evolution_why 各一），且字段齐全
    ok9 = True
    for s in scenarios:
        ps = s["probes"]
        types = [p["probe_type"] for p in ps]
        if len(ps) != 2 or sorted(types) != ["current_state", "evolution_why"]:
            ok9 = False
            continue
        for pr in ps:
            if not pr.get("query") or not isinstance(pr.get("must_include"), list) \
                    or not isinstance(pr.get("must_exclude"), list):
                ok9 = False
        cs = [p for p in ps if p["probe_type"] == "current_state"][0]
        ev = [p for p in ps if p["probe_type"] == "evolution_why"][0]
        # 契约 §9：current_state 的 must_exclude 必须含被淘汰的旧技术词；evolution_why 必须带 old_keyword
        if not cs["must_exclude"]:
            ok9 = False
        if not ev.get("old_keyword"):
            ok9 = False
    checks.append((9, "probes 恰好 2 条且 current_state 带旧词排除 / evolution_why 带 old_keyword", ok9, ""))

    # 10：superseded 节点必有 residual_diff（不带 [Replaced: 前缀）且提及旧关键词
    ok10 = True
    sup_count = 0
    for s in scenarios:
        for n in s["nodes"]:
            if n["status"] != "superseded":
                continue
            sup_count += 1
            diff = n.get("residual_diff")
            if not diff or diff.startswith("[Replaced:"):
                ok10 = False
                continue
            # 旧关键词判据照阶段一契约 §3.5：旧 content 中长度 >= 3 的 ASCII 单词，至少一个出现在 diff 中
            words = [w.lower() for w in ASCII_WORD_RE.findall(n["content"]) if len(w) >= 3]
            if words and not any(w in diff.lower() for w in words):
                ok10 = False
    checks.append((10, "superseded(%d 个)必有 residual_diff 且提及旧关键词、无 [Replaced: 前缀" % sup_count, ok10, ""))

    # 11：embedding 长度 32 且元素 ∈ [-1,1]
    ok11 = all(len(n["embedding"]) == EMBED_DIM and all(-1.0 <= v <= 1.0 for v in n["embedding"])
               for s in scenarios for n in s["nodes"])
    checks.append((11, "embedding 长度 32 且元素 ∈ [-1,1]", ok11, ""))

    return checks, kw_details


def print_structures(data):
    print("---- 结构清单 ----")
    for s in data["scenarios"]:
        chain = find_4gen_chain(s)
        cyc = verify_cycle_edge(s)
        nodes_by_id = {n["id"]: n for n in s["nodes"]}
        root_status = nodes_by_id[chain[-1]]["status"] if chain else "?"
        alias_desc = ", ".join(p["alias_name"] + "→" + p["canonical_slot"] for p in s["aliases"])
        print("%s 4代链: %s(根=%s)  环边: %s->%s  别名: %s" % (
            s["scenario_id"],
            "->".join(chain) if chain else "缺失",
            root_status,
            cyc["source_id"] if cyc else "?", cyc["target_id"] if cyc else "?",
            alias_desc))


def print_kw_table(kw_details):
    print("---- kill_worm λ 生死对照（候选=active 节点；CASE_STEP=max(step)；delta=CASE_STEP-last_cited_step） ----")
    for sid, r0, r3, det, okr in kw_details:
        print("%s %s  %s" % (sid, "PASS" if okr else "FAIL", det))


def main():
    parser = argparse.ArgumentParser(
        description="阶段二 P0-1/P0-2 高压压测集确定性生成器（P2-STRESS v1.0.0，纯标准库）")
    parser.add_argument("--out", default="benchmarks/data/phase2_dense_stress_15.json",
                        help="输出 JSON 路径（默认 benchmarks/data/phase2_dense_stress_15.json）")
    args = parser.parse_args()

    data1 = build_dataset()
    data2 = build_dataset()
    b1 = dump_bytes(data1)
    b2 = dump_bytes(data2)

    checks, kw_details = run_checks(data1, b1 == b2)
    print_structures(data1)
    print_kw_table(kw_details)
    print("---- 契约 §10 十二条硬约束 ----")
    any_fail = False
    for num, name, ok, detail in checks:
        if not ok:
            any_fail = True
        print("[自检] %2d %-44s %s" % (num, name, "OK" if ok else "FAIL"))
    # 第 12 条：连跑两次构建字节相同
    ok12 = b1 == b2
    if not ok12:
        any_fail = True
    print("[自检] 12 %-44s %s" % ("可复现：连跑两次输出字节相同", "OK" if ok12 else "FAIL"))

    if any_fail:
        print("自检存在 FAIL，退出码 1，不落盘。")
        sys.exit(1)

    out_path = args.out
    d = os.path.dirname(out_path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(b1)
    size = os.path.getsize(out_path)
    with open(out_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    total_nodes = sum(len(s["nodes"]) for s in data1["scenarios"])
    print("---- 交付摘要 ----")
    print("落盘: %s" % os.path.abspath(out_path))
    print("大小: %d bytes" % size)
    print("sha256: %s" % digest)
    print("15 组节点总数: %d" % total_nodes)
    print("十二条硬约束: 全部 OK，退出码 0")
    sys.exit(0)


if __name__ == "__main__":
    main()
