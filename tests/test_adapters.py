"""多 Agent 适配层测试（含 DSH 第一公民）。"""
from __future__ import annotations

import json

import pytest

from src.gated_mem.adapters import base as adapter_base
from src.gated_mem.adapters.claude_code import ClaudeCodeAdapter
from src.gated_mem.adapters.cursor import CursorAdapter
from src.gated_mem.adapters.dsh import DshAdapter, _append_patch_block, _render_patch_block


def test_registry_has_three_adapters():
    names = {a.agent_name for a in adapter_base.all_adapters()}
    assert names == {"dsh", "claude_code", "cursor"}


def test_dsh_is_first_by_priority():
    ordered = adapter_base.all_adapters()
    assert ordered[0].agent_name == "dsh", "DSH 必须是 P0 第一适配目标"


def test_get_adapter_unknown_raises():
    with pytest.raises(adapter_base.AdapterError):
        adapter_base.get_adapter("nope")


def test_dsh_home_respects_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DSH_HOME", str(tmp_path))
    assert DshAdapter.dsh_home() == tmp_path


def test_dsh_detect_installed_false_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "nope"))
    assert DshAdapter().detect_installed() is False


def test_dsh_detect_installed_true(monkeypatch, tmp_path):
    home = tmp_path / "dsh"
    (home / "profiles" / "desktop").mkdir(parents=True)
    (home / "profiles" / "desktop" / "cordis.patch.yml").write_text("[]", encoding="utf-8")
    monkeypatch.setenv("DSH_HOME", str(home))
    ad = DshAdapter()
    assert ad.detect_installed() is True
    assert ad.active_profile() == "desktop"


def test_dsh_mcp_entry_matches_real_schema(monkeypatch, tmp_path):
    monkeypatch.setenv("DSH_HOME", str(tmp_path))
    entry = DshAdapter().mcp_entry()
    assert entry["name"] == "@deepseek-ai/dsh-mcp-client"
    cfg = entry["config"]
    assert cfg["transport"] == "stdio"
    assert cfg["serverName"] == "gated-mem"
    assert "command" in cfg and "args" in cfg
    assert cfg["reconnect"]["enabled"] is True
    assert cfg["failOnStartupError"] is False


def test_dsh_install_writes_valid_yaml(monkeypatch, tmp_path):
    home = tmp_path / "dsh"
    prof = home / "profiles" / "desktop"
    prof.mkdir(parents=True)
    (prof / "cordis.patch.yml").write_text("[]\n", encoding="utf-8")
    monkeypatch.setenv("DSH_HOME", str(home))

    ad = DshAdapter()
    written = ad.install(tmp_path / "proj")
    assert len(written) == 2

    text = (prof / "cordis.patch.yml").read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError:
        pytest.skip("需要 PyYAML 验证")
    doc = yaml.safe_load(text)
    assert isinstance(doc, list)
    item = [e for e in doc if isinstance(e, dict) and "insert" in e][0]["insert"][0]
    assert item["id"] == "mcp-gated-mem"


def test_dsh_install_is_idempotent(monkeypatch, tmp_path):
    home = tmp_path / "dsh"
    prof = home / "profiles" / "desktop"
    prof.mkdir(parents=True)
    (prof / "cordis.patch.yml").write_text("[]\n", encoding="utf-8")
    monkeypatch.setenv("DSH_HOME", str(home))
    ad = DshAdapter()
    ad.install(tmp_path / "proj")
    first = (prof / "cordis.patch.yml").read_text(encoding="utf-8")
    ad.install(tmp_path / "proj")
    second = (prof / "cordis.patch.yml").read_text(encoding="utf-8")
    assert first == second, "重复安装不得重复追加"


def test_dsh_appends_to_existing_entries(monkeypatch, tmp_path):
    home = tmp_path / "dsh"
    prof = home / "profiles" / "desktop"
    prof.mkdir(parents=True)
    (prof / "cordis.patch.yml").write_text(
        "- id: some-plugin\n  name: '@x/y'\n", encoding="utf-8"
    )
    monkeypatch.setenv("DSH_HOME", str(home))
    DshAdapter().install(tmp_path / "proj")
    text = (prof / "cordis.patch.yml").read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError:
        pytest.skip("需要 PyYAML")
    doc = yaml.safe_load(text)
    assert len(doc) == 2


def test_dsh_skill_md_has_front_matter(monkeypatch, tmp_path):
    home = tmp_path / "dsh"
    (home / "profiles" / "desktop").mkdir(parents=True)
    monkeypatch.setenv("DSH_HOME", str(home))
    ad = DshAdapter()
    ad.install(tmp_path / "proj")
    skill = (home / "skills" / "gated-mem" / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---")
    assert "name: gated-mem" in skill
    assert "gate_remember" in skill
    assert "cited_ids" in skill


def test_dsh_dry_run_writes_nothing(monkeypatch, tmp_path):
    home = tmp_path / "dsh"
    (home / "profiles" / "desktop").mkdir(parents=True)
    monkeypatch.setenv("DSH_HOME", str(home))
    ad = DshAdapter()
    paths = ad.install(tmp_path / "proj", dry_run=True)
    assert paths
    assert not (home / "skills").exists()


def test_claude_code_generates_mcp_json(tmp_path):
    ad = ClaudeCodeAdapter()
    cfg = ad.generate_config(tmp_path)
    assert "mcpServers" in cfg
    assert cfg["mcpServers"]["gated-mem"]["command"]


def test_claude_code_install_merges_existing(tmp_path):
    existing = {"mcpServers": {"other": {"command": "x"}}}
    (tmp_path / ".mcp.json").write_text(json.dumps(existing), encoding="utf-8")
    ClaudeCodeAdapter().install(tmp_path)
    cfg = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert "other" in cfg["mcpServers"], "不得覆盖用户已有配置"
    assert "gated-mem" in cfg["mcpServers"]


def test_cursor_generates_nested_config(tmp_path):
    written = CursorAdapter().install(tmp_path)
    assert (tmp_path / ".cursor" / "mcp.json").exists()


def test_project_id_is_stable_and_path_based(tmp_path):
    ad = ClaudeCodeAdapter()
    a = ad.project_id_for(tmp_path)
    b = ad.project_id_for(tmp_path)
    assert a == b
    assert a.startswith("proj-")
    assert len(a) == len("proj-") + 12


def test_all_adapters_have_prompt_snippet():
    for ad in adapter_base.all_adapters():
        assert len(ad.get_system_prompt_snippet()) > 50
