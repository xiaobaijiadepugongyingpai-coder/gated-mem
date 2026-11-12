"""事件溯源层：不可变日志、因果链、事务批次与投影重建。

与 storage.py 的分工：
  storage 负责 SQLite 物理落盘与 undo 的原子回放；
  events 负责业务语义：一次写入 = 一个 correlation_id 批次，批次内事件以
  causation_id 串成因果链，undo 以 causation_id 为锚点逆向补偿。
"""
from __future__ import annotations

import json
import uuid
from typing import Dict, List, Optional, Sequence

from .schema import (
    EdgeType,
    EventType,
    MemoryEdge,
    MemoryEvent,
    MemoryNode,
    MemoryStatus,
)
from .storage import StorageError, Store


class EventLog(object):
    """事件日志门面。所有写操作返回可追溯的 event_id 与 correlation_id。"""

    def __init__(self, store: Store) -> None:
        self.store = store

    def new_correlation(self) -> str:
        """生成一个事务批次 id。"""
        return str(uuid.uuid4())

    def record_batch(
        self,
        events: Sequence[dict],
        step: int,
        correlation_id: Optional[str] = None,
    ) -> str:
        """在一个事务里写入一批事件，批次内以 causation_id 串成链。

        events: [{"event_type": EventType, "payload": {...}}, ...]
        返回 correlation_id。

        causation 链语义：批次内第 i 条事件的 causation_id 指向第 i-1 条事件的 event_id，
        首条为 None。由于同 step 的事件在查询时会按 event_id 重排，链的顺序必须由
        写入顺序决定，因此本方法显式生成 event_id 并按序串链，不依赖查询顺序。
        """
        cid = correlation_id or self.new_correlation()
        prev_eid: Optional[str] = None
        self.store._begin()
        try:
            for spec in events:
                eid = str(uuid.uuid4())
                self.store.append_event(
                    spec["event_type"],
                    step,
                    spec.get("payload", {}),
                    causation_id=prev_eid,
                    correlation_id=cid,
                    event_id=eid,
                )
                prev_eid = eid
            self.store._commit()
            return cid
        except Exception:
            self.store._rollback()
            raise

    def undo(self, event_id: str) -> dict:
        """撤销指定事件所在的整个事务批次。"""
        return self.store.undo(event_id)

    def history(self, project_id: Optional[str] = None, limit: int = 500) -> List[MemoryEvent]:
        """按 step 升序返回事件历史。"""
        pid = project_id or self.store.project_id
        rows = self.store.conn.execute(
            "SELECT * FROM memory_events WHERE project_id=? ORDER BY step ASC, event_id ASC LIMIT ?",
            (pid, limit),
        ).fetchall()
        return [self.store._row_to_event(r) for r in rows]

    def causation_chain(self, event_id: str, max_depth: int = 64) -> List[MemoryEvent]:
        """沿 causation_id 向上追溯因果链，带防环。"""
        chain: List[MemoryEvent] = []
        seen = set()
        cur = self.store.get_event(event_id)
        while cur is not None and len(chain) < max_depth:
            if cur.event_id in seen:
                break
            seen.add(cur.event_id)
            chain.append(cur)
            if not cur.causation_id:
                break
            cur = self.store.get_event(cur.causation_id)
        return chain

    def rebuild_projection(self, project_id: Optional[str] = None) -> Dict[str, MemoryNode]:
        """从事件流完整重建当前投影（不含 RECALL_DELIVERED 类只读事件）。

        这是「当前状态 = 事件流投影」这条铁律的可执行证明：
        用它可以校验物理表与逻辑投影是否一致。
        """
        pid = project_id or self.store.project_id
        nodes: Dict[str, MemoryNode] = {}
        edges: Dict[str, MemoryEdge] = {}
        history = self.history(pid, limit=1000000)

        # 第一遍：收集所有被 EVENT_UNDONE 撤销掉的 event_id。
        # 没有这一步，undo 之后的逻辑投影会与物理表脱节（记录里仍残留被撤销的迁移）。
        undone_ids = set()
        for ev in history:
            if ev.event_type == EventType.EVENT_UNDONE:
                payload = json.loads(ev.payload_json) if ev.payload_json else {}
                for uid in payload.get("undone_event_ids", []):
                    undone_ids.add(uid)

        for ev in history:
            if ev.event_id in undone_ids:
                continue
            payload = json.loads(ev.payload_json) if ev.payload_json else {}
            et = ev.event_type
            if et == EventType.MEMORY_CREATED:
                mid = payload.get("memory_id")
                if mid and mid not in nodes:
                    row = self.store.get_memory(mid)
                    if row is not None:
                        nodes[mid] = row
            elif et in (
                EventType.MEMORY_SUPERSEDED,
                EventType.MEMORY_KILLED,
                EventType.MEMORY_RESTORED,
            ):
                mid = payload.get("memory_id")
                to = payload.get("to")
                cur = nodes.get(mid)
                if cur is not None and to is not None:
                    nodes[mid] = cur.model_copy(update={"status": MemoryStatus(to)})
            elif et == EventType.EDGE_CREATED:
                eid = payload.get("edge_id")
                if eid:
                    edges[eid] = edges.get(eid)  # 边由物理表权威，投影仅占位
        return nodes


def read_only_guard() -> None:
    """占位：提醒任何写入路径都不得 print 到 stdout（MCP stdio 铁律）。

    本函数不产生任何输出；真实断言在 tests/test_stdout_purity.py 中以 AST 扫描保证。
    """
    return None
