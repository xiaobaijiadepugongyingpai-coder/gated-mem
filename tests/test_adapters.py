"""多 Agent 适配层测试（含 DSH 第一公民）。"""
from __future__ import annotations

import json
from pathlib import Path

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


# -- 权限防御：探测/推断在 (PermissionError, OSError) 下平滑降级 ---------------
def test_dsh_detect_installed_false_on_home_oserror(monkeypatch, tmp_path):
    """访问 Path.home()/.dsh 本身被拒（OSError）时，探测降级为 False。"""
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "dsh"))

    def deny(self):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "is_dir", deny)
    assert DshAdapter().detect_installed() is False


def test_dsh_detect_installed_false_on_iterdir_permission_error(monkeypatch, tmp_path):
    """主目录存在但遍历目录被拒（PermissionError）时，探测降级为 False。"""
    home = tmp_path / "dsh"
    home.mkdir()
    monkeypatch.setenv("DSH_HOME", str(home))

    def deny(self):
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "iterdir", deny)
    assert DshAdapter().detect_installed() is False


def test_dsh_active_profile_desktop_on_profiles_oserror(monkeypatch, tmp_path):
    """profiles 目录不可读（PermissionError）时，推断回退 'desktop'。"""
    home = tmp_path / "dsh"
    home.mkdir()
    monkeypatch.setenv("DSH_HOME", str(home))

    def deny(self):
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "is_dir", deny)
    assert DshAdapter().active_profile() == "desktop"


def test_dsh_active_profile_desktop_on_profiles_iterdir_permission_error(
    monkeypatch, tmp_path
):
    """遍历 profiles 被拒（PermissionError）时，推断回退 'desktop'。"""
    home = tmp_path / "dsh"
    (home / "profiles").mkdir(parents=True)
    monkeypatch.setenv("DSH_HOME", str(home))

    def deny(self):
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "iterdir", deny)
    assert DshAdapter().active_profile() == "desktop"


def test_dsh_active_profile_desktop_on_stat_oserror(monkeypatch, tmp_path):
    """读取 profile 的 cordis.patch.yml 元数据（mtime）被拒（OSError）时回退 'desktop'。"""
    home = tmp_path / "dsh"
    (home / "profiles" / "work").mkdir(parents=True)
    (home / "profiles" / "work" / "cordis.patch.yml").write_text("[]", encoding="utf-8")
    monkeypatch.setenv("DSH_HOME", str(home))

    real_stat = Path.stat

    def deny(self):
        if self.name == "cordis.patch.yml":
            raise OSError("stat denied")
        return real_stat(self)

    # exists() 内部会用 stat()，先放行存在性检查，让异常精确落在排序的 stat 上
    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(Path, "stat", deny)
    assert DshAdapter().active_profile() == "desktop"


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

# -- 基类权限防御（GM-VERDICT-P5-FINAL-v1.0.1 §3.1）-------------------------
# 异构黑盒审计发现：只给子类 dsh.py 打补丁会漏掉父类的探测路径，
# 受限沙箱下 is_installed_at() / uninstall() / _write_json() 会抛 PermissionError。
def test_safe_path_exists_swallows_permission_error(monkeypatch):
    """_safe_path_exists 对被拒路径返回 False，绝不向上抛异常。"""
    def deny(self):
        raise PermissionError("denied by ACL")

    monkeypatch.setattr(Path, "exists", deny)
    assert adapter_base._safe_path_exists(Path("whatever")) is False


def test_safe_path_exists_swallows_oserror(monkeypatch):
    """OSError 同样必须被吞掉。"""
    def deny(self):
        raise OSError("boom")

    monkeypatch.setattr(Path, "exists", deny)
    assert adapter_base._safe_path_exists(Path("whatever")) is False


def test_is_installed_at_survives_permission_error(monkeypatch):
    """受限目录下 is_installed_at 降级为 False，不崩溃。"""
    def deny(self):
        raise PermissionError("denied by ACL")

    monkeypatch.setattr(Path, "exists", deny)
    assert ClaudeCodeAdapter().is_installed_at(Path(".")) is False


def test_uninstall_survives_permission_error(monkeypatch):
    """受限目录下 uninstall 仍返回路径清单，不崩溃、不误删。"""
    def deny(self):
        raise PermissionError("denied by ACL")

    monkeypatch.setattr(Path, "exists", deny)
    removed = ClaudeCodeAdapter().uninstall(Path("."))
    assert isinstance(removed, list) and removed


def test_write_json_survives_permission_error_on_probe(monkeypatch, tmp_path):
    """_write_json 探测已有文件被拒时，退化为直接写入而不是崩溃。"""
    calls = {"n": 0}
    real_exists = Path.exists

    def flaky(self):
        # 第一次探测（合并已有配置）被拒，之后恢复正常
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("denied by ACL")
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", flaky)
    target = tmp_path / "cfg.json"
    ClaudeCodeAdapter()._write_json(target, {"mcpServers": {"gated-mem": {}}})
    assert target.exists()
    assert "gated-mem" in json.loads(target.read_text(encoding="utf-8"))["mcpServers"]


def test_safe_home_swallows_runtime_error(monkeypatch):
    """无 HOME/USERPROFILE 时 Path.home() 抛 RuntimeError，_safe_home() 返回 None。"""
    def no_home():
        raise RuntimeError("Can't determine home directory")

    monkeypatch.setattr(Path, "home", staticmethod(no_home))
    assert adapter_base._safe_home() is None


def test_dsh_detect_and_active_profile_survive_home_runtime_error(monkeypatch, capsys):
    """DSH_HOME 未设置且 Path.home() 抛 RuntimeError 时，探测与推断不二次抛错。"""
    monkeypatch.delenv("DSH_HOME", raising=False)

    def no_home():
        raise RuntimeError("Can't determine home directory")

    monkeypatch.setattr(Path, "home", staticmethod(no_home))
    ad = DshAdapter()
    assert ad.detect_installed() is False
    assert ad.active_profile() == "desktop"
    err = capsys.readouterr().err
    assert "~/.dsh/profiles" in err


def test_claude_and_cursor_detect_installed_survive_permission_and_runtime_error(monkeypatch):
    """ClaudeCodeAdapter 与 CursorAdapter 在 Path.home()/目录访问抛异常时降级为 False。"""
    def no_home():
        raise RuntimeError("Can't determine home directory")

    monkeypatch.setattr(Path, "home", staticmethod(no_home))
    assert ClaudeCodeAdapter().detect_installed() is False
    assert CursorAdapter().detect_installed() is False

    monkeypatch.undo()

    def deny_dir(self):
        raise PermissionError("denied by ACL")

    monkeypatch.setattr(Path, "is_dir", deny_dir)
    assert ClaudeCodeAdapter().detect_installed() is False
    assert CursorAdapter().detect_installed() is False


def test_detect_available_survives_adapter_exceptions(monkeypatch):
    """某个适配器 detect_installed 抛异常时，detect_available() 跳过它并继续探测其余适配器。"""
    def boom(self):
        raise RuntimeError("probe failed")

    monkeypatch.setattr(DshAdapter, "detect_installed", boom)
    monkeypatch.setattr(ClaudeCodeAdapter, "detect_installed", lambda self: True)
    monkeypatch.setattr(CursorAdapter, "detect_installed", lambda self: False)

    avail = adapter_base.detect_available()
    assert [a.agent_name for a in avail] == ["claude_code"]
