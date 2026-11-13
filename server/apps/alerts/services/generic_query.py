"""告警中心通用查询。告警和事件分开统计，过滤与分组在数据库内完成。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce

from apps.alerts.constants.constants import AlertStatus, EventLevel, EventStatus
from apps.alerts.models.models import Event
from apps.alerts.services.generic_query_limits import DETAIL_PAGE_SIZE_MAX, NATS_MESSAGE_MAX_BYTES, RANGE_MAX_SECONDS, STAT_GROUP_MAX

LEVEL_LABELS = dict(EventLevel.CHOICES)
ALERT_LEVELS = set(LEVEL_LABELS)
ALERT_STATUS_LABELS = dict(AlertStatus.CHOICES)
EVENT_STATUS_LABELS = dict(EventStatus.CHOICES)

QUERY_OBJECTS = {"alert", "event"}
MODES = ("detail", "count", "distribution")
ALERT_TIME_FIELDS = {"created_at", "updated_at", "first_event_time", "last_event_time", "closed_at"}
EVENT_TIME_FIELDS = {"received_at", "start_time", "end_time"}
ALERT_GROUP_FIELDS = {"level", "status", "source_name"}
EVENT_GROUP_FIELDS = {"level", "status", "source_name"}
ALERT_STATUSES = {value for value, _label in AlertStatus.CHOICES}
EVENT_STATUSES = {value for value, _label in EventStatus.CHOICES}
ALERT_SORT_FIELDS = ALERT_TIME_FIELDS | {"level", "status", "alert_id"}
EVENT_SORT_FIELDS = EVENT_TIME_FIELDS | {"level", "status", "event_id"}


class GenericQueryError(Exception):
    def __init__(self, message: str, *, status: str = "failed"):
        super().__init__(message)
        self.message = message
        self.status = status


def ensure_payload_limit(data: Any) -> None:
    encoded = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    if len(encoded) > NATS_MESSAGE_MAX_BYTES:
        raise GenericQueryError("结果超过 NATS 消息上限 1MB")


def query_alert_center(
    queryset,
    *,
    query_object: str,
    analysis_mode: str,
    source: str | None = None,
    level: str | None = None,
    status: str | None = None,
    time_field: str | None = None,
    time_range=None,
    group_by: str | None = None,
    order_by: str | None = None,
    order_dir: str | None = None,
    page=None,
    page_size=None,
) -> dict:
    target = str(query_object or "").strip()
    if target not in QUERY_OBJECTS:
        raise GenericQueryError("查询对象必须是告警或事件")
    mode = str(analysis_mode or "").strip()
    if not mode:
        raise GenericQueryError("分析方式不能为空")
    if mode not in MODES:
        raise GenericQueryError("分析方式不受支持")
    _reject_unused(
        mode,
        [
            (group_by, "分组", ("distribution",)),
            (order_by if str(order_by or "").strip() else order_dir, "排序", ("detail", "distribution")),
        ],
    )
    distribution_limit = _distribution_window(page, page_size) if mode == "distribution" else None
    if mode == "count":
        _reject_paging(page, page_size)
    if time_range in (None, "", [], {}):
        raise GenericQueryError("时间范围不能为空")
    time_fields = ALERT_TIME_FIELDS if target == "alert" else EVENT_TIME_FIELDS
    if time_field not in time_fields:
        raise GenericQueryError("时间字段不受支持")
    start, end = _parse_range(time_range)
    if (end - start).total_seconds() > RANGE_MAX_SECONDS:
        raise GenericQueryError("告警中心时间范围最长 90 天")
    queryset = queryset.filter(**{f"{time_field}__gte": start, f"{time_field}__lt": end})
    if level not in (None, ""):
        if str(level) not in ALERT_LEVELS:
            raise GenericQueryError("级别不受支持")
        queryset = queryset.filter(level=level)
    if status not in (None, ""):
        allowed_status = ALERT_STATUSES if target == "alert" else EVENT_STATUSES
        if status not in allowed_status:
            raise GenericQueryError("状态不受支持")
        queryset = queryset.filter(status=status)
    if source not in (None, ""):
        if target == "event":
            queryset = queryset.filter(source__source_id=str(source))
        else:
            # 子查询收窄告警，避免事件连接把分组 Count 放大。
            matched = queryset.filter(events__source__source_id=str(source)).values("pk")
            queryset = queryset.filter(pk__in=Subquery(matched))
    if mode == "count":
        return _value(queryset.count())
    if mode == "distribution":
        group_fields = ALERT_GROUP_FIELDS if target == "alert" else EVENT_GROUP_FIELDS
        field = group_by or "level"
        if field not in group_fields:
            raise GenericQueryError("分组字段不受支持")
        grouped, value_key = _grouped_counts(queryset, target, field)
        if grouped.count() > STAT_GROUP_MAX:
            raise GenericQueryError(f"统计分组超过 {STAT_GROUP_MAX} 组")
        items = [{field: _choice_label(row[value_key], target, field), "record_count": row["record_count"]} for row in grouped]
        sort_key, descending = _distribution_order(order_by, order_dir, field)
        items.sort(key=lambda item: (item.get(sort_key) is None, item.get(sort_key)), reverse=descending)
        shown = _slice_distribution(items, distribution_limit)
        return {
            "items": shown,
        }
    page_no, size = _parse_page(page, page_size)
    sort_fields = ALERT_SORT_FIELDS if target == "alert" else EVENT_SORT_FIELDS
    order_text = _detail_order(order_by, order_dir, sort_fields)
    total = queryset.count()
    page_rows = list(queryset.order_by(order_text)[(page_no - 1) * size : page_no * size])
    source_names = _alert_display_source_names(page_rows) if target == "alert" else {}
    rows = [_row(item, target, source_names) for item in page_rows]
    return {
        "items": rows,
        "count": total,
        "page": page_no,
        "page_size": size,
    }


def _choice_label(value, target: str, field: str) -> str:
    text = "" if value is None else str(value)
    if field == "level":
        return LEVEL_LABELS.get(text, text)
    if field == "status":
        labels = ALERT_STATUS_LABELS if target == "alert" else EVENT_STATUS_LABELS
        return labels.get(text, text)
    return text


def _grouped_counts(queryset, target: str, field: str):
    """按来源分组时用告警源名称。告警取关联事件里名称最靠前的一个，一条告警只进一组。"""
    if field == "source_name" and target == "alert":
        first_name = Event.objects.filter(alert=OuterRef("pk")).order_by("source__name").values("source__name")[:1]
        grouped = (
            queryset.annotate(_source_label=Coalesce(Subquery(first_name), "source_name")).values("_source_label").annotate(record_count=Count("id"))
        )
        return grouped, "_source_label"
    if field == "source_name" and target == "event":
        grouped = (
            queryset.annotate(_source_label=Coalesce("source__name", "source__source_id")).values("_source_label").annotate(record_count=Count("id"))
        )
        return grouped, "_source_label"
    return queryset.values(field).annotate(record_count=Count("id")), field


def _alert_display_source_names(alerts) -> dict:
    pks = [item.pk for item in alerts]
    names = {}
    if not pks:
        return names
    rows = Event.objects.filter(alert__pk__in=pks).order_by("source__name").values_list("alert__pk", "source__name")
    for alert_pk, source_name in rows:
        label = str(source_name or "").strip()
        if label:
            names.setdefault(alert_pk, label)
    return names


def _row(item, target: str, source_names: dict | None = None) -> dict:
    if target == "event":
        source = getattr(item, "source", None)
        return {
            "event_id": item.event_id,
            "title": item.title,
            "level": _choice_label(item.level, target, "level"),
            "status": _choice_label(item.status, target, "status"),
            "source_id": getattr(source, "source_id", "") or "",
            "source_name": getattr(source, "name", "") or "",
            "resource_id": item.resource_id or "",
            "resource_name": item.resource_name or "",
            "monitor_id": item.monitor_id or "",
            "cmdb_id": item.cmdb_id or "",
            "received_at": _iso(item.received_at),
            "start_time": _iso(item.start_time),
            "end_time": _iso(item.end_time),
        }
    names = source_names or {}
    return {
        "alert_id": item.alert_id,
        "title": item.title,
        "level": _choice_label(item.level, target, "level"),
        "status": _choice_label(item.status, target, "status"),
        "source_name": names.get(item.pk) or item.source_name or "",
        "resource_id": item.resource_id or "",
        "resource_name": item.resource_name or "",
        "resource_type": item.resource_type or "",
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
        "first_event_time": _iso(item.first_event_time),
        "last_event_time": _iso(item.last_event_time),
        "closed_at": _iso(item.closed_at),
    }


def _value(value) -> dict:
    return {
        "record_count": value,
    }


def _filled(value) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def _reject_unused(mode: str, checks: list[tuple[Any, str, tuple[str, ...]]]) -> None:
    blocked = [label for value, label, allowed in checks if mode not in allowed and _filled(value)]
    if blocked:
        raise GenericQueryError("当前分析方式不支持" + "、".join(blocked))


def _distribution_window(page, page_size) -> int | None:
    if page not in (None, ""):
        raise GenericQueryError("当前分析方式不支持页码")
    if page_size in (None, ""):
        return None
    size = _as_int(page_size, "page_size")
    if size < 1 or size > DETAIL_PAGE_SIZE_MAX:
        raise GenericQueryError(f"每页最多 {DETAIL_PAGE_SIZE_MAX} 条")
    return size


def _slice_distribution(items: list, limit: int | None) -> list:
    return items if limit is None else items[:limit]


def _reject_paging(page, page_size) -> None:
    if page not in (None, "") or page_size not in (None, ""):
        raise GenericQueryError("当前分析方式不支持分页")


def _parse_page(page, page_size) -> tuple[int, int]:
    if page in (None, "") or page_size in (None, ""):
        raise GenericQueryError("页码和每页条数必须同时填写")
    page_no = _as_int(page, "page")
    size = _as_int(page_size, "page_size")
    if page_no < 1:
        raise GenericQueryError("page 必须大于 0")
    if size < 1 or size > DETAIL_PAGE_SIZE_MAX:
        raise GenericQueryError(f"每页最多 {DETAIL_PAGE_SIZE_MAX} 条")
    return page_no, size


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


def _distribution_order(order_by, order_dir, group_field: str) -> tuple[str, bool]:
    requested = _sort_request(order_by, order_dir)
    if requested is None:
        return "record_count", True
    field, descending = requested
    if field not in {group_field, "record_count"}:
        raise GenericQueryError(f"不支持的排序字段: {field}")
    return field, descending


def _detail_order(order_by, order_dir, allowed: set[str]) -> str:
    requested = _sort_request(order_by, order_dir)
    if requested is None:
        return "id"
    field, descending = requested
    if field not in allowed:
        raise GenericQueryError(f"不支持的排序字段: {field}")
    return f"-{field}" if descending else field


def _parse_range(value) -> tuple[datetime, datetime]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        start_raw, end_raw = value
    elif isinstance(value, dict) and value.get("start") and value.get("end"):
        start_raw, end_raw = value["start"], value["end"]
    else:
        raise GenericQueryError("时间范围格式错误")
    start = _parse_dt(start_raw)
    end = _parse_dt(end_raw)
    if start >= end:
        raise GenericQueryError("开始时间必须小于结束时间")
    return start, end


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise GenericQueryError("时间格式错误") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _as_int(value, name: str) -> int:
    try:
        if isinstance(value, bool):
            raise ValueError
        return int(value)
    except (TypeError, ValueError) as exc:
        raise GenericQueryError(f"{name} 必须是整数") from exc
