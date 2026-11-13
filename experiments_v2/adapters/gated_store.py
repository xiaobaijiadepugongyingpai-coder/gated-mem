"""Gated-Mem 存储适配层。

**只调用 src/gated_mem 的既有公开接口，不修改它。**
所有实验臂共用这一层，通过 Arm 的开关决定行为差异。

已核实的关键 API（2026-11-12，对照 src/gated_mem/）：
  Store(path=":memory:", project_id="default")
    .insert_memory(node) -> str            # node.memory_id 必填
    .insert_edge(edge)   -> str            # edge.edge_id 必填
    .all_memories(...)   -> List[MemoryNode]
    .touch_citation(memory_id, step)
    .close()
  Retriever(store, lam=..., topk=..., provider=..., use_hybrid=...)
    .recall(query, case_step, topk, max_tokens,
            write_event=True, use_fts=True, use_vitality=True,
            auto_touch_on_recall=False) -> RecallReceipt
  RecallReceipt.injected_text() -> str

设计要点（来自 phase2_handoff.md §2.6 的明确提醒）：
  recall(write_event=True) 会自动 touch_citation 刷新所有命中节点，
  这会让"只要被捞出、哪怕没被使用，半衰期也无限续命"。
  **做 A/B 对比实验时必须 write_event=False**，否则噪音被续命、实验失效。
  本适配层默认绝不自动续命；只有显式传 cited_ids 时才刷新。
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from gated_mem import storage  # noqa: E402
from gated_mem.retrieval import Retriever  # noqa: E402
from gated_mem.schema import MemoryEdge, MemoryNode, MemoryType  # noqa: E402


def _new_id(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid.uuid4().hex[:16])


class GatedStore:
    """一个实验臂对应一个独立的临时库。"""

    def __init__(self, arm, project_id: str = "exp", db_path: str | None = None,
                 provider=None):
        self.arm = arm
        self.project_id = project_id
        if db_path is None:
            fd, db_path = tempfile.mkstemp(prefix="gm_exp_", suffix=".db")
            os.close(fd)
            self._tmp = True
        else:
            self._tmp = False
        self.db_path = db_path

        # 向量通道只有在 provider 非 None 时才会被计算
        # （见 src/gated_mem/retrieval.py:150 `if q_vec is not None and node.embedding`）
        # 所以任何"向量相关"的臂都必须注入 provider。
        self.provider = provider
        if provider is not None and not arm.fusion:
            # 单向量臂：要能算 s_vec，但不要 fts 融合 ⇒ 用 alpha=1.0 让融合退化为纯向量
            pass

        self.store = storage.Store(db_path, project_id)
        self.retriever = Retriever(
            self.store,
            lam=arm.lam if arm.lam > 0 else 0.0,
            topk=5,
            provider=provider,
            use_hybrid=bool(arm.fusion) or provider is not None,
            alpha=(1.0 if (provider is not None and not arm.fusion) else 0.6),
        )
        self._step = 0
        self._ids: list[str] = []

    # -- 写入 --------------------------------------------------------------
    def remember(self, content: str, subject: str, predicate: str,
                 scope: str = "global",
                 memory_type: str = "DECISION",
                 input_weight: float = 0.5,
                 parent_ids=None,
                 residual_diff: str | None = None) -> str:
        """写入一条记忆。

        arm.use_slots=False 时，强制让每条记忆走独立槽位，
        从而**永远不触发 SUPERSEDES** —— 这正是"纯向量基线"的语义，
        而不是靠另写一套检索。

        注意：槽位去重靠 subject+predicate+scope 三元组。
        给 subject 加序号后缀是安全的（不影响 FTS，因为 FTS 索引的是 content），
        但**绝不能**污染 content —— content 是检索信号源。
        """
        self._step += 1
        subj, pred = subject, predicate
        if not self.arm.use_slots:
            subj = "%s::%d" % (subject, self._step)
            pred = "%s::%d" % (predicate, self._step)

        try:
            mt = MemoryType[memory_type] if isinstance(memory_type, str) else memory_type
        except KeyError:
            mt = MemoryType.DECISION

        node = MemoryNode(
            memory_id=_new_id("m"),
            project_id=self.project_id,
            content=content,
            memory_type=mt,
            subject=subj,
            predicate=pred,
            scope=scope,
            input_weight=input_weight,
            residual_diff=residual_diff,
            created_step=self._step,
            last_cited_step=self._step,
        )
        # 向量必须写进 embedding 字段，否则 s_vec 恒为 0
        if self.provider is not None:
            try:
                node = node.model_copy(update={
                    "embedding": self.provider.embed_one(content),
                    "embedding_model": getattr(self.provider, "model_id",
                                               "builtin-hash"),
                })
            except Exception:
                pass
        # ★ 重要：insert_memory() 返回的是 **event_id**，不是 memory_id。
        #   已核实 src/gated_mem/storage.py insert_memory 末尾 `return eid`。
        #   节点真正的 memory_id 是调用方构造时传入的 node.memory_id。
        #   若误把返回值当 memory_id，去和 RecallItem.memory_id 比对会永远不相等，
        #   导致命中率恒为 0（本次调试踩过这个坑）。
        self.store.insert_memory(node)
        mid = node.memory_id
        self._ids.append(mid)

        for pid in (parent_ids or []):
            self.store.insert_edge(MemoryEdge(
                edge_id=_new_id("e"),
                project_id=self.project_id,
                source_id=mid,
                target_id=pid,
                edge_type="BELONGS_TO",
                created_step=self._step,
            ))
        return mid

    def remember_turn(self, text: str, idx: int, role: str = "user") -> str:
        """把一轮对话写进库（MAB ingest 用）。

        每轮独立槽位，标记为 EPHEMERAL —— 本实验不做跨轮覆盖，
        覆盖逻辑只由 MAB 的冲突事实本身触发。
        """
        return self.remember(
            content=("" if not text else str(text)),
            subject="conv:%d" % idx,
            predicate="turn:%s" % role,
            scope="conv:%d" % idx,
            memory_type="EPHEMERAL",
            input_weight=0.3,
        )

    # -- 检索 --------------------------------------------------------------
    def recall(self, query: str, topk: int = 5, max_tokens: int | None = 800,
               cited_ids=None):
        """检索。

        关键：write_event=False —— 见模块 docstring。
        只有显式传 cited_ids 时才续命。
        """
        receipt = self.retriever.recall(
            query,
            topk=topk,
            max_tokens=max_tokens,
            write_event=False,
            use_fts=self.arm.fusion,
            use_vitality=(self.arm.lam > 0.0),
            auto_touch_on_recall=False,
        )
        if cited_ids:
            for mid in cited_ids:
                try:
                    self.store.touch_citation(mid, self._step)
                except Exception:
                    pass
        return receipt

    @staticmethod
    def receipt_text(receipt) -> str:
        """取出用于注入的正文块（双通道隔离：不含演进块）。"""
        try:
            return receipt.injected_text()
        except Exception:
            return ""

    def size(self) -> int:
        return len(self._ids)

    # -- 清理 --------------------------------------------------------------
    def close(self) -> None:
        try:
            self.store.close()
        except Exception:
            pass
        if self._tmp and os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except OSError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
