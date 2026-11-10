#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""benchmarks/tools/build_dataset.py — Gated-Mem 阶段一（Spike Cut #1）40 组演进测试集生成器。

用法（见 CONTRACT.md §8.2）:
    python benchmarks/tools/build_dataset.py --out benchmarks/data/eval_cases_40.json

设计要点:
  * 纯标准库、零预算、确定性输出（无随机 / 无时间戳 / 无环境依赖，连跑两次字节一致）。
  * 每组用例一次 add() 调用，按 5 个模板族构造:
      std   标准形态 M1..M6（旧决策 → 靶子规范 → 偏好 → 新决策覆盖 → 安全约束 → 临时观察）
      multi 标准形态 + M7 双亲节点（multi_parent）
      scope 同 (subject, predicate) 跨 scope 节点对（scope_isolation）
      fake  同 subject 不同 predicate 假冲突对（fake_conflict）
      ctrl  负控制组：覆盖不涉及 anti_trap 靶子（靶子 M2 为根节点，不在被覆盖节点的子孙链上）
  * 三类探针设计意图（对应 CONTRACT §6 机械判定）:
      current_state.must_exclude 含旧技术词   -> 分支 A（新旧并存）必失败
      anti_trap.expect_survive 指向旧节点之子 -> 分支 B（强连坐）必误杀
      evolution_why.old_keyword 为旧技术词且出现在 residual_diff 中 -> A 必失败
    负控制组的 current_state.must_exclude 留空，用于证明 A 分支并非必然失败。
  * 落盘前内置 §3.5 九条硬约束自检（含覆盖事件 residual_diff 关键词判据），任何一条不满足即退出码 1。
"""
import argparse
import json
import os
import re
import sys

DATASET_VERSION = "1.0.0"
TARGET_CASES = 40
VALID_TYPES = ("DECISION", "CONSTRAINT", "PREFERENCE", "EPHEMERAL")
VALID_PROBES = ("current_state", "anti_trap", "evolution_why")


# ---------------------------------------------------------------------------
# 结构构造辅助（事件 / 探针 / 用例）
# ---------------------------------------------------------------------------

def ev(eid, content, subject, predicate, memory_type, input_weight,
       scope="global", parent_ids=None, residual_diff=None):
    """构造一条 session_event（字段与顺序对齐 CONTRACT §3.3）。"""
    node = {
        "id": eid,
        "content": content,
        "subject": subject,
        "predicate": predicate,
        "scope": scope,
        "memory_type": memory_type,
        "input_weight": input_weight,
    }
    if parent_ids:
        node["parent_ids"] = list(parent_ids)
    if residual_diff is not None:
        node["residual_diff"] = residual_diff
    return node


def probe(ptype, query, must_include, must_exclude,
          expect_survive=None, old_keyword=None, expect_nodes=None):
    """构造一条 probe（字段与顺序对齐 CONTRACT §3.4）。"""
    p = {
        "probe_type": ptype,
        "query": query,
        "must_include": list(must_include),
        "must_exclude": list(must_exclude),
    }
    if expect_survive is not None:
        p["expect_survive"] = list(expect_survive)
    if old_keyword is not None:
        p["old_keyword"] = old_keyword
    if expect_nodes is not None:
        p["expect_nodes"] = list(expect_nodes)
    return p


# ---------------------------------------------------------------------------
# 十个 domain 的主参数表（old_word 必须是旧 content 中长度>=3 的 ASCII 词）
# ---------------------------------------------------------------------------

DOMAINS = {
    "db": {"subject": "用户服务", "slot": "主数据库",
           "old_full": "MySQL 8.0", "new_full": "PostgreSQL 16",
           "old_word": "MySQL", "new_word": "PostgreSQL",
           "reason": "许可证模式与云托管成本"},
    "auth": {"subject": "登录模块", "slot": "会话存储",
             "old_full": "Memcached 1.6", "new_full": "Redis 7",
             "old_word": "Memcached", "new_word": "Redis",
             "reason": "数据结构丰富度与持久化能力"},
    "frontend": {"subject": "管理后台", "slot": "构建工具",
                 "old_full": "webpack 4", "new_full": "Vite 5",
                 "old_word": "webpack", "new_word": "Vite",
                 "reason": "冷启动与热更新速度"},
    "testing": {"subject": "回归测试", "slot": "E2E 框架",
                "old_full": "Selenium 3", "new_full": "Playwright",
                "old_word": "Selenium", "new_word": "Playwright",
                "reason": "执行稳定性与自动等待能力"},
    "deploy": {"subject": "订单服务", "slot": "容器编排平台",
               "old_full": "Docker Swarm", "new_full": "Kubernetes 1.29",
               "old_word": "Swarm", "new_word": "Kubernetes",
               "reason": "生态成熟度与调度能力"},
    "observability": {"subject": "网关服务", "slot": "指标采集通道",
                      "old_full": "StatsD", "new_full": "OpenTelemetry",
                      "old_word": "StatsD", "new_word": "OpenTelemetry",
                      "reason": "协议标准化与生态兼容性"},
    "api": {"subject": "开放平台", "slot": "接口协议",
            "old_full": "SOAP", "new_full": "gRPC",
            "old_word": "SOAP", "new_word": "gRPC",
            "reason": "强类型契约与传输效率"},
    "security": {"subject": "风控接口", "slot": "WAF 引擎",
                 "old_full": "ModSecurity 2.9", "new_full": "Coraza 3",
                 "old_word": "ModSecurity", "new_word": "Coraza",
                 "reason": "规则语法现代性与社区维护"},
    "cache": {"subject": "商品详情页", "slot": "本地缓存",
              "old_full": "Guava Cache", "new_full": "Caffeine 3",
              "old_word": "Guava", "new_word": "Caffeine",
              "reason": "淘汰算法效率与维护状态"},
    "build": {"subject": "发布流水线", "slot": "CI 引擎",
              "old_full": "Jenkins 2", "new_full": "GitHub Actions",
              "old_word": "Jenkins", "new_word": "GitHub Actions",
              "reason": "插件生态与维护成本"},
}

# 负控制组专用参数（覆盖发生在偏好槽位，anti_trap 郗子 M2 为根节点）
CTRL_PARAMS = {
    "S08": {"subject": "审计模块", "slot": "默认日志格式",
            "old_full": "logfmt", "new_full": "JSON Logs",
            "old_word": "logfmt", "new_word": "JSON"},
    "S13": {"subject": "埋点模块", "slot": "默认日志采集器",
            "old_full": "Fluentd", "new_full": "Vector",
            "old_word": "Fluentd", "new_word": "Vector"},
    "S17": {"subject": "对账模块", "slot": "报表导出格式",
            "old_full": "CSV", "new_full": "Parquet",
            "old_word": "CSV", "new_word": "Parquet"},
    "S21": {"subject": "运维脚本", "slot": "备份压缩格式",
            "old_full": "gzip", "new_full": "zstd",
            "old_word": "gzip", "new_word": "zstd"},
    "S24": {"subject": "冒烟测试", "slot": "默认报告格式",
            "old_full": "JUnit XML", "new_full": "Allure",
            "old_word": "JUnit", "new_word": "Allure"},
    "S29": {"subject": "限流模块", "slot": "默认告警渠道",
            "old_full": "PagerDuty", "new_full": "Webhook",
            "old_word": "PagerDuty", "new_word": "Webhook"},
    "S34": {"subject": "性能测试", "slot": "默认压测工具",
            "old_full": "JMeter", "new_full": "k6",
            "old_word": "JMeter", "new_word": "k6"},
    "S39": {"subject": "配置中心", "slot": "默认配置格式",
            "old_full": "YAML", "new_full": "TOML",
            "old_word": "YAML", "new_word": "TOML"},
}


# ---------------------------------------------------------------------------
# 五个模板族
# ---------------------------------------------------------------------------

def _std_note(p, extra=""):
    note = ("标准形态：M1 旧决策(" + p["old_full"] + ") -> M2 规范(Anti-trap 靶子, 父=M1) -> "
            "M3 偏好(父=M1) -> M4 新决策(" + p["new_full"] + ", 同槽覆盖 M1, 带 residual_diff) -> "
            "M5 安全约束(父=M1) -> M6 临时观察(父=M4)。"
            "current_state 的 must_exclude 含 " + p["old_word"] + " 以暴露分支 A 新旧并存的污染失败；"
            "anti_trap 靶子 M2 挂在旧节点 M1 之下以暴露分支 B 强连坐误杀；"
            "evolution_why 的 old_keyword=" + p["old_word"] + " 只能从 residual_diff 解释通道获得。")
    return note + extra


def _std_events(p):
    subject, slot = p["subject"], p["slot"]
    old_full, new_full = p["old_full"], p["new_full"]
    old_word, new_word, reason = p["old_word"], p["new_word"], p["reason"]
    return [
        ev("M1", subject + slot + "决策：采用 " + old_full + "，其他方案暂不考虑。",
           subject, slot, "DECISION", 0.9),
        ev("M2", subject + slot + "变更规范：所有改动必须先在测试环境演练，并回填数据字典。",
           subject, "变更流程规范", "CONSTRAINT", 0.7, parent_ids=["M1"]),
        ev("M3", "团队偏好" + subject + "的" + slot + "变更走灰度发布，避免一次性全量切换。",
           subject, "变更节奏偏好", "PREFERENCE", 0.5, parent_ids=["M1"]),
        ev("M4", subject + "改用 " + new_full + " 作为 " + slot + "。",
           subject, slot, "DECISION", 0.9,
           residual_diff=("因为 " + old_word + " 在" + reason + "方面逐渐成为瓶颈，团队切换到 " + new_full + "。")),
        ev("M5", "安全约束：" + subject + "的" + slot + "凭据禁止写入代码仓库，统一走密钥管理。",
           subject, "凭据安全约束", "CONSTRAINT", 0.8, parent_ids=["M1"]),
        ev("M6", "临时观察：" + new_word + " 上线后一周内跟踪 P99 延迟变化，到期自动归档。",
           subject, "上线观察", "EPHEMERAL", 0.3, parent_ids=["M4"]),
    ]


def _std_probes(p, expect_nodes_cs=("M4",)):
    subject, slot = p["subject"], p["slot"]
    old_word, new_word, reason = p["old_word"], p["new_word"], p["reason"]
    return [
        probe("current_state",
              subject + "现在的" + slot + "是什么？还在用 " + old_word + " 吗，还是已经换成了 " + new_word + "？",
              [new_word], [old_word], expect_nodes=list(expect_nodes_cs)),
        probe("anti_trap",
              subject + "的" + slot + "变更需要遵守什么规范流程？",
              ["测试环境"], [], expect_survive=["M2"]),
        probe("evolution_why",
              "为什么" + subject + "的" + slot + "从 " + old_word + " 切换到了 " + new_word + "？",
              [reason], [], old_keyword=old_word),
    ]


def build_std(p):
    return _std_events(p), _std_probes(p)


def build_multi(p):
    subject, slot = p["subject"], p["slot"]
    new_word = p["new_word"]
    events = _std_events(p)
    events.append(ev("M7", "临时记录：同步跟踪 " + new_word + " 迁移进度与" + slot + "规范落地情况。",
                     subject, "迁移跟踪", "EPHEMERAL", 0.2, parent_ids=["M2", "M4"]))
    probes = _std_probes(p)
    return events, probes


def build_scope(p):
    subject, slot = p["subject"], p["slot"]
    old_full, new_full = p["old_full"], p["new_full"]
    old_word, new_word, reason = p["old_word"], p["new_word"], p["reason"]
    wp, wo, wn, branch = p["witness_pred"], p["witness_old"], p["witness_new"], p["branch"]
    short = branch.split(":", 1)[1]
    events = [
        ev("M1", subject + slot + "决策：采用 " + old_full + "，其他方案暂不考虑。",
           subject, slot, "DECISION", 0.9),
        ev("M2", subject + slot + "变更规范：所有改动必须先在测试环境演练，并回填数据字典。",
           subject, "变更流程规范", "CONSTRAINT", 0.7, parent_ids=["M1"]),
        ev("M3", subject + "的" + wp + "（全局）：采用" + wo + "。",
           subject, wp, "DECISION", 0.7),
        ev("M4", subject + "在分支 " + short + " 上的" + wp + "：改为" + wn + "，仅该分支生效。",
           subject, wp, "DECISION", 0.7, scope=branch, parent_ids=["M3"]),
        ev("M5", subject + "改用 " + new_full + " 作为 " + slot + "。",
           subject, slot, "DECISION", 0.9,
           residual_diff=("因为 " + old_word + " 在" + reason + "方面逐渐成为瓶颈，团队切换到 " + new_full + "。")),
        ev("M6", "临时观察：" + new_word + " 上线后一周内跟踪错误率变化。",
           subject, "上线观察", "EPHEMERAL", 0.3, parent_ids=["M5"]),
    ]
    probes = [
        probe("current_state",
              subject + "全局的" + wp + "是什么？分支 " + short + " 上又改成了什么？" + slot + "还在用 " + old_word + " 吗，还是已经换成了 " + new_word + "？",
              [wo, wn, new_word], [old_word], expect_nodes=["M3", "M4", "M5"]),
        probe("anti_trap",
              subject + "的" + slot + "变更需要遵守什么规范流程？",
              ["测试环境"], [], expect_survive=["M2"]),
        probe("evolution_why",
              "为什么" + subject + "的" + slot + "从 " + old_word + " 切换到了 " + new_word + "？",
              [reason], [], old_keyword=old_word),
    ]
    return events, probes


def build_fake(p):
    subject, slot = p["subject"], p["slot"]
    old_full, new_full = p["old_full"], p["new_full"]
    old_word, new_word, reason = p["old_word"], p["new_word"], p["reason"]
    wp, ww = p["witness_pred"], p["witness_word"]
    events = [
        ev("M1", subject + slot + "决策：采用 " + old_full + "，其他方案暂不考虑。",
           subject, slot, "DECISION", 0.9),
        ev("M2", subject + slot + "变更规范：所有改动必须先在测试环境演练，并回填数据字典。",
           subject, "变更流程规范", "CONSTRAINT", 0.7, parent_ids=["M1"]),
        ev("M3", subject + "的" + wp + "：统一使用 " + ww + "。",
           subject, wp, "PREFERENCE", 0.5, parent_ids=["M1"]),
        ev("M4", subject + "改用 " + new_full + " 作为 " + slot + "。",
           subject, slot, "DECISION", 0.9,
           residual_diff=("因为 " + old_word + " 在" + reason + "方面逐渐成为瓶颈，团队切换到 " + new_full + "。")),
        ev("M5", "安全约束：" + subject + "的" + slot + "凭据禁止写入代码仓库，统一走密钥管理。",
           subject, "凭据安全约束", "CONSTRAINT", 0.8, parent_ids=["M1"]),
        ev("M6", "临时观察：" + new_word + " 上线后一周内跟踪 P99 延迟变化。",
           subject, "上线观察", "EPHEMERAL", 0.3, parent_ids=["M4"]),
    ]
    probes = [
        probe("current_state",
              subject + "现在的" + slot + "是什么？已经从 " + old_word + " 换成 " + new_word + " 了吗？" + wp + "有变化吗？",
              [new_word, ww], [old_word], expect_nodes=["M3", "M4"]),
        probe("anti_trap",
              subject + "的" + slot + "变更需要遵守什么规范流程？",
              ["测试环境"], [], expect_survive=["M2"]),
        probe("evolution_why",
              "为什么" + subject + "的" + slot + "从 " + old_word + " 切换到了 " + new_word + "？",
              [reason], [], old_keyword=old_word),
    ]
    return events, probes


def build_ctrl(p):
    subject, slot = p["subject"], p["slot"]
    old_full, new_full = p["old_full"], p["new_full"]
    old_word, new_word = p["old_word"], p["new_word"]
    events = [
        ev("M1", "团队偏好：" + subject + "统一采用 " + old_full + " 作为" + slot + "。",
           subject, slot, "PREFERENCE", 0.6),
        ev("M2", subject + "运维规范：所有告警必须附带 trace_id，禁止静默失败。",
           subject, "运维规范", "CONSTRAINT", 0.7),
        ev("M3", subject + "改用 " + new_full + " 作为" + slot + "。",
           subject, slot, "PREFERENCE", 0.6,
           residual_diff=("因为 " + old_word + " 的表达能力和工具链支持逐渐不足，团队迁移到 " + new_full + "。")),
        ev("M4", subject + "的变更记录统一归档到运维知识库，附变更单号。",
           subject, "变更归档", "DECISION", 0.6),
        ev("M5", "临时观察：trace_id 覆盖率是否达到 100%。",
           subject, "规范观察", "EPHEMERAL", 0.3, parent_ids=["M2"]),
        ev("M6", "团队偏好周五下午发布，避开周一流量高峰。",
           subject, "发布窗口偏好", "PREFERENCE", 0.4, parent_ids=["M4"]),
    ]
    probes = [
        probe("current_state",
              "团队现在" + subject + "的" + slot + "是什么？已经用上 " + new_word + " 了吗？",
              [new_word], [], expect_nodes=["M3"]),
        probe("anti_trap",
              subject + "的运维规范对告警和 trace_id 有什么要求？",
              ["trace_id"], [], expect_survive=["M2"]),
        probe("evolution_why",
              "为什么" + subject + "的" + slot + "从 " + old_word + " 改成了 " + new_word + "？",
              ["表达能力和工具链支持"], [], old_keyword=old_word),
    ]
    return events, probes


BUILDERS = {
    "std": build_std,
    "multi": build_multi,
    "scope": build_scope,
    "fake": build_fake,
    "ctrl": build_ctrl,
}


# ---------------------------------------------------------------------------
# 40 组用例规格表（kind, domain, 附加参数）
# ---------------------------------------------------------------------------

def _spec(kind, domain, extra=None):
    s = {"kind": kind, "domain": domain}
    if extra:
        s.update(extra)
    return s


SPECS = [
    _spec("std", "db"),                                                                    # S01
    _spec("std", "auth"),                                                                  # S02
    _spec("std", "frontend"),                                                              # S03
    _spec("std", "testing"),                                                               # S04
    _spec("multi", "deploy"),                                                              # S05
    _spec("scope", "observability", {"witness_pred": "采样策略", "witness_old": "全量采样",
                                     "witness_new": "尾部采样", "branch": "branch:feat-gw-tail"}),   # S06
    _spec("fake", "api", {"witness_pred": "文档格式偏好", "witness_word": "OpenAPI 3.0"}),           # S07
    _spec("ctrl", "security", CTRL_PARAMS["S08"]),                                          # S08
    _spec("std", "cache"),                                                                 # S09
    _spec("std", "build"),                                                                 # S10
    _spec("std", "db"),                                                                    # S11
    _spec("std", "auth"),                                                                  # S12
    _spec("ctrl", "frontend", CTRL_PARAMS["S13"]),                                          # S13
    _spec("std", "testing"),                                                               # S14
    _spec("multi", "deploy"),                                                              # S15
    _spec("scope", "observability", {"witness_pred": "告警降噪策略", "witness_old": "静态阈值",
                                     "witness_new": "动态基线", "branch": "branch:feat-alert-dyn"}),  # S16
    _spec("ctrl", "api", CTRL_PARAMS["S17"]),                                               # S17
    _spec("std", "security"),                                                              # S18
    _spec("fake", "cache", {"witness_pred": "序列化格式偏好", "witness_word": "MessagePack"}),       # S19
    _spec("std", "build"),                                                                 # S20
    _spec("ctrl", "db", CTRL_PARAMS["S21"]),                                                # S21
    _spec("std", "auth"),                                                                  # S22
    _spec("std", "frontend"),                                                              # S23
    _spec("ctrl", "testing", CTRL_PARAMS["S24"]),                                           # S24
    _spec("std", "deploy"),                                                                # S25
    _spec("scope", "observability", {"witness_pred": "存储后端策略", "witness_old": "本地落盘",
                                     "witness_new": "对象存储", "branch": "branch:feat-remote-store"}), # S26
    _spec("multi", "api"),                                                                 # S27
    _spec("std", "security"),                                                              # S28
    _spec("ctrl", "cache", CTRL_PARAMS["S29"]),                                             # S29
    _spec("std", "build"),                                                                 # S30
    _spec("std", "db"),                                                                    # S31
    _spec("std", "auth"),                                                                  # S32
    _spec("scope", "frontend", {"witness_pred": "主题方案", "witness_old": "浅色主题",
                                "witness_new": "深色主题", "branch": "branch:feat-dark-mode"}),       # S33
    _spec("ctrl", "testing", CTRL_PARAMS["S34"]),                                           # S34
    _spec("fake", "deploy", {"witness_pred": "发布节奏偏好", "witness_word": "金丝雀发布"}),          # S35
    _spec("std", "observability"),                                                          # S36
    _spec("scope", "api", {"witness_pred": "限流策略", "witness_old": "固定窗口",
                           "witness_new": "滑动窗口", "branch": "branch:feat-slide-rl"}),            # S37
    _spec("multi", "security"),                                                             # S38
    _spec("ctrl", "cache", CTRL_PARAMS["S39"]),                                             # S39
    _spec("std", "build"),                                                                  # S40
]


# ---------------------------------------------------------------------------
# 组装 40 组用例（每组一次 add()）
# ---------------------------------------------------------------------------

CASES = []


def add(scenario_id, domain, description, is_control, construction_note,
        tags, session_events, probes):
    CASES.append({
        "scenario_id": scenario_id,
        "domain": domain,
        "description": description,
        "is_control": is_control,
        "construction_note": construction_note,
        "tags": list(tags),
        "session_events": session_events,
        "probes": probes,
    })


def _desc(kind, p):
    subject, slot = p["subject"], p["slot"]
    base = subject + "的" + slot + "从 " + p["old_full"] + " 演进到 " + p["new_full"]
    if kind == "std":
        return base + " 的标准记忆演化场景。"
    if kind == "multi":
        return base + "，且含同时挂两个父节点的多亲事件。"
    if kind == "scope":
        return base + "，并含同 (subject, predicate) 跨 scope 的隔离节点对（" + p["branch"] + "）。"
    if kind == "fake":
        return base + "，并含同实体不同属性的假冲突对（" + p["witness_pred"] + "）。"
    return "控制组：" + subject + "的" + slot + "从 " + p["old_full"] + " 迁移到 " + p["new_full"] + "，覆盖不涉及 anti_trap 靶子。"


def _tags(kind):
    if kind == "std":
        return ["evolution"]
    if kind == "multi":
        return ["evolution", "multi_parent"]
    if kind == "scope":
        return ["evolution", "scope_isolation"]
    if kind == "fake":
        return ["evolution", "fake_conflict"]
    return ["control"]


def _ctrl_note(p):
    return ("控制组：覆盖仅发生在偏好槽位（" + p["slot"] + "），anti_trap 靶子 M2 为根节点、"
            "不在被覆盖节点 M1 的子孙链上，因此分支 B 的连坐不会误杀靶子；"
            "current_state 的 must_exclude 留空，用于证明分支 A 并非必然失败。")


def _scope_extra_note(p):
    return " 另含 M3/M4 同 (subject, predicate) 不同 scope（global vs " + p["branch"] + "）的隔离对，current_state 探针同时断言两侧共存、互不覆盖。"


def _fake_extra_note(p):
    return " 另含 M1/M3 同 subject 不同 predicate（" + p["witness_pred"] + "）的假冲突对，槽位三元组不同，不得发生覆盖。"


def build_all():
    for idx, spec in enumerate(SPECS, start=1):
        sid = "S%02d" % idx
        kind, domain = spec["kind"], spec["domain"]
        if kind == "ctrl":
            p = dict(spec)
            p.pop("kind", None)
            p.pop("domain", None)
        else:
            p = dict(DOMAINS[domain])
            for key in ("kind", "domain"):
                p.pop(key, None)
            p.update({k: v for k, v in spec.items() if k not in ("kind", "domain")})
        events, probes = BUILDERS[kind](p)
        if kind == "std":
            note = _std_note(p)
        elif kind == "multi":
            note = _std_note(p, " 另含 M7 同时挂 M2/M4 两个父节点的多亲事件。")
        elif kind == "scope":
            note = _std_note(p, _scope_extra_note(p))
        elif kind == "fake":
            note = _std_note(p, _fake_extra_note(p))
        else:
            note = _ctrl_note(p)
        add(sid, domain, _desc(kind, p), kind == "ctrl", note, _tags(kind), events, probes)
    return CASES


# ---------------------------------------------------------------------------
# 生成期自检（CONTRACT §3.5 九条硬约束的确定性实现）
# ---------------------------------------------------------------------------

def _slot_of(e):
    return (e["subject"], e["predicate"], e["scope"])


def _coverage_pairs(events):
    """按 §2.1 槽位规则模拟覆盖，返回 [(new_event, old_event_min_id), ...]。"""
    active = []
    pairs = []
    for e in events:
        slot = _slot_of(e)
        olds = [a for a in active if _slot_of(a) == slot]
        if olds:
            old = min(olds, key=lambda x: x["id"])
            pairs.append((e, old))
            active = [a for a in active if a not in olds]
        active.append(e)
    return pairs


def _tech_keywords(text):
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9_.\-]*", text) if len(w) >= 3]
    if words:
        return words
    runs = re.findall(r"[\u4e00-\u9fff]+", text)
    if runs and len(runs[-1]) >= 2:
        return [runs[-1][-2:]]
    return []


def _check_case(case, errors):
    sid = case["scenario_id"]
    events = case["session_events"]
    probes = case["probes"]

    # 约束 2/3：事件数与探针数
    if not (6 <= len(events) <= 8):
        errors.append(sid + ": 事件数 " + str(len(events)) + " 不在 [6,8]")
    if len(probes) != 3 or sorted(pp["probe_type"] for pp in probes) != sorted(VALID_PROBES):
        errors.append(sid + ": probes 必须恰好三条且三类各一")

    # 事件 id 唯一 + 父引用只允许更早出现（禁止前向/自引用/环）
    seen = set()
    for e in events:
        if e["id"] in seen:
            errors.append(sid + ": 事件 id 重复 " + e["id"])
        seen.add(e["id"])
    earlier = set()
    for e in events:
        for pid in e.get("parent_ids", []):
            if pid == e["id"] or pid not in earlier:
                errors.append(sid + ": " + e["id"] + " 非法父引用 " + pid)
        earlier.add(e["id"])

    # 字段合法性
    for e in events:
        if e["memory_type"] not in VALID_TYPES:
            errors.append(sid + ": " + e["id"] + " 非法 memory_type")
        if not (0.1 <= e["input_weight"] <= 1.0):
            errors.append(sid + ": " + e["id"] + " input_weight 越界")
        if not e["scope"]:
            errors.append(sid + ": " + e["id"] + " scope 为空")

    # 覆盖事件必须带 residual_diff 且提及旧节点技术关键词；diff 不得带 [Replaced 前缀
    diffs = []
    for e in events:
        if e.get("residual_diff"):
            diffs.append(e["residual_diff"])
            if "[Replaced" in e["residual_diff"]:
                errors.append(sid + ": " + e["id"] + " residual_diff 带 [Replaced 前缀")
    for new_e, old_e in _coverage_pairs(events):
        if not new_e.get("residual_diff"):
            errors.append(sid + ": 覆盖事件 " + new_e["id"] + " 缺 residual_diff")
        else:
            kws = _tech_keywords(old_e["content"])
            low = new_e["residual_diff"].lower()
            if not any(k.lower() in low for k in kws):
                errors.append(sid + ": " + new_e["id"] + " residual_diff 未提及旧节点关键词 " + repr(kws))

    # evolution_why 探针：old_keyword 必须出现在某条 residual_diff 中
    for pp in probes:
        if pp["probe_type"] == "evolution_why":
            ok = old_kw = pp.get("old_keyword")
            if not old_kw:
                errors.append(sid + ": evolution_why 缺 old_keyword")
            elif not any(ok.lower() in d.lower() for d in diffs):
                errors.append(sid + ": old_keyword 未出现在任何 residual_diff")
        if not pp["must_include"]:
            errors.append(sid + ": " + pp["probe_type"] + " must_include 为空")


def validate_built(cases):
    errors = []
    # 约束 1：数量与编号
    if len(cases) != TARGET_CASES:
        errors.append("case_count != 40: " + str(len(cases)))
    for i, c in enumerate(cases, start=1):
        if c["scenario_id"] != "S%02d" % i:
            errors.append("scenario_id 顺序错误: " + c["scenario_id"])

    # 约束 4：domain 去重
    domains = sorted(set(c["domain"] for c in cases))
    if len(domains) < 6:
        errors.append("domain 去重不足 6 种: " + str(len(domains)))

    # 约束 5/6/7/8：特殊用例计数
    def has_tag(tag):
        return [c["scenario_id"] for c in cases if tag in c["tags"]]
    if len(has_tag("multi_parent")) < 3:
        errors.append("multi_parent 用例不足 3")
    if len(has_tag("scope_isolation")) < 4:
        errors.append("scope_isolation 用例不足 4")
    if len(has_tag("fake_conflict")) < 2:
        errors.append("fake_conflict 用例不足 2")
    ctrls = [c for c in cases if c["is_control"]]
    if len(ctrls) < 8:
        errors.append("负控制组不足 8")
    for c in ctrls:
        if len(c["construction_note"]) < 10:
            errors.append(c["scenario_id"] + ": 控制组 construction_note 过短")

    for c in cases:
        _check_case(c, errors)
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Gated-Mem 阶段一 40 组演进测试集生成器（纯标准库、确定性输出）")
    ap.add_argument("--out", default=os.path.join("benchmarks", "data", "eval_cases_40.json"),
                    help="输出 JSON 路径（默认 benchmarks/data/eval_cases_40.json）")
    args = ap.parse_args(argv)

    cases = build_all()
    errors = validate_built(cases)
    if errors:
        print("[build] 自检 FAIL:")
        for msg in errors:
            print("  FAIL - " + msg)
        return 1

    multi = [c["scenario_id"] for c in cases if "multi_parent" in c["tags"]]
    scope = [c["scenario_id"] for c in cases if "scope_isolation" in c["tags"]]
    fake = [c["scenario_id"] for c in cases if "fake_conflict" in c["tags"]]
    ctrl = [c["scenario_id"] for c in cases if c["is_control"]]
    domains = sorted(set(c["domain"] for c in cases))
    n_diff = sum(1 for c in cases for e in c["session_events"] if e.get("residual_diff"))
    n_cov = sum(len(_coverage_pairs(c["session_events"])) for c in cases)

    out_path = args.out
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    dataset = {
        "dataset_version": DATASET_VERSION,
        "case_count": len(cases),
        "cases": cases,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")

    size = os.path.getsize(out_path)
    print("[build] 用例总数: %d (S01..S40)，case_count=%d, len(cases)=%d" % (len(cases), dataset["case_count"], len(dataset["cases"])))
    print("[build] domain 去重: %d 种 -> %s" % (len(domains), ", ".join(domains)))
    print("[build] 多亲(multi_parent): %d 组 -> %s" % (len(multi), " ".join(multi)))
    print("[build] scope 隔离(scope_isolation): %d 组 -> %s" % (len(scope), " ".join(scope)))
    print("[build] 假冲突(fake_conflict): %d 组 -> %s" % (len(fake), " ".join(fake)))
    print("[build] 负控制组(is_control): %d 组 -> %s" % (len(ctrl), " ".join(ctrl)))
    print("[build] 含 residual_diff 的事件: %d 个；同槽覆盖对: %d 个" % (n_diff, n_cov))
    print("[build] 九条硬约束自检: OK")
    print("[build] 已写出: %s (%d bytes)" % (os.path.abspath(out_path), size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
