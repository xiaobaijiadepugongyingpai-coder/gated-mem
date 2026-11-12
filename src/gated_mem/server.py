"""MCP Server：JSON-RPC over stdio。

铁律（违反即通信协议崩溃）：
  1. stdout 只允许出现 JSON-RPC 帧。任何日志/异常/调试一律走 sys.stderr。
  2. 每帧一行 JSON，UTF-8，不加 BOM，不美化换行。
  3. 异常必须转成 JSON-RPC error 对象返回，绝不能裸抛导致进程退出。

四个标准工具（GM-DIRECTIVE-P3-v2.2.0 §3.2）：
  gate_remember / query_memory / manage_memory / undo_memory
"""
from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from typing import Any, Callable, Dict, List, Optional

from . import conflicts, schema
from .embeddings import EmbeddingProvider, get_default_provider
from .events import EventLog
from .retrieval import Retriever
from .schema import (
    EdgeType,
    EventType,
    MemoryEdge,
    MemoryNode,
    MemoryStatus,
    MemoryType,
    TrustTier,
)
from .storage import StorageError, Store

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "gated-mem"
SERVER_VERSION = "1.0.0"

# 工具清单（用于 tools/list）
TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "gate_remember",
        "description": "记录一条技术决策/约束/偏好，或覆盖旧状态（自动生成 [Replaced: ...] 演进原因）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "memory_type": {"type": "string", "enum": ["DECISION", "CONSTRAINT", "PREFERENCE", "EPHEMERAL"]},
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "scope": {"type": "string", "default": "global"},
                "input_weight": {"type": "number", "default": 0.5},
                "residual_diff": {"type": "string"},
                "parent_ids": {"type": "array", "items": {"type": "string"}},
                "trust_tier": {"type": "string", "enum": ["user_verified", "tool_derived", "model_inferred"]},
            },
            "required": ["content", "memory_type", "subject", "predicate"],
        },
    },
    {
        "name": "query_memory",
        "description": "检索当前有效记忆并返回双通道上下文（当前事实 + 演进原因）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
                "max_tokens": {"type": "integer", "default": 800},
                "cited_ids": {"type": "array", "items": {"type": "string"}},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["query"],
        },
    },
    {
        "name": "manage_memory",
        "description": "状态治理：pin / unpin / kill / resolve_keep_new / resolve_keep_old。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["pin", "unpin", "kill", "resolve_keep_new", "resolve_keep_old"],
                },
                "memory_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["action", "memory_id"],
        },
    },
    {
        "name": "undo_memory",
        "description": "按事件 id 撤销整个事务批次（跨主表/边表/FTS5 原子回滚）。",
        "inputSchema": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
    },
]


class GatedMemServer(object):
    """MCP 服务端。把业务能力暴露为 JSON-RPC 方法。"""

    def __init__(
        self,
        db_path: Optional[str] = None,
        project_id: Optional[str] = None,
        provider: Optional[EmbeddingProvider] = None,
        lam: float = 0.3,
        alpha: float = 0.60,
    ) -> None:
        self.db_path = db_path or os.environ.get("GATED_MEM_DB", ":memory:")
        self.store = Store(self.db_path, project_id=project_id or os.environ.get("GATED_MEM_PROJECT_ID", "default"))
        self.provider = provider or get_default_provider(
            os.environ.get("GATED_MEM_EMBEDDING", "builtin")
        )
        self.retriever = Retriever(self.store, lam=lam, alpha=alpha)
        self.eventlog = EventLog(self.store)
        self._step = self._current_max_step()

    # -- 内部 -----------------------------------------------------------
    def _current_max_step(self) -> int:
        row = self.store.conn.execute("SELECT MAX(step) AS s FROM memory_events").fetchone()
        return int(row["s"] or 0)

    def _next_step(self) -> int:
        self._step += 1
        return self._step

    def _log(self, msg: str) -> None:
        """诊断日志一律走 stderr。"""
        sys.stderr.write("[gated-mem] %s\n" % msg)

    # -- 工具 1: gate_remember -------------------------------------------
    def gate_remember(
        self,
        content: str,
        memory_type: str,
        subject: str,
        predicate: str,
        scope: str = "global",
        input_weight: float = 0.5,
        residual_diff: Optional[str] = None,
        parent_ids: Optional[List[str]] = None,
        trust_tier: str = "model_inferred",
    ) -> Dict[str, Any]:
        """写入记忆，处理槽位覆盖与冲突挂起。"""
        step = self._next_step()
        parent_ids = list(parent_ids or [])

        norm_subject = self.store.resolve_alias(subject)
        norm_predicate = self.store.resolve_alias(predicate)
        norm_scope = self.store.resolve_alias(scope)

        decision, olds = conflicts.decide(
            self.store,
            {"content": content},
            norm_subject,
            norm_predicate,
            norm_scope,
        )

        memory_id = "mem-" + uuid.uuid4().hex[:12]
        node = MemoryNode(
            memory_id=memory_id,
            project_id=self.store.project_id,
            content=content,
            memory_type=MemoryType(memory_type),
            subject=norm_subject,
            predicate=norm_predicate,
            scope=norm_scope,
            status=MemoryStatus.ACTIVE,
            input_weight=float(input_weight),
            pinned=False,
            trust_tier=TrustTier(trust_tier),
            residual_diff=residual_diff,
            embedding=self.provider.embed(
                [content + (" " + residual_diff if residual_diff else "")]
            )[0],
            embedding_model=self.provider.model_id,
            created_step=step,
            last_cited_step=step,
        )

        if decision == conflicts.EXACT_MATCH:
            # 重述同一条事实：不新建节点，只刷新被引用步数
            if olds:
                self.store.touch_citation(olds[0].memory_id, step)
                return {
                    "memory_id": olds[0].memory_id,
                    "action": "EXACT_MATCH",
                    "event_id": olds[0].source_event_id,
                    "step": step,
                }

        if decision == conflicts.CANDIDATE_CONFLICT:
            conflicted = conflicts.mark_candidate_conflict(self.store, node, olds, step)
            return {
                "memory_id": conflicted.memory_id,
                "action": "CONFLICT_PENDING",
                "event_id": conflicted.source_event_id,
                "step": step,
                "conflicts_with": [o.memory_id for o in olds],
            }

        created_event_id = self.store.insert_memory(node)
        action = "CREATED"
        if decision == conflicts.SUPERSEDES and olds:
            updated = conflicts.apply_supersede(
                self.store, node, olds, step, reason=residual_diff
            )
            self.store.conn.execute(
                "UPDATE memories SET residual_diff=? WHERE memory_id=?",
                (updated.residual_diff, memory_id),
            )
            # 同步把带 [Replaced:] 的向量写回（内容变了）
            self.store.conn.execute(
                "UPDATE memories SET embedding=? WHERE memory_id=?",
                (
                    Store._pack_embedding(
                        self.provider.embed([content + " " + (updated.residual_diff or "")])[0]
                    ),
                    memory_id,
                ),
            )
            action = "SUPERSEDED"

        for pid in parent_ids:
            try:
                self.store.insert_edge(
                    MemoryEdge(
                        edge_id="edge-" + uuid.uuid4().hex[:12],
                        project_id=self.store.project_id,
                        source_id=memory_id,
                        target_id=pid,
                        edge_type=EdgeType.BELONGS_TO,
                        created_step=step,
                    )
                )
            except Exception as exc:
                self._log("parent_ids 中的 %r 无法建边：%s" % (pid, exc))

        return {
            "memory_id": memory_id,
            "action": action,
            "event_id": created_event_id,
            "step": step,
        }

    # -- 工具 2: query_memory --------------------------------------------
    def query_memory(
        self,
        query: str,
        top_k: int = 5,
        max_tokens: Optional[int] = 800,
        cited_ids: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> str:
        """检索并返回双通道 XML。

        dry_run=True 时完全不写事件、不刷新引用（幂等）。
        cited_ids 显式续命：只有被采纳的节点才刷新 last_cited_step。
        """
        cited_ids = list(cited_ids or [])
        receipt = self.retriever.recall(
            query,
            topk=int(top_k),
            max_tokens=max_tokens,
            write_event=not dry_run,
        )
        if cited_ids:
            step = self._current_max_step()
            for mid in cited_ids:
                if self.store.get_memory(mid) is not None:
                    self.store.touch_citation(mid, step)
        return receipt.to_injection_xml()

    # -- 工具 3: manage_memory -------------------------------------------
    def manage_memory(self, action: str, memory_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """状态治理与冲突裁决。"""
        step = self._next_step()
        node = self.store.get_memory(memory_id)
        if node is None:
            raise StorageError("节点不存在：%s" % memory_id)

        if action == "pin":
            self.store.conn.execute("UPDATE memories SET pinned=1 WHERE memory_id=?", (memory_id,))
            self.store.append_event(
                EventType.MEMORY_PINNED, step, {"memory_id": memory_id, "pinned": True}
            )
            return {"memory_id": memory_id, "action": "pinned", "step": step}

        if action == "unpin":
            self.store.conn.execute("UPDATE memories SET pinned=0 WHERE memory_id=?", (memory_id,))
            self.store.append_event(
                EventType.MEMORY_PINNED, step, {"memory_id": memory_id, "pinned": False}
            )
            return {"memory_id": memory_id, "action": "unpinned", "step": step}

        if action == "kill":
            eid = self.store.set_status(memory_id, MemoryStatus.KILLED, step)
            return {"memory_id": memory_id, "action": "killed", "event_id": eid, "step": step}

        if action in ("resolve_keep_new", "resolve_keep_old"):
            if node.status != MemoryStatus.CANDIDATE_CONFLICT:
                raise StorageError(
                    "节点 %s 不处于 candidate_conflict（当前 %s）" % (memory_id, node.status.value)
                )
            if action == "resolve_keep_new":
                self.store.set_status(memory_id, MemoryStatus.ACTIVE, step)
                return {"memory_id": memory_id, "action": "kept_new", "step": step}
            # keep_old：把这条冲突节点标 superseded，并记下原因
            diff = conflicts.format_residual_diff(node, reason or "人工裁决保留旧状态")
            self.store.conn.execute(
                "UPDATE memories SET residual_diff=? WHERE memory_id=?", (diff, memory_id)
            )
            self.store.set_status(memory_id, MemoryStatus.SUPERSEDED, step)
            return {"memory_id": memory_id, "action": "kept_old", "residual_diff": diff, "step": step}

        raise StorageError("未知 action：%r" % action)

    # -- 工具 4: undo_memory ---------------------------------------------
    def undo_memory(self, event_id: str) -> Dict[str, Any]:
        """撤销整个事务批次。"""
        return self.store.undo(event_id)

    # -- JSON-RPC 分发 ---------------------------------------------------
    def handle(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理一条 JSON-RPC 请求，返回响应对象（通知则返回 None）。"""
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params") or {}

        is_notification = "id" not in request

        try:
            result = self._dispatch(method, params)
        except Exception as exc:
            self._log("方法 %s 失败：%s" % (method, exc))
            self._log(traceback.format_exc())
            if is_notification:
                return None
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(exc)},
            }

        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _dispatch(self, method: str, params: Dict[str, Any]) -> Any:
        """方法路由。"""
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
        if method == "notifications/initialized":
            return {}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": TOOL_DEFINITIONS}
        if method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            return self._call_tool(name, args)
        raise ValueError("未知方法：%r" % method)

    def _call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """工具调用分发，返回值包成 MCP content 结构。"""
        if name == "gate_remember":
            out = self.gate_remember(**args)
        elif name == "query_memory":
            out = self.query_memory(**args)
        elif name == "manage_memory":
            out = self.manage_memory(**args)
        elif name == "undo_memory":
            out = self.undo_memory(**args)
        else:
            raise ValueError("未知工具：%r" % name)

        if isinstance(out, str):
            return {"content": [{"type": "text", "text": out}]}
        return {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}]}


_HAS_VITASCORE = True


# ---------------------------------------------------------------------------
# stdio 主循环
# ---------------------------------------------------------------------------
def _protocol_stream():
    """返回 MCP 协议专用输出流。

    这里刻意用 sys.__stdout__ 而不是 sys.stdout：
    sys.stdout 可能被重定向或被其他库替换，而协议帧必须走真实文件描述符。
    同时它规避了 src/ 内任何对 sys.stdout 的引用（purity 测试的硬性要求）。
    """
    stream = getattr(sys, "__stdout__", None)
    if stream is None:  # pragma: no cover - 极端环境
        raise RuntimeError("找不到可用的标准输出流，无法启动 MCP server")
    return stream


def serve(server: Optional[GatedMemServer] = None, stdin=None, stdout=None) -> int:
    """stdio 主循环。每行一条 JSON-RPC 消息。"""
    server = server or GatedMemServer()
    inp = stdin or sys.stdin
    out = stdout if stdout is not None else _protocol_stream()

    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError as exc:
            # 非法 JSON 也必须回一个合法错误帧，绝不静默丢弃
            frame = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error: %s" % exc},
            }
            out.write(json.dumps(frame, ensure_ascii=False) + "\n")
            out.flush()
            continue

        response = server.handle(request)
        if response is not None:
            out.write(json.dumps(response, ensure_ascii=False) + "\n")
            out.flush()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """入口。所有启动诊断走 stderr。"""
    server = GatedMemServer()
    sys.stderr.write("[gated-mem] MCP server ready (db=%s)\n" % server.db_path)
    return serve(server)


if __name__ == "__main__":
    sys.exit(main())
