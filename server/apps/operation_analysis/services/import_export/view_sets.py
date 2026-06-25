from typing import Any

from apps.operation_analysis.constants.import_export import ObjectType


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


def _normalize_topology_presentation(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def normalize_canvas_view_sets_for_storage(view_sets: Any, object_type: ObjectType) -> list | dict:
    if object_type == ObjectType.DASHBOARD:
        return view_sets if isinstance(view_sets, list) else []

    if object_type == ObjectType.TOPOLOGY:
        if not isinstance(view_sets, dict):
            return {"nodes": [], "edges": [], "filters": [], "viewport": {}, "presentation": {}}
        nodes = view_sets.get("nodes", [])
        edges = view_sets.get("edges", [])
        filters = view_sets.get("filters", [])
        viewport = view_sets.get("viewport", {})
        presentation = view_sets.get("presentation", {})
        return {
            "nodes": nodes if isinstance(nodes, list) else [],
            "edges": edges if isinstance(edges, list) else [],
            "filters": filters if isinstance(filters, list) else [],
            "viewport": viewport if isinstance(viewport, dict) else {},
            "presentation": _normalize_topology_presentation(presentation),
        }

    if object_type == ObjectType.ARCHITECTURE:
        if not isinstance(view_sets, dict):
            return {"items": [], "views": []}
        items = view_sets.get("items", [])
        views = view_sets.get("views", [])
        return {
            "items": items if isinstance(items, list) else [],
            "views": views if isinstance(views, list) else [],
        }

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
            "viewport": view_sets.get("viewport", {}) if isinstance(view_sets.get("viewport", {}), dict) else {},
            "presentation": _normalize_topology_presentation(view_sets.get("presentation", {})),
        }

    if object_type == ObjectType.ARCHITECTURE:
        return {
            "items": _rewrite_datasource_refs(view_sets.get("items", []), ds_key_map),
            "views": _rewrite_datasource_refs(view_sets.get("views", []), ds_key_map),
        }

    return _rewrite_datasource_refs(view_sets, ds_key_map)


def rewrite_canvas_view_sets_refs_for_storage(view_sets: list | dict, object_type: ObjectType, datasource_key_to_id: dict[str, int]) -> list | dict:
    normalized = normalize_canvas_view_sets_for_storage(view_sets, object_type)

    if object_type == ObjectType.DASHBOARD:
        return _rewrite_datasource_refs(normalized, datasource_key_to_id)

    if object_type == ObjectType.TOPOLOGY:
        return {
            "nodes": _rewrite_datasource_refs(normalized.get("nodes", []), datasource_key_to_id),
            "edges": _rewrite_datasource_refs(normalized.get("edges", []), datasource_key_to_id),
            "filters": normalized.get("filters", []) if isinstance(normalized.get("filters", []), list) else [],
            "viewport": normalized.get("viewport", {}) if isinstance(normalized.get("viewport", {}), dict) else {},
            "presentation": _normalize_topology_presentation(normalized.get("presentation", {})),
        }

    if object_type == ObjectType.ARCHITECTURE:
        return {
            "items": _rewrite_datasource_refs(normalized.get("items", []), datasource_key_to_id),
            "views": _rewrite_datasource_refs(normalized.get("views", []), datasource_key_to_id),
        }

    return _rewrite_datasource_refs(normalized, datasource_key_to_id)
