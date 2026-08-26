from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError

from apps.operation_analysis.constants.import_export import ObjectType
from apps.operation_analysis.services.canvas_draft.constants import WIDGET_CHART_TYPES
from apps.operation_analysis.services.canvas_draft.errors import DraftValidationFailed
from apps.operation_analysis.services.import_export.view_sets import normalize_canvas_view_sets_for_storage
from apps.operation_analysis.services.network_topology.canvas_config import _validate_payload as validate_network_topology_view_sets


def _error(code: str, message: str, field: str | None = None) -> dict:
    item = {"code": code, "message": message}
    if field:
        item["field"] = field
    return item


def collect_datasource_refs(value: Any) -> list:
    refs: list = []
    if isinstance(value, list):
        for item in value:
            refs.extend(collect_datasource_refs(item))
        return refs
    if not isinstance(value, dict):
        return refs
    value_config = value.get("valueConfig")
    if isinstance(value_config, dict) and "dataSource" in value_config:
        refs.append(value_config["dataSource"])
    for nested in value.values():
        if nested is value_config:
            continue
        refs.extend(collect_datasource_refs(nested))
    return refs


def _require_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _widget_chart_type(item: dict) -> str | None:
    if isinstance(item.get("chartType"), str):
        return item["chartType"]
    value_config = item.get("valueConfig")
    if isinstance(value_config, dict) and isinstance(value_config.get("chartType"), str):
        return value_config["chartType"]
    return None


def _validate_widget_item(item: Any, *, id_field: str, errors: list[dict], path: str) -> str | None:
    if not isinstance(item, dict):
        errors.append(_error("invalid_component", "组件必须是对象", path))
        return None
    item_id = item.get(id_field) or item.get("id") or item.get("i")
    if item_id in (None, ""):
        errors.append(_error("missing_id", "组件缺少 id", path))
        return None
    chart_type = _widget_chart_type(item)
    if chart_type and chart_type not in WIDGET_CHART_TYPES:
        errors.append(_error("unknown_component_type", f"不支持的组件类型: {chart_type}", path))
    return str(item_id)


def _widget_filter_bindings(item: dict) -> dict | None:
    if isinstance(item.get("filterBindings"), dict):
        return item["filterBindings"]
    value_config = item.get("valueConfig")
    if isinstance(value_config, dict) and isinstance(value_config.get("filterBindings"), dict):
        return value_config["filterBindings"]
    return None


def _filter_definition_ids(filters: Any) -> set[str]:
    ids: set[str] = set()
    if not isinstance(filters, list):
        return ids
    for item in filters:
        if isinstance(item, dict) and item.get("id") not in (None, ""):
            ids.add(str(item["id"]))
    return ids


def _validate_filter_bindings(items: list, filter_ids: set[str], errors: list[dict], path_prefix: str) -> None:
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        bindings = _widget_filter_bindings(item)
        if not bindings:
            continue
        for filter_id, enabled in bindings.items():
            if enabled and str(filter_id) not in filter_ids:
                errors.append(_error("broken_filter_binding", "筛选绑定了不存在的筛选字段", f"{path_prefix}[{index}]"))


def _validate_dashboard(view_sets: Any, filters: Any = None) -> list[dict]:
    errors: list[dict] = []
    if not isinstance(view_sets, list):
        return [_error("invalid_view_sets", "view_sets 必须是列表")]
    for index, item in enumerate(view_sets):
        path = f"view_sets[{index}]"
        if not isinstance(item, dict):
            errors.append(_error("invalid_component", "组件必须是对象", path))
            continue
        _validate_widget_item(item, id_field="i", errors=errors, path=path)
        for coord in ("x", "y", "w", "h"):
            if not _require_number(item.get(coord)):
                errors.append(_error("invalid_layout", f"缺少布局字段 {coord}", path))
    _validate_filter_bindings(view_sets, _filter_definition_ids(filters), errors, "view_sets")
    return errors


def _validate_screen(view_sets: Any) -> list[dict]:
    errors: list[dict] = []
    try:
        normalized = normalize_canvas_view_sets_for_storage(view_sets, ObjectType.SCREEN)
    except ValueError as exc:
        return [_error("invalid_view_sets", str(exc))]
    items = normalized.get("items") or []
    for index, item in enumerate(items):
        path = f"view_sets.items[{index}]"
        _validate_widget_item(item, id_field="id", errors=errors, path=path)
        if not isinstance(item, dict):
            continue
        for coord in ("x", "y", "w", "h"):
            if not _require_number(item.get(coord)):
                errors.append(_error("invalid_layout", f"缺少布局字段 {coord}", path))
    _validate_filter_bindings(items, _filter_definition_ids(normalized.get("filters") or []), errors, "view_sets.items")
    return errors


def _validate_topology(view_sets: Any) -> list[dict]:
    errors: list[dict] = []
    if not isinstance(view_sets, dict):
        return [_error("invalid_view_sets", "view_sets 必须是对象")]
    nodes = view_sets.get("nodes") or []
    if not isinstance(nodes, list):
        return [_error("invalid_view_sets", "nodes 必须是列表")]
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not node.get("id"):
            errors.append(_error("missing_id", "节点缺少 id", f"view_sets.nodes[{index}]"))
    return errors


def _validate_architecture(view_sets: Any) -> list[dict]:
    errors: list[dict] = []
    if not isinstance(view_sets, dict):
        return [_error("invalid_view_sets", "view_sets 必须是对象")]
    items = view_sets.get("items") or []
    if not isinstance(items, list):
        return [_error("invalid_view_sets", "items 必须是列表")]
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not item.get("id"):
            errors.append(_error("missing_id", "节点缺少 id", f"view_sets.items[{index}]"))
    return errors


def _validate_report(view_sets: Any) -> list[dict]:
    if not isinstance(view_sets, dict):
        return [_error("invalid_view_sets", "view_sets 必须是对象")]
    sections = view_sets.get("sections")
    if sections is None:
        return []
    if not isinstance(sections, list):
        return [_error("invalid_view_sets", "sections 必须是列表")]
    return []


def _validate_network_topology(view_sets: Any) -> list[dict]:
    try:
        validate_network_topology_view_sets(view_sets or {})
    except DjangoValidationError as exc:
        messages = []
        if hasattr(exc, "message_dict"):
            for field, field_errors in exc.message_dict.items():
                messages.extend(f"{field}: {item}" for item in field_errors)
        else:
            messages.append(str(exc))
        return [_error("invalid_view_sets", "; ".join(messages) or "view_sets 非法")]
    return []


_VALIDATORS = {
    ObjectType.DASHBOARD: _validate_dashboard,
    ObjectType.SCREEN: _validate_screen,
    ObjectType.TOPOLOGY: _validate_topology,
    ObjectType.ARCHITECTURE: _validate_architecture,
    ObjectType.REPORT: _validate_report,
    ObjectType.NETWORK_TOPOLOGY: _validate_network_topology,
}


def validate_projectable(object_type: ObjectType, view_sets: Any, filters: Any = None) -> None:
    validator = _VALIDATORS[object_type]
    errors = validator(view_sets, filters) if object_type == ObjectType.DASHBOARD else validator(view_sets)
    if errors:
        raise DraftValidationFailed(errors)
