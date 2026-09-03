"""按本插件 UI.json 覆盖表单帮助文案，避免跨插件按字段名继承。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.monitor.models import MonitorPlugin

_HELP_FIELD_KEYS = ("description", "description_en", "tooltip", "guide_short")
_HELP_WIDGET_KEYS = ("placeholder", "placeholder_en")


def _named_items(items) -> dict:
    return {str(item.get("name")): item for item in (items or []) if isinstance(item, dict) and item.get("name")}


def _copy_help_keys(target: dict, source: dict, keys: tuple[str, ...]) -> None:
    for key in keys:
        if key not in source:
            continue
        value = source.get(key)
        if value in (None, ""):
            continue
        target[key] = deepcopy(value)


def overlay_form_field_help_from_plugin_files(content: dict | None, plugin: MonitorPlugin | None) -> dict | None:
    """用当前插件 UI.json 覆盖 form_fields 的 description/placeholder。

    按字段 name 只对齐「同一个插件」的磁盘文案，不会把 Windows WMI 的
    domain\\user 套到 Host AIX Remote 或 Host Remote。
    """
    if content is None or not plugin or not isinstance(content, dict):
        return content

    from apps.monitor.services.plugin_guide import PluginGuideService

    plugin_dir = PluginGuideService.resolve_plugin_dir(plugin)
    if plugin_dir is None:
        return content
    ui_file = Path(plugin_dir) / "UI.json"
    if not ui_file.is_file():
        return content
    try:
        file_ui = json.loads(ui_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return content
    if not isinstance(file_ui, dict):
        return content

    file_fields = _named_items(file_ui.get("form_fields"))
    if not file_fields:
        return content

    enriched = deepcopy(content)
    form_fields = enriched.get("form_fields")
    if not isinstance(form_fields, list):
        return enriched
    for field in form_fields:
        if not isinstance(field, dict):
            continue
        source = file_fields.get(str(field.get("name") or ""))
        if not source:
            continue
        _copy_help_keys(field, source, _HELP_FIELD_KEYS)
        source_widget = source.get("widget_props")
        if not isinstance(source_widget, dict):
            continue
        field_widget = field.get("widget_props")
        if not isinstance(field_widget, dict):
            field_widget = {}
            field["widget_props"] = field_widget
        _copy_help_keys(field_widget, source_widget, _HELP_WIDGET_KEYS)
    return enriched
