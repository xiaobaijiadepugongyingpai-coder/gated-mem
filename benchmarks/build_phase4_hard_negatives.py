#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段四 Track B：同语境高碰撞难负例基准集（20 组）构建 + 三通道评测。

设计依据：GM-DIRECTIVE-P4-v3.0.0 §3.2（数学必然性）。

目标：构造「背景语境 90%+ 雷同、只有关键标识符差 1~2 个字符」的难负例，
使 bge-small 的 384 维稠密空间把 5 条候选挤进极窄区间，单向量通道 Top-1
以高概率被前序节点挤占；而 FTS5 bm25() 对精确标识符 token 的高 IDF 爆发力
经由有界校准融合（0.85*s_fts 保底）把正确节点精准置顶。

验收门（硬性）：融合 Top-1 准确率 - 单向量 Top-1 准确率 >= 20pp。

铁律：
  1. 数据生成只用字面常量与确定性字符串模板：禁 random / time / 环境变量。
     连跑两次数据文件逐字节相同。
  2. 评测公式一律复用 src/gated_mem/gates.py 的 calibrated_fusion /
     saturate_bm25 / bm25_to_positive，严禁本地重写（口径一致性）。
  3. 评测结果浮点统一 round 到 6 位。

用法（在 gated-mem 专用 conda 环境内）：
  <conda-env>/python benchmarks/build_phase4_hard_negatives.py
选项：
  --skip-build   不重建 JSON（读现有文件做评测）
  --skip-eval    只生成数据，不做评测
  --skip-report  跳过 Markdown 报告
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

DATA_PATH = os.path.join(PROJECT_ROOT, "benchmarks", "data", "phase4_hard_negatives_20.json")
REPORT_PATH = os.path.join(PROJECT_ROOT, "benchmarks", "reports", "phase4_hard_negatives_report.md")

TOPK = 3
EXPECTED_IDX_CYCLE = (4, 2, 0, 3, 1, 1, 2, 0, 3, 3, 0, 3, 1, 4, 2, 0, 2, 1, 0, 4)

# ---------------------------------------------------------------------------
# 第 1 部分：数据构造（纯字面模板，零随机）
# ---------------------------------------------------------------------------
# 每组：一个 module + 一条模板（占位 {ident}/{val}）+ 5 个 (标识符, 参数值)。
# 5 条记忆的正文只差 {ident} 与 {val} 两处，其余措辞 100% 相同；
# 标识符族内每个成员都含至少一个组内唯一的子 token（FTS5 unicode61 会把
# 下划线与点号切开，唯一子 token 即高 IDF 区分器）。

GROUP_DEFS: List[Dict[str, Any]] = [
    # ---------------- error_code × 5 ----------------
    {
        "case_id": "H01",
        "entity_kind": "error_code",
        "module": "分布式事务重试模块",
        "subject": "分布式事务重试模块",
        "predicate": "处置记录",
        "template": (
            "在分布式事务重试模块的联调复盘里，值守团队把错误码 {ident} 的处置动作固化为一条记录："
            "先将重试退避阈值 tx_backoff_ms 调整为 {val}，再保持幂等去重窗口开启，"
            "最后把本次变更登记到当班值守日志的回滚开关清单；该策略自上线以来运行平稳，"
            "未再触发重试风暴，与同族错误码共用同一套处置模板，仅参数取值不同，评审时按编号逐条核对即可。"
        ),
        "items": [
            ("ERR_XA_RMFAIL_04", "500"),
            ("ERR_XA_RMERR_05", "1500"),
            ("ERR_XA_NOTA_06", "800"),
            ("ERR_XA_INVAL_07", "1200"),
            ("ERR_XA_PROTO_08", "2000"),
        ],
        "query": "高并发压测之后，分布式事务重试模块里错误码 ERR_XA_PROTO_08 的退避参数应按哪条记录调整？",
    },
    {
        "case_id": "H02",
        "entity_kind": "error_code",
        "module": "存储网关巡检模块",
        "subject": "存储网关巡检模块",
        "predicate": "处置记录",
        "template": (
            "在存储网关巡检模块的巡检周报里，当 PostgreSQL 后端抛出错误码 {ident} 时，"
            "值班团队会把该错误码登记进巡检看板：先将连接重试上限 conn_retry_limit 调整为 {val}，"
            "再保持只读副本探活开启，最后把处置依据链接写进当班交接文档；"
            "该预案自上线以来稳定运行，未再出现误杀连接，与同族错误码共用同一模板，仅参数不同，评审时逐条核对即可。"
        ),
        "items": [
            ("PG_ERR_42P01", "3"),
            ("PG_ERR_42P02", "5"),
            ("PG_ERR_42704", "7"),
            ("PG_ERR_42883", "9"),
            ("PG_ERR_42P07", "11"),
        ],
        "query": "存储网关巡检模块的看板里，错误码 PG_ERR_42704 对应的处置参数记录在哪一条？",
    },
    {
        "case_id": "H03",
        "entity_kind": "error_code",
        "module": "消息队列接入模块",
        "subject": "消息队列接入模块",
        "predicate": "告警处置记录",
        "template": (
            "在消息队列接入模块的早班告警复盘里，序列号空洞告警 {ident} 触发后，"
            "值守团队按预案登记处置记录：先把序列回补步长 seq_refill_step 调整为 {val}，"
            "再保持消费位点校验开启，最后把告警窗口截图归档到当班交接文档；"
            "该预案自上线以来稳定运行，未再出现重复消费，与同族告警共用同一模板，仅参数不同，评审时逐条核对即可。"
        ),
        "items": [
            ("MQ_SEQ_GAP_11", "32"),
            ("MQ_SEQ_GAP_12", "64"),
            ("MQ_SEQ_GAP_13", "96"),
            ("MQ_SEQ_GAP_14", "128"),
            ("MQ_SEQ_GAP_15", "160"),
        ],
        "query": "消息队列接入模块的早班复盘里，告警 MQ_SEQ_GAP_11 对应的回补参数记录在哪一条？",
    },
    {
        "case_id": "H04",
        "entity_kind": "error_code",
        "module": "配置中心热更新模块",
        "subject": "配置中心热更新模块",
        "predicate": "变更处置记录",
        "template": (
            "在配置中心热更新模块的变更审计里，当热更新同步失败并上报错误码 {ident} 时，"
            "值守团队会把处置动作写进变更审计簿：先将全量对账间隔 full_reconcile_sec 调整为 {val}，"
            "再保持灰度名单校验开启，最后把受影响租户清单附在当班交接文档；"
            "该预案自上线以来稳定运行，未再出现配置漂移，与同族错误码共用同一模板，仅参数不同，评审时逐条核对即可。"
        ),
        "items": [
            ("CFG_HOT_SYNC_FAIL_31", "30"),
            ("CFG_HOT_SYNC_FAIL_32", "45"),
            ("CFG_HOT_SYNC_FAIL_33", "60"),
            ("CFG_HOT_SYNC_FAIL_34", "75"),
            ("CFG_HOT_SYNC_FAIL_35", "90"),
        ],
        "query": "配置中心热更新模块的审计簿里，错误码 CFG_HOT_SYNC_FAIL_34 的对账参数记录在哪一条？",
    },
    {
        "case_id": "H05",
        "entity_kind": "error_code",
        "module": "幂等去重模块",
        "subject": "幂等去重模块",
        "predicate": "风控处置记录",
        "template": (
            "在幂等去重模块的风控复盘里，当去重窗口冲突并抛出错误码 {ident} 时，"
            "值守团队会把处置动作登记成一条记录：先将去重窗口宽度 idem_window_ms 调整为 {val}，"
            "再保持请求指纹校验开启，最后把冲突样本清单归档到当班交接文档；"
            "该预案自上线以来稳定运行，未再出现重复扣减，与同族错误码共用同一模板，仅参数不同，评审时逐条核对即可。"
        ),
        "items": [
            ("IDEM_DUP_WIN_71", "1000"),
            ("IDEM_DUP_WIN_72", "1500"),
            ("IDEM_DUP_WIN_73", "2000"),
            ("IDEM_DUP_WIN_74", "2500"),
            ("IDEM_DUP_WIN_75", "3000"),
        ],
        "query": "幂等去重模块的复盘记录里，错误码 IDEM_DUP_WIN_72 的窗口参数对应哪一条？",
    },
    # ---------------- config_key × 5 ----------------
    {
        "case_id": "H06",
        "entity_kind": "config_key",
        "module": "网关读缓冲调优模块",
        "subject": "网关读缓冲调优模块",
        "predicate": "容量评审记录",
        "template": (
            "在网关读缓冲调优模块的容量评审里，配置项 {ident} 的推荐取值被写成一条记录："
            "先把读缓冲上限落到该配置项并设为 {val}，再保持背压水位探测开启，"
            "最后把压测曲线截图附到当班交接文档；该取值自上线以来稳定运行，未再触发缓冲抖动，"
            "与同族配置项共用同一模板，仅后缀与取值不同，评审时逐条核对即可。"
        ),
        "items": [
            ("read_buffer_size_kb", "512"),
            ("read_buffer_size_mb", "1024"),
            ("read_buffer_size_gb", "2048"),
            ("read_buffer_size_kib", "4096"),
            ("read_buffer_size_mib", "8192"),
        ],
        "query": "网关读缓冲调优模块的评审记录里，配置项 read_buffer_size_mb 的推荐取值是哪一条？",
    },
    {
        "case_id": "H07",
        "entity_kind": "config_key",
        "module": "会话过期调度模块",
        "subject": "会话过期调度模块",
        "predicate": "容量复盘记录",
        "template": (
            "在会话过期调度模块的容量复盘里，配置项 {ident} 的基线取值被登记成一条记录："
            "先把会话清扫节奏落到该配置项并设为 {val}，再保持过期键抽样校验开启，"
            "最后把清扫耗时曲线附到当班交接文档；该取值自上线以来稳定运行，未再出现清扫积压，"
            "与同族配置项共用同一模板，仅后缀与取值不同，评审时逐条核对即可。"
        ),
        "items": [
            ("session_gc_interval_min", "15"),
            ("session_gc_interval_sec", "30"),
            ("session_gc_interval_hr", "45"),
            ("session_gc_interval_day", "60"),
            ("session_gc_interval_tick", "75"),
        ],
        "query": "会话过期调度模块的复盘里，配置项 session_gc_interval_hr 的基线取值是哪一条？",
    },
    {
        "case_id": "H08",
        "entity_kind": "config_key",
        "module": "TLS 握手压测模块",
        "subject": "TLS 握手压测模块",
        "predicate": "调优纪要记录",
        "template": (
            "在 TLS 握手压测模块的调优纪要里，配置项 {ident} 的推荐取值被登记成一条记录："
            "先把握手超时上限落到该配置项并设为 {val}，再保持会话票据复用开启，"
            "最后把握手分位数曲线附到当班交接文档；该取值自上线以来稳定运行，未再出现握手雪崩，"
            "与同族配置项共用同一模板，仅后缀与取值不同，评审时逐条核对即可。"
        ),
        "items": [
            ("tls_handshake_timeout_ms", "200"),
            ("tls_handshake_timeout_us", "400"),
            ("tls_handshake_timeout_ns", "600"),
            ("tls_handshake_timeout_s", "800"),
            ("tls_handshake_timeout_sec", "1000"),
        ],
        "query": "TLS 握手压测模块的纪要里，配置项 tls_handshake_timeout_ms 的推荐取值是哪一条？",
    },
    {
        "case_id": "H09",
        "entity_kind": "config_key",
        "module": "日志轮转模块",
        "subject": "日志轮转模块",
        "predicate": "巡检纪要记录",
        "template": (
            "在日志轮转模块的巡检纪要里，配置项 {ident} 的基线取值被登记成一条记录："
            "先把单文件轮转上限落到该配置项并设为 {val}，再保持磁盘水位告警开启，"
            "最后把轮转耗时统计附到当班交接文档；该取值自上线以来稳定运行，未再出现日志盘写满，"
            "与同族配置项共用同一模板，仅后缀与取值不同，评审时逐条核对即可。"
        ),
        "items": [
            ("log_rotate_max_size_mb", "64"),
            ("log_rotate_max_size_kb", "128"),
            ("log_rotate_max_size_gb", "256"),
            ("log_rotate_max_size_tb", "512"),
            ("log_rotate_max_size_pb", "1024"),
        ],
        "query": "日志轮转模块的巡检纪要里，配置项 log_rotate_max_size_tb 的基线取值是哪一条？",
    },
    {
        "case_id": "H10",
        "entity_kind": "config_key",
        "module": "限流器调参模块",
        "subject": "限流器调参模块",
        "predicate": "演练纪要记录",
        "template": (
            "在限流器调参模块的攻防演练纪要里，配置项 {ident} 的基线取值被登记成一条记录："
            "先把突发容量落到该配置项并设为 {val}，再保持令牌桶回填探测开启，"
            "最后把限流命中分布附到当班交接文档；该取值自上线以来稳定运行，未再出现突发击穿，"
            "与同族配置项共用同一模板，仅后缀与取值不同，评审时逐条核对即可。"
        ),
        "items": [
            ("rate_limit_burst_64", "2"),
            ("rate_limit_burst_128", "4"),
            ("rate_limit_burst_256", "6"),
            ("rate_limit_burst_512", "8"),
            ("rate_limit_burst_1024", "10"),
        ],
        "query": "限流器调参模块的演练纪要里，配置项 rate_limit_burst_512 的冷却参数记录在哪一条？",
    },
    # ---------------- version × 5 ----------------
    {
        "case_id": "H11",
        "entity_kind": "version",
        "module": "网关灰度发布模块",
        "subject": "网关灰度发布模块",
        "predicate": "演练档案记录",
        "template": (
            "在网关灰度发布模块的演练档案里，版本 {ident} 的灰度表现被登记成一条记录："
            "先在该版本的批次里把放量比例 rollout_ratio_pct 设为 {val}，再保持错误率熔断探测开启，"
            "最后把批次观测结论附到当班交接文档；该版本自上线以来稳定运行，未再触发回滚预案，"
            "与同族版本共用同一模板，仅版本号与比例不同，评审时逐条核对即可。"
        ),
        "items": [
            ("v2.14.37-rc1", "5"),
            ("v2.14.38-rc1", "10"),
            ("v2.14.39-rc1", "15"),
            ("v2.14.40-rc1", "20"),
            ("v2.14.41-rc1", "25"),
        ],
        "query": "网关灰度发布模块的演练档案里，版本 v2.14.37-rc1 的放量比例记录在哪一条？",
    },
    {
        "case_id": "H12",
        "entity_kind": "version",
        "module": "网卡固件升级模块",
        "subject": "网卡固件升级模块",
        "predicate": "机房纪要记录",
        "template": (
            "在网卡固件升级模块的机房纪要里，固件版本 {ident} 的升级表现被登记成一条记录："
            "先在该版本的批次里把批量刷写间隔 batch_flash_interval_sec 设为 {val}，"
            "再保持固件签名校验开启，最后把刷写成功率附到当班交接文档；"
            "该版本自上线以来稳定运行，未再触发回退流程，与同族版本共用同一模板，仅版本号与间隔不同，评审时逐条核对即可。"
        ),
        "items": [
            ("fw_1.8.52-hotfix", "30"),
            ("fw_1.8.53-hotfix", "45"),
            ("fw_1.8.54-hotfix", "60"),
            ("fw_1.8.55-hotfix", "75"),
            ("fw_1.8.56-hotfix", "90"),
        ],
        "query": "网卡固件升级模块的机房纪要里，固件版本 fw_1.8.55-hotfix 的刷写间隔记录在哪一条？",
    },
    {
        "case_id": "H13",
        "entity_kind": "version",
        "module": "客户端 SDK 发布模块",
        "subject": "客户端 SDK 发布模块",
        "predicate": "发布评审记录",
        "template": (
            "在客户端 SDK 发布模块的发布评审里，SDK 版本 {ident} 的发布表现被登记成一条记录："
            "先在该版本的批次里把预热流量比例 warmup_traffic_pct 设为 {val}，"
            "再保持崩溃率哨兵探测开启，最后把兼容性结论附到当班交接文档；"
            "该版本自上线以来稳定运行，未再触发紧急下架，与同族版本共用同一模板，仅版本号与比例不同，评审时逐条核对即可。"
        ),
        "items": [
            ("sdk_3.4.21-beta", "10"),
            ("sdk_3.4.22-beta", "20"),
            ("sdk_3.4.23-beta", "30"),
            ("sdk_3.4.24-beta", "40"),
            ("sdk_3.4.25-beta", "50"),
        ],
        "query": "客户端 SDK 发布模块的评审里，SDK 版本 sdk_3.4.22-beta 的预热比例记录在哪一条？",
    },
    {
        "case_id": "H14",
        "entity_kind": "version",
        "module": "容器镜像发布模块",
        "subject": "容器镜像发布模块",
        "predicate": "值守纪要记录",
        "template": (
            "在容器镜像发布模块的值守纪要里，镜像版本 {ident} 的部署表现被登记成一条记录："
            "先在该版本的批次里把滚动窗口宽度 rolling_window_sec 设为 {val}，"
            "再保持健康探针门禁开启，最后把回滚点清单附到当班交接文档；"
            "该版本自上线以来稳定运行，未再出现起播失败，与同族版本共用同一模板，仅版本号与窗口不同，评审时逐条核对即可。"
        ),
        "items": [
            ("img_1.21.44-stable", "60"),
            ("img_1.21.45-stable", "90"),
            ("img_1.21.46-stable", "120"),
            ("img_1.21.47-stable", "150"),
            ("img_1.21.48-stable", "180"),
        ],
        "query": "容器镜像发布模块的值守纪要里，镜像版本 img_1.21.48-stable 的滚动窗口记录在哪一条？",
    },
    {
        "case_id": "H15",
        "entity_kind": "version",
        "module": "内核模块兼容性模块",
        "subject": "内核模块兼容性模块",
        "predicate": "回归纪要记录",
        "template": (
            "在内核模块兼容性模块的回归纪要里，内核模块版本 {ident} 的回归表现被登记成一条记录："
            "先在该版本的批次里把回归用例并发数 regression_parallelism 设为 {val}，"
            "再保持符号版本校验开启，最后把失败用例清单附到当班交接文档；"
            "该版本自上线以来稳定运行，未再出现加载失败，与同族版本共用同一模板，仅版本号与并发数不同，评审时逐条核对即可。"
        ),
        "items": [
            ("kmod_6.2.17-lts", "4"),
            ("kmod_6.2.18-lts", "6"),
            ("kmod_6.2.19-lts", "8"),
            ("kmod_6.2.20-lts", "10"),
            ("kmod_6.2.21-lts", "12"),
        ],
        "query": "内核模块兼容性模块的回归纪要里，版本 kmod_6.2.19-lts 的回归并发记录在哪一条？",
    },
    # ---------------- function_name × 5 ----------------
    {
        "case_id": "H16",
        "entity_kind": "function_name",
        "module": "账务对账服务模块",
        "subject": "账务对账服务模块",
        "predicate": "值班纪要记录",
        "template": (
            "在账务对账服务模块的值班纪要里，函数 {ident} 的调用约定被登记成一条记录："
            "先在该函数的封装层把分片大小 shard_batch_rows 设为 {val}，再保持幂等键校验开启，"
            "最后把调用耗时分布附到当班交接文档；该约定自上线以来稳定运行，未再出现对账缺口，"
            "与同族函数共用同一模板，仅函数名与分片不同，评审时逐条核对即可。"
        ),
        "items": [
            ("reconcile_ledger_entries", "500"),
            ("reconcile_ledger_entry", "1000"),
            ("reconcile_ledger_vouchers", "1500"),
            ("reconcile_ledger_invoices", "2000"),
            ("reconcile_ledger_receipts", "2500"),
        ],
        "query": "账务对账服务模块的值班纪要里，函数 reconcile_ledger_entries 的分片大小记录在哪一条？",
    },
    {
        "case_id": "H17",
        "entity_kind": "function_name",
        "module": "流解析服务模块",
        "subject": "流解析服务模块",
        "predicate": "性能复盘记录",
        "template": (
            "在流解析服务模块的性能复盘里，函数 {ident} 的解析约定被登记成一条记录："
            "先在该函数的入口层把解析缓冲区 parse_buffer_kb 设为 {val}，再保持非法帧计数器开启，"
            "最后把吞吐基线附到当班交接文档；该约定自上线以来稳定运行，未再出现解析卡顿，"
            "与同族函数共用同一模板，仅函数名与缓冲不同，评审时逐条核对即可。"
        ),
        "items": [
            ("parse_wire_payload", "64"),
            ("parse_wire_header", "128"),
            ("parse_wire_trailer", "256"),
            ("parse_wire_checksum", "512"),
            ("parse_wire_padding", "1024"),
        ],
        "query": "流解析服务模块的复盘里，函数 parse_wire_trailer 的缓冲区参数记录在哪一条？",
    },
    {
        "case_id": "H18",
        "entity_kind": "function_name",
        "module": "刷写队列服务模块",
        "subject": "刷写队列服务模块",
        "predicate": "巡检纪要记录",
        "template": (
            "在刷写队列服务模块的巡检纪要里，函数 {ident} 的调度约定被登记成一条记录："
            "先在该函数的调度层把单轮配额 drain_quota_per_round 设为 {val}，"
            "再保持队列水位探测开启，最后把排空耗时附到当班交接文档；"
            "该约定自上线以来稳定运行，未再出现队列淤积，与同族函数共用同一模板，仅函数名与配额不同，评审时逐条核对即可。"
        ),
        "items": [
            ("drain_flush_queue", "100"),
            ("drain_flush_queues", "200"),
            ("drain_flush_queued", "300"),
            ("drain_purge_queue", "400"),
            ("drain_retry_queue", "500"),
        ],
        "query": "刷写队列服务模块的巡检纪要里，函数 drain_flush_queues 的单轮配额记录在哪一条？",
    },
    {
        "case_id": "H19",
        "entity_kind": "function_name",
        "module": "指标抓取服务模块",
        "subject": "指标抓取服务模块",
        "predicate": "观测纪要记录",
        "template": (
            "在指标抓取服务模块的观测纪要里，函数 {ident} 的抓取约定被登记成一条记录："
            "先在该函数的采集层把抓取超时 scrape_timeout_ms 设为 {val}，再保持目标去重校验开启，"
            "最后把抓取成功率附到当班交接文档；该约定自上线以来稳定运行，未再出现指标断流，"
            "与同族函数共用同一模板，仅函数名与超时不同，评审时逐条核对即可。"
        ),
        "items": [
            ("scrape_targat_refresh", "1000"),
            ("scrape_target_refresh", "2000"),
            ("scrape_targets_refresh", "3000"),
            ("scrape_target_relabel", "4000"),
            ("scrape_target_expired", "5000"),
        ],
        "query": "指标抓取服务模块的观测纪要里，函数 scrape_targat_refresh 的抓取超时记录在哪一条？",
    },
    {
        "case_id": "H20",
        "entity_kind": "function_name",
        "module": "SST 压实服务模块",
        "subject": "SST 压实服务模块",
        "predicate": "巡检纪要记录",
        "template": (
            "在 SST 压实服务模块的巡检纪要里，函数 {ident} 的压实约定被登记成一条记录："
            "先在该函数的执行层把单批压实页数 compact_pages_per_batch 设为 {val}，"
            "再保持写放大监控开启，最后把压实耗时分布附到当班交接文档；"
            "该约定自上线以来稳定运行，未再出现写停顿，与同族函数共用同一模板，仅函数名与页数不同，评审时逐条核对即可。"
        ),
        "items": [
            ("compact_sst_segments", "128"),
            ("compact_sst_segment", "256"),
            ("compact_sst_segmemts", "512"),
            ("compact_sst_blocks", "1024"),
            ("compact_sst_tables", "2048"),
        ],
        "query": "SST 压实服务模块的巡检纪要里，函数 compact_sst_tables 的单批页数记录在哪一条？",
    },
]


def _expected_idx(case_index: int) -> int:
    """确定性摊派正确答案位置（覆盖 0..4，避免位置偏差）。"""
    return EXPECTED_IDX_CYCLE[case_index % len(EXPECTED_IDX_CYCLE)]


def build_cases() -> List[Dict[str, Any]]:
    """把 20 组模板展开成结构化 case。全程无随机源。"""
    cases: List[Dict[str, Any]] = []
    for gi, g in enumerate(GROUP_DEFS):
        exp_idx = _expected_idx(gi) % len(g["items"])
        expected_id = "%s_M%d" % (g["case_id"], exp_idx + 1)
        memories: List[Dict[str, Any]] = []
        for mi, (ident, val) in enumerate(g["items"]):
            memories.append(
                {
                    "id": "%s_M%d" % (g["case_id"], mi + 1),
                    "content": g["template"].format(ident=ident, val=val),
                    "subject": g["subject"],
                    "predicate": g["predicate"],
                    "memory_type": "DECISION",
                    "step": gi * 10 + mi + 1,
                    "input_weight": 0.5,
                    "identifier": ident,
                    "value": val,
                }
            )
        cases.append(
            {
                "case_id": g["case_id"],
                "entity_kind": g["entity_kind"],
                "module": g["module"],
                "query": g["query"],
                "identifier": g["items"][exp_idx][0],
                "expected_id": expected_id,
                "expected_top3": [expected_id],
                "memories": memories,
            }
        )
    _validate_cases(cases)
    return cases


_IDENT_BOUNDARY_RE = re.compile(r"[A-Za-z0-9]")


def _ident_in_query(query: str, ident: str) -> bool:
    """词边界感知的标识符匹配（与 tokenize 的 ASCII 整词语义一致）。

    纯 substring 匹配会被族内前缀关系误伤（如 drain_flush_queue 是
    drain_flush_queues 的前缀）；这里要求标识符两侧不能紧贴字母数字。
    """
    start = query.find(ident)
    while start != -1:
        end = start + len(ident)
        before_ok = start == 0 or not _IDENT_BOUNDARY_RE.match(query[start - 1])
        after_ok = end >= len(query) or not _IDENT_BOUNDARY_RE.match(query[end])
        if before_ok and after_ok:
            return True
        start = query.find(ident, start + 1)
    return False


def _validate_cases(cases: List[Dict[str, Any]]) -> None:
    """结构自检：规格硬约束逐条断言。"""
    if len(cases) != 20:
        raise AssertionError("case 数必须为 20，实际 %d" % len(cases))
    kinds: Dict[str, int] = {}
    for c in cases:
        kinds[c["entity_kind"]] = kinds.get(c["entity_kind"], 0) + 1
        if len(c["memories"]) != 5:
            raise AssertionError("%s 记忆数不为 5" % c["case_id"])
        idents = [m["identifier"] for m in c["memories"]]
        if len(set(idents)) != 5:
            raise AssertionError("%s 标识符不唯一" % c["case_id"])
        for m in c["memories"]:
            if len(m["content"]) < 60:
                raise AssertionError("%s/%s 正文不足 60 字" % (c["case_id"], m["id"]))
        q = c["query"]
        hit = [m["id"] for m in c["memories"] if _ident_in_query(q, m["identifier"])]
        if hit != [c["expected_id"]]:
            raise AssertionError("%s query 标识符定位失败：%r" % (c["case_id"], hit))
        if c["entity_kind"] not in ("error_code", "config_key", "version", "function_name"):
            raise AssertionError("非法 entity_kind：%r" % c["entity_kind"])
    for k in ("error_code", "config_key", "version", "function_name"):
        if kinds.get(k) != 5:
            raise AssertionError("entity_kind=%s 覆盖数不为 5：%r" % (k, kinds))


def build_dataset_document(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "dataset": "phase4_hard_negatives_20",
        "version": "1.0.0",
        "generator": "benchmarks/build_phase4_hard_negatives.py",
        "description": (
            "同语境高碰撞难负例基准：每组 5 条正文措辞高度雷同的长记忆，"
            "仅关键标识符差 1~2 个字符；单向量通道必然挤在一起，"
            "必须依赖 FTS5 精确 token 的 IDF 才能区分。"
        ),
        "determinism": "纯字面模板生成；无 random/time/env；连跑两次逐字节相同",
        "case_count": len(cases),
        "memories_per_case": 5,
        "cases": cases,
    }


def write_dataset(path: str, doc: Dict[str, Any]) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---------------------------------------------------------------------------
# 第 2 部分：三通道评测（公式全部复用 src/gated_mem/gates.py）
# ---------------------------------------------------------------------------

def evaluate(dataset_path: str) -> Dict[str, Any]:
    """用真实 FastEmbedProvider 跑 vec / fts / fusion 三通道 Top-1 与 Top-3。"""
    from src.gated_mem.embeddings import FastEmbedProvider, non_negative_cosine
    from src.gated_mem.gates import bm25_to_positive, calibrated_fusion, saturate_bm25
    from src.gated_mem.retrieval import _fts_query, _slot_hit
    from src.gated_mem.schema import MemoryNode, MemoryType
    from src.gated_mem.storage import Store

    with open(dataset_path, "r", encoding="utf-8") as f:
        doc = json.load(f)

    provider = FastEmbedProvider()
    rows: List[Dict[str, Any]] = []
    tallies = {"vec": {"top1": 0, "top3": 0}, "fts": {"top1": 0, "top3": 0}, "fusion": {"top1": 0, "top3": 0}}

    for case in doc["cases"]:
        store = Store(":memory:")
        nodes_by_id: Dict[str, MemoryNode] = {}
        for m in case["memories"]:
            node = MemoryNode(
                memory_id=m["id"],
                content=m["content"],
                memory_type=MemoryType(m["memory_type"]),
                subject=m["subject"],
                predicate=m["predicate"],
                input_weight=float(m.get("input_weight", 0.5)),
                embedding=provider.embed_one(m["content"]),
                embedding_model=provider.model_id,
                created_step=int(m["step"]),
                last_cited_step=int(m["step"]),
            )
            store.insert_memory(node)
            nodes_by_id[m["id"]] = node
        query = case["query"]
        q_vec = provider.embed_one(query)
        expected = case["expected_id"]

        # FTS 通道：复用生产 _fts_query + saturate_bm25(bm25_to_positive(bm25))，k=5.0 默认
        s_fts_map: Dict[str, float] = {}
        for mid, raw in store.fts_search(_fts_query(query), limit=500):
            s_fts_map[mid] = saturate_bm25(bm25_to_positive(raw))

        # scored: (memory_id, s_vec, s_fts, s_fusion)
        scored: List[Tuple[str, float, float, float]] = []
        for mid, node in nodes_by_id.items():
            sf = s_fts_map.get(mid, 0.0)
            sv = non_negative_cosine(q_vec, node.embedding) if node.embedding else 0.0
            fusion = calibrated_fusion(sv, sf, _slot_hit(query, node))
            scored.append((mid, sv, sf, fusion))

        detail: Dict[str, Dict[str, Any]] = {}
        for mid, sv, sf, fu in scored:
            detail[mid] = {
                "s_vec": round(sv, 6),
                "s_fts": round(sf, 6),
                "s_fusion": round(fu, 6),
                "slot_hit": bool(_slot_hit(query, nodes_by_id[mid])),
            }

        ranks: Dict[str, Dict[str, Any]] = {}
        for mode, key_idx in (("vec", 1), ("fts", 2), ("fusion", 3)):
            ordered = sorted(scored, key=lambda x: (-x[key_idx], x[0]))
            order = [mid for mid, *_r in ordered]
            rank_of_expected = order.index(expected) + 1
            ranks[mode] = {
                "order": order,
                "expected_rank": rank_of_expected,
                "top1_hit": rank_of_expected == 1,
                "top3_hit": rank_of_expected <= TOPK,
                "top1_id": order[0],
            }
            if ranks[mode]["top1_hit"]:
                tallies[mode]["top1"] += 1
            if ranks[mode]["top3_hit"]:
                tallies[mode]["top3"] += 1

        rows.append(
            {
                "case_id": case["case_id"],
                "entity_kind": case["entity_kind"],
                "identifier": case["identifier"],
                "expected_id": expected,
                "ranks": {
                    mode: {
                        "order": ranks[mode]["order"],
                        "expected_rank": ranks[mode]["expected_rank"],
                        "top1_hit": ranks[mode]["top1_hit"],
                        "top3_hit": ranks[mode]["top3_hit"],
                        "top1_id": ranks[mode]["top1_id"],
                    }
                    for mode in ("vec", "fts", "fusion")
                },
                "scores": detail,
            }
        )
        store.close()

    n = len(rows)
    summary: Dict[str, Dict[str, Any]] = {}
    for mode in ("vec", "fts", "fusion"):
        summary[mode] = {
            "top1_passed": tallies[mode]["top1"],
            "top3_passed": tallies[mode]["top3"],
            "top1_rate": round(tallies[mode]["top1"] / float(n), 6),
            "top3_rate": round(tallies[mode]["top3"] / float(n), 6),
        }

    by_kind: Dict[str, Dict[str, Any]] = {}
    for kind in ("error_code", "config_key", "version", "function_name"):
        kind_rows = [r for r in rows if r["entity_kind"] == kind]
        kn = len(kind_rows)
        by_kind[kind] = {
            "total": kn,
            **{
                "%s_%s" % (mode, metric): round(
                    sum(1 for r in kind_rows if r["ranks"][mode][metric]) / float(kn), 6
                )
                for mode in ("vec", "fts", "fusion")
                for metric in ("top1_hit", "top3_hit")
            },
        }

    gap_pp = round((summary["fusion"]["top1_rate"] - summary["vec"]["top1_rate"]) * 100.0, 6)
    result = {
        "dataset": doc["dataset"],
        "provider": "fastembed-bge-small-zh-v1.5",
        "topk": TOPK,
        "cases": n,
        "by_mode": summary,
        "by_entity_kind": by_kind,
        "fusion_minus_vec_top1_pp": gap_pp,
        "gate_fusion_gain_ge_20pp": gap_pp >= 20.0,
        "rows": rows,
    }
    return result


# ---------------------------------------------------------------------------
# 第 3 部分：Markdown 报告
# ---------------------------------------------------------------------------

def _pct(x: float) -> str:
    return "%.2f%%" % (round(x * 100.0, 2))


def render_report(result: Dict[str, Any], dataset_path: str, sha256: str) -> str:
    rows = result["rows"]
    summary = result["by_mode"]
    n = result["cases"]

    with open(dataset_path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    case_by_id = {c["case_id"]: c for c in doc["cases"]}

    lines: List[str] = []
    ap = lines.append
    ap("# 阶段四 Track B：同语境高碰撞难负例基准（20 组）三通道评测报告")
    ap("")
    ap("基准：benchmarks/data/phase4_hard_negatives_20.json（sha256 " + sha256 + "）")
    ap("")
    ap("Provider：FastEmbedProvider（BAAI/bge-small-zh-v1.5，384 维，fastembed 本地 ONNX）。")
    ap("")
    ap("## 1. 构造目标与判定门")
    ap("")
    ap("- 每组 5 条长记忆（每条 >= 120 汉字）正文措辞 100% 同模板，仅关键标识符与一个参数值不同（标识符族内成员相差 1~2 个字符）。")
    ap("- 判定门（GM-DIRECTIVE-P4-v3.0.0 §3.2）：融合 Top-1 准确率 - 单向量 Top-1 准确率 >= 20pp。")
    ap("- 三通道口径与 benchmarks/eval_phase3_hybrid.py、src/gated_mem/gates.py 完全一致：")
    ap("  - vec = 非负余弦（non_negative_cosine）；")
    ap("  - fts = saturate_bm25(bm25_to_positive(bm25), k=5.0)；")
    ap("  - fusion = calibrated_fusion(s_vec, s_fts, slot_hit)，即 min(1.0, max(0.6*s_vec + 0.4*s_fts, 0.85*s_fts) + 0.15*slot_hit)。")
    ap("- 本组数据中每组 5 条记忆的 subject 相同且出现在 query 中，因此 slot_hit 对 5 条候选同时为真（+0.15 均匀加成，不影响组内排序）；组内区分完全由 FTS 通道承担。")
    ap("")
    ap("## 2. 总表：三通道 Top-1 / Top-3 准确率（%d 组）" % n)
    ap("")
    ap("| 通道 | Top-1 | Top-1 准确率 | Top-3 | Top-3 准确率 |")
    ap("| --- | --- | --- | --- | --- |")
    for mode, label in (("vec", "单向量 vec"), ("fts", "单 FTS5 fts"), ("fusion", "混合融合 fusion")):
        s = summary[mode]
        ap("| %s | %d/%d | %s | %d/%d | %s |" % (
            label, s["top1_passed"], n, _pct(s["top1_rate"]),
            s["top3_passed"], n, _pct(s["top3_rate"]),
        ))
    ap("")
    ap("**融合相对单向量的净增益：fusion Top-1 - vec Top-1 = %+.2f pp**（判定门 >= 20pp：%s）" % (
        result["fusion_minus_vec_top1_pp"], "PASS" if result["gate_fusion_gain_ge_20pp"] else "FAIL",
    ))
    ap("")
    ap("## 3. 分标识符类型小计")
    ap("")
    ap("| entity_kind | 组数 | vec Top-1 | fts Top-1 | fusion Top-1 | vec Top-3 | fts Top-3 | fusion Top-3 |")
    ap("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for kind, d in result["by_entity_kind"].items():
        ap("| %s | %d | %s | %s | %s | %s | %s | %s |" % (
            kind, d["total"], _pct(d["vec_top1_hit"]), _pct(d["fts_top1_hit"]), _pct(d["fusion_top1_hit"]),
            _pct(d["vec_top3_hit"]), _pct(d["fts_top3_hit"]), _pct(d["fusion_top3_hit"]),
        ))
    ap("")
    ap("## 4. 逐组明细（三通道各自对正确答案的排名）")
    ap("")
    ap("| 组 | entity_kind | 查询标识符 | 正确 id | vec 排名 | fts 排名 | fusion 排名 | vec Top-1 落在 |")
    ap("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        ap("| %s | %s | %s | %s | %d | %d | %d | %s |" % (
            r["case_id"], r["entity_kind"], r["identifier"], r["expected_id"],
            r["ranks"]["vec"]["expected_rank"], r["ranks"]["fts"]["expected_rank"],
            r["ranks"]["fusion"]["expected_rank"],
            r["ranks"]["vec"]["top1_id"] + ("" if r["ranks"]["vec"]["top1_hit"] else "（错）"),
        ))
    ap("")
    ap("## 5. 逐组候选打分明细（5 条记忆 × 三通道得分，round 6 位）")
    ap("")
    for r in rows:
        c = case_by_id[r["case_id"]]
        ap("### %s（%s / %s）" % (r["case_id"], r["entity_kind"], c["module"]))
        ap("")
        ap("- query：%s" % c["query"])
        ap("- 正确答案：%s" % r["expected_id"])
        ap("")
        ap("| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |")
        ap("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for m in c["memories"]:
            mid = m["id"]
            sc = r["scores"][mid]
            rv = r["ranks"]["vec"]["order"].index(mid) + 1
            rf = r["ranks"]["fts"]["order"].index(mid) + 1
            rfus = r["ranks"]["fusion"]["order"].index(mid) + 1
            ap("| %s%s | %s | %.6f | %.6f | %.6f | %d | %d | %d |" % (
                mid, " ✅" if mid == r["expected_id"] else "", m["identifier"],
                sc["s_vec"], sc["s_fts"], sc["s_fusion"], rv, rf, rfus,
            ))
        ap("")
    vec_wrong = [r for r in rows if not r["ranks"]["vec"]["top1_hit"]]
    ap("## 6. 单向量失分案例剖析（共 %d 组 vec Top-1 失分，截取前 2 组）" % len(vec_wrong))
    ap("")
    for r in vec_wrong[:2]:
        c = case_by_id[r["case_id"]]
        ap("### 案例 %s：vec 把 %s 排到了第一，正确答案是 %s（%s）" % (
            r["case_id"], r["ranks"]["vec"]["top1_id"], r["expected_id"], r["identifier"],
        ))
        ap("")
        ap("- query：%s" % c["query"])
        ap("- vec Top-1 错误记忆全文：")
        wrong = next(m for m in c["memories"] if m["id"] == r["ranks"]["vec"]["top1_id"])
        exp = next(m for m in c["memories"] if m["id"] == r["expected_id"])
        ap("")
        ap("  > %s" % wrong["content"])
        ap("")
        ap("- 正确记忆全文（只差标识符 %s -> %s 与参数值 %s -> %s）：" % (
            wrong["identifier"], exp["identifier"], wrong["value"], exp["value"],
        ))
        ap("")
        ap("  > %s" % exp["content"])
        ap("")
        ap("- 三通道得分对比（round 6）：")
        ap("")
        ap("| 记忆 id | s_vec | s_fts | s_fusion |")
        ap("| --- | --- | --- | --- |")
        for mid in (r["ranks"]["vec"]["top1_id"], r["expected_id"]):
            sc = r["scores"][mid]
            ap("| %s | %.6f | %.6f | %.6f |" % (mid, sc["s_vec"], sc["s_fts"], sc["s_fusion"]))
        ap("")
        ap("- 机理：两条记忆共享 100%% 句式与背景措辞，差异 token 只占全文极小占比，"
          "bge-small 在 384 维空间里把二者挤进极窄区间，单向量通道被语义噪音挤占 Top-1；"
          "FTS5 对唯一子 token（%s）产生高 IDF bm25 爆发，经 0.85*s_fts 保底融合后正确节点置顶。" % exp["identifier"])
        ap("")
    ap("## 7. 构造方法与可复现说明")
    ap("")
    ap("### 7.1 构造方法")
    ap("")
    ap("1. 同模板碰撞：每组一条 140+ 字中文模板，内含 {ident} 与 {val} 两个占位符；5 条记忆由同一模板渲染，措辞差异仅来自这两个占位符——背景语境雷同度 100%%（句式、参数名、收尾话术完全一致）。")
    ap("2. 标识符微差：族内成员只差 1~2 个字符（ERR_XA_RMFAIL_04 <-> ERR_XA_RMERR_05、read_buffer_size_kb <-> _mb、v2.14.37-rc1 <-> v2.14.38-rc1、reconcile_ledger_entries <-> _entry），且每个成员都含至少一个组内唯一子 token（FTS5 unicode61 会把下划线/点号切开，04/mb/37/entries 即高 IDF 区分器）。")
    ap("3. query 中性化：query 只含模块名（全部候选共享）与唯一精确标识符，不含任何指向正确记忆参数值的暗示。")
    ap("4. 位置摊派：正确答案在 5 条候选中的位置按固定序列摊派到 0..4，避免位置偏差。")
    ap("5. slot_hit 均匀化：每组 5 条记忆 subject 相同且出现在 query 中，slot_hit +0.15 对组内候选等权，不参与组内排序——融合的组内区分完全来自 FTS 通道。")
    ap("")
    ap("### 7.2 可复现步骤")
    ap("")
    ap("~~~")
    ap("# 专用 conda 环境（含 fastembed，禁止污染 base）")
    ap("<conda-env>/python benchmarks/build_phase4_hard_negatives.py")
    ap("")
    ap("# 确定性自检：连跑两次数据文件 sha256 必须一致")
    ap("<conda-env>/python benchmarks/build_phase4_hard_negatives.py --skip-eval --skip-report")
    ap("~~~")
    ap("")
    ap("- 数据文件：benchmarks/data/phase4_hard_negatives_20.json，sha256 " + sha256 + "。")
    ap("- 数据规格：case_id H01..H20；entity_kind 四类各 5 组；每组恰 5 条 >= 120 字长记忆；query 内嵌唯一精确标识符且仅定位到 expected_id。")
    ap("- 评测确定性：无 random/time/env 依赖；FastEmbed ONNX 推理确定性；同分按 memory_id 升序；浮点统一 round 6 位。")
    ap("- 本报告由 build_phase4_hard_negatives.py 在评测后自动渲染，与评测输出逐字一致。")
    ap("")
    return "\n".join(lines)


def main() -> int:
    ap2 = argparse.ArgumentParser(description="阶段四难负例基准构建 + 三通道评测")
    ap2.add_argument("--skip-build", action="store_true", help="不重建 JSON")
    ap2.add_argument("--skip-eval", action="store_true", help="只生成数据，不评测")
    ap2.add_argument("--skip-report", action="store_true", help="不写 Markdown 报告")
    args = ap2.parse_args()

    cases = build_cases()
    doc = build_dataset_document(cases)
    sha = ""
    if not args.skip_build:
        sha = write_dataset(DATA_PATH, doc)
        print("[build] wrote %s (sha256=%s)" % (os.path.relpath(DATA_PATH, PROJECT_ROOT), sha))
    else:
        if os.path.exists(DATA_PATH):
            with open(DATA_PATH, "rb") as f:
                sha = hashlib.sha256(f.read()).hexdigest()
        print("[build] skipped (existing sha256=%s)" % sha)

    if args.skip_eval:
        print("[eval] skipped")
        return 0

    result = evaluate(DATA_PATH)
    summary = result["by_mode"]
    print("=" * 78)
    print("  阶段四难负例三通道评测（%d 组 / Top-%d / fastembed bge-small-zh-v1.5）" % (result["cases"], TOPK))
    print("=" * 78)
    print("  通道      Top-1   Top-1率    Top-3   Top-3率")
    for mode in ("vec", "fts", "fusion"):
        s = summary[mode]
        print("  %-8s %4d/20 %9.2f%% %6d/20 %9.2f%%" % (
            mode.upper(), s["top1_passed"], s["top1_rate"] * 100,
            s["top3_passed"], s["top3_rate"] * 100,
        ))
    print("-" * 78)
    print("  fusion - vec Top-1 净增益 = %+.2f pp（门限 >= 20pp：%s）" % (
        result["fusion_minus_vec_top1_pp"], "PASS" if result["gate_fusion_gain_ge_20pp"] else "FAIL",
    ))
    print("=" * 78)

    if not args.skip_report:
        if not sha:
            with open(DATA_PATH, "rb") as f:
                sha = hashlib.sha256(f.read()).hexdigest()
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8", newline="\n") as f:
            f.write(render_report(result, DATA_PATH, sha))
        print("[report] wrote %s" % os.path.relpath(REPORT_PATH, PROJECT_ROOT))
    return 0 if result["gate_fusion_gain_ge_20pp"] else 1


if __name__ == "__main__":
    sys.exit(main())
