from types import SimpleNamespace
from typing import Any

import yaml
from pydantic import ValidationError as PydanticValidationError

from apps.operation_analysis.constants.canvas_refresh import CANVAS_REFRESH_OBJECT_TYPES, normalize_canvas_refresh_interval
from apps.operation_analysis.constants.import_export import SENSITIVE_PLACEHOLDER, ObjectType
from apps.operation_analysis.schemas.import_export_schema import (
    ArchitectureItem,
    DashboardItem,
    NetworkTopologyItem,
    ReportItem,
    ScreenItem,
    TopologyItem,
)
from apps.operation_analysis.services.canvas_draft.constants import PACKAGE_KEYS
from apps.operation_analysis.services.canvas_draft.errors import DraftValidationFailed
from apps.operation_analysis.services.canvas_draft.validation import collect_datasource_refs, validate_projectable
from apps.operation_analysis.services.import_export.export_service import ExportService
from apps.operation_analysis.services.import_export.view_sets import normalize_canvas_view_sets_for_storage, rewrite_canvas_view_sets_refs_for_storage

_ITEM_MODELS = {
    ObjectType.DASHBOARD: DashboardItem,
    ObjectType.TOPOLOGY: TopologyItem,
    ObjectType.ARCHITECTURE: ArchitectureItem,
    ObjectType.SCREEN: ScreenItem,
    ObjectType.REPORT: ReportItem,
    ObjectType.NETWORK_TOPOLOGY: NetworkTopologyItem,
}


def canvas_to_payload(canvas, object_type: ObjectType) -> dict:
    payload: dict[str, Any] = {
        "name": canvas.name,
        "desc": canvas.desc or "",
        "view_sets": canvas.view_sets if canvas.view_sets is not None else _empty_view_sets(object_type),
    }
    if object_type != ObjectType.NETWORK_TOPOLOGY:
        payload["other"] = getattr(canvas, "other", None) or {}
    if object_type == ObjectType.DASHBOARD:
        payload["filters"] = canvas.filters or []
    if object_type in CANVAS_REFRESH_OBJECT_TYPES:
        payload["refresh_interval"] = normalize_canvas_refresh_interval(getattr(canvas, "refresh_interval", 0))
    if object_type == ObjectType.NETWORK_TOPOLOGY:
        payload["base_url"] = canvas.base_url
    return payload


def _empty_view_sets(object_type: ObjectType):
    if object_type == ObjectType.DASHBOARD:
        return []
    if object_type == ObjectType.TOPOLOGY:
        return {"nodes": [], "edges": [], "filters": []}
    if object_type == ObjectType.ARCHITECTURE:
        return {"items": [], "views": []}
    if object_type == ObjectType.SCREEN:
        return {"viewport": {"width": 1920, "height": 1080}, "items": [], "decorations": {}}
    if object_type == ObjectType.REPORT:
        return {"time_range": None, "sections": []}
    return {"nodes": [], "links": []}


def encode_yaml(canvas, payload: dict, object_type: ObjectType, ds_key_map: dict[int, str], ns_key_map: dict[int, str]) -> str:
    stub = SimpleNamespace(
        name=payload.get("name") or canvas.name,
        desc=payload.get("desc") if payload.get("desc") is not None else (canvas.desc or ""),
        view_sets=payload.get("view_sets"),
        other=payload.get("other") or {},
        filters=payload.get("filters") or [],
        refresh_interval=payload.get("refresh_interval", getattr(canvas, "refresh_interval", 0)),
        base_url=payload.get("base_url") or getattr(canvas, "base_url", ""),
        token=SENSITIVE_PLACEHOLDER,
    )
    entry = ExportService.convert_canvas_to_yaml(stub, object_type, ds_key_map, ns_key_map)
    document = {"type": object_type.value, **entry}
    return yaml.safe_dump(document, allow_unicode=True, sort_keys=False)


def decode_yaml(
    yaml_content: str,
    *,
    canvas,
    object_type: ObjectType,
    datasource_key_to_id: dict[str, int],
) -> dict:
    try:
        document = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        raise DraftValidationFailed([{"code": "invalid_yaml", "message": f"YAML 无法解析: {exc}"}]) from exc

    if not isinstance(document, dict):
        raise DraftValidationFailed([{"code": "invalid_yaml", "message": "YAML 必须是单画布对象"}])

    extra = PACKAGE_KEYS.intersection(document)
    if extra:
        raise DraftValidationFailed([{"code": "package_document", "message": f"禁止携带整包字段: {', '.join(sorted(extra))}"}])

    doc_type = document.get("type")
    if doc_type != object_type.value:
        raise DraftValidationFailed([{"code": "type_mismatch", "message": f"type 必须为 {object_type.value}"}])

    item_data = {key: value for key, value in document.items() if key != "type"}
    item_data.setdefault("key", ExportService.generate_business_key(canvas, object_type))
    item_data.setdefault("name", canvas.name)
    if object_type == ObjectType.NETWORK_TOPOLOGY:
        item_data.setdefault("base_url", canvas.base_url)
        item_data.setdefault("token", SENSITIVE_PLACEHOLDER)

    try:
        item = _ITEM_MODELS[object_type](**item_data)
    except PydanticValidationError as exc:
        errors = [
            {"code": "invalid_slice", "message": err["msg"], "field": ".".join(str(part) for part in err.get("loc", ()))} for err in exc.errors()
        ]
        raise DraftValidationFailed(errors) from exc

    unresolved = [
        ref for ref in collect_datasource_refs(item.view_sets) if ref not in (None, "") and (ref not in datasource_key_to_id or _is_int_id(ref))
    ]
    if unresolved:
        raise DraftValidationFailed([{"code": "unresolved_datasource", "message": "业务键无法解析为当前可见数据源"}])

    view_sets = rewrite_canvas_view_sets_refs_for_storage(
        normalize_canvas_view_sets_for_storage(item.view_sets, object_type),
        object_type,
        datasource_key_to_id,
    )
    leftover = [ref for ref in collect_datasource_refs(view_sets) if ref not in (None, "") and not _is_int_id(ref)]
    if leftover:
        raise DraftValidationFailed([{"code": "unresolved_datasource", "message": "业务键无法解析为当前可见数据源"}])

    validate_projectable(object_type, view_sets, filters=getattr(item, "filters", None))

    payload = canvas_to_payload(canvas, object_type)
    payload["name"] = item.name
    payload["desc"] = item.desc or ""
    payload["view_sets"] = view_sets
    if object_type != ObjectType.NETWORK_TOPOLOGY:
        payload["other"] = item.other or {}
    if object_type == ObjectType.DASHBOARD:
        payload["filters"] = item.filters or []
    if object_type in CANVAS_REFRESH_OBJECT_TYPES:
        payload["refresh_interval"] = item.refresh_interval
    if object_type == ObjectType.NETWORK_TOPOLOGY:
        payload["base_url"] = item.base_url
    return payload


def _is_int_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
