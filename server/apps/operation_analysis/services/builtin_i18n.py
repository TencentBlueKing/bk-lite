"""运营分析内置对象读时语言覆盖。

身份是 build_in_key；只覆盖展示字段，缺词条回退库内原文。用户副本 is_build_in=False 不覆盖。
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from apps.core.utils.loader import LanguageLoader

SECTION_BY_PREFIX = {
    "dashboard::": "dashboards",
    "screen::": "screens",
    "topology::": "topologies",
    "architecture::": "architectures",
    "report::": "reports",
}


def normalize_oa_language(language: str | None) -> str:
    raw = str(language or "zh-Hans").strip()
    if not raw:
        return "zh-Hans"
    return "en" if raw.lower().startswith("en") else "zh-Hans"


def locale_from_serializer_context(context: Mapping[str, Any] | None) -> str | None:
    request = (context or {}).get("request")
    user = getattr(request, "user", None) if request is not None else None
    return getattr(user, "locale", None)


def _catalog(language: str | None, catalog: dict | None) -> dict:
    if catalog is not None:
        return catalog
    return LanguageLoader("operation_analysis", normalize_oa_language(language)).translations or {}


def _section(catalog: dict, *keys: str) -> dict:
    current: Any = catalog
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _apply_text(target: dict, field: str, translated: Any) -> None:
    if translated and isinstance(translated, str):
        target[field] = translated


def _widget_entry(widgets: dict, node: dict) -> dict:
    for key in (node.get("id"), node.get("i")):
        if key and key in widgets and isinstance(widgets[key], dict):
            return widgets[key]
    return {}


def _overlay_choice_labels(options: Any, option_map: dict) -> None:
    if not isinstance(options, list) or not option_map:
        return
    for option in options:
        if not isinstance(option, dict):
            continue
        translated = option_map.get(option.get("value"))
        if translated:
            option["label"] = translated


def _overlay_params(params: Any, param_map: dict) -> None:
    if not isinstance(params, list) or not param_map:
        return
    for item in params:
        if not isinstance(item, dict):
            continue
        translated = param_map.get(item.get("name"))
        option_map = {}
        if isinstance(translated, dict):
            option_map = translated.get("options") or {}
            translated = translated.get("name") or translated.get("alias_name")
        if translated:
            item["alias_name"] = translated
        input_config = item.get("inputConfig")
        if isinstance(input_config, dict):
            source = input_config.get("optionsSource")
            if isinstance(source, dict):
                _overlay_choice_labels(source.get("staticItems"), option_map)


def _overlay_columns(columns: Any, column_map: dict) -> None:
    if not isinstance(columns, list) or not column_map:
        return
    for column in columns:
        if not isinstance(column, dict):
            continue
        translated = column_map.get(column.get("key"))
        if translated:
            column["title"] = translated


def _overlay_actions(actions: Any, action_map: dict) -> None:
    if not isinstance(actions, list) or not action_map:
        return
    for action in actions:
        if not isinstance(action, dict):
            continue
        translated = action_map.get(action.get("columnKey")) or action_map.get(action.get("text"))
        if translated:
            action["text"] = translated


def _overlay_node(node: dict, widgets: dict) -> None:
    entry = _widget_entry(widgets, node)
    if entry:
        _apply_text(node, "name", entry.get("name"))
        _apply_text(node, "description", entry.get("description"))
        _apply_text(node, "title", entry.get("title") or entry.get("name"))
        value_config = node.get("valueConfig")
        if isinstance(value_config, dict):
            _apply_text(value_config, "name", entry.get("name"))
            _apply_text(value_config, "description", entry.get("description"))
            table_config = value_config.get("tableConfig")
            if isinstance(table_config, dict):
                _overlay_columns(table_config.get("columns"), entry.get("columns") or {})
            _overlay_params(value_config.get("dataSourceParams"), entry.get("params") or {})
            _overlay_actions(value_config.get("actions"), entry.get("actions") or {})

    children = None
    sub_grid = node.get("subGridOpts")
    if isinstance(sub_grid, dict):
        children = sub_grid.get("children")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                _overlay_node(child, widgets)


def _overlay_view_sets(view_sets: Any, entry: dict) -> Any:
    if not view_sets:
        return view_sets
    widgets = entry.get("widgets") or {}
    cloned = copy.deepcopy(view_sets)
    if isinstance(cloned, list):
        for node in cloned:
            if isinstance(node, dict):
                _overlay_node(node, widgets)
        return cloned
    if isinstance(cloned, dict):
        items = cloned.get("items")
        if isinstance(items, list):
            for node in items:
                if isinstance(node, dict):
                    _overlay_node(node, widgets)
        sections = cloned.get("sections")
        if isinstance(sections, list):
            for node in sections:
                if isinstance(node, dict):
                    _overlay_node(node, widgets)
        if "filters" in cloned:
            cloned["filters"] = _overlay_filters(cloned.get("filters"), entry.get("filters") or {})
        decorations = cloned.get("decorations")
        deco_entry = entry.get("decorations") or {}
        if isinstance(decorations, dict):
            _apply_text(decorations, "title", deco_entry.get("title"))
        return cloned
    return cloned


def _overlay_filters(filters: Any, filter_map: dict) -> Any:
    if not isinstance(filters, list) or not filter_map:
        return filters
    cloned = copy.deepcopy(filters)
    for item in cloned:
        if not isinstance(item, dict):
            continue
        translated = filter_map.get(item.get("key")) or filter_map.get(item.get("id"))
        if not translated:
            continue
        option_map = {}
        if isinstance(translated, dict):
            _apply_text(item, "name", translated.get("name"))
            option_map = translated.get("options") or {}
            _overlay_choice_labels(item.get("options"), option_map)
        elif isinstance(translated, str):
            item["name"] = translated
        input_config = item.get("inputConfig")
        if isinstance(input_config, dict) and option_map:
            source = input_config.get("optionsSource")
            if isinstance(source, dict):
                _overlay_choice_labels(source.get("staticItems"), option_map)
    return cloned


def overlay_canvas_payload(data: dict, instance, language: str | None, catalog: dict | None = None) -> dict:
    if not data or not getattr(instance, "is_build_in", False):
        return data
    build_in_key = getattr(instance, "build_in_key", None)
    if not build_in_key:
        return data
    translations = _catalog(language, catalog)
    section_name = next((name for prefix, name in SECTION_BY_PREFIX.items() if str(build_in_key).startswith(prefix)), None)
    if not section_name:
        return data
    entry = _section(translations, section_name, str(build_in_key))
    if not entry:
        return data
    _apply_text(data, "name", entry.get("name"))
    _apply_text(data, "desc", entry.get("desc"))
    if "filters" in data:
        data["filters"] = _overlay_filters(data.get("filters"), entry.get("filters") or {})
    if "view_sets" in data:
        data["view_sets"] = _overlay_view_sets(data.get("view_sets"), entry)
    return data


def overlay_datasource_payload(data: dict, instance, language: str | None, catalog: dict | None = None) -> dict:
    if not data or not getattr(instance, "is_build_in", False):
        return data
    build_in_key = getattr(instance, "build_in_key", None)
    if not build_in_key:
        return data
    entry = _section(_catalog(language, catalog), "datasources", str(build_in_key))
    if not entry:
        return data
    _apply_text(data, "name", entry.get("name"))
    _apply_text(data, "desc", entry.get("desc"))
    fields = entry.get("fields") or {}
    schema = data.get("field_schema")
    if isinstance(schema, list) and fields:
        data["field_schema"] = copy.deepcopy(schema)
        for item in data["field_schema"]:
            if not isinstance(item, dict):
                continue
            field_entry = fields.get(item.get("key")) or {}
            if isinstance(field_entry, dict):
                _apply_text(item, "title", field_entry.get("title"))
                _apply_text(item, "description", field_entry.get("description"))
            elif isinstance(field_entry, str):
                item["title"] = field_entry
    params = data.get("params")
    if isinstance(params, list) and entry.get("params"):
        data["params"] = copy.deepcopy(params)
        _overlay_params(data["params"], entry.get("params") or {})
    return data


def overlay_directory_payload(data: dict, instance, language: str | None, catalog: dict | None = None) -> dict:
    if not data or not getattr(instance, "is_build_in", False):
        return data
    build_in_key = getattr(instance, "build_in_key", None)
    if not build_in_key:
        return data
    entry = _section(_catalog(language, catalog), "directories", str(build_in_key))
    _apply_text(data, "name", (entry or {}).get("name"))
    _apply_text(data, "desc", (entry or {}).get("desc"))
    return data


def apply_canvas_representation(data: dict, instance, context: Mapping[str, Any] | None) -> dict:
    return overlay_canvas_payload(data, instance, locale_from_serializer_context(context))


def apply_datasource_representation(data: dict, instance, context: Mapping[str, Any] | None) -> dict:
    return overlay_datasource_payload(data, instance, locale_from_serializer_context(context))


def apply_directory_representation(data: dict, instance, context: Mapping[str, Any] | None) -> dict:
    return overlay_directory_payload(data, instance, locale_from_serializer_context(context))
