"""阶段四新增能力的回归测试（uninstall / doctor / version / 打包分层）。"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.gated_mem import __version__, cli
from src.gated_mem.adapters import base as adapter_base
from src.gated_mem.adapters.dsh import DshAdapter, _strip_patch_block


# ---------------------------------------------------------------------------
# 版本与打包
# ---------------------------------------------------------------------------
def test_version_is_1_0_0():
    assert __version__ == "1.0.0"


def test_pyproject_core_has_zero_dependencies():
    """生死级打包规范：核心依赖必须为空，否则会毁掉用户的 numpy/torch 环境。"""
    root = Path(__file__).resolve().parent.parent
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r"^dependencies\s*=\s*(\[.*?\])", text, re.M | re.S)
    assert m is not None, "pyproject.toml 缺少 dependencies 字段"
    assert m.group(1).strip() in ("[]", "[ ]"), "核心 dependencies 必须为空，实际为 %r" % m.group(1)


def test_pyproject_extras_contain_fastembed():
    root = Path(__file__).resolve().parent.parent
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project.optional-dependencies]" in text
    assert "fastembed" in text
    assert "[project.scripts]" in text
    assert 'gated-mem = "gated_mem.cli:main"' in text


# ---------------------------------------------------------------------------
# DSH 卸载：来去无痕
# ---------------------------------------------------------------------------
def _dsh_env(monkeypatch, tmp_path, initial="[]\n"):
    home = tmp_path / "dsh"
    prof = home / "profiles" / "desktop"
    prof.mkdir(parents=True)
    patch = prof / "cordis.patch.yml"
    with open(str(patch), "wb") as f:
        f.write(initial.encode("utf-8"))
    monkeypatch.setenv("DSH_HOME", str(home))
    return home, patch


def test_dsh_install_then_uninstall_is_byte_identical(monkeypatch, tmp_path):
    """装完再卸，patch.yml 必须逐字节还原。"""
    home, patch = _dsh_env(monkeypatch, tmp_path)
    original = patch.read_bytes()

    ad = DshAdapter()
    ad.install(tmp_path / "proj")
    assert patch.read_bytes() != original

    ad.uninstall(tmp_path / "proj")
    assert patch.read_bytes() == original, "卸载后未逐字节还原"


def test_dsh_uninstall_preserves_user_entries(monkeypatch, tmp_path):
    """卸载只能摘掉我们那段，绝不能删用户的插件配置。"""
    user_cfg = "- id: user-plugin\n  name: '@x/y'\n"
    home, patch = _dsh_env(monkeypatch, tmp_path, initial=user_cfg)

    ad = DshAdapter()
    ad.install(tmp_path / "proj")
    ad.uninstall(tmp_path / "proj")

    text = patch.read_text(encoding="utf-8")
    assert "user-plugin" in text, "用户的插件配置被误删"
    assert "mcp-gated-mem" not in text, "我们的配置块未被清除"

    try:
        import yaml
    except ImportError:
        return
    assert yaml.safe_load(text) == [{"id": "user-plugin", "name": "@x/y"}]


def test_dsh_uninstall_removes_skill_and_empty_dir(monkeypatch, tmp_path):
    home, patch = _dsh_env(monkeypatch, tmp_path)
    ad = DshAdapter()
    ad.install(tmp_path / "proj")
    skill = home / "skills" / "gated-mem" / "SKILL.md"
    assert skill.exists()
    ad.uninstall(tmp_path / "proj")
    assert not skill.exists()
    assert not (home / "skills" / "gated-mem").exists(), "空目录未清理"


def test_dsh_uninstall_when_not_installed_is_noop(monkeypatch, tmp_path):
    home, patch = _dsh_env(monkeypatch, tmp_path)
    before = patch.read_bytes()
    removed = DshAdapter().uninstall(tmp_path / "proj")
    assert removed
    assert patch.read_bytes() == before


def test_strip_patch_block_handles_no_marker():
    text = "- id: a\n"
    assert _strip_patch_block(text, {}) == text


def test_strip_patch_block_marker_in_middle():
    text = (
        "- id: before\n"
        "  name: '@a/b'\n"
        "# --- Gated-Mem MCP（由 gated-mem setup 自动写入）---\n"
        "- insert:\n"
        "    - id: mcp-gated-mem\n"
        "      name: '@deepseek-ai/dsh-mcp-client'\n"
        "- id: after\n"
        "  name: '@c/d'\n"
    )
    out = _strip_patch_block(text, {})
    assert "before" in out and "after" in out
    assert "mcp-gated-mem" not in out
    assert "Gated-Mem MCP" not in out


# ---------------------------------------------------------------------------
# base.uninstall 默认实现
# ---------------------------------------------------------------------------
def test_base_uninstall_deletes_config_files(tmp_path):
    from src.gated_mem.adapters.claude_code import ClaudeCodeAdapter

    ad = ClaudeCodeAdapter()
    ad.install(tmp_path)
    assert (tmp_path / ".mcp.json").exists()
    removed = ad.uninstall(tmp_path)
    assert removed
    assert not (tmp_path / ".mcp.json").exists()


def test_base_uninstall_dry_run_keeps_files(tmp_path):
    from src.gated_mem.adapters.claude_code import ClaudeCodeAdapter

    ad = ClaudeCodeAdapter()
    ad.install(tmp_path)
    ad.uninstall(tmp_path, dry_run=True)
    assert (tmp_path / ".mcp.json").exists()


# ---------------------------------------------------------------------------
# CLI: setup --uninstall / doctor / --version
# ---------------------------------------------------------------------------
def test_cli_setup_uninstall_via_subprocess_flow(tmp_path, monkeypatch, capsys):
    home, patch = _dsh_env(monkeypatch, tmp_path)
    monkeypatch.setenv("GATED_MEM_DB", str(tmp_path / "m.db"))
    project = str(tmp_path / "proj")
    Path(project).mkdir(exist_ok=True)

    assert cli.main(["setup", "--agent", "dsh", "--project", project]) == 0
    capsys.readouterr()
    assert "mcp-gated-mem" in patch.read_text(encoding="utf-8")

    assert cli.main(["setup", "--agent", "dsh", "--project", project, "--uninstall"]) == 0
    out = capsys.readouterr().out
    assert "卸载完成" in out
    assert "mcp-gated-mem" not in patch.read_text(encoding="utf-8")


def test_cli_setup_uninstall_dry_run(tmp_path, monkeypatch, capsys):
    home, patch = _dsh_env(monkeypatch, tmp_path)
    monkeypatch.setenv("GATED_MEM_DB", str(tmp_path / "m.db"))
    project = str(tmp_path / "proj")
    Path(project).mkdir(exist_ok=True)
    cli.main(["setup", "--agent", "dsh", "--project", project])
    before = patch.read_bytes()
    capsys.readouterr()

    assert cli.main(["setup", "--agent", "dsh", "--project", project,
                     "--uninstall", "--dry-run"]) == 0
    assert patch.read_bytes() == before


def test_cli_doctor_reports_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GATED_MEM_DB", str(tmp_path / "m.db"))
    rc = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Python" in out
    assert "SQLite" in out
    assert "Embedder" in out
    assert "已配置的 Agent" in out


def test_cli_doctor_lists_adapters(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GATED_MEM_DB", str(tmp_path / "m.db"))
    cli.main(["doctor"])
    out = capsys.readouterr().out
    for name in ("dsh", "claude_code", "cursor"):
        assert name in out
