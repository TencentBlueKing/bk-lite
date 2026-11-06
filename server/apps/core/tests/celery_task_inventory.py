"""只解析源码，不导入业务依赖；显式名称无法解析时失败，避免猜测注册名。"""

import ast
from pathlib import Path


def collect_tasks():
    apps = Path(__file__).resolve().parents[2]
    result = {}
    for source in apps.rglob("*.py"):
        if "tests" in source.parts or "migrations" in source.parts:
            continue
        tree = ast.parse(source.read_text())
        constants = {
            target.id: node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if not (
                    (isinstance(target, ast.Name) and target.id == "shared_task") or (isinstance(target, ast.Attribute) and target.attr == "task")
                ):
                    continue
                options = {item.arg: item.value for item in decorator.keywords} if isinstance(decorator, ast.Call) else {}

                def value(key):
                    expression = options.get(key)
                    if expression is None:
                        return None
                    if isinstance(expression, ast.Constant):
                        return expression.value
                    if isinstance(expression, ast.Name) and expression.id in constants:
                        return constants[expression.id]
                    raise AssertionError(f"需人工解析 {source}:{node.lineno} 的 {key}")

                module = ".".join(source.relative_to(apps.parent).with_suffix("").parts)
                name = value("name") or f"{module}.{node.name}"
                assert name not in result, f"重复注册名称 {name}"
                result[name] = {
                    "source": str(source.relative_to(apps.parent.parent)),
                    "line": node.lineno,
                    "declared_queue": value("queue"),
                    "summary": (ast.get_docstring(node) or "").split("\n")[0],
                }
    return result
