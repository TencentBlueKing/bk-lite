"""AST whitelist helpers for ops-analysis transform scripts."""

from __future__ import annotations

import ast

ALLOWED_IMPORT_MODULES = frozenset({"json", "math", "datetime", "collections"})


class ScriptValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "script_invalid"):
        super().__init__(message)
        self.code = code


def validate_script_ast(script: str) -> ast.Module:
    if not isinstance(script, str) or not script.strip():
        raise ScriptValidationError("script 不能为空", code="script_empty")
    try:
        tree = ast.parse(script, mode="exec")
    except SyntaxError as exc:
        raise ScriptValidationError(f"脚本语法错误: {exc.msg}", code="script_syntax_error") from exc

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".", 1)[0] for alias in node.names]
            elif node.module:
                names = [node.module.split(".", 1)[0]]
            for name in names:
                if name not in ALLOWED_IMPORT_MODULES:
                    raise ScriptValidationError(
                        f"不允许导入模块: {name}",
                        code="script_import_not_allowed",
                    )
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise ScriptValidationError("不允许使用 global/nonlocal", code="script_forbidden_syntax")
    return tree
