"""Legacy stringList → string + inputConfig.multiple 规范化。

与前端 `stringParamMultipleMigrate.ts` 对齐：仅用于读兼容与写路径规范化，
不得在运行时请求组装中根据 stringList 决定数组形状。
"""

from __future__ import annotations

import copy
import json
from typing import Any

LEGACY_STRING_LIST_TYPE = "stringList"
WARNING_COMPONENT_SWITCH = "string_list_component_switch_conflict"
WARNING_DUAL_ID = "string_list_dual_id_incompatible"

DEFAULT_MULTIPLE_SELECT_CONFIG: dict[str, Any] = {
    "control": "select",
    "multiple": True,
    "optionsSource": {"type": "static", "staticItems": []},
}


def _stable_serialize(value: Any) -> str:
    if value is None or not isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if isinstance(value, list):
        return "[" + ",".join(_stable_serialize(item) for item in value) + "]"
    keys = sorted(value.keys())
    return "{" + ",".join(f"{json.dumps(key, ensure_ascii=False)}:{_stable_serialize(value[key])}" for key in keys) + "}"


def _options_source_identity(options_source: Any) -> str:
    if not isinstance(options_source, dict):
        return _stable_serialize(options_source)
    if options_source.get("type") == "static":
        values = sorted(str(item.get("value")) for item in (options_source.get("staticItems") or []) if isinstance(item, dict))
        return _stable_serialize({"type": "static", "values": values})
    return _stable_serialize(options_source)


def are_normalized_input_configs_compatible(left: Any, right: Any) -> bool:
    if not left and not right:
        return True
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    if left.get("control") != right.get("control"):
        return False
    if left.get("control") == "input" or right.get("control") == "input":
        return left.get("control") == right.get("control")
    left_picker = left.get("picker") or "dropdown"
    right_picker = right.get("picker") or "dropdown"
    if left_picker != right_picker:
        return False
    return _options_source_identity(left.get("optionsSource")) == _options_source_identity(right.get("optionsSource"))


def _normalize_legacy_options_to_input_config(entity: dict) -> dict | None:
    input_config = entity.get("inputConfig")
    if isinstance(input_config, dict):
        return copy.deepcopy(input_config)
    options = entity.get("options")
    if isinstance(options, list) and options:
        return {
            "control": "select",
            "optionsSource": {
                "type": "static",
                "staticItems": copy.deepcopy(options),
            },
        }
    return None


def normalize_string_list_input_config(entity: dict | None) -> tuple[dict, list[dict]]:
    warnings: list[dict] = []
    normalized = _normalize_legacy_options_to_input_config(entity or {})
    if not normalized:
        return copy.deepcopy(DEFAULT_MULTIPLE_SELECT_CONFIG), warnings

    if normalized.get("control") == "input":
        return {"control": "input"}, warnings

    next_config: dict[str, Any] = {
        "control": normalized.get("control") or "select",
        "optionsSource": copy.deepcopy(normalized.get("optionsSource") or {"type": "static", "staticItems": []}),
        "multiple": True,
    }
    if "maxCount" in normalized:
        next_config["maxCount"] = normalized.get("maxCount")
    if normalized.get("picker"):
        next_config["picker"] = normalized.get("picker")

    if normalized.get("componentSwitch"):
        warnings.append(
            {
                "code": WARNING_COMPONENT_SWITCH,
                "message": "旧 stringList 与 componentSwitch 互斥；已保留列表传参（multiple: true）并关闭 componentSwitch",
            }
        )

    return next_config, warnings


def string_filter_definition_id(key: str) -> str:
    return f"{key}__string"


def migrate_param_item(param: Any) -> tuple[Any, list[dict]]:
    if not isinstance(param, dict) or param.get("type") != LEGACY_STRING_LIST_TYPE:
        return param, []
    input_config, warnings = normalize_string_list_input_config(param)
    next_param = copy.deepcopy(param)
    next_param["type"] = "string"
    next_param["inputConfig"] = input_config
    next_param.pop("options", None)
    for warning in warnings:
        warning["key"] = param.get("name")
    return next_param, warnings


def migrate_param_items(params: Any) -> tuple[list, list[dict]]:
    if not isinstance(params, list):
        return [], []
    warnings: list[dict] = []
    next_params = []
    for param in params:
        migrated, item_warnings = migrate_param_item(param)
        warnings.extend(item_warnings)
        next_params.append(migrated)
    return next_params, warnings


def migrate_filter_bindings(bindings: Any) -> dict:
    if not isinstance(bindings, dict):
        return {}
    next_bindings: dict[str, bool] = {}
    suffix = f"__{LEGACY_STRING_LIST_TYPE}"
    for filter_id, enabled in bindings.items():
        target_id = f"{str(filter_id)[: -len(suffix)]}__string" if str(filter_id).endswith(suffix) else str(filter_id)
        if target_id in next_bindings:
            next_bindings[target_id] = bool(next_bindings[target_id] or enabled)
        else:
            next_bindings[target_id] = bool(enabled)
    return next_bindings


def _migrate_single_filter_definition(definition: dict) -> tuple[dict, list[dict]]:
    if definition.get("type") != LEGACY_STRING_LIST_TYPE:
        return copy.deepcopy(definition), []
    input_config, warnings = normalize_string_list_input_config(definition)
    next_definition = copy.deepcopy(definition)
    next_definition["id"] = string_filter_definition_id(str(definition.get("key") or ""))
    next_definition["type"] = "string"
    next_definition["inputConfig"] = input_config
    next_definition.pop("options", None)
    for warning in warnings:
        warning["key"] = definition.get("key")
    return next_definition, warnings


def migrate_unified_filter_definitions(definitions: Any) -> tuple[list[dict], list[dict]]:
    if not isinstance(definitions, list):
        return [], []

    warnings: list[dict] = []
    originals = [item for item in definitions if isinstance(item, dict)]
    migrated_singles: list[dict] = []
    for item in originals:
        migrated, item_warnings = _migrate_single_filter_definition(item)
        warnings.extend(item_warnings)
        migrated_singles.append(migrated)

    by_key: dict[str, list[dict]] = {}
    for item in migrated_singles:
        key = str(item.get("key") or "")
        by_key.setdefault(key, []).append(item)

    next_definitions: list[dict] = []
    for key, group in by_key.items():
        string_id = string_filter_definition_id(key)
        list_origin = next(
            (item for item in originals if item.get("key") == key and item.get("type") == LEGACY_STRING_LIST_TYPE),
            None,
        )
        string_origin = next(
            (item for item in originals if item.get("key") == key and item.get("type") == "string" and item.get("id") == string_id),
            None,
        )

        if list_origin and string_origin:
            list_migrated, _ = _migrate_single_filter_definition(list_origin)
            string_migrated = copy.deepcopy(string_origin)
            if not are_normalized_input_configs_compatible(
                list_migrated.get("inputConfig"),
                string_migrated.get("inputConfig"),
            ):
                warnings.append(
                    {
                        "code": WARNING_DUAL_ID,
                        "key": key,
                        "message": (f"筛选项 {key} 同时存在 string 与 stringList，配置不兼容；" f"已以 stringList 侧为准合并为 {string_id}"),
                        "fields": ["control", "picker", "optionsSource"],
                    }
                )
            merged = copy.deepcopy(list_migrated)
            merged["id"] = string_id
            merged["type"] = "string"
            merged["order"] = min(list_migrated.get("order") or 0, string_migrated.get("order") or 0)
            merged["enabled"] = bool(list_migrated.get("enabled") or string_migrated.get("enabled"))
            next_definitions.append(merged)
            continue

        next_definitions.append(group[0])

    next_definitions.sort(key=lambda item: (item.get("order") or 0, str(item.get("id") or "")))
    return next_definitions, warnings


def _walk_migrate_value_configs(value: Any, warnings: list[dict]) -> Any:
    if isinstance(value, list):
        return [_walk_migrate_value_configs(item, warnings) for item in value]
    if not isinstance(value, dict):
        return value

    cloned = {key: _walk_migrate_value_configs(item, warnings) for key, item in value.items()}
    value_config = cloned.get("valueConfig")
    if isinstance(value_config, dict):
        next_config = dict(value_config)
        if "filterBindings" in next_config:
            next_config["filterBindings"] = migrate_filter_bindings(next_config.get("filterBindings"))
        if "dataSourceParams" in next_config:
            migrated_params, param_warnings = migrate_param_items(next_config.get("dataSourceParams"))
            next_config["dataSourceParams"] = migrated_params
            warnings.extend(param_warnings)
        cloned["valueConfig"] = next_config
    return cloned


def migrate_filters_payload(filters: Any) -> tuple[Any, list[dict]]:
    if isinstance(filters, list):
        return migrate_unified_filter_definitions(filters)

    if isinstance(filters, dict):
        next_filters = copy.deepcopy(filters)
        warnings: list[dict] = []
        for key in ("definitions", "unifiedFilters"):
            if key in next_filters:
                migrated, item_warnings = migrate_unified_filter_definitions(next_filters.get(key))
                next_filters[key] = migrated
                warnings.extend(item_warnings)
        return next_filters, warnings

    return filters, []


def migrate_canvas_view_sets(view_sets: Any) -> tuple[Any, list[dict]]:
    warnings: list[dict] = []
    if isinstance(view_sets, list):
        return _walk_migrate_value_configs(view_sets, warnings), warnings

    if not isinstance(view_sets, dict):
        return view_sets, warnings

    next_view_sets = _walk_migrate_value_configs(view_sets, warnings)
    if isinstance(next_view_sets.get("filters"), list):
        migrated_filters, filter_warnings = migrate_unified_filter_definitions(next_view_sets.get("filters"))
        next_view_sets["filters"] = migrated_filters
        warnings.extend(filter_warnings)
    if isinstance(next_view_sets.get("sections"), list):
        next_view_sets["sections"] = _walk_migrate_value_configs(next_view_sets.get("sections"), warnings)
    return next_view_sets, warnings


def collect_migration_warnings_for_document(
    *,
    object_key: str,
    object_name: str,
    params: Any = None,
    filters: Any = None,
    view_sets: Any = None,
) -> list[dict]:
    """生成与实际 migrate 结果一致的导入 warning 列表（含 object_key/field）。"""
    warnings: list[dict] = []

    if isinstance(params, list):
        for param in params:
            if not isinstance(param, dict) or param.get("type") != LEGACY_STRING_LIST_TYPE:
                continue
            key = param.get("name") or "unknown"
            input_config = param.get("inputConfig")
            if isinstance(input_config, dict) and input_config.get("componentSwitch"):
                message = f"{object_name} 参数 '{key}' 为旧 stringList 且启用了 componentSwitch；" "导入后将保留列表传参（multiple）并关闭 componentSwitch"
            else:
                message = f"{object_name} 参数 '{key}' 使用旧类型 stringList，导入后将规范为 string + multiple"
            warnings.append(
                {
                    "code": "OA_STRING_LIST_MIGRATION",
                    "message": message,
                    "object_key": object_key,
                    "field": f"params.{key}",
                }
            )

    filter_list = filters
    if filter_list is None and isinstance(view_sets, dict):
        filter_list = view_sets.get("filters")
    if not isinstance(filter_list, list):
        return warnings

    by_key: dict[str, list[dict]] = {}
    for item in filter_list:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "")
        by_key.setdefault(key, []).append(item)
        if item.get("type") != LEGACY_STRING_LIST_TYPE:
            continue
        filter_id = item.get("id") or key
        input_config = item.get("inputConfig")
        if isinstance(input_config, dict) and input_config.get("componentSwitch"):
            message = f"画布 '{object_name}' 筛选项 '{filter_id}' 为旧 stringList " "且启用了 componentSwitch；导入后将保留 multiple 并关闭 componentSwitch"
        else:
            message = f"画布 '{object_name}' 筛选项 '{filter_id}' 使用旧类型 stringList，" "导入后将规范为 string + multiple / key__string"
        warnings.append(
            {
                "code": "OA_STRING_LIST_MIGRATION",
                "message": message,
                "object_key": object_key,
                "field": f"filters.{filter_id}",
            }
        )

    for key, items in by_key.items():
        if not key:
            continue
        types = {item.get("type") for item in items}
        ids = {item.get("id") for item in items}
        if LEGACY_STRING_LIST_TYPE in types and ("string" in types or f"{key}__string" in ids):
            warnings.append(
                {
                    "code": "OA_STRING_LIST_MIGRATION",
                    "message": (f"画布 '{object_name}' 筛选项 key '{key}' 同时存在 string 与 stringList；" "导入后将以 stringList 侧为准合并为 key__string"),
                    "object_key": object_key,
                    "field": f"filters.{key}",
                }
            )

    return warnings
