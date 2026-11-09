from collections.abc import Callable
from typing import Any

Lookup = Callable[[str], list[dict[str, Any]]]


def resolve_options(
    field: dict[str, Any], dictionary_lookup: Lookup | None = None, datasource_lookup: Lookup | None = None, datatable_lookup: Lookup | None = None
) -> list[dict[str, Any]]:
    """解析静态选项和字典。数据源、数据表只留接口，当前返回空列表。"""
    source = field.get("source") or {}
    source_type = source.get("type") or "static"
    if source_type == "static":
        return list(source.get("options") or field.get("props", {}).get("options") or [])
    if source_type == "dict":
        if dictionary_lookup is None:
            return []
        return list(dictionary_lookup(str(source.get("dict") or "")))
    if source_type == "datasource":
        if datasource_lookup is None:
            return []
        return list(datasource_lookup(str(source.get("id") or "")))
    if source_type == "datatable":
        if datatable_lookup is None:
            return []
        return list(datatable_lookup(str(source.get("id") or "")))
    return list(field.get("props", {}).get("options") or [])
