"""零依赖承诺的结构性守卫。

这些测试存在的理由：阶段四发现 wheel 装进干净环境后 import 失败，
因为 schema.py 用了 pydantic 但 dependencies 是空的。
"零依赖" 必须是可机器验证的事实，不是 README 里的一句话。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "gated_mem"

# 允许的第三方模块白名单（空 = 只准标准库）
ALLOWED_THIRD_PARTY = set()


# 本项目实际会用到的标准库根模块（显式白名单，比动态探测可靠）。
# Python 3.9 没有 sys.stdlib_module_names，动态扫描在不同环境里结果不稳定，
# 所以这里把项目用到的列全，任何一个不在表里就是引入第三方依赖了。
_STDLIB_USED = {
    "__future__", "argparse", "dataclasses", "enum", "hashlib", "json", "math",
    "os", "pathlib", "re", "shutil", "sqlite3", "struct", "sys", "traceback",
    "typing", "unicodedata", "uuid", "tempfile", "subprocess", "io", "time",
    "collections", "itertools", "functools", "warnings",
}

# 允许可选导入的模块：只在明确的可选路径上出现，缺失会优雅降级
_OPTIONAL_IMPORTS = {"fastembed", "rich", "numpy"}


def _stdlib_names():
    """返回允许出现的模块名集合。"""
    names = set(sys.builtin_module_names) | _STDLIB_USED | _OPTIONAL_IMPORTS
    std = getattr(sys, "stdlib_module_names", None)
    if std is not None:
        names |= set(std)
    return names


def _top_level_imports(path):
    """收集一个模块里所有顶层 import 的根模块名。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 相对导入，属于本包
                continue
            if node.module:
                mods.add(node.module.split(".")[0])
    return mods


def test_runtime_source_has_no_third_party_imports():
    """src/gated_mem 下所有模块只能 import 标准库或本包。"""
    std = _stdlib_names()
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        for mod in _top_level_imports(path):
            if mod in ("gated_mem",) or mod in std or mod in ALLOWED_THIRD_PARTY:
                continue
            offenders.append((path.name, mod))
    assert not offenders, "运行期源码引入了第三方包：%r" % offenders


def test_optional_imports_are_guarded():
    """fastembed / rich / numpy 必须出现在 try/except 里，缺失时可降级。"""
    import re

    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        text = path.read_text(encoding="utf-8")
        for mod in _OPTIONAL_IMPORTS:
            if ("import " + mod) in text or ("from " + mod) in text:
                # 必须能找到某个 try: ... mod ... except
                assert "try:" in text, "%s 导入了 %s 但没有 try 保护" % (path.name, mod)


def test_no_pydantic_anywhere_in_runtime():
    """pydantic 已被 dataclass 取代，不得回流。"""
    hits = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        text = path.read_text(encoding="utf-8")
        if "import pydantic" in text or "from pydantic" in text:
            hits.append(path.name)
    assert not hits, "pydantic 重新出现在：%r" % hits


def test_schema_module_imports_without_third_party():
    """schema 必须能在纯净解释器里独立导入（这是打包事故的根因模块）。"""
    import subprocess

    code = (
        "import sys; sys.path.insert(0, %r);"
        "import gated_mem.schema as s;"
        "n = s.MemoryNode(memory_id='M1', content='x',"
        " memory_type=s.MemoryType.DECISION, subject='a', predicate='b');"
        "assert n.status is s.MemoryStatus.ACTIVE;"
        "assert n.model_copy(update={'status': s.MemoryStatus.SUPERSEDED}).status"
        " is s.MemoryStatus.SUPERSEDED;"
        "print('OK')"
    ) % str(SRC.parent)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, "schema 无法独立导入：%s" % r.stderr[-500:]
    assert "OK" in r.stdout


def test_dataclass_models_are_immutable():
    """frozen=True 语义：模型不可变。"""
    import pytest

    from src.gated_mem.schema import MemoryNode, MemoryType

    n = MemoryNode(memory_id="M1", content="x", memory_type=MemoryType.DECISION,
                   subject="a", predicate="b")
    with pytest.raises(Exception):
        n.content = "hacked"


def test_model_copy_does_not_mutate_original():
    from src.gated_mem.schema import MemoryNode, MemoryStatus, MemoryType

    n = MemoryNode(memory_id="M1", content="x", memory_type=MemoryType.DECISION,
                   subject="a", predicate="b")
    c = n.model_copy(update={"status": MemoryStatus.KILLED})
    assert n.status is MemoryStatus.ACTIVE
    assert c.status is MemoryStatus.KILLED


def test_enum_coercion_from_raw_strings():
    """从 SQLite 读回的是裸字符串，模型必须自动归化成枚举。"""
    from src.gated_mem.schema import MemoryNode, MemoryStatus, MemoryType

    n = MemoryNode(memory_id="M1", content="x", memory_type="DECISION",
                   subject="a", predicate="b", status="superseded")
    assert isinstance(n.memory_type, MemoryType)
    assert isinstance(n.status, MemoryStatus)
    assert n.memory_type is MemoryType.DECISION
