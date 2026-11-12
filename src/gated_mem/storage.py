"""SQLite 存储层：WAL、FTS5、事件溯源与原子 undo。

铁律：
  - 边方向恒为 source_id=child -> target_id=parent
  - superseded / killed 不得被普通写入复活（5x5 矩阵在 schema 层校验，这里再兜一层）
  - undo 必须跨表、跨索引原子：主表 + 边表 + FTS5 一起回滚
  - 严禁任何 print 到 stdout（MCP stdio 协议铁律）
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .schema import (
    EdgeType,
    EventType,
    MemoryEdge,
    MemoryEvent,
    MemoryNode,
    MemoryStatus,
    TrustTier,
    is_transition_allowed,
)

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS memory_events (
    event_id        TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    step            INTEGER NOT NULL,
    event_type      TEXT NOT NULL,
    causation_id    TEXT,
    correlation_id  TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_proj_step ON memory_events(project_id, step);
CREATE INDEX IF NOT EXISTS idx_events_causation ON memory_events(causation_id);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON memory_events(correlation_id);

CREATE TABLE IF NOT EXISTS memories (
    memory_id        TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL,
    content          TEXT NOT NULL,
    memory_type      TEXT NOT NULL,
    subject          TEXT NOT NULL,
    predicate        TEXT NOT NULL,
    scope            TEXT NOT NULL DEFAULT 'global',
    status           TEXT NOT NULL,
    input_weight     REAL NOT NULL DEFAULT 0.5,
    citation_count   INTEGER NOT NULL DEFAULT 0,
    pinned           INTEGER NOT NULL DEFAULT 0,
    trust_tier       TEXT NOT NULL DEFAULT 'model_inferred',
    residual_diff    TEXT,
    embedding        BLOB,
    embedding_model  TEXT NOT NULL DEFAULT 'bge-small',
    created_step     INTEGER NOT NULL,
    last_cited_step  INTEGER NOT NULL,
    source_event_id  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_lookup
    ON memories(project_id, subject, predicate, scope, status);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(project_id, status);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    memory_id UNINDEXED,
    subject,
    content,
    residual_diff,
    tokenize = 'unicode61'
);

CREATE TRIGGER IF NOT EXISTS trg_memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(memory_id, subject, content, residual_diff)
    VALUES (new.memory_id, new.subject, new.content, new.residual_diff);
END;
CREATE TRIGGER IF NOT EXISTS trg_memories_ad AFTER DELETE ON memories BEGIN
    DELETE FROM memories_fts WHERE memory_id = old.memory_id;
END;
CREATE TRIGGER IF NOT EXISTS trg_memories_au AFTER UPDATE ON memories BEGIN
    DELETE FROM memories_fts WHERE memory_id = old.memory_id;
    INSERT INTO memories_fts(memory_id, subject, content, residual_diff)
    VALUES (new.memory_id, new.subject, new.content, new.residual_diff);
END;

CREATE TABLE IF NOT EXISTS memory_edges (
    edge_id         TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    edge_type       TEXT NOT NULL,
    residual_diff   TEXT,
    created_step    INTEGER NOT NULL,
    source_event_id TEXT NOT NULL,
    FOREIGN KEY(source_id) REFERENCES memories(memory_id) ON DELETE CASCADE,
    FOREIGN KEY(target_id) REFERENCES memories(memory_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON memory_edges(project_id, source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON memory_edges(project_id, target_id);

CREATE TABLE IF NOT EXISTS slot_aliases (
    project_id     TEXT NOT NULL,
    alias_name     TEXT NOT NULL,
    canonical_slot TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (project_id, alias_name)
);
"""


class StorageError(RuntimeError):
    """存储层业务错误。"""


class Store(object):
    """单文件 SQLite 存储。

    所有写操作都在显式事务内完成；undo 走同一事务保证跨表原子性。
    """

    def __init__(self, path: str = ":memory:", project_id: str = "default") -> None:
        self.project_id = project_id
        self.conn = sqlite3.connect(path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.executescript(SCHEMA_SQL)

    # -- 事务 -----------------------------------------------------------
    def _begin(self) -> None:
        self.conn.execute("BEGIN IMMEDIATE")

    def _commit(self) -> None:
        self.conn.execute("COMMIT")

    def _rollback(self) -> None:
        try:
            self.conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass

    # -- 事件 -----------------------------------------------------------
    def append_event(
        self,
        event_type: EventType,
        step: int,
        payload: dict,
        causation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> str:
        """追加不可变事件，返回 event_id。"""
        eid = event_id or str(uuid.uuid4())
        cid = correlation_id or str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO memory_events(event_id, project_id, step, event_type,"
            " causation_id, correlation_id, payload_json)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                eid,
                self.project_id,
                step,
                event_type.value,
                causation_id,
                cid,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
        return eid

    def get_event(self, event_id: str) -> Optional[MemoryEvent]:
        """按 id 取事件。"""
        row = self.conn.execute(
            "SELECT * FROM memory_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        return MemoryEvent(
            event_id=row["event_id"],
            project_id=row["project_id"],
            step=row["step"],
            event_type=row["event_type"],
            causation_id=row["causation_id"],
            correlation_id=row["correlation_id"],
            payload_json=row["payload_json"],
        )

    def events_of_correlation(self, correlation_id: str) -> List[MemoryEvent]:
        """取同一事务批次的全部事件，按 step 升序。"""
        rows = self.conn.execute(
            "SELECT * FROM memory_events WHERE correlation_id = ? ORDER BY step ASC, event_id ASC",
            (correlation_id,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def _row_to_event(self, row) -> MemoryEvent:
        return MemoryEvent(
            event_id=row["event_id"],
            project_id=row["project_id"],
            step=row["step"],
            event_type=row["event_type"],
            causation_id=row["causation_id"],
            correlation_id=row["correlation_id"],
            payload_json=row["payload_json"],
        )

    # -- 记忆节点 -------------------------------------------------------
    @staticmethod
    def _pack_embedding(vec: Optional[Sequence[float]]) -> Optional[bytes]:
        """float32 小端序列化。零依赖 numpy 也走这条路径。"""
        if vec is None:
            return None
        import struct

        return struct.pack("<%df" % len(vec), *[float(x) for x in vec])

    @staticmethod
    def unpack_embedding(blob: Optional[bytes]) -> Optional[List[float]]:
        """反序列化 float32 向量。"""
        if blob is None:
            return None
        import struct

        n = len(blob) // 4
        return list(struct.unpack("<%df" % n, blob))

    def insert_memory(self, node: MemoryNode) -> str:
        """插入新节点并写入 MEMORY_CREATED 事件。"""
        self._begin()
        try:
            eid = self.append_event(
                EventType.MEMORY_CREATED,
                node.created_step,
                {
                    "memory_id": node.memory_id,
                    "content": node.content,
                    "status": node.status.value,
                    "stale_parent_warning": False,
                },
            )
            self.conn.execute(
                "INSERT INTO memories(memory_id, project_id, content, memory_type, subject,"
                " predicate, scope, status, input_weight, citation_count, pinned, trust_tier,"
                " residual_diff, embedding, embedding_model, created_step, last_cited_step,"
                " source_event_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    node.memory_id,
                    # 以 store 的 project_id 为准：调用方构造 MemoryNode 时常不传 project_id，
                    # 若用 node.project_id 会把节点写进 'default' 库，导致跨实例读不到。
                    self.project_id,
                    node.content,
                    node.memory_type.value,
                    node.subject,
                    node.predicate,
                    node.scope,
                    node.status.value,
                    node.input_weight,
                    node.citation_count,
                    1 if node.pinned else 0,
                    node.trust_tier.value,
                    node.residual_diff,
                    self._pack_embedding(node.embedding),
                    node.embedding_model,
                    node.created_step,
                    node.last_cited_step,
                    eid,
                ),
            )
            self._commit()
            return eid
        except Exception:
            self._rollback()
            raise

    def get_memory(self, memory_id: str) -> Optional[MemoryNode]:
        """按 id 取节点。"""
        row = self.conn.execute(
            "SELECT * FROM memories WHERE memory_id = ? AND project_id = ?",
            (memory_id, self.project_id),
        ).fetchone()
        return self._row_to_node(row) if row else None

    def _row_to_node(self, row) -> MemoryNode:
        return MemoryNode(
            memory_id=row["memory_id"],
            project_id=row["project_id"],
            content=row["content"],
            memory_type=row["memory_type"],
            subject=row["subject"],
            predicate=row["predicate"],
            scope=row["scope"],
            status=row["status"],
            input_weight=row["input_weight"],
            citation_count=row["citation_count"],
            pinned=bool(row["pinned"]),
            trust_tier=row["trust_tier"],
            residual_diff=row["residual_diff"],
            embedding=self.unpack_embedding(row["embedding"]),
            embedding_model=row["embedding_model"],
            created_step=row["created_step"],
            last_cited_step=row["last_cited_step"],
            source_event_id=row["source_event_id"],
        )

    def all_memories(
        self,
        statuses: Optional[Sequence[str]] = None,
        scope: Optional[str] = None,
    ) -> List[MemoryNode]:
        """列出节点，可按状态与 scope 过滤。"""
        sql = "SELECT * FROM memories WHERE project_id = ?"
        args: List[object] = [self.project_id]
        if statuses:
            sql += " AND status IN (%s)" % ",".join("?" * len(statuses))
            args.extend(statuses)
        if scope is not None:
            sql += " AND scope = ?"
            args.append(scope)
        sql += " ORDER BY created_step ASC, memory_id ASC"
        return [self._row_to_node(r) for r in self.conn.execute(sql, args).fetchall()]

    def find_active_by_slot(self, subject: str, predicate: str, scope: str) -> List[MemoryNode]:
        """按槽位三元组查活跃节点。"""
        rows = self.conn.execute(
            "SELECT * FROM memories WHERE project_id=? AND subject=? AND predicate=?"
            " AND scope=? AND status=? ORDER BY memory_id ASC",
            (self.project_id, subject, predicate, scope, MemoryStatus.ACTIVE.value),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def set_status(
        self,
        memory_id: str,
        new_status: MemoryStatus,
        step: int,
        causation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        allow_matrix_bypass: bool = False,
    ) -> str:
        """状态迁移。默认强制校验 5x5 矩阵，禁止普通写入复活。"""
        node = self.get_memory(memory_id)
        if node is None:
            raise StorageError("节点不存在：%s" % memory_id)
        if not allow_matrix_bypass and not is_transition_allowed(node.status.value, new_status.value):
            raise StorageError(
                "非法状态迁移 %s -> %s（节点 %s）。superseded/killed 只能经 undo 补偿恢复。"
                % (node.status.value, new_status.value, memory_id)
            )
        etype = {
            MemoryStatus.SUPERSEDED.value: EventType.MEMORY_SUPERSEDED,
            MemoryStatus.KILLED.value: EventType.MEMORY_KILLED,
            MemoryStatus.ACTIVE.value: EventType.MEMORY_RESTORED,
        }.get(new_status.value, EventType.MEMORY_RESTORED)
        eid = self.append_event(
            etype,
            step,
            {"memory_id": memory_id, "from": node.status.value, "to": new_status.value},
            causation_id=causation_id,
            correlation_id=correlation_id,
        )
        self.conn.execute(
            "UPDATE memories SET status = ? WHERE memory_id = ?", (new_status.value, memory_id)
        )
        return eid

    def touch_citation(self, memory_id: str, step: int) -> None:
        """刷新 last_cited_step 与 citation_count。

        连接是 isolation_level=None（自动提交），因此不需要显式 commit；
        但必须带 project_id 约束，避免跨项目误改同名节点。
        """
        self.conn.execute(
            "UPDATE memories SET last_cited_step = ?, citation_count = citation_count + 1"
            " WHERE memory_id = ? AND project_id = ?",
            (step, memory_id, self.project_id),
        )

    # -- 边 -------------------------------------------------------------
    def insert_edge(self, edge: MemoryEdge) -> str:
        """插入边并写入 EDGE_CREATED 事件。"""
        self._begin()
        try:
            eid = self.append_event(
                EventType.EDGE_CREATED,
                edge.created_step,
                {
                    "edge_id": edge.edge_id,
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "edge_type": edge.edge_type.value,
                },
            )
            self.conn.execute(
                "INSERT INTO memory_edges(edge_id, project_id, source_id, target_id, edge_type,"
                " residual_diff, created_step, source_event_id) VALUES (?,?,?,?,?,?,?,?)",
                (
                    edge.edge_id,
                    edge.project_id,
                    edge.source_id,
                    edge.target_id,
                    edge.edge_type.value,
                    edge.residual_diff,
                    edge.created_step,
                    eid,
                ),
            )
            self._commit()
            return eid
        except Exception:
            self._rollback()
            raise

    def parents_of(self, memory_id: str, edge_type: Optional[EdgeType] = None) -> List[str]:
        """取父节点 id 列表（source=child -> target=parent）。"""
        sql = "SELECT target_id FROM memory_edges WHERE project_id=? AND source_id=?"
        args: List[object] = [self.project_id, memory_id]
        if edge_type is not None:
            sql += " AND edge_type=?"
            args.append(edge_type.value)
        sql += " ORDER BY target_id ASC"
        return [r["target_id"] for r in self.conn.execute(sql, args).fetchall()]

    def children_of(self, memory_id: str, edge_type: Optional[EdgeType] = None) -> List[str]:
        """取子节点 id 列表。"""
        sql = "SELECT source_id FROM memory_edges WHERE project_id=? AND target_id=?"
        args: List[object] = [self.project_id, memory_id]
        if edge_type is not None:
            sql += " AND edge_type=?"
            args.append(edge_type.value)
        sql += " ORDER BY source_id ASC"
        return [r["source_id"] for r in self.conn.execute(sql, args).fetchall()]

    def ancestors_recursive(
        self, memory_id: str, max_depth: int = 8, edge_type: EdgeType = EdgeType.BELONGS_TO
    ) -> List[Tuple[str, int]]:
        """递归 CTE 向上追溯祖先，返回 [(ancestor_id, depth)]，带防环与深度上限。

        环保护：UNION（去重）语义天然阻断重复节点，另加 depth 上限。
        """
        sql = (
            "WITH RECURSIVE anc(id, depth) AS ("
            "  SELECT target_id, 1 FROM memory_edges"
            "   WHERE project_id=? AND source_id=? AND edge_type=?"
            "  UNION"
            "  SELECT e.target_id, anc.depth+1 FROM memory_edges e"
            "   JOIN anc ON e.source_id = anc.id"
            "   WHERE e.project_id=? AND e.edge_type=? AND anc.depth < ?"
            ") SELECT id, MIN(depth) AS d FROM anc GROUP BY id ORDER BY d ASC, id ASC"
        )
        rows = self.conn.execute(
            sql,
            (
                self.project_id,
                memory_id,
                edge_type.value,
                self.project_id,
                edge_type.value,
                max_depth,
            ),
        ).fetchall()
        return [(r["id"], r["d"]) for r in rows]

    # -- 槽位别名 -------------------------------------------------------
    def upsert_alias(self, alias_name: str, canonical_slot: str) -> None:
        """写入/更新别名映射。"""
        self.conn.execute(
            "INSERT INTO slot_aliases(project_id, alias_name, canonical_slot) VALUES (?,?,?)"
            " ON CONFLICT(project_id, alias_name) DO UPDATE SET canonical_slot=excluded.canonical_slot",
            (self.project_id, alias_name, canonical_slot),
        )

    def resolve_alias(self, name: str) -> str:
        """把别名归一化为规范名；无映射则原样返回。"""
        row = self.conn.execute(
            "SELECT canonical_slot FROM slot_aliases WHERE project_id=? AND alias_name=?",
            (self.project_id, name),
        ).fetchone()
        return row["canonical_slot"] if row else name

    # -- FTS5 -----------------------------------------------------------
    def fts_search(self, query: str, limit: int = 100) -> List[Tuple[str, float]]:
        """FTS5 全文检索，返回 [(memory_id, bm25)]，bm25 越小越相关。"""
        if not query.strip():
            return []
        try:
            rows = self.conn.execute(
                "SELECT memory_id, bm25(memories_fts) AS r FROM memories_fts"
                " WHERE memories_fts MATCH ? ORDER BY r ASC LIMIT ?",
                (query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [(r["memory_id"], r["r"]) for r in rows]

    # -- undo -----------------------------------------------------------
    def undo(self, event_id: str) -> dict:
        """按事件撤销。

        策略：
          - 取该事件所在 correlation_id 的整个批次；
          - 逆序回放，对每个事件按其 payload 还原主表/边表；
          - 写入 EVENT_UNDONE 补偿事件（causation_id 指向被撤销事件）；
          - 整个批次在一个事务内完成，FTS5 由触发器同步维护，天然原子。
        """
        target = self.get_event(event_id)
        if target is None:
            raise StorageError("事件不存在：%s" % event_id)
        batch = self.events_of_correlation(target.correlation_id)

        self._begin()
        try:
            undone: List[str] = []
            for ev in reversed(batch):
                if ev.event_type == EventType.EVENT_UNDONE:
                    continue
                self._replay_one(ev)
                undone.append(ev.event_id)
            self.append_event(
                EventType.EVENT_UNDONE,
                0,
                {"undone_event_ids": undone, "target_event_id": event_id},
                causation_id=event_id,
                correlation_id=target.correlation_id,
            )
            self._commit()
            return {
                "undone_event_ids": undone,
                "target_event_id": event_id,
                "correlation_id": target.correlation_id,
            }
        except Exception:
            self._rollback()
            raise

    def _replay_one(self, ev: MemoryEvent) -> None:
        """把单个事件逆向还原。只回滚主表与边表，FTS5 由触发器跟。"""
        import json as _json

        payload = _json.loads(ev.payload_json) if ev.payload_json else {}
        et = ev.event_type
        if et == EventType.MEMORY_CREATED:
            mid = payload.get("memory_id")
            if mid:
                self.conn.execute("DELETE FROM memory_edges WHERE source_id=? OR target_id=?", (mid, mid))
                self.conn.execute("DELETE FROM memories WHERE memory_id=?", (mid,))
        elif et == EventType.MEMORY_SUPERSEDED or et == EventType.MEMORY_KILLED or et == EventType.MEMORY_RESTORED:
            mid = payload.get("memory_id")
            prev = payload.get("from")
            if mid and prev:
                # undo 是特权路径，允许绕过矩阵（这正是「只能经 undo 恢复」的实现）
                self.conn.execute("UPDATE memories SET status=? WHERE memory_id=?", (prev, mid))
        elif et == EventType.EDGE_CREATED:
            eid = payload.get("edge_id")
            if eid:
                self.conn.execute("DELETE FROM memory_edges WHERE edge_id=?", (eid,))
        elif et == EventType.RECALL_DELIVERED:
            # 召回事件是只读审计记录，undo 不删除它（保留审计痕迹），
            # 但把相关节点的 last_cited_step 还原由 created 快照负责。
            pass

    # -- 全表快照（供审计做 undo 无损性比对）---------------------------
    def snapshot(self) -> dict:
        """导出主表与边表的完整快照，用于 undo 前后逐字段比对。"""
        mem = []
        for r in self.conn.execute(
            "SELECT * FROM memories ORDER BY memory_id ASC"
        ).fetchall():
            d = dict(r)
            d["embedding"] = None if d.get("embedding") is None else self.unpack_embedding(d["embedding"])
            mem.append(d)
        edges = [
            dict(r)
            for r in self.conn.execute("SELECT * FROM memory_edges ORDER BY edge_id ASC").fetchall()
        ]
        fts = [
            dict(r)
            for r in self.conn.execute(
                "SELECT memory_id, subject, content, residual_diff FROM memories_fts ORDER BY memory_id ASC"
            ).fetchall()
        ]
        return {"memories": mem, "edges": edges, "fts": fts}

    def close(self) -> None:
        """关闭连接。"""
        self.conn.close()
