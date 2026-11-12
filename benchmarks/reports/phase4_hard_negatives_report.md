# 阶段四 Track B：同语境高碰撞难负例基准（20 组）三通道评测报告

基准：benchmarks/data/phase4_hard_negatives_20.json（sha256 e679a18066f225fecad0a01b86ec3501d6dfce7ab74b28388d2981c83758bf26）

Provider：FastEmbedProvider（BAAI/bge-small-zh-v1.5，384 维，fastembed 本地 ONNX）。

## 1. 构造目标与判定门

- 每组 5 条长记忆（每条 >= 120 汉字）正文措辞 100% 同模板，仅关键标识符与一个参数值不同（标识符族内成员相差 1~2 个字符）。
- 判定门（GM-DIRECTIVE-P4-v3.0.0 §3.2）：融合 Top-1 准确率 - 单向量 Top-1 准确率 >= 20pp。
- 三通道口径与 benchmarks/eval_phase3_hybrid.py、src/gated_mem/gates.py 完全一致：
  - vec = 非负余弦（non_negative_cosine）；
  - fts = saturate_bm25(bm25_to_positive(bm25), k=5.0)；
  - fusion = calibrated_fusion(s_vec, s_fts, slot_hit)，即 min(1.0, max(0.6*s_vec + 0.4*s_fts, 0.85*s_fts) + 0.15*slot_hit)。
- 本组数据中每组 5 条记忆的 subject 相同且出现在 query 中，因此 slot_hit 对 5 条候选同时为真（+0.15 均匀加成，不影响组内排序）；组内区分完全由 FTS 通道承担。

## 2. 总表：三通道 Top-1 / Top-3 准确率（20 组）

| 通道 | Top-1 | Top-1 准确率 | Top-3 | Top-3 准确率 |
| --- | --- | --- | --- | --- |
| 单向量 vec | 12/20 | 60.00% | 16/20 | 80.00% |
| 单 FTS5 fts | 20/20 | 100.00% | 20/20 | 100.00% |
| 混合融合 fusion | 20/20 | 100.00% | 20/20 | 100.00% |

**融合相对单向量的净增益：fusion Top-1 - vec Top-1 = +40.00 pp**（判定门 >= 20pp：PASS）

## 3. 分标识符类型小计

| entity_kind | 组数 | vec Top-1 | fts Top-1 | fusion Top-1 | vec Top-3 | fts Top-3 | fusion Top-3 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| error_code | 5 | 80.00% | 100.00% | 100.00% | 80.00% | 100.00% | 100.00% |
| config_key | 5 | 60.00% | 100.00% | 100.00% | 80.00% | 100.00% | 100.00% |
| version | 5 | 0.00% | 100.00% | 100.00% | 60.00% | 100.00% | 100.00% |
| function_name | 5 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |

## 4. 逐组明细（三通道各自对正确答案的排名）

| 组 | entity_kind | 查询标识符 | 正确 id | vec 排名 | fts 排名 | fusion 排名 | vec Top-1 落在 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H01 | error_code | ERR_XA_PROTO_08 | H01_M5 | 1 | 1 | 1 | H01_M5 |
| H02 | error_code | PG_ERR_42704 | H02_M3 | 1 | 1 | 1 | H02_M3 |
| H03 | error_code | MQ_SEQ_GAP_11 | H03_M1 | 1 | 1 | 1 | H03_M1 |
| H04 | error_code | CFG_HOT_SYNC_FAIL_34 | H04_M4 | 4 | 1 | 1 | H04_M5（错） |
| H05 | error_code | IDEM_DUP_WIN_72 | H05_M2 | 1 | 1 | 1 | H05_M2 |
| H06 | config_key | read_buffer_size_mb | H06_M2 | 1 | 1 | 1 | H06_M2 |
| H07 | config_key | session_gc_interval_hr | H07_M3 | 1 | 1 | 1 | H07_M3 |
| H08 | config_key | tls_handshake_timeout_ms | H08_M1 | 1 | 1 | 1 | H08_M1 |
| H09 | config_key | log_rotate_max_size_tb | H09_M4 | 4 | 1 | 1 | H09_M5（错） |
| H10 | config_key | rate_limit_burst_512 | H10_M4 | 2 | 1 | 1 | H10_M1（错） |
| H11 | version | v2.14.37-rc1 | H11_M1 | 4 | 1 | 1 | H11_M3（错） |
| H12 | version | fw_1.8.55-hotfix | H12_M4 | 3 | 1 | 1 | H12_M5（错） |
| H13 | version | sdk_3.4.22-beta | H13_M2 | 3 | 1 | 1 | H13_M4（错） |
| H14 | version | img_1.21.48-stable | H14_M5 | 2 | 1 | 1 | H14_M4（错） |
| H15 | version | kmod_6.2.19-lts | H15_M3 | 4 | 1 | 1 | H15_M1（错） |
| H16 | function_name | reconcile_ledger_entries | H16_M1 | 1 | 1 | 1 | H16_M1 |
| H17 | function_name | parse_wire_trailer | H17_M3 | 1 | 1 | 1 | H17_M3 |
| H18 | function_name | drain_flush_queues | H18_M2 | 1 | 1 | 1 | H18_M2 |
| H19 | function_name | scrape_targat_refresh | H19_M1 | 1 | 1 | 1 | H19_M1 |
| H20 | function_name | compact_sst_tables | H20_M5 | 1 | 1 | 1 | H20_M5 |

## 5. 逐组候选打分明细（5 条记忆 × 三通道得分，round 6 位）

### H01（error_code / 分布式事务重试模块）

- query：高并发压测之后，分布式事务重试模块里错误码 ERR_XA_PROTO_08 的退避参数应按哪条记录调整？
- 正确答案：H01_M5

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H01_M1 | ERR_XA_RMFAIL_04 | 0.814864 | 0.000000 | 0.638918 | 3 | 2 | 3 |
| H01_M2 | ERR_XA_RMERR_05 | 0.811287 | 0.000000 | 0.636772 | 5 | 3 | 5 |
| H01_M3 | ERR_XA_NOTA_06 | 0.814923 | 0.000000 | 0.638954 | 2 | 4 | 2 |
| H01_M4 | ERR_XA_INVAL_07 | 0.814808 | 0.000000 | 0.638885 | 4 | 5 | 4 |
| H01_M5 ✅ | ERR_XA_PROTO_08 | 0.816859 | 0.180141 | 0.712172 | 1 | 1 | 1 |

### H02（error_code / 存储网关巡检模块）

- query：存储网关巡检模块的看板里，错误码 PG_ERR_42704 对应的处置参数记录在哪一条？
- 正确答案：H02_M3

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H02_M1 | PG_ERR_42P01 | 0.820597 | 0.000000 | 0.642358 | 3 | 2 | 3 |
| H02_M2 | PG_ERR_42P02 | 0.820407 | 0.000000 | 0.642244 | 4 | 3 | 4 |
| H02_M3 ✅ | PG_ERR_42704 | 0.836606 | 0.180141 | 0.724020 | 1 | 1 | 1 |
| H02_M4 | PG_ERR_42883 | 0.829836 | 0.000000 | 0.647902 | 2 | 4 | 2 |
| H02_M5 | PG_ERR_42P07 | 0.819962 | 0.000000 | 0.641977 | 5 | 5 | 5 |

### H03（error_code / 消息队列接入模块）

- query：消息队列接入模块的早班复盘里，告警 MQ_SEQ_GAP_11 对应的回补参数记录在哪一条？
- 正确答案：H03_M1

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H03_M1 ✅ | MQ_SEQ_GAP_11 | 0.810844 | 0.180141 | 0.708563 | 1 | 1 | 1 |
| H03_M2 | MQ_SEQ_GAP_12 | 0.807483 | 0.000000 | 0.634490 | 2 | 2 | 2 |
| H03_M3 | MQ_SEQ_GAP_13 | 0.804545 | 0.000000 | 0.632727 | 5 | 3 | 5 |
| H03_M4 | MQ_SEQ_GAP_14 | 0.807392 | 0.000000 | 0.634435 | 3 | 4 | 3 |
| H03_M5 | MQ_SEQ_GAP_15 | 0.807371 | 0.000000 | 0.634423 | 4 | 5 | 4 |

### H04（error_code / 配置中心热更新模块）

- query：配置中心热更新模块的审计簿里，错误码 CFG_HOT_SYNC_FAIL_34 的对账参数记录在哪一条？
- 正确答案：H04_M4

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H04_M1 | CFG_HOT_SYNC_FAIL_31 | 0.800167 | 0.000000 | 0.630100 | 5 | 2 | 5 |
| H04_M2 | CFG_HOT_SYNC_FAIL_32 | 0.801648 | 0.000000 | 0.630989 | 3 | 3 | 4 |
| H04_M3 | CFG_HOT_SYNC_FAIL_33 | 0.801674 | 0.000000 | 0.631004 | 2 | 4 | 3 |
| H04_M4 ✅ | CFG_HOT_SYNC_FAIL_34 | 0.801049 | 0.180141 | 0.702686 | 4 | 1 | 1 |
| H04_M5 | CFG_HOT_SYNC_FAIL_35 | 0.802107 | 0.000000 | 0.631264 | 1 | 5 | 2 |

### H05（error_code / 幂等去重模块）

- query：幂等去重模块的复盘记录里，错误码 IDEM_DUP_WIN_72 的窗口参数对应哪一条？
- 正确答案：H05_M2

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H05_M1 | IDEM_DUP_WIN_71 | 0.798594 | 0.000000 | 0.629157 | 5 | 2 | 5 |
| H05_M2 ✅ | IDEM_DUP_WIN_72 | 0.803259 | 0.180141 | 0.704012 | 1 | 1 | 1 |
| H05_M3 | IDEM_DUP_WIN_73 | 0.802113 | 0.000000 | 0.631268 | 2 | 3 | 2 |
| H05_M4 | IDEM_DUP_WIN_74 | 0.801721 | 0.000000 | 0.631032 | 3 | 4 | 3 |
| H05_M5 | IDEM_DUP_WIN_75 | 0.799485 | 0.000000 | 0.629691 | 4 | 5 | 4 |

### H06（config_key / 网关读缓冲调优模块）

- query：网关读缓冲调优模块的评审记录里，配置项 read_buffer_size_mb 的推荐取值是哪一条？
- 正确答案：H06_M2

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H06_M1 | read_buffer_size_kb | 0.908092 | 0.000000 | 0.694855 | 2 | 2 | 2 |
| H06_M2 ✅ | read_buffer_size_mb | 0.915902 | 0.180141 | 0.771598 | 1 | 1 | 1 |
| H06_M3 | read_buffer_size_gb | 0.899719 | 0.000000 | 0.689831 | 4 | 3 | 4 |
| H06_M4 | read_buffer_size_kib | 0.895496 | 0.000000 | 0.687297 | 5 | 4 | 5 |
| H06_M5 | read_buffer_size_mib | 0.905890 | 0.000000 | 0.693534 | 3 | 5 | 3 |

### H07（config_key / 会话过期调度模块）

- query：会话过期调度模块的复盘里，配置项 session_gc_interval_hr 的基线取值是哪一条？
- 正确答案：H07_M3

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H07_M1 | session_gc_interval_min | 0.875866 | 0.000000 | 0.675520 | 3 | 2 | 3 |
| H07_M2 | session_gc_interval_sec | 0.873368 | 0.000000 | 0.674021 | 4 | 3 | 4 |
| H07_M3 ✅ | session_gc_interval_hr | 0.884994 | 0.180141 | 0.753053 | 1 | 1 | 1 |
| H07_M4 | session_gc_interval_day | 0.878281 | 0.000000 | 0.676968 | 2 | 4 | 2 |
| H07_M5 | session_gc_interval_tick | 0.869133 | 0.000000 | 0.671480 | 5 | 5 | 5 |

### H08（config_key / TLS 握手压测模块）

- query：TLS 握手压测模块的纪要里，配置项 tls_handshake_timeout_ms 的推荐取值是哪一条？
- 正确答案：H08_M1

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H08_M1 ✅ | tls_handshake_timeout_ms | 0.840174 | 0.180142 | 0.726161 | 1 | 1 | 1 |
| H08_M2 | tls_handshake_timeout_us | 0.832948 | 0.000000 | 0.649769 | 5 | 2 | 5 |
| H08_M3 | tls_handshake_timeout_ns | 0.835964 | 0.000000 | 0.651578 | 2 | 3 | 2 |
| H08_M4 | tls_handshake_timeout_s | 0.835250 | 0.000000 | 0.651150 | 4 | 4 | 4 |
| H08_M5 | tls_handshake_timeout_sec | 0.835524 | 0.000000 | 0.651314 | 3 | 5 | 3 |

### H09（config_key / 日志轮转模块）

- query：日志轮转模块的巡检纪要里，配置项 log_rotate_max_size_tb 的基线取值是哪一条？
- 正确答案：H09_M4

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H09_M1 | log_rotate_max_size_mb | 0.894010 | 0.000000 | 0.686406 | 2 | 2 | 3 |
| H09_M2 | log_rotate_max_size_kb | 0.892871 | 0.000000 | 0.685723 | 3 | 3 | 4 |
| H09_M3 | log_rotate_max_size_gb | 0.889386 | 0.000000 | 0.683632 | 5 | 4 | 5 |
| H09_M4 ✅ | log_rotate_max_size_tb | 0.892156 | 0.180141 | 0.757350 | 4 | 1 | 1 |
| H09_M5 | log_rotate_max_size_pb | 0.894052 | 0.000000 | 0.686431 | 1 | 5 | 2 |

### H10（config_key / 限流器调参模块）

- query：限流器调参模块的演练纪要里，配置项 rate_limit_burst_512 的冷却参数记录在哪一条？
- 正确答案：H10_M4

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H10_M1 | rate_limit_burst_64 | 0.806750 | 0.000000 | 0.634050 | 1 | 2 | 2 |
| H10_M2 | rate_limit_burst_128 | 0.804446 | 0.000000 | 0.632667 | 3 | 3 | 3 |
| H10_M3 | rate_limit_burst_256 | 0.804162 | 0.000000 | 0.632497 | 4 | 4 | 4 |
| H10_M4 ✅ | rate_limit_burst_512 | 0.804552 | 0.180141 | 0.704788 | 2 | 1 | 1 |
| H10_M5 | rate_limit_burst_1024 | 0.800451 | 0.000000 | 0.630271 | 5 | 5 | 5 |

### H11（version / 网关灰度发布模块）

- query：网关灰度发布模块的演练档案里，版本 v2.14.37-rc1 的放量比例记录在哪一条？
- 正确答案：H11_M1

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H11_M1 ✅ | v2.14.37-rc1 | 0.822304 | 0.180142 | 0.715439 | 4 | 1 | 1 |
| H11_M2 | v2.14.38-rc1 | 0.822808 | 0.000001 | 0.643685 | 2 | 2 | 3 |
| H11_M3 | v2.14.39-rc1 | 0.823180 | 0.000001 | 0.643908 | 1 | 3 | 2 |
| H11_M4 | v2.14.40-rc1 | 0.821529 | 0.000001 | 0.642918 | 5 | 4 | 5 |
| H11_M5 | v2.14.41-rc1 | 0.822494 | 0.000001 | 0.643496 | 3 | 5 | 4 |

### H12（version / 网卡固件升级模块）

- query：网卡固件升级模块的机房纪要里，固件版本 fw_1.8.55-hotfix 的刷写间隔记录在哪一条？
- 正确答案：H12_M4

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H12_M1 | fw_1.8.52-hotfix | 0.861173 | 0.000001 | 0.666704 | 5 | 2 | 5 |
| H12_M2 | fw_1.8.53-hotfix | 0.862538 | 0.000001 | 0.667523 | 4 | 3 | 4 |
| H12_M3 | fw_1.8.54-hotfix | 0.863260 | 0.000001 | 0.667956 | 2 | 4 | 3 |
| H12_M4 ✅ | fw_1.8.55-hotfix | 0.862586 | 0.180142 | 0.739608 | 3 | 1 | 1 |
| H12_M5 | fw_1.8.56-hotfix | 0.863326 | 0.000001 | 0.667996 | 1 | 5 | 2 |

### H13（version / 客户端 SDK 发布模块）

- query：客户端 SDK 发布模块的评审里，SDK 版本 sdk_3.4.22-beta 的预热比例记录在哪一条？
- 正确答案：H13_M2

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H13_M1 | sdk_3.4.21-beta | 0.821184 | 0.000001 | 0.642711 | 5 | 2 | 5 |
| H13_M2 ✅ | sdk_3.4.22-beta | 0.823074 | 0.180142 | 0.715901 | 3 | 1 | 1 |
| H13_M3 | sdk_3.4.23-beta | 0.824362 | 0.000001 | 0.644618 | 2 | 3 | 3 |
| H13_M4 | sdk_3.4.24-beta | 0.824543 | 0.000001 | 0.644726 | 1 | 4 | 2 |
| H13_M5 | sdk_3.4.25-beta | 0.823071 | 0.000001 | 0.643843 | 4 | 5 | 4 |

### H14（version / 容器镜像发布模块）

- query：容器镜像发布模块的值守纪要里，镜像版本 img_1.21.48-stable 的滚动窗口记录在哪一条？
- 正确答案：H14_M5

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H14_M1 | img_1.21.44-stable | 0.842721 | 0.000001 | 0.655633 | 3 | 2 | 3 |
| H14_M2 | img_1.21.45-stable | 0.842495 | 0.000001 | 0.655497 | 4 | 3 | 4 |
| H14_M3 | img_1.21.46-stable | 0.841807 | 0.000001 | 0.655084 | 5 | 4 | 5 |
| H14_M4 | img_1.21.47-stable | 0.845168 | 0.000001 | 0.657101 | 1 | 5 | 2 |
| H14_M5 ✅ | img_1.21.48-stable | 0.844109 | 0.180142 | 0.728522 | 2 | 1 | 1 |

### H15（version / 内核模块兼容性模块）

- query：内核模块兼容性模块的回归纪要里，版本 kmod_6.2.19-lts 的回归并发记录在哪一条？
- 正确答案：H15_M3

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H15_M1 | kmod_6.2.17-lts | 0.853411 | 0.000001 | 0.662047 | 1 | 2 | 2 |
| H15_M2 | kmod_6.2.18-lts | 0.853143 | 0.000001 | 0.661886 | 2 | 3 | 3 |
| H15_M3 ✅ | kmod_6.2.19-lts | 0.852038 | 0.180142 | 0.733280 | 4 | 1 | 1 |
| H15_M4 | kmod_6.2.20-lts | 0.848425 | 0.000001 | 0.659055 | 5 | 4 | 5 |
| H15_M5 | kmod_6.2.21-lts | 0.852129 | 0.000001 | 0.661277 | 3 | 5 | 4 |

### H16（function_name / 账务对账服务模块）

- query：账务对账服务模块的值班纪要里，函数 reconcile_ledger_entries 的分片大小记录在哪一条？
- 正确答案：H16_M1

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H16_M1 ✅ | reconcile_ledger_entries | 0.819877 | 0.180141 | 0.713983 | 1 | 1 | 1 |
| H16_M2 | reconcile_ledger_entry | 0.804057 | 0.000000 | 0.632434 | 5 | 2 | 5 |
| H16_M3 | reconcile_ledger_vouchers | 0.806629 | 0.000000 | 0.633978 | 4 | 3 | 4 |
| H16_M4 | reconcile_ledger_invoices | 0.812164 | 0.000000 | 0.637299 | 3 | 4 | 3 |
| H16_M5 | reconcile_ledger_receipts | 0.816756 | 0.000000 | 0.640054 | 2 | 5 | 2 |

### H17（function_name / 流解析服务模块）

- query：流解析服务模块的复盘里，函数 parse_wire_trailer 的缓冲区参数记录在哪一条？
- 正确答案：H17_M3

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H17_M1 | parse_wire_payload | 0.801661 | 0.000000 | 0.630997 | 5 | 2 | 5 |
| H17_M2 | parse_wire_header | 0.815019 | 0.000000 | 0.639012 | 3 | 3 | 3 |
| H17_M3 ✅ | parse_wire_trailer | 0.841216 | 0.180141 | 0.726786 | 1 | 1 | 1 |
| H17_M4 | parse_wire_checksum | 0.816886 | 0.000000 | 0.640132 | 2 | 4 | 2 |
| H17_M5 | parse_wire_padding | 0.802993 | 0.000000 | 0.631796 | 4 | 5 | 4 |

### H18（function_name / 刷写队列服务模块）

- query：刷写队列服务模块的巡检纪要里，函数 drain_flush_queues 的单轮配额记录在哪一条？
- 正确答案：H18_M2

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H18_M1 | drain_flush_queue | 0.828486 | 0.000000 | 0.647092 | 2 | 2 | 2 |
| H18_M2 ✅ | drain_flush_queues | 0.830330 | 0.180141 | 0.720254 | 1 | 1 | 1 |
| H18_M3 | drain_flush_queued | 0.827857 | 0.000000 | 0.646714 | 3 | 3 | 3 |
| H18_M4 | drain_purge_queue | 0.822822 | 0.000000 | 0.643693 | 4 | 4 | 4 |
| H18_M5 | drain_retry_queue | 0.822716 | 0.000000 | 0.643630 | 5 | 5 | 5 |

### H19（function_name / 指标抓取服务模块）

- query：指标抓取服务模块的观测纪要里，函数 scrape_targat_refresh 的抓取超时记录在哪一条？
- 正确答案：H19_M1

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H19_M1 ✅ | scrape_targat_refresh | 0.877862 | 0.180141 | 0.748774 | 1 | 1 | 1 |
| H19_M2 | scrape_target_refresh | 0.868142 | 0.000000 | 0.670885 | 3 | 2 | 3 |
| H19_M3 | scrape_targets_refresh | 0.870938 | 0.000000 | 0.672563 | 2 | 3 | 2 |
| H19_M4 | scrape_target_relabel | 0.860600 | 0.000000 | 0.666360 | 4 | 4 | 4 |
| H19_M5 | scrape_target_expired | 0.858610 | 0.000000 | 0.665166 | 5 | 5 | 5 |

### H20（function_name / SST 压实服务模块）

- query：SST 压实服务模块的巡检纪要里，函数 compact_sst_tables 的单批页数记录在哪一条？
- 正确答案：H20_M5

| 记忆 id | 标识符 | s_vec | s_fts | s_fusion | vec 排名 | fts 排名 | fusion 排名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H20_M1 | compact_sst_segments | 0.846031 | 0.000001 | 0.657619 | 4 | 2 | 4 |
| H20_M2 | compact_sst_segment | 0.846133 | 0.000001 | 0.657680 | 3 | 3 | 3 |
| H20_M3 | compact_sst_segmemts | 0.843207 | 0.000001 | 0.655924 | 5 | 4 | 5 |
| H20_M4 | compact_sst_blocks | 0.852807 | 0.000001 | 0.661684 | 2 | 5 | 2 |
| H20_M5 ✅ | compact_sst_tables | 0.859705 | 0.180142 | 0.737880 | 1 | 1 | 1 |

## 6. 单向量失分案例剖析（共 8 组 vec Top-1 失分，截取前 2 组）

### 案例 H04：vec 把 H04_M5 排到了第一，正确答案是 H04_M4（CFG_HOT_SYNC_FAIL_34）

- query：配置中心热更新模块的审计簿里，错误码 CFG_HOT_SYNC_FAIL_34 的对账参数记录在哪一条？
- vec Top-1 错误记忆全文：

  > 在配置中心热更新模块的变更审计里，当热更新同步失败并上报错误码 CFG_HOT_SYNC_FAIL_35 时，值守团队会把处置动作写进变更审计簿：先将全量对账间隔 full_reconcile_sec 调整为 90，再保持灰度名单校验开启，最后把受影响租户清单附在当班交接文档；该预案自上线以来稳定运行，未再出现配置漂移，与同族错误码共用同一模板，仅参数不同，评审时逐条核对即可。

- 正确记忆全文（只差标识符 CFG_HOT_SYNC_FAIL_35 -> CFG_HOT_SYNC_FAIL_34 与参数值 90 -> 75）：

  > 在配置中心热更新模块的变更审计里，当热更新同步失败并上报错误码 CFG_HOT_SYNC_FAIL_34 时，值守团队会把处置动作写进变更审计簿：先将全量对账间隔 full_reconcile_sec 调整为 75，再保持灰度名单校验开启，最后把受影响租户清单附在当班交接文档；该预案自上线以来稳定运行，未再出现配置漂移，与同族错误码共用同一模板，仅参数不同，评审时逐条核对即可。

- 三通道得分对比（round 6）：

| 记忆 id | s_vec | s_fts | s_fusion |
| --- | --- | --- | --- |
| H04_M5 | 0.802107 | 0.000000 | 0.631264 |
| H04_M4 | 0.801049 | 0.180141 | 0.702686 |

- 机理：两条记忆共享 100% 句式与背景措辞，差异 token 只占全文极小占比，bge-small 在 384 维空间里把二者挤进极窄区间，单向量通道被语义噪音挤占 Top-1；FTS5 对唯一子 token（CFG_HOT_SYNC_FAIL_34）产生高 IDF bm25 爆发，经 0.85*s_fts 保底融合后正确节点置顶。

### 案例 H09：vec 把 H09_M5 排到了第一，正确答案是 H09_M4（log_rotate_max_size_tb）

- query：日志轮转模块的巡检纪要里，配置项 log_rotate_max_size_tb 的基线取值是哪一条？
- vec Top-1 错误记忆全文：

  > 在日志轮转模块的巡检纪要里，配置项 log_rotate_max_size_pb 的基线取值被登记成一条记录：先把单文件轮转上限落到该配置项并设为 1024，再保持磁盘水位告警开启，最后把轮转耗时统计附到当班交接文档；该取值自上线以来稳定运行，未再出现日志盘写满，与同族配置项共用同一模板，仅后缀与取值不同，评审时逐条核对即可。

- 正确记忆全文（只差标识符 log_rotate_max_size_pb -> log_rotate_max_size_tb 与参数值 1024 -> 512）：

  > 在日志轮转模块的巡检纪要里，配置项 log_rotate_max_size_tb 的基线取值被登记成一条记录：先把单文件轮转上限落到该配置项并设为 512，再保持磁盘水位告警开启，最后把轮转耗时统计附到当班交接文档；该取值自上线以来稳定运行，未再出现日志盘写满，与同族配置项共用同一模板，仅后缀与取值不同，评审时逐条核对即可。

- 三通道得分对比（round 6）：

| 记忆 id | s_vec | s_fts | s_fusion |
| --- | --- | --- | --- |
| H09_M5 | 0.894052 | 0.000000 | 0.686431 |
| H09_M4 | 0.892156 | 0.180141 | 0.757350 |

- 机理：两条记忆共享 100% 句式与背景措辞，差异 token 只占全文极小占比，bge-small 在 384 维空间里把二者挤进极窄区间，单向量通道被语义噪音挤占 Top-1；FTS5 对唯一子 token（log_rotate_max_size_tb）产生高 IDF bm25 爆发，经 0.85*s_fts 保底融合后正确节点置顶。

## 7. 构造方法与可复现说明

### 7.1 构造方法

1. 同模板碰撞：每组一条 140+ 字中文模板，内含 {ident} 与 {val} 两个占位符；5 条记忆由同一模板渲染，措辞差异仅来自这两个占位符——背景语境雷同度 100%%（句式、参数名、收尾话术完全一致）。
2. 标识符微差：族内成员只差 1~2 个字符（ERR_XA_RMFAIL_04 <-> ERR_XA_RMERR_05、read_buffer_size_kb <-> _mb、v2.14.37-rc1 <-> v2.14.38-rc1、reconcile_ledger_entries <-> _entry），且每个成员都含至少一个组内唯一子 token（FTS5 unicode61 会把下划线/点号切开，04/mb/37/entries 即高 IDF 区分器）。
3. query 中性化：query 只含模块名（全部候选共享）与唯一精确标识符，不含任何指向正确记忆参数值的暗示。
4. 位置摊派：正确答案在 5 条候选中的位置按固定序列摊派到 0..4，避免位置偏差。
5. slot_hit 均匀化：每组 5 条记忆 subject 相同且出现在 query 中，slot_hit +0.15 对组内候选等权，不参与组内排序——融合的组内区分完全来自 FTS 通道。

### 7.2 可复现步骤

~~~
# 专用 conda 环境（含 fastembed，禁止污染 base）
<conda-env>/python benchmarks/build_phase4_hard_negatives.py

# 确定性自检：连跑两次数据文件 sha256 必须一致
<conda-env>/python benchmarks/build_phase4_hard_negatives.py --skip-eval --skip-report
~~~

- 数据文件：benchmarks/data/phase4_hard_negatives_20.json，sha256 e679a18066f225fecad0a01b86ec3501d6dfce7ab74b28388d2981c83758bf26。
- 数据规格：case_id H01..H20；entity_kind 四类各 5 组；每组恰 5 条 >= 120 字长记忆；query 内嵌唯一精确标识符且仅定位到 expected_id。
- 评测确定性：无 random/time/env 依赖；FastEmbed ONNX 推理确定性；同分按 memory_id 升序；浮点统一 round 6 位。
- 本报告由 build_phase4_hard_negatives.py 在评测后自动渲染，与评测输出逐字一致。
