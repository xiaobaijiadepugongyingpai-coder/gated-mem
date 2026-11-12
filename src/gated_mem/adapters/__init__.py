"""宿主 Agent 适配层。

导入本包即自动注册全部适配器（按 priority 排序，DSH 为 P0 第一公民）。
"""
from .base import (
    AdapterError,
    BaseAgentAdapter,
    all_adapters,
    detect_available,
    get_adapter,
    register,
)
from .claude_code import ClaudeCodeAdapter
from .cursor import CursorAdapter
from .dsh import DshAdapter

# 注册顺序无关紧要，all_adapters() 按 priority 排序，DSH 恒在最前。
register(DshAdapter)
register(ClaudeCodeAdapter)
register(CursorAdapter)

__all__ = [
    "AdapterError",
    "BaseAgentAdapter",
    "all_adapters",
    "detect_available",
    "get_adapter",
    "register",
]
