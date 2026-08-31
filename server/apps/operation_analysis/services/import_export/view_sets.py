from typing import Any

from apps.operation_analysis.constants.import_export import ObjectType
from apps.operation_analysis.services.report_view_sets import normalize_report_view_sets
from apps.operation_analysis.services.string_param_multiple_migrate import migrate_canvas_view_sets

_SCENE_WIDGET_SURFACES = {
    "networkStatusTopology": {ObjectType.DASHBOARD, ObjectType.SCREEN},
    "application3D": {ObjectType.SCREEN},
}


def _validate_scene_widget_surfaces(value: Any, object_type: ObjectType) -> None:
    if isinstance(value, list):
        for item in value:
            _validate_scene_widget_surfaces(item, object_type)
        return
    if not isinstance(value, dict):
        return
    scene_type = value.get("sceneWidgetType") or value.get("chartType")
    if scene_type in _SCENE_WIDGET_SURFACES and object_type not in _SCENE_WIDGET_SURFACES[scene_type]:
        raise ValueError(f"{scene_type} is not supported on {object_type.value}")
    for item in value.values():
        _validate_scene_widget_surfaces(item, object_type)


def _rewrite_datasource_refs(value: Any, key_map: dict[Any, Any]) -> Any:
    if isinstance(value, list):
        return [_rewrite_datasource_refs(item, key_map) for item in value]

    if not isinstance(value, dict):
        return value

    cloned = {key: _rewrite_datasource_refs(item, key_map) for key, item in value.items()}
    value_config = cloned.get("valueConfig")
    if isinstance(value_config, dict):
        data_source = value_config.get("dataSource")
        if data_source in key_map:
            next_value_config = dict(value_config)
            next_value_config["dataSource"] = key_map[data_source]
            cloned["valueConfig"] = next_value_config

    return cloned


def _require_positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{path} must be a positive integer")
    return value


def _normalize_screen_view_sets(view_sets: Any) -> dict:
    if not isinstance(view_sets, dict):
        raise ValueError("view_sets must be an object")

    viewport = view_sets.get("viewport")
    if not isinstance(viewport, dict):
        raise ValueError("view_sets.viewport must be an object")

    items = view_sets.get("items")
    if not isinstance(items, list):
        raise ValueError("view_sets.items must be a list")

    decorations = view_sets.get("decorations")
    if not isinstance(decorations, dict):
        raise ValueError("view_sets.decorations must be an object")

    normalized_viewport = dict(viewport)
    normalized_viewport["width"] = _require_positive_int(
        viewport.get("width"),
        "view_sets.viewport.width",
    )
    normalized_viewport["height"] = _require_positive_int(
        viewport.get("height"),
        "view_sets.viewport.height",
    )
    normalized = {
        "viewport": normalized_viewport,
        "items": list(items),
        "decorations": dict(decorations),
    }
    if "filters" in view_sets:
        filters = view_sets.get("filters")
        normalized["filters"] = filters if isinstance(filters, list) else []

    return normalized


def normalize_canvas_view_sets_for_storage(view_sets: Any, object_type: ObjectType) -> list | dict:
    _validate_scene_widget_surfaces(view_sets, object_type)
    if object_type == ObjectType.DASHBOARD:
        base = view_sets if isinstance(view_sets, list) else []
        migrated, _ = migrate_canvas_view_sets(base)
        return migrated if isinstance(migrated, list) else []

    if object_type == ObjectType.TOPOLOGY:
        if not isinstance(view_sets, dict):
            return {"nodes": [], "edges": [], "filters": []}
        nodes = view_sets.get("nodes", [])
        edges = view_sets.get("edges", [])
        filters = view_sets.get("filters", [])
        base = {
            "nodes": nodes if isinstance(nodes, list) else [],
            "edges": edges if isinstance(edges, list) else [],
            "filters": filters if isinstance(filters, list) else [],
        }
        migrated, _ = migrate_canvas_view_sets(base)
        return migrated if isinstance(migrated, dict) else base

    if object_type == ObjectType.ARCHITECTURE:
        if not isinstance(view_sets, dict):
            return {"items": [], "views": []}
        items = view_sets.get("items", [])
        views = view_sets.get("views", [])
        return {
            "items": items if isinstance(items, list) else [],
            "views": views if isinstance(views, list) else [],
        }

    if object_type == ObjectType.SCREEN:
        normalized = _normalize_screen_view_sets(view_sets)
        migrated, _ = migrate_canvas_view_sets(normalized)
        return migrated if isinstance(migrated, dict) else normalized

    if object_type == ObjectType.REPORT:
        normalized = normalize_report_view_sets(view_sets)
        migrated, _ = migrate_canvas_view_sets(normalized)
        return migrated if isinstance(migrated, dict) else normalized

    return view_sets if isinstance(view_sets, (list, dict)) else []


def normalize_canvas_view_sets_for_yaml(view_sets: Any, object_type: ObjectType) -> list | dict:
    normalized = normalize_canvas_view_sets_for_storage(view_sets, object_type)

    if object_type == ObjectType.DASHBOARD:
        return normalized if isinstance(normalized, list) else []

    if isinstance(normalized, dict):
        return normalized

    return {}


def rewrite_canvas_view_sets_refs_for_yaml(view_sets: list | dict, object_type: ObjectType, ds_key_map: dict[int, str]) -> list | dict:
    if object_type == ObjectType.DASHBOARD:
        return _rewrite_datasource_refs(view_sets if isinstance(view_sets, list) else [], ds_key_map)

    if object_type == ObjectType.TOPOLOGY:
        return {
            "nodes": _rewrite_datasource_refs(view_sets.get("nodes", []), ds_key_map),
            "edges": _rewrite_datasource_refs(view_sets.get("edges", []), ds_key_map),
            "filters": view_sets.get("filters", []) if isinstance(view_sets.get("filters", []), list) else [],
        }

    if object_type == ObjectType.ARCHITECTURE:
        return {
            "items": _rewrite_datasource_refs(view_sets.get("items", []), ds_key_map),
            "views": _rewrite_datasource_refs(view_sets.get("views", []), ds_key_map),
        }

    if object_type == ObjectType.SCREEN:
        result = {
            "viewport": view_sets.get("viewport", {}) if isinstance(view_sets.get("viewport", {}), dict) else {},
            "items": _rewrite_datasource_refs(view_sets.get("items", []), ds_key_map),
            "decorations": view_sets.get("decorations", {}) if isinstance(view_sets.get("decorations", {}), dict) else {},
        }
        if isinstance(view_sets.get("filters"), list):
            result["filters"] = view_sets.get("filters", [])
        return result

    if object_type == ObjectType.REPORT:
        return {
            "schema_version": view_sets.get("schema_version", 1),
            "filters": view_sets.get("filters", []) if isinstance(view_sets.get("filters", []), list) else [],
            "sections": _rewrite_datasource_refs(view_sets.get("sections", []), ds_key_map),
        }

    return _rewrite_datasource_refs(view_sets, ds_key_map)


def rewrite_canvas_view_sets_refs_for_storage(view_sets: list | dict, object_type: ObjectType, datasource_key_to_id: dict[str, int]) -> list | dict:
    if object_type == ObjectType.REPORT:
        if not isinstance(view_sets, dict):
            return normalize_report_view_sets(view_sets)
        rewritten = {
            "schema_version": view_sets.get("schema_version", 1),
            "filters": view_sets.get("filters", []),
            "sections": _rewrite_datasource_refs(view_sets.get("sections", []), datasource_key_to_id),
        }
        return normalize_report_view_sets(rewritten)

    normalized = normalize_canvas_view_sets_for_storage(view_sets, object_type)

    if object_type == ObjectType.DASHBOARD:
        return _rewrite_datasource_refs(normalized, datasource_key_to_id)

    if object_type == ObjectType.TOPOLOGY:
        return {
            "nodes": _rewrite_datasource_refs(normalized.get("nodes", []), datasource_key_to_id),
            "edges": _rewrite_datasource_refs(normalized.get("edges", []), datasource_key_to_id),
            "filters": normalized.get("filters", []) if isinstance(normalized.get("filters", []), list) else [],
        }

    if object_type == ObjectType.ARCHITECTURE:
        return {
            "items": _rewrite_datasource_refs(normalized.get("items", []), datasource_key_to_id),
            "views": _rewrite_datasource_refs(normalized.get("views", []), datasource_key_to_id),
        }

    if object_type == ObjectType.SCREEN:
        result = {
            "viewport": normalized.get("viewport", {}) if isinstance(normalized.get("viewport", {}), dict) else {},
            "items": _rewrite_datasource_refs(normalized.get("items", []), datasource_key_to_id),
            "decorations": normalized.get("decorations", {}) if isinstance(normalized.get("decorations", {}), dict) else {},
        }
        if isinstance(normalized.get("filters"), list):
            result["filters"] = normalized.get("filters", [])
        return result

    return _rewrite_datasource_refs(normalized, datasource_key_to_id)
