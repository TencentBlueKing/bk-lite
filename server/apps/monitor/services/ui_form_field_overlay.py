"""按本插件 UI.json 覆盖表单帮助文案，避免跨插件按字段名继承。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.monitor.models import MonitorPlugin

# 英语 locale 用 guide_short_en 替换 guide_short；不覆盖则磁盘新文案到不了英文界面。
_HELP_FIELD_KEYS = ("description", "description_en", "tooltip", "guide_short", "guide_short_en")
_HELP_WIDGET_KEYS = ("placeholder", "placeholder_en")
# 标签和同一行布局也以磁盘 UI.json 为准。采集页读的是 DB 模板，
# 不覆盖的话要等下一次 plugin_init 才会改标签和左右并排。
_DISPLAY_FIELD_KEYS = ("label", "label_en", "row")
# RocketMQ 表单已去掉「超时」。已初始化 DB 模板仍可能留着 response_timeout，
# 读路径按磁盘字段集丢掉它，官方采集页不用再跑 plugin_init。
_ROCKETMQ_RETIRED_FORM_FIELDS = ("response_timeout",)


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


def _sync_row_from_file(target: dict, source: dict) -> None:
    """磁盘未声明 row 时清掉 DB 里的旧并排标记。"""
    row = source.get("row")
    if isinstance(row, str) and row.strip():
        target["row"] = row
        return
    target.pop("row", None)


def _is_rocketmq_ui(file_ui: dict, content: dict) -> bool:
    for candidate in (file_ui, content):
        if str(candidate.get("instance_type") or "").strip().lower() == "rocketmq":
            return True
        config_type = candidate.get("config_type") or []
        if isinstance(config_type, str):
            config_type = [config_type]
        if isinstance(config_type, (list, tuple)) and any(
            str(item).strip().lower() == "rocketmq" for item in config_type
        ):
            return True
    return False


def _drop_retired_rocketmq_fields(form_fields: list, file_fields: dict, file_ui: dict, content: dict) -> list:
    if not _is_rocketmq_ui(file_ui, content):
        return form_fields
    retired = {name for name in _ROCKETMQ_RETIRED_FORM_FIELDS if name not in file_fields}
    if not retired:
        return form_fields
    return [
        field
        for field in form_fields
        if not (isinstance(field, dict) and str(field.get("name") or "") in retired)
    ]


def overlay_form_field_help_from_plugin_files(content: dict | None, plugin: MonitorPlugin | None) -> dict | None:
    """用当前插件 UI.json 覆盖 form_fields 的说明、标签和同一行布局。

    按字段 name 只对齐「同一个插件」的磁盘文案，不会把 Windows WMI 的
    domain\\user 套到 Host AIX Remote、Host FreeBSD Remote、Host HP-UX Remote、Host Solaris Remote 或 Host Remote。
    RocketMQ 磁盘表单不再包含 response_timeout 时，读路径去掉已初始化模板里的「超时」。
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

    enriched = deepcopy(content)
    from apps.monitor.services.qcloud_ui_overlay import merge_qcloud_ui_from_file

    # 腾讯云：补齐磁盘上的 region / instance_id 等结构字段（不限于帮助文案）。
    enriched = merge_qcloud_ui_from_file(enriched, file_ui) or enriched

    file_fields = _named_items(file_ui.get("form_fields"))
    if not file_fields:
        return enriched

    form_fields = enriched.get("form_fields")
    if not isinstance(form_fields, list):
        return enriched
    form_fields = _drop_retired_rocketmq_fields(form_fields, file_fields, file_ui, enriched)
    enriched["form_fields"] = form_fields
    for field in form_fields:
        if not isinstance(field, dict):
            continue
        source = file_fields.get(str(field.get("name") or ""))
        if not source:
            continue
        _copy_help_keys(field, source, _HELP_FIELD_KEYS)
        _copy_help_keys(field, source, _DISPLAY_FIELD_KEYS)
        _sync_row_from_file(field, source)
        source_widget = source.get("widget_props")
        if not isinstance(source_widget, dict):
            continue
        field_widget = field.get("widget_props")
        if not isinstance(field_widget, dict):
            field_widget = {}
            field["widget_props"] = field_widget
        _copy_help_keys(field_widget, source_widget, _HELP_WIDGET_KEYS)
    return enriched
