"""SNMP 采集配置中的接口维度过滤规范化。"""

from __future__ import annotations

import re

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.monitor.constants.snmp_interface import (
    FIELD_IFDESCR_EXCLUDE,
    FIELD_IFDESCR_INCLUDE,
    FIELD_IFTYPE_EXCLUDE,
    FIELD_IFTYPE_INCLUDE,
)

_IFTYPE_LABELED_RE = re.compile(r"^(\d+)\s+-\s+.+$")

_MSG_IFTYPE_MUTEX = {
    "zh": "排除与仅采集的接口类型不能同时配置，请先清空其中一侧",
    "en": "Excluded and included interface types cannot be set together. Clear one side first",
}
_MSG_IFDESCR_MUTEX = {
    "zh": "排除与仅采集的接口名称不能同时配置，请先清空其中一侧",
    "en": "Excluded and included interface names cannot be set together. Clear one side first",
}


def _is_english_locale() -> bool:
    try:
        from django.utils.translation import get_language

        lang = (get_language() or "").lower().replace("_", "-")
    except Exception:
        return False
    return lang.startswith("en")


def _mutex_message(messages: dict[str, str]) -> str:
    return messages["en"] if _is_english_locale() else messages["zh"]


def normalize_filter_list(value) -> list[str]:
    """规范化黑白名单字段为去空白字符串列表；空输入返回 []。"""
    if value is None or value is False:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def normalize_iftype_list(value) -> list[str]:
    """ifType 仅保留数字；兼容「24 - Loopback」展示格式，丢弃非法项。"""
    values: list[str] = []
    seen: set[str] = set()
    for item in normalize_filter_list(value):
        if item.isdigit():
            parsed = item
        else:
            match = _IFTYPE_LABELED_RE.match(item)
            if not match:
                continue
            parsed = match.group(1)
        if parsed not in seen:
            seen.add(parsed)
            values.append(parsed)
    return values


def _prune_table_key(config: dict, table_name: str, key: str, values: list[str]) -> None:
    table = config.get(table_name)
    if values:
        if not isinstance(table, dict):
            table = {}
            config[table_name] = table
        table[key] = values
        return
    if not isinstance(table, dict):
        return
    table.pop(key, None)
    if not table:
        config.pop(table_name, None)


def assert_snmp_interface_filter_mutex(
    *,
    iftype_include: list[str] | None = None,
    iftype_exclude: list[str] | None = None,
    ifdescr_include: list[str] | None = None,
    ifdescr_exclude: list[str] | None = None,
) -> None:
    """黑白名单互斥：同一维度两侧不能同时有值。"""
    iftype_include_values = normalize_iftype_list(iftype_include)
    iftype_exclude_values = normalize_iftype_list(iftype_exclude)
    if iftype_include_values and iftype_exclude_values:
        raise ValidationAppException(_mutex_message(_MSG_IFTYPE_MUTEX))

    ifdescr_include_values = normalize_filter_list(ifdescr_include)
    ifdescr_exclude_values = normalize_filter_list(ifdescr_exclude)
    if ifdescr_include_values and ifdescr_exclude_values:
        raise ValidationAppException(_mutex_message(_MSG_IFDESCR_MUTEX))


def assert_snmp_interface_filter_mutex_from_values(values: dict | None) -> None:
    """从创建/编辑表单字段校验黑白名单互斥；顺带规范化 ifType 为数字。"""
    values = values or {}
    if FIELD_IFTYPE_INCLUDE in values:
        values[FIELD_IFTYPE_INCLUDE] = normalize_iftype_list(values.get(FIELD_IFTYPE_INCLUDE))
    if FIELD_IFTYPE_EXCLUDE in values:
        values[FIELD_IFTYPE_EXCLUDE] = normalize_iftype_list(values.get(FIELD_IFTYPE_EXCLUDE))
    assert_snmp_interface_filter_mutex(
        iftype_include=values.get(FIELD_IFTYPE_INCLUDE),
        iftype_exclude=values.get(FIELD_IFTYPE_EXCLUDE),
        ifdescr_include=values.get(FIELD_IFDESCR_INCLUDE),
        ifdescr_exclude=values.get(FIELD_IFDESCR_EXCLUDE),
    )


def normalize_snmp_interface_filter_config(content: dict | None, form_values: dict | None = None) -> dict | None:
    """规范化 child content 中的 tagpass/tagdrop，空规则删除键。

    form_values 可选：来自编辑表单的原始字段，优先于 content 内已有值。
    """
    if not isinstance(content, dict):
        return content
    config = content.get("config")
    if not isinstance(config, dict):
        return content

    form_values = form_values or {}

    def resolve(field_name: str, table: str, key: str, *, iftype: bool = False) -> list[str]:
        normalizer = normalize_iftype_list if iftype else normalize_filter_list
        if field_name in form_values:
            return normalizer(form_values.get(field_name))
        table_obj = config.get(table)
        if isinstance(table_obj, dict):
            return normalizer(table_obj.get(key))
        return []

    iftype_include = resolve(FIELD_IFTYPE_INCLUDE, "tagpass", "ifType", iftype=True)
    iftype_exclude = resolve(FIELD_IFTYPE_EXCLUDE, "tagdrop", "ifType", iftype=True)
    ifdescr_include = resolve(FIELD_IFDESCR_INCLUDE, "tagpass", "ifDescr")
    ifdescr_exclude = resolve(FIELD_IFDESCR_EXCLUDE, "tagdrop", "ifDescr")

    assert_snmp_interface_filter_mutex(
        iftype_include=iftype_include,
        iftype_exclude=iftype_exclude,
        ifdescr_include=ifdescr_include,
        ifdescr_exclude=ifdescr_exclude,
    )

    _prune_table_key(config, "tagpass", "ifType", iftype_include)
    _prune_table_key(config, "tagpass", "ifDescr", ifdescr_include)
    _prune_table_key(config, "tagdrop", "ifType", iftype_exclude)
    _prune_table_key(config, "tagdrop", "ifDescr", ifdescr_exclude)

    if "tagexclude" not in config:
        config["tagexclude"] = ["ifType"]
    return content
