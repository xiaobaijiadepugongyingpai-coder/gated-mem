"""Cursor 适配器：生成 .cursor/mcp.json。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .base import BaseAgentAdapter

SERVER_NAME = "gated-mem"


class CursorAdapter(BaseAgentAdapter):
    """Cursor 编辑器适配器。"""

    agent_name = "cursor"
    display_name = "Cursor"
    priority = 20

    def config_paths(self, project_dir: Path) -> List[Path]:
        """将写入的文件清单。"""
        return [Path(project_dir) / ".cursor" / "mcp.json"]

    def detect_installed(self) -> bool:
        """检测 Cursor：存在 ~/.cursor 目录。"""
        return (Path.home() / ".cursor").is_dir()

    def generate_config(self, project_dir: Path) -> Dict[str, Any]:
        """生成 .cursor/mcp.json 内容。"""
        spec = self.command_spec()
        return {
            "mcpServers": {
                SERVER_NAME: {
                    "command": spec["command"],
                    "args": list(spec["args"]),
                    "env": {"GATED_MEM_PROJECT_ID": self.project_id_for(project_dir)},
                }
            }
        }

    def _plan_writes(self, project_dir: Path) -> Dict[str, Any]:
        """只写 .cursor/mcp.json。"""
        return {str(Path(project_dir) / ".cursor" / "mcp.json"): self.generate_config(project_dir)}

    def get_system_prompt_snippet(self) -> str:
        """Cursor 的规则片段。"""
        return CURSOR_SNIPPET


CURSOR_SNIPPET = '''## Gated-Mem 记忆引擎

本项目挂载了 Gated-Mem MCP 服务。开始任务前用 query_memory 查当前技术状态；
做出技术决策后用 gate_remember 写入；覆盖旧决策时填 residual_diff 说明原因。

返回值中 active_memories 是当前事实，evolution_history 是历史原因，不要混淆。
带 stale=true 的条目表示其祖先已废弃，需核实是否仍适用。
'''
