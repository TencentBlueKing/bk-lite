"""Metric Enum unit 按语言包 enum 映射本地化。

metrics.json / DB 中 Enum 的 unit 多为中文硬编码。语言包提供
``monitor_object_metric.<Object>.<metric>.enum``（id→译名）时按 id 覆盖 name。
LanguageLoader 已按账号 locale 加载，中文界面无 enum 条目则保持原样。
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Optional


def _enum_id_key(value: Any) -> str:
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def localize_metric_enum_unit(
    unit: str,
    *,
    enum_translations: Optional[Mapping[Any, Any]] = None,
) -> str:
    """用 language yaml 的 enum 映射本地化 Enum 指标 unit。无映射或解析失败时原样返回。"""
    if not unit or not isinstance(unit, str):
        return unit
    if not isinstance(enum_translations, Mapping) or not enum_translations:
        return unit

    stripped = unit.strip()
    if not stripped.startswith("["):
        return unit

    try:
        options = json.loads(stripped)
    except (TypeError, ValueError, json.JSONDecodeError):
        return unit
    if not isinstance(options, list):
        return unit

    yaml_map: dict[str, str] = {}
    for key, value in enum_translations.items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            yaml_map[_enum_id_key(key)] = text

    if not yaml_map:
        return unit

    changed = False
    for option in options:
        if not isinstance(option, dict):
            continue
        name = option.get("name")
        if not isinstance(name, str):
            continue
        translated = yaml_map.get(_enum_id_key(option.get("id")))
        if translated is not None and translated != name:
            option["name"] = translated
            changed = True

    if not changed:
        return unit
    return json.dumps(options, ensure_ascii=False, separators=(",", ":"))
