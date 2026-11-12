"""代码纯净度与 stdio 安全测试（Gate 2 第 4 项红线）。"""
from __future__ import annotations

import ast
import os
import unittest


SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "gated_mem")


def _py_files():
    out = []
    for name in sorted(os.listdir(SRC_DIR)):
        if name.endswith(".py"):
            out.append(os.path.join(SRC_DIR, name))
    return out


class TestStdoutPurity(unittest.TestCase):
    def test_no_bare_print(self):
        """MCP stdio 铁律：src/ 下不得出现任何 print() 调用。"""
        offenders = []
        for path in _py_files():
            tree = ast.parse(open(path, "r", encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    if isinstance(fn, ast.Name) and fn.id == "print":
                        offenders.append((os.path.basename(path), node.lineno))
        self.assertEqual(offenders, [], "src/ 中出现 print()：%r" % offenders)

    def test_no_todo_placeholders(self):
        """零 # TODO / # FIXME / 占位符。"""
        offenders = []
        for path in _py_files():
            with open(path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    low = line.lower()
                    if "# todo" in low or "# fixme" in low or "not implemented" in low:
                        offenders.append((os.path.basename(path), i, line.strip()[:60]))
        self.assertEqual(offenders, [], "发现占位符：%r" % offenders)

    def test_no_connotation_residue(self):
        """零物理连坐残余：代码中不得出现任何连坐扣分逻辑。"""
        bad_tokens = ("connotation", "cascade_multiplier", "PSI", "psi_factor")
        offenders = []
        for path in _py_files():
            src = open(path, "r", encoding="utf-8").read()
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in bad_tokens:
                    offenders.append((os.path.basename(path), node.id))
        self.assertEqual(offenders, [], "发现连坐残余：%r" % offenders)

    def test_no_sys_stdout_writes(self):
        """不得直接写 sys.stdout。"""
        offenders = []
        for path in _py_files():
            tree = ast.parse(open(path, "r", encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr == "stdout":
                    offenders.append((os.path.basename(path), node.lineno))
        self.assertEqual(offenders, [], "发现 sys.stdout：%r" % offenders)

    def test_python39_syntax_compat(self):
        """源码必须能在 3.9 语法下解析（禁 match 语句）。"""
        for path in _py_files():
            src = open(path, "r", encoding="utf-8").read()
            tree = ast.parse(src)
            for node in ast.walk(tree):
                self.assertFalse(
                    node.__class__.__name__ == "Match",
                    "%s 使用了 match 语句（Python 3.9 不支持）" % os.path.basename(path),
                )


if __name__ == "__main__":
    unittest.main()
