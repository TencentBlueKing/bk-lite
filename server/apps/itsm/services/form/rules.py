import ast
from datetime import datetime, timezone
from typing import Any


class ExpressionError(ValueError):
    pass


def match_when(when: dict[str, Any] | None, data: dict[str, Any]) -> bool:
    if not when:
        return True
    if "logic" in when:
        items = [match_when(item, data) for item in when.get("items") or []]
        return all(items) if when.get("logic") == "and" else any(items)
    actual = _value_at(data, str(when.get("field") or ""))
    op = when.get("op")
    expected = when.get("value")
    if op == "=":
        return actual == expected
    if op == "!=":
        return actual != expected
    if op == ">":
        return actual is not None and actual > expected
    if op == ">=":
        return actual is not None and actual >= expected
    if op == "<":
        return actual is not None and actual < expected
    if op == "<=":
        return actual is not None and actual <= expected
    if op == "in":
        return actual in (expected or [])
    if op == "not_in":
        return actual not in (expected or [])
    if op == "contains":
        return expected in actual if actual is not None else False
    if op == "is_empty":
        return actual in (None, "", [], {})
    if op == "not_empty":
        return actual not in (None, "", [], {})
    return False


def _value_at(data: dict[str, Any], field: str) -> Any:
    current: Any = data
    for part in field.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def evaluate_expr(expr: str, data: dict[str, Any]) -> Any:
    """白名单表达式。只允许字面量、字段路径，以及 sum/avg/concat/now/if。"""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError("表达式无法解析") from exc
    return _eval(tree.body, data)


def _eval(node: ast.AST, data: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return data.get(node.id)
    if isinstance(node, ast.Attribute):
        return _path(node, data)
    if isinstance(node, ast.List):
        return [_eval(item, data) for item in node.elts]
    if isinstance(node, ast.Call):
        return _call(node, data)
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        return match_when({"field": _name_of(node.left), "op": _op(node.ops[0]), "value": _eval(node.comparators[0], data)}, data)
    raise ExpressionError("表达式含有未允许的语法")


def _call(node: ast.Call, data: dict[str, Any]) -> Any:
    if not isinstance(node.func, ast.Name):
        raise ExpressionError("只允许直接调用白名单函数")
    name = node.func.id
    args = [_eval(arg, data) for arg in node.args]
    if name == "sum":
        return sum(_numbers(args[0] if args else []))
    if name == "avg":
        values = _numbers(args[0] if args else [])
        return sum(values) / len(values) if values else 0
    if name == "concat":
        return "".join("" if item is None else str(item) for item in args)
    if name == "now":
        return datetime.now(timezone.utc).isoformat()
    if name == "if":
        condition, yes, no = (args + [None, None, None])[:3]
        return yes if condition else no
    raise ExpressionError(f"函数 {name} 不在白名单")


def _path(node: ast.Attribute, data: dict[str, Any]) -> Any:
    names: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        names.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        raise ExpressionError("字段路径不合法")
    names.append(current.id)
    names.reverse()
    value: Any = data.get(names[0])
    for part in names[1:]:
        if isinstance(value, list):
            value = [item.get(part) if isinstance(item, dict) else None for item in value]
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _numbers(value: Any) -> list[float]:
    if isinstance(value, list):
        return [float(item) for item in value if isinstance(item, (int, float))]
    if isinstance(value, (int, float)):
        return [float(value)]
    return []


def _name_of(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    raise ExpressionError("比较表达式左侧必须是字段名")


def _op(node: ast.cmpop) -> str:
    mapping = {ast.Eq: "=", ast.NotEq: "!=", ast.Gt: ">", ast.GtE: ">=", ast.Lt: "<", ast.LtE: "<="}
    if type(node) not in mapping:
        raise ExpressionError("不支持的比较")
    return mapping[type(node)]
