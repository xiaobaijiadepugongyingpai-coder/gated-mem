"""生成 docs/demo_memory_graph.html 开源演示图谱。

跑一段真实的架构演进剧本，覆盖 active / superseded / pinned /
stale_parent_warning / [Replaced: ...] 全部分支，导出成单文件离线 HTML。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.gated_mem.embeddings import BuiltinHashEmbedder
from src.gated_mem.exporter import build_snapshot, export_html
from src.gated_mem.schema import EdgeType, MemoryEdge, MemoryNode, MemoryStatus, MemoryType
from src.gated_mem.storage import Store


def build_demo() -> Store:
    """构造 15 个节点的真实演进剧本。"""
    p = BuiltinHashEmbedder()
    s = Store(":memory:", project_id="demo")

    def add(mid, content, mtype, subject, predicate, step, pinned=False,
            parents=(), residual=None, scope="global"):
        s.insert_memory(MemoryNode(
            memory_id=mid, content=content, memory_type=mtype,
            subject=subject, predicate=predicate, scope=scope,
            pinned=pinned, residual_diff=residual,
            embedding=p.embed_one(content), embedding_model=p.model_id,
            created_step=step, last_cited_step=step,
        ))
        for par in parents:
            s.insert_edge(MemoryEdge(
                edge_id="E_%s_%s" % (mid, par), source_id=mid, target_id=par,
                edge_type=EdgeType.BELONGS_TO, created_step=step,
            ))

    # --- 旧技术栈（将被覆盖） ---
    add("M1", "主数据库选用 MySQL 8.0 作为生产存储，三节点主从复制。",
        MemoryType.DECISION, "主数据库", "选型", 1)
    add("M2", "单元测试必须 mock 数据库连接，禁止直连生产库。",
        MemoryType.CONSTRAINT, "测试规范", "隔离", 12, parents=("M1",))
    add("M3", "注释一律使用中文，变量名保持英文。",
        MemoryType.PREFERENCE, "代码风格", "注释语言", 20, parents=("M1",))
    add("M4", "全库禁止硬编码任何密钥，一律走环境变量注入。",
        MemoryType.CONSTRAINT, "安全约束", "密钥管理", 28, parents=("M1",), pinned=True)

    # --- 覆盖：MySQL -> PostgreSQL ---
    add("M5", "主数据库切换为 PostgreSQL 16，以支持 JSONB 高并发索引查询。",
        MemoryType.DECISION, "主数据库", "选型", 140,
        residual="[Replaced: MySQL] 连接池在写入高峰期持续打满，JSONB 查询需求无法满足。")

    # --- 新一代细则（挂在被覆盖的 M1 下，用于演示 stale 告警） ---
    add("M6", "分片键统一使用 tenant_id，禁止使用自增主键作为路由依据。",
        MemoryType.CONSTRAINT, "分库分表", "分片键", 60, parents=("M1",))
    add("M7", "连接池大小固定为 20，超过则触发告警而非自动扩容。",
        MemoryType.CONSTRAINT, "连接池", "容量", 75, parents=("M6",))
    add("M8", "慢查询阈值设为 200ms，超过即记录到审计表。",
        MemoryType.PREFERENCE, "可观测性", "慢查询阈值", 90, parents=("M7",))

    # --- 认证演进 ---
    add("M9", "认证方案使用 Session Cookie，有效期 7 天。",
        MemoryType.DECISION, "认证", "方案", 110)
    add("M10", "认证方案升级为 OAuth 2.1 + PKCE，不再使用服务端会话。",
        MemoryType.DECISION, "认证", "方案", 210,
        residual="[Replaced: Session Cookie] 多端登录与会话劫持风险无法在接受范围内收敛。")

    # --- 前端构建 ---
    add("M11", "前端构建器使用 webpack 5，配置集中在 config/ 目录。",
        MemoryType.DECISION, "前端构建", "工具", 130)
    add("M12", "前端构建器替换为 Vite 5，开发期冷启动从 40s 降到 1.2s。",
        MemoryType.DECISION, "前端构建", "工具", 260,
        residual="[Replaced: webpack] 大型 monorepo 下 HMR 退化严重，构建耗时不可接受。")

    # --- 临时观察与锁定节点 ---
    add("M13", "昨晚编译失败疑似 CI 缓存未清理，已手动清理待观察。",
        MemoryType.EPHEMERAL, "CI", "临时观察", 300)
    add("M14", "发布窗口固定在每周二与周四 20:00-22:00，其余时间禁止上线。",
        MemoryType.CONSTRAINT, "发布流程", "窗口", 320, pinned=True)
    add("M15", "告警通道从 PagerDuty 迁移到 Grafana OnCall，降低误报噪音。",
        MemoryType.DECISION, "告警", "通道", 340,
        residual="[Replaced: PagerDuty] 分级策略无法自定义，值班同学半夜被无意义告警吵醒。")

    # --- 执行覆盖：把 M1 / M9 / M11 标为 superseded ---
    for mid, step in (("M1", 141), ("M9", 211), ("M11", 261)):
        s.set_status(mid, MemoryStatus.SUPERSEDED, step)

    return s


def main() -> int:
    store = build_demo()
    out = ROOT / "docs" / "demo_memory_graph.html"
    stats = export_html(store, out)
    snap = build_snapshot(store)
    stale = [n["id"] for n in snap["nodes"] if n["stale"]]
    by_status = {}
    for n in snap["nodes"]:
        by_status[n["status"]] = by_status.get(n["status"], 0) + 1
    pinned = [n["id"] for n in snap["nodes"] if n["pinned"]]
    with_diff = [n["id"] for n in snap["nodes"] if n["residual_diff"]]

    print("已导出 %s" % out)
    print("  节点 %d / 边 %d / %.1f KB" % (stats["nodes"], stats["edges"], stats["bytes"] / 1024.0))
    print("  状态分布: %s" % by_status)
    print("  pinned: %s" % pinned)
    print("  带 [Replaced:] 轨迹: %s" % with_diff)
    print("  stale 告警节点: %s" % stale)
    store.close()
    return 0 if stats["nodes"] == 15 else 1


if __name__ == "__main__":
    sys.exit(main())
