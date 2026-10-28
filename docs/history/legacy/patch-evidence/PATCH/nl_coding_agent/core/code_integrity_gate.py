"""Conservative, independent structural checks on proposed source/test edits.

These gates reject obvious destructive changes, but cannot prove functional
correctness; the original regression suite must still run on the candidate.
"""
from __future__ import annotations

import ast


def _tree(text: str) -> ast.AST | None:
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def _names(tree: ast.AST) -> set[str]:
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _is_stub_body(body: list[ast.stmt]) -> bool:
    meaningful = [n for n in body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
    if not meaningful:
        return True
    return all(isinstance(n, ast.Pass) or
               (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and n.value.value is Ellipsis) or
               (isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call) and isinstance(n.exc.func, ast.Name) and n.exc.func.id == "NotImplementedError")
               for n in meaningful)


def detect_stub(content: str, baseline: str | None = None) -> bool:
    if not content.strip():
        return bool(baseline and baseline.strip())
    candidate = _tree(content)
    if candidate is None:
        return True  # invalid Python; caller should only use this for .py files
    if baseline is not None and baseline.strip():
        old_tree = _tree(baseline)
        if old_tree is not None:
            old_defs = _names(old_tree)
            new_defs = _names(candidate)
            if old_defs - new_defs:
                return True  # API vanished; requires explicit approval for refactor
            if len(content.strip()) < len(baseline.strip()) * 0.3 and len(baseline) > 100:
                return True
            old_nodes = {n.name: n for n in ast.walk(old_tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            new_nodes = {n.name: n for n in ast.walk(candidate) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for name in old_nodes.keys() & new_nodes.keys():
                if not _is_stub_body(old_nodes[name].body) and _is_stub_body(new_nodes[name].body):
                    return True
    return False


def detect_weak_test(baseline: str, current: str) -> bool:
    old, new = _tree(baseline), _tree(current)
    if old is None:
        return False
    if new is None:
        return True
    old_tests = {n.name for n in ast.walk(old) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")}
    new_tests = {n.name for n in ast.walk(new) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")}
    if old_tests - new_tests:
        return True
    # A test using only assert True is not evidence of behavior.
    for node in ast.walk(new):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            statements = [n for n in node.body if not isinstance(n, ast.Expr) or not isinstance(n.value, ast.Constant) or not isinstance(n.value.value, str)]
            if not statements or all(isinstance(s, ast.Assert) and isinstance(s.test, ast.Constant) and s.test.value is True for s in statements):
                return True
    return False
