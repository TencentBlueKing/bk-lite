"""实例明细行的公开字段。

密码属性及其展示副本不进入响应行。不按字段名猜测。
"""

from __future__ import annotations

_SENSITIVE_ATTR_TYPES = frozenset({"pwd"})


def sensitive_hidden_keys(attr_types: dict | None) -> set[str]:
    """按属性类型隐藏密码字段和它的展示副本，不按字段名猜测。"""
    hidden: set[str] = set()
    for attr_id, kind in (attr_types or {}).items():
        if str(kind or "").lower() not in _SENSITIVE_ATTR_TYPES:
            continue
        key = str(attr_id).strip()
        if not key:
            continue
        hidden.add(key)
        hidden.add(f"{key}_display")
    return hidden


def public_instance(row: dict, hidden: set[str] | None = None) -> dict:
    if not isinstance(row, dict):
        return {}
    blocked = hidden or set()
    return {str(key): value for key, value in row.items() if not str(key).startswith("_") and str(key) not in blocked}
