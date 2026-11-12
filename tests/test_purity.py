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
    # MCP stdio 协议路径：这些模块一旦 print 就会污染 JSON-RPC 管道
    MCP_PATH_MODULES = ("server.py", "storage.py", "retrieval.py", "gates.py",
                        "schema.py", "events.py", "conflicts.py", "embeddings.py")

    def test_no_bare_print_in_mcp_path(self):
        """MCP stdio 铁律：协议路径上的模块不得出现任何 print()。

        cli.py 与 exporter.py 是终端/文件输出工具，不参与 stdio 协议，允许 print。
        """
        offenders = []
        for path in _py_files():
            name = os.path.basename(path)
            if name not in self.MCP_PATH_MODULES:
                continue
            tree = ast.parse(open(path, "r", encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    if isinstance(fn, ast.Name) and fn.id == "print":
                        offenders.append((name, node.lineno))
        self.assertEqual(offenders, [], "MCP 路径出现 print()：%r" % offenders)

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

    def test_no_sys_stdout_writes_in_mcp_path(self):
        """MCP 协议路径不得直接写 sys.stdout。

        server.py 走 sys.__stdout__（真实文件描述符），cli.py 走 print（终端工具）。
        """
        offenders = []
        for path in _py_files():
            name = os.path.basename(path)
            if name not in self.MCP_PATH_MODULES:
                continue
            tree = ast.parse(open(path, "r", encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr == "stdout":
                    # sys.__stdout__ 的 attr 名是 "__stdout__"，不会命中
                    offenders.append((name, node.lineno))
        self.assertEqual(offenders, [], "MCP 路径出现 sys.stdout：%r" % offenders)

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
