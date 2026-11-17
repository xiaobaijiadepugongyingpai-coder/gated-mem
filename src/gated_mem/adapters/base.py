"""多 Agent 适配层抽象基类。

设计目标：让 Gated-Mem 能被任意宿主 Agent 一键挂载，而不是硬绑某一个。

每个适配器只需回答四个问题：
  1. 这台机器上装没装这个 Agent？        -> detect_installed()
  2. 它的 MCP 配置长什么样？             -> generate_config()
  3. 它的 Agent 该怎么用这些记忆？        -> get_system_prompt_snippet()
  4. 怎么把它写进磁盘？                   -> install()

铁律：本模块与所有子类都不得向 sys.stdout 写任何内容。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


class AdapterError(RuntimeError):
    """适配器安装/配置错误。"""


def _safe_path_exists(p: Path) -> bool:
    """在受限沙箱或无权限目录中安全探测路径是否存在，绝不向上抛出 OS 权限异常。

    背景（GM-VERDICT-P5-FINAL-v1.0.1）：阶段五只给子类 dsh.py 打了权限补丁，
    漏掉了父类这里直接调用 path.exists() 的几处，导致 Windows 受限目录下
    doctor / uninstall 会抛 PermissionError。探测类操作必须永远可降级：
    无法确认存在时一律当作"不存在"，而不是把异常抛给调用方。
    """
    try:
        return p.exists()
    except (PermissionError, OSError):
        return False


def _safe_home() -> Optional[Path]:
    """在受限沙箱或无 HOME 环境变量的容器中安全获取主目录，绝不抛出 RuntimeError/OSError。"""
    try:
        return Path.home()
    except (RuntimeError, PermissionError, OSError):
        return None


class BaseAgentAdapter(object):
    """宿主 Agent 适配器基类。"""

    #: 稳定的机器可读名称，用于 CLI 的 --agent 参数
    agent_name: str = "base"
    #: 人类可读名称
    display_name: str = "Base Agent"
    #: 该 Agent 的模块级优先级（数字越小越优先）。DSH 为 P0 第一公民，取 0。
    priority: int = 100

    # -- 必须由子类实现 -------------------------------------------------
    def detect_installed(self) -> bool:
        """检测宿主环境是否存在当前 Agent 的配置。"""
        raise NotImplementedError

    def config_paths(self, project_dir: Path) -> List[Path]:
        """返回将要写入的配置文件路径列表（用于预演与幂等检查）。"""
        raise NotImplementedError

    def generate_config(self, project_dir: Path) -> Dict[str, Any]:
        """生成该 Agent 的 MCP 挂载配置（不落盘）。"""
        raise NotImplementedError

    def get_system_prompt_snippet(self) -> str:
        """返回针对该 Agent 调优的记忆使用指南。"""
        raise NotImplementedError

    # -- 通用实现 -------------------------------------------------------
    def install(self, project_dir: Path, dry_run: bool = False) -> List[str]:
        """一键写入配置。返回写入的文件路径列表。

        dry_run=True 时只返回将要写入的路径，不触碰磁盘。
        """
        written: List[str] = []
        for rel_path, payload in self._plan_writes(project_dir).items():
            target = Path(rel_path)
            written.append(str(target))
            if dry_run:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(payload, str):
                self._write_text(target, payload)
            else:
                self._write_json(target, payload)
        return written

    def _plan_writes(self, project_dir: Path) -> Dict[str, Any]:
        """返回 {绝对路径: payload}。payload 为 str 写文本，dict/list 写 JSON。"""
        raise NotImplementedError

    # -- 工具方法 -------------------------------------------------------
    def command_spec(self) -> Dict[str, Any]:
        """Gated-Mem MCP 服务的启动命令规格。

        统一用 python -m 调用，避免依赖 PATH 上的可执行脚本。
        """
        return {
            "command": sys.executable,
            "args": ["-m", "gated_mem.server"],
        }

    def project_id_for(self, project_dir: Path) -> str:
        """以项目绝对路径的短哈希作为 project_id（跨机器可复现、无冲突）。"""
        import hashlib

        norm = os.path.abspath(str(project_dir)).replace("\\", "/").lower()
        return "proj-" + hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]

    def _write_text(self, path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")

    def _write_json(self, path: Path, obj: Any) -> None:
        """JSON 写入，保留已有文件的其他键（幂等合并）。"""
        merged = obj
        if _safe_path_exists(path):
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(existing, dict) and isinstance(obj, dict):
                    merged = _deep_merge(existing, obj)
            except (ValueError, OSError):
                merged = obj
        path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def is_installed_at(self, project_dir: Path) -> bool:
        """Gated-Mem 是否已在该项目里挂载过。"""
        return any(_safe_path_exists(p) for p in self.config_paths(project_dir))

    # -- 卸载（P4 §3.3：来去无痕）---------------------------------------
    def uninstall(self, project_dir: Path, dry_run: bool = False) -> List[str]:
        """撤销 install() 的写入，返回被清理的路径列表。

        默认实现：直接删除 config_paths() 列出的文件。
        需要「保留文件、只摘掉自己那块」的适配器（如 DSH 的 patch.yml）
        必须覆写本方法。
        """
        removed: List[str] = []
        for path in self.config_paths(project_dir):
            removed.append(str(path))
            if dry_run or not _safe_path_exists(path):
                continue
            try:
                path.unlink()
            except OSError as exc:  # pragma: no cover - 权限异常
                raise AdapterError("无法删除 %s: %s" % (path, exc))
        return removed


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """深合并，overlay 覆盖 base，dict 递归，其余整体替换。"""
    out = dict(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# 适配器注册表
# ---------------------------------------------------------------------------
_REGISTRY: Dict[str, BaseAgentAdapter] = {}


def register(adapter_cls) -> None:
    """注册一个适配器类（实例化后按 agent_name 索引）。"""
    inst = adapter_cls()
    _REGISTRY[inst.agent_name] = inst


def get_adapter(name: str) -> BaseAgentAdapter:
    """按名称取适配器。"""
    if name not in _REGISTRY:
        raise AdapterError(
            "未知的 agent：%r。可用：%s"
            % (name, ", ".join(sorted(_REGISTRY.keys())) or "(尚未注册)")
        )
    return _REGISTRY[name]


def all_adapters() -> List[BaseAgentAdapter]:
    """返回全部已注册适配器，按 priority 升序（DSH 在最前）。"""
    return sorted(_REGISTRY.values(), key=lambda a: (a.priority, a.agent_name))


def detect_available() -> List[BaseAgentAdapter]:
    """探测本机已安装的 Agent，按 priority 排序。"""
    out: List[BaseAgentAdapter] = []
    for a in all_adapters():
        try:
            if a.detect_installed():
                out.append(a)
        except (PermissionError, OSError, RuntimeError):
            continue
    return out


def reset_registry() -> None:
    """清空注册表（仅测试使用）。"""
    _REGISTRY.clear()
