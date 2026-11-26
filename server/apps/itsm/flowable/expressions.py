from typing import Any

_OPS = {
    "=": "==",
    "!=": "!=",
    ">": ">",
    ">=": ">=",
    "<": "<",
    "<=": "<=",
}


def to_juel(condition: dict[str, Any] | None) -> str:
    """条件构造器 JSON 转 JUEL。字段 form.amount 写成 form_amount。"""
    if not condition:
        return "${true}"
    return "${" + _expr(condition) + "}"


def _expr(node: dict[str, Any]) -> str:
    if "logic" in node:
        joiner = " && " if node.get("logic") == "and" else " || "
        parts = [_expr(item) for item in node.get("items") or []]
        return "(" + joiner.join(parts) + ")" if parts else "true"
    field = _field(str(node.get("field") or ""))
    op = str(node.get("op") or "=")
    value = node.get("value")
    if op in _OPS:
        return f"{field} {_OPS[op]} {_literal(value)}"
    if op == "in":
        items = value if isinstance(value, list) else []
        if not items:
            return "false"
        return "(" + " || ".join(f"{field} == {_literal(item)}" for item in items) + ")"
    if op == "not_in":
        items = value if isinstance(value, list) else []
        if not items:
            return "true"
        return "(" + " && ".join(f"{field} != {_literal(item)}" for item in items) + ")"
    if op == "contains":
        return f"{field}.contains({_literal(value)})"
    if op == "is_empty":
        return f"empty {field}"
    if op == "not_empty":
        return f"!empty {field}"
    raise ValueError(f"不支持的运算符 {op}")


def _field(name: str) -> str:
    return name.replace(".", "_")


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = "" if value is None else str(value).replace("'", "\\'")
    return f"'{text}'"
