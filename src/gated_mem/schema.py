"""Gated-Mem 领域模型定义。

阶段二生产代码。本模块只定义不可变的数据契约，不含任何 IO 与业务逻辑。

设计铁律（来自 GM-DIRECTIVE-P2-v2.1.2）：
  - 五状态机：active / candidate_conflict / superseded / archived / killed
  - 状态迁移禁止普通写入复活 superseded 与 killed，只能经由 undo 补偿事件
  - stale_parent_warning 是一等公民，必须显式出现在 RecallItem 与回执中
  - 检索回执必须物理分离 injected_items（正文）与 evolution_traces（演进轨迹）
"""
from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryType(str, Enum):
    """四类记忆及其幂律衰减参数。"""

    DECISION = "DECISION"
    CONSTRAINT = "CONSTRAINT"
    PREFERENCE = "PREFERENCE"
    EPHEMERAL = "EPHEMERAL"

    @property
    def beta(self) -> float:
        """幂律衰减指数 beta。"""
        return _TYPE_PARAMS[self.value][0]

    @property
    def t0_base(self) -> float:
        """基准时间尺度 t0_base（步）。"""
        return _TYPE_PARAMS[self.value][1]


# (beta, t0_base)，与阶段一 CONTRACT §1.1 完全一致，不得改动。
_TYPE_PARAMS: Dict[str, Tuple[float, float]] = {
    MemoryType.DECISION.value: (0.10, 100.0),
    MemoryType.CONSTRAINT.value: (0.05, 200.0),
    MemoryType.PREFERENCE.value: (0.15, 80.0),
    MemoryType.EPHEMERAL.value: (1.20, 5.0),
}


class MemoryStatus(str, Enum):
    """五状态机。"""

    ACTIVE = "active"
    CANDIDATE_CONFLICT = "candidate_conflict"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    KILLED = "killed"


class TrustTier(str, Enum):
    """来源信任分级，user_verified > tool_derived > model_inferred。"""

    USER_VERIFIED = "user_verified"
    TOOL_DERIVED = "tool_derived"
    MODEL_INFERRED = "model_inferred"


class EdgeType(str, Enum):
    """拓扑边类型。方向恒为 source=child -> target=parent。"""

    BELONGS_TO = "BELONGS_TO"
    SUPERSEDES = "SUPERSEDES"
    REFINES = "REFINES"
    CONTRADICTS = "CONTRADICTS"


class EventType(str, Enum):
    """不可变事件类型。"""

    MEMORY_CREATED = "MEMORY_CREATED"
    MEMORY_SUPERSEDED = "MEMORY_SUPERSEDED"
    MEMORY_RESTORED = "MEMORY_RESTORED"
    MEMORY_PINNED = "MEMORY_PINNED"
    MEMORY_KILLED = "MEMORY_KILLED"
    EDGE_CREATED = "EDGE_CREATED"
    EVENT_UNDONE = "EVENT_UNDONE"
    RECALL_DELIVERED = "RECALL_DELIVERED"


# ---------------------------------------------------------------------------
# 5x5 状态迁移矩阵
# ---------------------------------------------------------------------------
# ALLOWED_TRANSITIONS[from][to] == True 表示允许。
# 铁律：superseded 与 killed 不得被普通写入迁回 active，只能由 undo() 生成
# MEMORY_RESTORED 事件后经内部路径恢复（见 storage.undo）。
ALLOWED_TRANSITIONS: Dict[str, Dict[str, bool]] = {
    MemoryStatus.ACTIVE.value: {
        MemoryStatus.ACTIVE.value: True,
        MemoryStatus.CANDIDATE_CONFLICT.value: True,
        MemoryStatus.SUPERSEDED.value: True,
        MemoryStatus.ARCHIVED.value: True,
        MemoryStatus.KILLED.value: True,
    },
    MemoryStatus.CANDIDATE_CONFLICT.value: {
        MemoryStatus.ACTIVE.value: True,
        MemoryStatus.CANDIDATE_CONFLICT.value: True,
        MemoryStatus.SUPERSEDED.value: True,
        MemoryStatus.ARCHIVED.value: True,
        MemoryStatus.KILLED.value: True,
    },
    MemoryStatus.SUPERSEDED.value: {
        MemoryStatus.ACTIVE.value: False,  # 严禁普通写入复活
        MemoryStatus.CANDIDATE_CONFLICT.value: False,
        MemoryStatus.SUPERSEDED.value: True,
        MemoryStatus.ARCHIVED.value: True,
        MemoryStatus.KILLED.value: True,
    },
    MemoryStatus.ARCHIVED.value: {
        MemoryStatus.ACTIVE.value: True,  # 归档可被重新启用
        MemoryStatus.CANDIDATE_CONFLICT.value: False,
        MemoryStatus.SUPERSEDED.value: True,
        MemoryStatus.ARCHIVED.value: True,
        MemoryStatus.KILLED.value: True,
    },
    MemoryStatus.KILLED.value: {
        MemoryStatus.ACTIVE.value: False,  # 严禁普通写入复活
        MemoryStatus.CANDIDATE_CONFLICT.value: False,
        MemoryStatus.SUPERSEDED.value: False,
        MemoryStatus.ARCHIVED.value: True,
        MemoryStatus.KILLED.value: True,
    },
}


def is_transition_allowed(src: str, dst: str) -> bool:
    """查询 5x5 状态迁移矩阵。未知状态一律拒绝。"""
    return ALLOWED_TRANSITIONS.get(src, {}).get(dst, False)


# ---------------------------------------------------------------------------
# 分词与相似度（与阶段一 CONTRACT §4 逐位一致，两套实现必须同结果）
# ---------------------------------------------------------------------------
_ASCII_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> frozenset:
    """NFKC + 小写；ASCII 整词 + 中文单字 + 相邻二元组。"""
    s = unicodedata.normalize("NFKC", text).lower()
    toks = set(_ASCII_TOKEN_RE.findall(s))
    for run in _CJK_RUN_RE.findall(s):
        toks.update(run)
        if len(run) >= 2:
            for i in range(len(run) - 1):
                toks.add(run[i : i + 2])
    return frozenset(toks)


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------
class MemoryNode(BaseModel):
    """当前有效记忆投影。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str
    project_id: str = "default"
    content: str
    memory_type: MemoryType
    subject: str
    predicate: str
    scope: str = "global"
    status: MemoryStatus = MemoryStatus.ACTIVE
    input_weight: float = Field(default=0.5, ge=0.1, le=1.0)
    citation_count: int = Field(default=0, ge=0)
    pinned: bool = False
    trust_tier: TrustTier = TrustTier.MODEL_INFERRED
    residual_diff: Optional[str] = None
    embedding: Optional[List[float]] = None
    embedding_model: str = "bge-small"
    created_step: int = Field(default=0, ge=0)
    last_cited_step: int = Field(default=0, ge=0)
    source_event_id: str = ""

    @field_validator("embedding")
    @classmethod
    def _check_embedding(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        """向量必须是有限浮点；这里只校验形状，不强制维度。"""
        if v is None:
            return None
        for x in v:
            if x != x or x in (float("inf"), float("-inf")):
                raise ValueError("embedding 含 NaN 或 Inf")
        return v

    @property
    def slot(self) -> Tuple[str, str, str]:
        """槽位三元组，用于同槽覆盖判定。"""
        return (self.subject, self.predicate, self.scope)


class MemoryEdge(BaseModel):
    """拓扑边。方向恒为 source_id(子) -> target_id(父)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: str
    project_id: str = "default"
    source_id: str  # 子节点
    target_id: str  # 父节点
    edge_type: EdgeType = EdgeType.BELONGS_TO
    residual_diff: Optional[str] = None
    created_step: int = Field(default=0, ge=0)
    source_event_id: str = ""

    @field_validator("target_id")
    @classmethod
    def _no_self_loop(cls, v: str, info) -> str:
        """自环直接拒绝。真正的多跳成环由 traversal 的 visited 集合阻断。"""
        src = info.data.get("source_id")
        if src is not None and src == v:
            raise ValueError("边不允许自环：source_id 与 target_id 相同")
        return v


class MemoryEvent(BaseModel):
    """不可变事件。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    project_id: str = "default"
    step: int = Field(ge=0)
    event_type: EventType
    causation_id: Optional[str] = None
    correlation_id: str
    payload_json: str


class EvolutionTrace(BaseModel):
    """演进轨迹通道。绝不与正文混淆。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str
    subject: str
    residual_diff: str
    replaced_entity: str = ""


class RecallItem(BaseModel):
    """召回条目。stale_parent_warning 与 stale_ancestor_ids 是一等公民。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str
    content: str
    memory_type: MemoryType
    subject: str
    predicate: str
    scope: str
    trust_tier: TrustTier = TrustTier.MODEL_INFERRED
    relevance: float = 0.0
    vitality: float = 1.0
    score: float = 0.0
    stale_parent_warning: bool = False
    stale_ancestor_ids: List[str] = Field(default_factory=list)


class RecallReceipt(BaseModel):
    """检索回执。双通道物理隔离：正文与演进轨迹分属不同字段。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    recall_event_id: str
    query: str
    injected_items: List[RecallItem] = Field(default_factory=list)
    evolution_traces: List[EvolutionTrace] = Field(default_factory=list)
    excluded_stale_ids: List[str] = Field(default_factory=list)
    stale_warning_ids: List[str] = Field(default_factory=list)
    tokens_used: int = 0
    truncated_candidates: int = 0
    candidate_pool_size: int = 0

    def injected_text(self) -> str:
        """事实通道：只拼接正文，绝不含 residual_diff。"""
        return "\n".join(item.content for item in self.injected_items)

    def evolution_text(self) -> str:
        """解释通道：只拼接演进轨迹。"""
        return "\n".join(traces_line(self.evolution_traces)) if self.evolution_traces else ""

    def to_injection_xml(self) -> str:
        """渲染为注入宿主的 XML。

        事实通道进 <active_memories>，演进轨迹进 <evolution_history>，
        两者物理隔离；stale 告警以独立属性块显式透出（P0-3）。
        """
        parts: List[str] = ["<gated_mem_context>"]
        parts.append("  <active_memories>")
        for item in self.injected_items:
            attrs = ['memory_id="%s"' % item.memory_id, 'type="%s"' % item.memory_type.value]
            if item.stale_parent_warning:
                attrs.append('stale="true"')
                attrs.append('stale_ancestors="%s"' % ",".join(item.stale_ancestor_ids))
            parts.append("    <memory %s>" % " ".join(attrs))
            parts.append("      %s" % _xml_escape(item.content))
            if item.stale_parent_warning:
                parts.append(
                    "      [⚠️ STALE_ANCESTOR_WARNING: 关联上游节点 %s 已废弃，请核实本条细则是否仍适用]"
                    % ",".join(item.stale_ancestor_ids)
                )
            parts.append("    </memory>")
        parts.append("  </active_memories>")
        if self.evolution_traces:
            parts.append("  <evolution_history>")
            for tr in self.evolution_traces:
                parts.append(
                    '    <trace memory_id="%s" replaced="%s">%s</trace>'
                    % (tr.memory_id, _xml_escape(tr.replaced_entity), _xml_escape(tr.residual_diff))
                )
            parts.append("  </evolution_history>")
        parts.append("</gated_mem_context>")
        return "\n".join(parts)


def traces_line(traces: List[EvolutionTrace]) -> List[str]:
    """把演进轨迹渲染成 [Replaced: ...] 形式。"""
    out: List[str] = []
    for tr in traces:
        if tr.replaced_entity:
            out.append("[Replaced: %s] %s" % (tr.replaced_entity, tr.residual_diff))
        else:
            out.append(tr.residual_diff)
    return out


def _xml_escape(s: str) -> str:
    """XML 文本转义，防止注入破坏定界符。"""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
