import ast
import contextlib
from io import StringIO

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from loguru import logger

FORBIDDEN_PYTHON_CALLS = {"eval", "exec", "__import__"}
FORBIDDEN_PYTHON_NODES = (ast.Import, ast.ImportFrom)
SAFE_BUILTINS = {
    "abs": abs,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


class PythonSecurityVisitor(ast.NodeVisitor):
    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_PYTHON_CALLS:
            raise ValueError(f"检测到禁止调用的高危函数: {node.func.id}")
        self.generic_visit(node)

    def visit_Import(self, node):
        raise ValueError("检测到禁止执行的语句: import")

    def visit_ImportFrom(self, node):
        raise ValueError("检测到禁止执行的语句: import")


def _validate_python_code(code: str) -> ast.AST:
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise ValueError(f"Python代码语法错误: {exc}") from exc

    PythonSecurityVisitor().visit(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "__import__":
            raise ValueError("检测到禁止调用的高危函数: __import__")
        if isinstance(node, FORBIDDEN_PYTHON_NODES):
            raise ValueError("检测到禁止执行的语句: import")
    return tree


def _prepare_python_tree(tree: ast.Module) -> ast.Module:
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last_expr = tree.body[-1].value
        if isinstance(last_expr, ast.Call) and isinstance(last_expr.func, ast.Name) and last_expr.func.id == "print":
            return tree
        tree.body[-1] = ast.Expr(
            value=ast.Call(
                func=ast.Name(id="print", ctx=ast.Load()),
                args=[last_expr],
                keywords=[],
            )
        )
        ast.fix_missing_locations(tree)
    return tree


def _execute_python_code(code: str) -> str:
    normalized_code = (code or "").strip()
    if not normalized_code:
        return "代码执行完成，但没有输出"

    tree = _prepare_python_tree(_validate_python_code(normalized_code))

    output_buffer = StringIO()
    error_buffer = StringIO()
    exec_globals = {"__builtins__": SAFE_BUILTINS}
    exec_locals = {}

    with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
        try:
            compiled = compile(tree, "<python_execute_direct>", "exec")
            exec(compiled, exec_globals, exec_locals)
        except Exception as exec_error:
            print(f"执行错误: {exec_error}")

    stdout_content = output_buffer.getvalue()
    stderr_content = error_buffer.getvalue()

    result_parts = []
    if stdout_content.strip():
        result_parts.append(stdout_content.strip())
    if stderr_content.strip():
        result_parts.append(f"错误信息: {stderr_content.strip()}")

    return "\n".join(result_parts) if result_parts else "代码执行完成，但没有输出"


@tool(parse_docstring=True)
def python_execute_direct(code: str, config: RunnableConfig) -> str:
    """
    直接执行Python代码的工具,不允许执行高危的、恶意的代码，不允许执行系统命令,不允许查看涉密信息。

    Args:
        code: 被执行的python代码

    Returns:
        执行结果
    """
    try:
        logger.info(f"Python直接执行工具执行代码:{code}")
        final_result = _execute_python_code(code)
        logger.info(f"Python直接执行工具执行结果:{final_result}")
        return final_result

    except Exception as e:
        logger.error(f"Python直接执行工具执行失败:{e}")
        return f"Python直接执行工具执行失败:{e}"
