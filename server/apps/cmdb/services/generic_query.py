"""CMDB 通用查询：过滤、统计、排序和分页都在本模块完成。"""

from __future__ import annotations

import json
from typing import Any

from apps.cmdb.display_field.constants import DISPLAY_FIELD_TYPES, DISPLAY_SUFFIX, DISPLAY_VALUES_SEPARATOR
from apps.cmdb.graph.validators import CQLValidator
from apps.cmdb.services.generic_query_columns import public_instance, sensitive_hidden_keys
from apps.cmdb.services.generic_query_graph import GenericQueryGraphError, aggregate_numeric, count_by_attr
from apps.cmdb.services.generic_query_limits import DETAIL_PAGE_SIZE_MAX, NATS_MESSAGE_MAX_BYTES, SCAN_INSTANCE_MAX, STAT_GROUP_MAX
from apps.cmdb.services.instance import InstanceManage
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.condition_group import ConditionGroupError, parse_condition_group

MODEL_MODES = ("detail", "count", "distribution")
INSTANCE_MODES = ("detail", "count", "distribution", "aggregate")
ONE_HOP_MODES = ("detail", "count", "distribution")
_FILTER_TYPES = {
    ("string", "eq"): "str=",
    ("string", "ne"): "str<>",
    ("string", "contains"): "str*",
    ("string", "empty"): "empty",
    ("number", "eq"): "int=",
    ("number", "gt"): "int>",
    ("number", "gte"): "int>=",
    ("number", "lt"): "int<",
    ("number", "lte"): "int<=",
}
_ENUM_ATTR_TYPES = {"enum"}
_NUMBER_ATTR_TYPES = {"int", "integer", "float", "number", "long", "double"}


class GenericQueryError(Exception):
    def __init__(self, message: str, *, status: str = "failed"):
        super().__init__(message)
        self.message = message
        self.status = status


def _filled(value) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def _reject_unused(mode: str, checks: list[tuple[Any, str, tuple[str, ...]]]) -> None:
    """当前分析方式用不到、但请求里写了值的参数直接拒绝。空值视为没填。"""
    blocked = [label for value, label, allowed in checks if mode not in allowed and _filled(value)]
    if blocked:
        raise GenericQueryError("当前分析方式不支持" + "、".join(blocked))


def ensure_payload_limit(data: Any) -> None:
    encoded = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    if len(encoded) > NATS_MESSAGE_MAX_BYTES:
        raise GenericQueryError("结果超过 NATS 消息上限 1MB")


def query_models(
    *,
    models: list[dict],
    instance_counts: dict,
    analysis_mode: str,
    classification_id: str | None = None,
    model_ids: list[str] | None = None,
    page=None,
    page_size=None,
) -> dict:
    """模型查询。分类和模型只缩小范围，零实例模型保留。

    单值固定为范围内模型数量。分布先统计全部可见模型的实例数，
    按实例数从高到低、模型标识升序稳定排序。分布不接受页码。
    未传每页条数时返回全部；传入时只取排序后的前若干条。计数不接受非空分页。
    明细两个都空时返回全部模型，结果不带页码。只填页码或每页条数之一则失败。
    """
    mode = _mode(analysis_mode, MODEL_MODES)
    if mode == "distribution" and page not in (None, ""):
        raise GenericQueryError("当前分析方式不支持页码")
    if mode == "count" and (page not in (None, "") or page_size not in (None, "")):
        raise GenericQueryError("当前分析方式不支持分页")
    rows = [_model_row(item, instance_counts) for item in models]
    if classification_id:
        rows = [row for row in rows if row["classification_id"] == classification_id]
    if model_ids:
        selected = set(model_ids)
        found = {row["model_id"] for row in rows}
        missing = [item for item in model_ids if item not in found]
        if missing:
            raise GenericQueryError("指定模型不存在或无权访问", status="forbidden")
        rows = [row for row in rows if row["model_id"] in selected]
    scanned = sum(int(row["instance_count"]) for row in rows)
    if mode != "detail":
        _ensure_scan(scanned)
    if mode == "count":
        return _value_payload(len(rows), field="model_count")
    if mode == "distribution":
        # 分类和模型只缩小范围。每个可见模型一项，不再按分类把实例数加总。
        # 先完成全部统计和排序，再截取当前页。重名保留原始模型名称，身份看 model_id。
        items = _model_distribution_items(rows)
        _ensure_groups(len(items))
        items.sort(key=lambda item: (-int(item.get("instance_count") or 0), str(item.get("model_id") or "")))
        limit = _distribution_return_limit(page_size)
        page_items = items if limit is None else items[:limit]
        return {
            "items": page_items,
        }
    rows.sort(
        key=lambda item: (
            str(item.get("classification_name") or ""),
            str(item.get("model_name") or ""),
            str(item.get("model_id") or ""),
        )
    )
    public = [_public_model_detail(row) for row in rows]
    window = _model_page(page, page_size)
    if window is None:
        return {"items": public, "count": len(public)}
    page_no, size = window
    start = (page_no - 1) * size
    return {
        "items": public[start : start + size],
        "count": len(public),
        "page": page_no,
        "page_size": size,
    }


def query_instances(
    *,
    model_id: str,
    analysis_mode: str,
    attr_types: dict[str, str],
    permission_map: dict,
    filters=None,
    group_by: str | None = None,
    aggregate_field: str | None = None,
    aggregate_op: str | None = None,
    order_by: str | None = None,
    order_dir: str | None = None,
    page=None,
    page_size=None,
    group_labels: dict[str, str] | None = None,
) -> dict:
    if not str(model_id or "").strip():
        raise GenericQueryError("模型不能为空")
    mode = _mode(analysis_mode, INSTANCE_MODES)
    _reject_unused(
        mode,
        [
            (group_by, "分布属性", ("distribution",)),
            (aggregate_field, "聚合属性", ("aggregate",)),
            (aggregate_op, "聚合方式", ("aggregate",)),
            (order_by if str(order_by or "").strip() else order_dir, "排序", ("detail", "distribution")),
        ],
    )
    distribution_limit = _distribution_window(mode, page, page_size) if mode == "distribution" else None
    if mode in {"count", "aggregate"}:
        _parse_page(page, page_size, enabled=False)
    base_params = [{"field": "model_id", "type": "str=", "value": str(model_id)}]
    logic, condition_params = _attribute_filters(attr_types, filters)
    if mode == "detail":
        page_no, size = _parse_page(page, page_size, enabled=True)
        field, desc = _resolve_sort(
            order_by,
            order_dir,
            set(attr_types) | {"inst_name", "inst_uuid"},
            empty=("inst_uuid", False),
        )
        _validate_sort_field(field)
        order_text = f"-{field}" if desc else field
        items, count = InstanceManage.instance_list(
            model_id=str(model_id),
            params=[],
            page=page_no,
            page_size=size,
            order=order_text,
            permission_map=permission_map,
            condition_params=condition_params,
            condition_logic=logic,
        )
        hidden = sensitive_hidden_keys(attr_types)
        rows = [_present_display_fields(_public_instance(item, hidden), attr_types) for item in items or []]
        return _page_payload(rows, page_no, size, count=int(count or 0))

    if mode == "aggregate":
        if not aggregate_field or not aggregate_op:
            raise GenericQueryError("数值聚合必须指定聚合字段和聚合方式")
        attr_type = _attr_kind(attr_types, aggregate_field)
        if attr_type != "number":
            raise GenericQueryError("聚合字段不是数值属性")
        try:
            aggregated = aggregate_numeric(
                aggregate_field,
                aggregate_op,
                base_params,
                permission_map,
                condition_params=condition_params,
                condition_logic=logic,
            )
        except GenericQueryGraphError as exc:
            raise GenericQueryError(exc.message) from exc
        _ensure_scan(int(aggregated.get("scanned") or 0))
        if int(aggregated.get("scanned") or 0) == 0:
            return {
                "aggregate_value": None,
            }
        return _value_payload(aggregated.get("value"), field="aggregate_value")

    group_field = "" if mode == "count" else _group_field(attr_types, group_by)
    grouped_counts = count_by_attr(
        "model_id" if mode == "count" else group_field,
        base_params,
        permission_map,
        condition_params=condition_params,
        condition_logic=logic,
    )
    scanned = sum(int(value or 0) for value in grouped_counts.values())
    _ensure_scan(scanned)
    if mode == "count":
        return _value_payload(scanned, field="instance_count")
    items = _distribution_items(group_field, grouped_counts, group_labels)
    _ensure_groups(len(items))
    field, desc = _resolve_sort(
        order_by,
        order_dir,
        {group_field, "instance_count"},
        empty=("instance_count", True),
    )
    items.sort(key=lambda item: (item.get(field) is None, item.get(field)), reverse=desc)
    shown = _slice_distribution(items, distribution_limit)
    return _category_payload(shown)


def one_hop_query_plan(analysis_mode: str | None, page, page_size) -> dict:
    """定下图查询要取的那一块。明细按起点、终点名称翻页，分布按关联数取前几名。"""
    mode = _mode(analysis_mode, ONE_HOP_MODES)
    if mode == "count":
        _parse_page(page, page_size, enabled=False)
        return {"part": "count"}
    if mode == "distribution":
        return {"part": "distribution", "limit": _distribution_window(mode, page, page_size)}
    page_no, size = _parse_page(page, page_size, enabled=True)
    return {"part": "detail", "skip": (page_no - 1) * size, "limit": size}


def query_one_hop_relations(
    *,
    analysis_mode: str,
    graph_result: dict,
    page=None,
    page_size=None,
    association_name: str = "",
    association_id: str = "",
) -> dict:
    """一跳关联：计数是对应关系条数，分布是每个起点的关联数量。"""
    mode = _mode(analysis_mode, ONE_HOP_MODES)
    distribution_limit = _distribution_window(mode, page, page_size) if mode == "distribution" else None
    if mode == "count":
        _parse_page(page, page_size, enabled=False)
    graph_result = graph_result or {}
    pair_count = int(graph_result.get("pair_count") or 0)
    if mode == "count":
        return _value_payload(pair_count, field="relation_count")
    if mode == "distribution":
        items = [
            {
                "start_name": item.get("start_name") or "",
                "start_uuid": item.get("start_uuid") or "",
                "relation_count": int(item.get("relation_count", item.get("value")) or 0),
            }
            for item in graph_result.get("groups") or []
        ]
        total = int(graph_result["group_count"]) if "group_count" in graph_result else len(items)
        _ensure_groups(total)
        items.sort(key=lambda item: (-(item.get("relation_count") or 0), item.get("start_uuid") or ""))
        shown = items if "group_count" in graph_result else _slice_distribution(items, distribution_limit)
        return _category_payload(shown)
    relation_name = str(association_name or "")
    relation_id = str(association_id or "")
    rows = [
        {
            "start_uuid": item.get("start_uuid") or "",
            "start_name": item.get("start_name") or "",
            "end_uuid": item.get("end_uuid") or "",
            "end_name": item.get("end_name") or "",
            "asst_name": relation_name,
            "model_asst_id": relation_id,
        }
        for item in graph_result.get("pairs") or []
    ]
    if graph_result.get("paged"):
        return _page_payload(rows, page, page_size, count=pair_count)
    rows.sort(
        key=lambda item: (
            item.get("start_name") or "",
            item.get("end_name") or "",
            item.get("start_uuid") or "",
            item.get("end_uuid") or "",
        )
    )
    return _page_payload(rows, page, page_size)


def _enum_membership_values(value, *, split_commas: bool) -> list[str]:
    """枚举入库统一是 id 列表。等于、不等于、属于都按成员关系比较。"""
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if value in (None, ""):
        return []
    text = str(value)
    if split_commas:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [text]


def build_attribute_filter(attr_types: dict[str, str], field: str | None, op: str | None, value) -> dict | None:
    if field in (None, "") and op in (None, "") and value in (None, ""):
        return None
    if field in (None, "") or op in (None, ""):
        raise GenericQueryError("属性过滤必须同时给出字段和运算符")
    kind = _attr_kind(attr_types, field)
    if kind == "enum":
        if op not in {"eq", "ne", "in"}:
            raise GenericQueryError("属性过滤运算符不受支持")
        selected = _enum_membership_values(value, split_commas=op == "in")
        if not selected:
            raise GenericQueryError("属性过滤必须给出值")
        return {
            "field": field,
            "type": "list_none[]" if op == "ne" else "list_any[]",
            "value": selected,
        }
    mapped = _FILTER_TYPES.get((kind, op))
    if mapped is None:
        raise GenericQueryError("属性过滤运算符不受支持")
    if op == "empty":
        return {"field": field, "type": mapped}
    if value in (None, "") or (isinstance(value, list) and not value):
        raise GenericQueryError("属性过滤必须给出值")
    parsed = value
    if kind == "number":
        parsed = _as_number(value)
    if op == "in":
        if not isinstance(parsed, list):
            parsed = [part.strip() for part in str(value).split(",") if part.strip()]
        if not parsed:
            raise GenericQueryError("属性过滤必须给出值")
    return {"field": field, "type": mapped, "value": parsed}


def _attribute_filters(attr_types, filters) -> tuple[str, list]:
    try:
        logic, items = parse_condition_group(filters)
    except ConditionGroupError as exc:
        raise GenericQueryError(exc.message) from exc
    group = []
    for item in items:
        parsed = build_attribute_filter(attr_types, item.get("field"), item.get("op"), item.get("value"))
        if parsed:
            group.append(parsed)
    return logic, group


compile_attribute_conditions = _attribute_filters


def _model_row(model: dict, counts: dict) -> dict:
    model_id = str(model.get("model_id") or "")
    return {
        "model_id": model_id,
        "model_name": model.get("model_name") or model_id,
        "classification_id": str(model.get("classification_id") or ""),
        "classification_name": model.get("classification_name") or "",
        "instance_count": int(counts.get(model_id, 0) or 0),
    }


def _public_model_detail(row: dict) -> dict:
    """明细只返回模型定义上的四列。分布使用同一组业务键，不另造 name/value。"""
    return {
        "classification_name": row.get("classification_name") or "",
        "model_name": row.get("model_name") or "",
        "model_id": row.get("model_id") or "",
        "instance_count": int(row.get("instance_count") or 0),
    }


def _model_distribution_items(rows: list[dict]) -> list[dict]:
    return [_public_model_detail(row) for row in rows]


def _bucket_value(key):
    """分组键保留 0、false 和空串。只有缺失分组才是 None。"""
    if key is None:
        return None
    if isinstance(key, bool) or isinstance(key, (int, float)):
        return key
    return str(key)


def _distribution_items(group_field: str, grouped_counts: dict, group_labels: dict[str, str] | None) -> list[dict]:
    """枚举分布按选项名称出分类，同一名称的计数合并。其他类型保持原分组键。"""
    merged: dict[Any, int] = {}
    for key, value in grouped_counts.items():
        presented = _present_group_value(key, group_labels)
        merged[presented] = merged.get(presented, 0) + int(value or 0)
    return [{group_field: key, "instance_count": count} for key, count in merged.items()]


def _present_group_value(key, group_labels: dict[str, str] | None):
    if group_labels is None:
        return _bucket_value(key)
    if key is None:
        return None
    parts = _enum_id_parts(key)
    if parts is None:
        return group_labels.get(str(key), str(key))
    names = [group_labels.get(str(part), str(part)) for part in parts if part not in (None, "")]
    return DISPLAY_VALUES_SEPARATOR.join(names)


def _enum_id_parts(key):
    if isinstance(key, list):
        return key
    if isinstance(key, str) and key.startswith("["):
        try:
            parsed = json.loads(key)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, list):
            return parsed
    return None


def _validate_sort_field(field: str) -> None:
    try:
        CQLValidator.validate_field(field)
    except BaseAppException as exc:
        raise GenericQueryError(f"不支持的排序字段: {field}") from exc


def _group_field(attr_types: dict[str, str], group_by: str | None) -> str:
    if not group_by:
        raise GenericQueryError("属性分布必须指定分组字段")
    _attr_kind(attr_types, group_by)
    CQLValidator.validate_field(group_by)
    return group_by


def _attr_kind(attr_types: dict[str, str], field: str) -> str:
    if field not in attr_types:
        raise GenericQueryError(f"属性不存在或无权使用: {field}")
    raw = str(attr_types.get(field) or "string").lower()
    if raw in _ENUM_ATTR_TYPES:
        return "enum"
    if raw in _NUMBER_ATTR_TYPES:
        return "number"
    return "string"


def _mode(value: str | None, allowed: tuple[str, ...]) -> str:
    mode = str(value or "").strip()
    if not mode:
        raise GenericQueryError("分析方式不能为空")
    if mode not in allowed:
        raise GenericQueryError("分析方式不受支持")
    return mode


def _ensure_scan(scanned: int) -> None:
    if scanned > SCAN_INSTANCE_MAX:
        raise GenericQueryError(f"统计范围超过 {SCAN_INSTANCE_MAX} 个实例")


def _ensure_groups(count: int) -> None:
    if count > STAT_GROUP_MAX:
        raise GenericQueryError(f"统计分组超过 {STAT_GROUP_MAX} 组")


def _sort_request(order_by, order_dir) -> tuple[str, bool] | None:
    """两个都空表示没指定排序。只填一个直接报错，不补另一个。"""
    field = "" if order_by in (None, "") else str(order_by).strip()
    direction = "" if order_dir in (None, "") else str(order_dir).strip()
    if not field and not direction:
        return None
    if not field or not direction:
        raise GenericQueryError("排序和排序方式必须同时填写")
    if direction not in {"asc", "desc"}:
        raise GenericQueryError("排序方式不受支持")
    return field, direction == "desc"


def _resolve_sort(order_by, order_dir, allowed: set[str], *, empty: tuple[str, bool]) -> tuple[str, bool]:
    requested = _sort_request(order_by, order_dir)
    if requested is None:
        return empty
    field, descending = requested
    if field not in allowed:
        raise GenericQueryError(f"不支持的排序字段: {field}")
    return field, descending


def _distribution_window(mode: str, page, page_size) -> int | None:
    """分布不接受页码。返回条数空着表示全部，写了就取排序后的前几条。"""
    del mode
    if page not in (None, ""):
        raise GenericQueryError("当前分析方式不支持页码")
    return _distribution_return_limit(page_size)


def _slice_distribution(items: list, limit: int | None) -> list:
    return items if limit is None else items[:limit]


def _distribution_return_limit(page_size) -> int | None:
    """分布只看返回条数。页码不读。空条数表示全部，显式条数仍受每页上限约束。"""
    if page_size in (None, ""):
        return None
    size = _as_int(page_size, "page_size")
    if size < 1 or size > DETAIL_PAGE_SIZE_MAX:
        raise GenericQueryError(f"每页最多 {DETAIL_PAGE_SIZE_MAX} 条")
    return size


def _model_page(page, page_size) -> tuple[int, int] | None:
    """模型明细两个都空时返回全部。只填一个不补另一个。"""
    if page in (None, "") and page_size in (None, ""):
        return None
    return _parse_page(page, page_size, enabled=True)


def _parse_page(page, page_size, *, enabled: bool) -> tuple[int, int]:
    if not enabled:
        if page not in (None, "") or page_size not in (None, ""):
            raise GenericQueryError("当前分析方式不支持分页")
        return 1, DETAIL_PAGE_SIZE_MAX
    if page in (None, "") or page_size in (None, ""):
        raise GenericQueryError("页码和每页条数必须同时填写")
    page_no = _as_int(page, "page")
    size = _as_int(page_size, "page_size")
    if page_no < 1:
        raise GenericQueryError("page 必须大于 0")
    if size < 1 or size > DETAIL_PAGE_SIZE_MAX:
        raise GenericQueryError(f"每页最多 {DETAIL_PAGE_SIZE_MAX} 条")
    return page_no, size


def _page_payload(rows: list, page, page_size, *, count: int | None = None) -> dict:
    page_no, size = _parse_page(page, page_size, enabled=True)
    total = len(rows) if count is None else count
    if count is None:
        start = (page_no - 1) * size
        rows = rows[start : start + size]
    return {
        "items": rows,
        "count": total,
        "page": page_no,
        "page_size": size,
    }


def _value_payload(value, *, field: str) -> dict:
    return {
        field: value,
    }


def _category_payload(items: list[dict]) -> dict:
    return {
        "items": items,
    }


def _public_instance(row: dict, hidden: set[str] | None = None) -> dict:
    return public_instance(row, hidden)


def _present_display_fields(row: dict, attr_types: dict[str, str]) -> dict:
    """明细用属性上的展示名。没有展示名时保留原值，展示副本不再另返回。"""
    for attr_id, kind in (attr_types or {}).items():
        if str(kind or "").lower() not in DISPLAY_FIELD_TYPES:
            continue
        key = str(attr_id).strip()
        if not key:
            continue
        display_key = f"{key}{DISPLAY_SUFFIX}"
        display = row.get(display_key)
        if _has_display_text(display):
            row[key] = display
        row.pop(display_key, None)
    return row


def _has_display_text(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _as_int(value, name: str) -> int:
    try:
        if isinstance(value, bool):
            raise ValueError
        return int(value)
    except (TypeError, ValueError) as exc:
        raise GenericQueryError(f"{name} 必须是整数") from exc


def _as_number(value):
    try:
        if isinstance(value, bool):
            raise ValueError
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise GenericQueryError("筛选值必须是数值") from exc
    if number.is_integer():
        return int(number)
    return number
