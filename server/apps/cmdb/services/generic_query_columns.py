"""实例和一跳明细的表格列。

列来自模型属性元数据，不来自首行采样。统计协议字段不在这里生成。
密码属性及其展示副本不进入候选列，调用方还要从响应行里删掉。
"""

from __future__ import annotations

_SENSITIVE_ATTR_TYPES = frozenset({"pwd"})
_DISPLAY_ATTR_TYPES = frozenset({"organization", "user", "enum", "tag", "table"})
_SYSTEM_LINK_ATTR_IDS = frozenset({"node_id", "monitor_id"})
_NOT_DEFAULT_ATTR_IDS = frozenset({"inst_uuid", "model_id"})
_SIDE_SKIP = frozenset({"inst_uuid", "inst_name", "model_id"})
_ONE_HOP_IDENTITY = (
    ("start_name", "起点名称", True),
    ("end_name", "终点名称", True),
    ("start_uuid", "起点标识", False),
    ("end_uuid", "终点标识", False),
    ("start_model_id", "起点模型", False),
    ("end_model_id", "终点模型", False),
)


def sensitive_hidden_keys(attr_types: dict | None) -> set[str]:
    """按属性类型隐藏密码字段和它的展示副本，不按字段名猜测。"""
    hidden: set[str] = set()
    for attr_id, kind in (attr_types or {}).items():
        if str(kind or "").lower() not in _SENSITIVE_ATTR_TYPES:
            continue
        key = str(attr_id).strip()
        if not key:
            continue
        hidden.add(key)
        hidden.add(f"{key}_display")
    return hidden


def sensitive_hidden_keys_from_attrs(attrs: list | None) -> set[str]:
    types = {}
    for attr in attrs or []:
        if not isinstance(attr, dict):
            continue
        attr_id = str(attr.get("attr_id") or "").strip()
        if attr_id:
            types[attr_id] = attr.get("attr_type")
    return sensitive_hidden_keys(types)


def public_instance(row: dict, hidden: set[str] | None = None) -> dict:
    if not isinstance(row, dict):
        return {}
    blocked = hidden or set()
    return {str(key): value for key, value in row.items() if not str(key).startswith("_") and str(key) not in blocked}


def build_instance_column_fields(attrs: list | None, *, model_key: str) -> dict:
    fields: list[dict] = []
    for attr in attrs or []:
        field = _candidate_field(attr)
        if field:
            fields.append(field)
    keys = {field["key"] for field in fields}
    if "inst_name" in keys:
        index = next(i for i, field in enumerate(fields) if field["key"] == "inst_name")
        name = fields.pop(index)
        name["default_visible"] = True
        fields.insert(0, name)
    else:
        fields.insert(0, _plain_field("inst_name", "实例名称", default_visible=True))
    if "inst_uuid" not in {field["key"] for field in fields}:
        fields.append(_plain_field("inst_uuid", "实例标识", default_visible=False))
    for field in fields:
        if field["key"] == "inst_name":
            field["default_visible"] = True
        elif field["key"] in _NOT_DEFAULT_ATTR_IDS or field["key"] in _SYSTEM_LINK_ATTR_IDS:
            field["default_visible"] = False
    return {"source": "model_attrs", "model_key": str(model_key), "fields": fields}


def build_one_hop_column_fields(start_attrs: list | None, end_attrs: list | None, *, model_key: str) -> dict:
    start_business = [
        _prefixed(field, "start:", "起点·")
        for field in build_instance_column_fields(start_attrs, model_key="start")["fields"]
        if field["key"] not in _SIDE_SKIP
    ]
    end_business = [
        _prefixed(field, "end:", "终点·")
        for field in build_instance_column_fields(end_attrs, model_key="end")["fields"]
        if field["key"] not in _SIDE_SKIP
    ]
    fields = [
        _plain_field("start_name", "起点名称", default_visible=True),
        *start_business,
        _plain_field("end_name", "终点名称", default_visible=True),
        *end_business,
    ]
    present = {field["key"] for field in fields}
    for key, title, visible in _ONE_HOP_IDENTITY:
        if key in present:
            continue
        if key in {"start_name", "end_name"}:
            continue
        fields.append(_plain_field(key, title, default_visible=visible))
    return {"source": "model_attrs", "model_key": str(model_key), "fields": fields}


def project_one_hop_rows(
    rows: list | None,
    *,
    starts: list | None,
    ends: list | None,
    start_attrs: list | None,
    end_attrs: list | None,
) -> list[dict]:
    start_by_uuid = _index_by_uuid(starts)
    end_by_uuid = _index_by_uuid(ends)
    projected = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        merged = dict(row)
        start = start_by_uuid.get(str(row.get("start_uuid") or ""))
        end = end_by_uuid.get(str(row.get("end_uuid") or ""))
        merged.update(project_side_attributes(start, start_attrs, "start:"))
        merged.update(project_side_attributes(end, end_attrs, "end:"))
        projected.append(merged)
    return projected


def project_side_attributes(instance: dict | None, attrs: list | None, prefix: str) -> dict:
    hidden = sensitive_hidden_keys_from_attrs(attrs)
    public = public_instance(instance or {}, hidden)
    return {f"{prefix}{key}": value for key, value in public.items() if key not in _SIDE_SKIP}


def _index_by_uuid(rows: list | None) -> dict[str, dict]:
    indexed = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        uuid = str(row.get("inst_uuid") or "").strip()
        if uuid and uuid not in indexed:
            indexed[uuid] = row
    return indexed


def _candidate_field(attr: dict) -> dict | None:
    if not isinstance(attr, dict):
        return None
    attr_id = str(attr.get("attr_id") or "").strip()
    if not attr_id or attr_id.startswith("_") or attr.get("is_display_field"):
        return None
    attr_type = str(attr.get("attr_type") or "str")
    if attr_type.lower() in _SENSITIVE_ATTR_TYPES:
        return None
    field = _plain_field(attr_id, str(attr.get("attr_name") or attr_id), default_visible=True, attr_type=attr_type)
    if attr.get("is_system_link") or attr_id in _SYSTEM_LINK_ATTR_IDS or attr_id in _NOT_DEFAULT_ATTR_IDS:
        field["default_visible"] = False
    lowered = attr_type.lower()
    if lowered in _DISPLAY_ATTR_TYPES:
        field["display_key"] = f"{attr_id}_display"
    if lowered == "enum":
        field["options"] = _enum_options(attr)
    if lowered == "time":
        option = attr.get("option") if isinstance(attr.get("option"), dict) else {}
        field["display_format"] = "date" if option.get("display_format") == "date" else "datetime"
    return field


def _plain_field(key: str, title: str, *, default_visible: bool, attr_type: str = "str") -> dict:
    return {
        "key": key,
        "title": title,
        "attr_type": attr_type,
        "default_visible": default_visible,
    }


def _prefixed(field: dict, prefix: str, title_prefix: str) -> dict:
    copied = dict(field)
    copied["key"] = f"{prefix}{field['key']}"
    copied["title"] = f"{title_prefix}{field['title']}"
    if copied.get("display_key"):
        copied["display_key"] = f"{prefix}{copied['display_key']}"
    return copied


def _enum_options(attr: dict) -> list[dict]:
    from apps.cmdb.services.model import ModelManage

    options = []
    for option in ModelManage.resolve_runtime_enum_options(attr) or []:
        if not isinstance(option, dict):
            continue
        option_id = option.get("id")
        if option_id is None or option_id == "":
            continue
        label = option.get("name") or option.get("label") or option_id
        options.append({"value": str(option_id), "label": str(label)})
    return options
