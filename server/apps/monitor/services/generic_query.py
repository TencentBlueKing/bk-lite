"""监控通用查询。过滤、统计、排序和分页在监控模块内完成。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from django.db.models import Case, CharField, Count, IntegerField, Max, OuterRef, Subquery, Value, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, NullIf

from apps.core.utils.loader import LanguageLoader
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.models.monitor_object import MonitorInstance
from apps.monitor.services.authorized_metric_query import _instance_lookup_candidates
from apps.monitor.services.generic_query_limits import (
    ALERT_RANGE_MAX_SECONDS,
    DETAIL_PAGE_SIZE_MAX,
    METRIC_INSTANCE_MAX,
    METRIC_POINTS_MAX,
    METRIC_SERIES_MAX,
    NATS_MESSAGE_MAX_BYTES,
    STAT_GROUP_MAX,
)
from apps.monitor.services.metrics import Metrics
from apps.monitor.services.range_step import query_range_point_count
from apps.monitor.utils.alert_name_variables import ASSET_IP_FACT, resolve_resource_ip
from apps.monitor.utils.dimension import parse_instance_id

INSTANCE_MODES = ("detail",)
_INSTANCE_STATUS_LABEL = {True: "启用", False: "停用"}
_AGGREGATION_LABELS = {
    "avg": "平均",
    "sum": "求和",
    "max": "最大",
    "min": "最小",
    "count": "计数",
}
ALERT_MODES = ("detail", "count", "distribution")
ALERT_LEVELS = {"warning", "error", "critical", "no_data"}
ALERT_STATUSES = {"new", "closed", "recovered"}
ALERT_TYPES = {"alert", "no_data"}
_ALERT_CHOICE_LABELS = {
    "level": {
        "warning": "警告",
        "error": "错误",
        "critical": "严重",
        "no_data": "无数据",
    },
    "status": {
        "new": "未恢复",
        "recovered": "已恢复",
        "closed": "已关闭",
    },
    "alert_type": {
        "alert": "阈值告警",
        "no_data": "无数据告警",
    },
}
ALERT_TIME_FIELDS = {"start_event_time", "end_event_time", "created_at"}
ALERT_GROUP_FIELDS = {"level", "status", "alert_type", "monitor_instance_id", "monitor_object_id"}
_SEVERITY_RANK = {"critical": 4, "error": 3, "warning": 2, "no_data": 1}
_ORPHAN_OBJECT_LABEL = "策略已删除"
ALERT_SORT_FIELDS = {
    "start_event_time",
    "end_event_time",
    "created_at",
    "level",
    "status",
    "monitor_instance_name",
}


class GenericQueryError(Exception):
    def __init__(self, message: str, *, status: str = "failed"):
        super().__init__(message)
        self.message = message
        self.status = status


def ensure_payload_limit(data: Any) -> None:
    encoded = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    if len(encoded) > NATS_MESSAGE_MAX_BYTES:
        raise GenericQueryError("结果超过 NATS 消息上限 1MB")


def query_instances(
    queryset,
    *,
    analysis_mode: str,
    status: str | None = None,
    instance_ids=None,
    group_by: str | None = None,
    order_by: str | None = None,
    order_dir: str | None = None,
    page=None,
    page_size=None,
    locale: str | None = None,
) -> dict:
    _mode(analysis_mode, INSTANCE_MODES)
    if _filled(group_by):
        raise GenericQueryError("当前查询不支持分组")
    queryset = _filter_instances(queryset, status, instance_ids)
    page_no, size = _parse_page(page, page_size)
    queryset = _order_instances(queryset, _instance_order(order_by, order_dir))
    total = queryset.count()
    page_rows = list(queryset[(page_no - 1) * size : page_no * size])
    object_label = _monitor_object_label(queryset, locale)
    rows = [_instance_row(item, _cloud_region_names(page_rows), object_label) for item in page_rows]
    return _table(rows, total, page_no, size)


def validate_metric_request(*, instance_ids, time_range, step) -> dict:
    ids = _id_list(instance_ids)
    if not ids:
        raise GenericQueryError("实例范围不能为空")
    if len(ids) > METRIC_INSTANCE_MAX:
        raise GenericQueryError(f"指标查询实例超过 {METRIC_INSTANCE_MAX} 个")
    if step in (None, ""):
        raise GenericQueryError("步长不能为空")
    try:
        step_seconds = Metrics.parse_step_to_seconds(step)
    except ValueError as exc:
        raise GenericQueryError("步长格式错误") from exc
    if step_seconds < 1:
        raise GenericQueryError("步长最短 1 秒")
    start, end = _parse_range(time_range)
    points = query_range_point_count((end - start).total_seconds(), int(step_seconds))
    if points > METRIC_POINTS_MAX:
        raise GenericQueryError(f"单条序列超过 {METRIC_POINTS_MAX} 个点（点数包含起止两端），请缩短时间范围或加大步长")
    return {
        "instance_ids": ids,
        "start": start,
        "end": end,
        "step": str(step),
        "points": points,
    }


def _metric_number(raw):
    if raw in (None, "NaN", "nan", ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _dimension_text(labels: dict) -> str:
    skipped = {"instance_id", "bk_inst_id", "__name__"}
    parts = []
    for key, value in labels.items():
        if key in skipped or value in (None, ""):
            continue
        parts.append(f"{key}={value}")
    return ", ".join(parts)


def _aggregation_label(aggregation: str) -> str:
    key = str(aggregation or "").strip().lower()
    if key in _AGGREGATION_LABELS:
        return _AGGREGATION_LABELS[key]
    if not key:
        return "平均"
    return str(aggregation)


def metric_instance_labels(storage_ids) -> dict[str, str]:
    """表格里的实例标识用名称。主键和 VictoriaMetrics 上的单维标签都指向同一个名称。"""
    ids = []
    for item in storage_ids or []:
        text = str(item).strip()
        if text and text not in ids:
            ids.append(text)
    if not ids:
        return {}
    labels = {}
    for instance_id, name in MonitorInstance.objects.filter(id__in=ids).values_list("id", "name"):
        stored = str(instance_id)
        label = str(name or "").strip() or stored
        labels[stored] = label
        values = parse_instance_id(stored)
        if len(values) == 1 and values[0] not in (None, ""):
            logical = str(values[0])
            labels.setdefault(logical, label)
    return labels


def _instance_label(instance_id: str, names: dict[str, str]) -> str:
    if not instance_id:
        return instance_id
    return names.get(instance_id) or instance_id


def _table_row(instance_id: str, value, moment: str, unit: str, aggregation: str) -> dict:
    return {
        "instance_id": instance_id,
        "value": value,
        **({"time": moment} if moment else {}),
        "unit": unit,
        "aggregation": _aggregation_label(aggregation),
    }


def _identity_candidates(value: str) -> set[str]:
    return set(_instance_lookup_candidates(value))


def _series_identity_candidates(labels: dict, identity_keys: list[str]) -> set[str]:
    """返回序列按实例标识键拼回存储身份。单维标签和元组主键算同一台。"""
    keys = [str(key).strip() for key in identity_keys or [] if str(key).strip()]
    if keys:
        values = []
        complete = True
        for key in keys:
            raw = labels.get(key)
            if raw in (None, ""):
                complete = False
                break
            values.append(str(raw))
        if complete and values:
            if len(values) == 1:
                return _identity_candidates(values[0])
            return _identity_candidates(str(tuple(values)))
    instance_id = str(labels.get("instance_id") or labels.get("bk_inst_id") or "")
    if not instance_id:
        return set()
    return _identity_candidates(instance_id)


def _matched_requested_ids(series_candidates: set[str], requested_ids: list[str], requested_candidates: dict[str, set[str]]) -> list[str]:
    return [requested for requested in requested_ids if series_candidates & requested_candidates[requested]]


def _per_instance_rows(
    parsed,
    *,
    mode: str,
    unit: str,
    aggregation: str,
    requested_ids: list[str],
    requested_candidates: dict[str, set[str]],
    instance_names: dict[str, str],
) -> list[dict]:
    rows = []
    seen = set()
    for series in parsed:
        matched = _matched_requested_ids(series["candidates"], requested_ids, requested_candidates)
        seen.update(matched)
        label_id = matched[0] if matched else series["instance_id"]
        points = series["points"]
        numbers = [point["value"] for point in points if point["value"] is not None]
        if mode == "latest":
            last = next((point for point in reversed(points) if point["value"] is not None), None)
            value = None if last is None else last["value"]
            moment = "" if last is None else last["time"]
        else:
            value = None if not numbers else _reduce(numbers, aggregation)
            moment = ""
        rows.append(_table_row(_instance_label(label_id, instance_names), value, moment, unit, aggregation))
    for instance_id in requested_ids:
        if instance_id in seen:
            continue
        rows.append(_table_row(_instance_label(instance_id, instance_names), None, "", unit, aggregation))
    return rows


def build_metric_result(
    *,
    mode: str,
    response: dict,
    unit: str,
    aggregation: str,
    requested_ids: list[str],
    instance_names: dict[str, str] | None = None,
    identity_keys: list[str] | None = None,
) -> dict:
    if not isinstance(response, dict) or response.get("status") != "success":
        message = ""
        if isinstance(response, dict):
            message = str(response.get("error") or response.get("message") or "")
        raise GenericQueryError(message or "指标查询失败")
    result = ((response.get("data") or {}).get("result")) or []
    if len(result) > METRIC_SERIES_MAX:
        raise GenericQueryError(f"返回序列超过 {METRIC_SERIES_MAX} 条")
    series_payload = {}
    parsed = []
    requested_candidates = {item: _identity_candidates(str(item)) for item in requested_ids}
    for index, series in enumerate(result):
        values = series.get("values") or []
        if len(values) > METRIC_POINTS_MAX:
            raise GenericQueryError(f"单条序列超过 {METRIC_POINTS_MAX} 个点（点数包含起止两端），请缩短时间范围或加大步长")
        labels = series.get("metric") or {}
        instance_id = str(labels.get("instance_id") or labels.get("bk_inst_id") or "")
        candidates = _series_identity_candidates(labels, identity_keys or [])
        dimension = _dimension_text(labels)
        if instance_id and dimension:
            name = f"{instance_id} {dimension}"
        else:
            name = instance_id or f"series-{index + 1}"
        points = []
        for sample in values:
            if not isinstance(sample, (list, tuple)) or len(sample) < 2:
                continue
            numeric = _metric_number(sample[1])
            points.append(
                {
                    "time": _epoch_name(sample[0]),
                    "value": numeric,
                    "instance_id": instance_id,
                    "unit": unit,
                    "aggregation": aggregation,
                }
            )
        series_payload[name] = points
        parsed.append({"instance_id": instance_id, "candidates": candidates, "points": points})
    if mode in {"value", "latest"}:
        rows = _per_instance_rows(
            parsed,
            mode=mode,
            unit=unit,
            aggregation=aggregation,
            requested_ids=requested_ids,
            requested_candidates=requested_candidates,
            instance_names=instance_names or {},
        )
        return {
            "items": rows,
            "count": len(rows),
        }
    has_value = any(point.get("value") is not None for points in series_payload.values() for point in points)
    if not has_value:
        return {}
    return {name: [[point["time"], point["value"]] for point in points] for name, points in series_payload.items()}


def query_alerts(
    queryset,
    *,
    analysis_mode: str,
    level=None,
    status=None,
    alert_type=None,
    instance_ids=None,
    time_field: str | None = None,
    time_range=None,
    group_by: str | None = None,
    order_by: str | None = None,
    order_dir: str | None = None,
    page=None,
    page_size=None,
    locale: str | None = None,
) -> dict:
    mode = _mode(analysis_mode, ALERT_MODES)
    _reject_unused(
        mode,
        [
            (group_by, "分组", ("distribution",)),
            (order_by if str(order_by or "").strip() else order_dir, "排序", ("detail", "distribution")),
        ],
    )
    if mode == "count":
        _reject_paging(page, page_size)
    distribution_limit = None
    if mode == "distribution":
        if not _filled(group_by):
            raise GenericQueryError("分布必须选择分组")
        if group_by not in ALERT_GROUP_FIELDS:
            raise GenericQueryError("分组字段不受支持")
        if page not in (None, ""):
            raise GenericQueryError("当前分析方式不支持页码")
        distribution_limit = _distribution_return_limit(page_size)
    queryset = _filter_alerts(queryset, level, status, alert_type, instance_ids, time_field, time_range)
    if mode == "count":
        return _value(queryset.count(), field="alert_count")
    if mode == "distribution":
        return _alert_distribution(queryset, group_by, order_by, order_dir, distribution_limit, locale)
    page_no, size = _parse_page(page, page_size)
    order_field = _alert_detail_order(order_by, order_dir)
    total = queryset.count()
    page_rows = list(_order_alerts(queryset, order_field)[(page_no - 1) * size : page_no * size])
    annotated = list(_annotate_monitor_object(queryset.filter(pk__in=[item.pk for item in page_rows])))
    by_id = {item.pk: item for item in annotated}
    ordered = [by_id[item.pk] for item in page_rows if item.pk in by_id]
    labels = _object_labels([getattr(item, "_monitor_object_id", None) for item in ordered], locale)
    rows = [_alert_row(item, labels) for item in ordered]
    return _table(rows, total, page_no, size)


def _filter_instances(queryset, status, instance_ids):
    ids = _id_list(instance_ids) if instance_ids not in (None, "", []) else []
    if ids:
        found = {str(item) for item in queryset.filter(id__in=ids).values_list("id", flat=True)}
        missing = [item for item in ids if item not in found]
        if missing:
            raise GenericQueryError("实例不存在、已删除或无权访问: " + ", ".join(missing))
        queryset = queryset.filter(id__in=ids)
    if status in ("active", "inactive"):
        queryset = queryset.filter(is_active=(status == "active"))
    elif status not in (None, "", "all"):
        raise GenericQueryError("实例状态不受支持")
    return queryset


def _order_instances(queryset, order_field: str):
    if order_field.lstrip("-") != "ip":
        if order_field.lstrip("-") == "id":
            return queryset.order_by(order_field)
        return queryset.order_by(order_field, "id")
    asset_ip = KeyTextTransform(ASSET_IP_FACT, "summary_facts")
    access_ip = Cast("ip", output_field=CharField())
    display_ip = Coalesce(NullIf(asset_ip, Value("")), access_ip, Value(""), output_field=CharField())
    descending = order_field.startswith("-")
    return queryset.annotate(display_ip=display_ip).order_by("-display_ip" if descending else "display_ip", "id")


def _cloud_region_names(instances) -> dict:
    ids = {item.cloud_region_id for item in instances if item.cloud_region_id not in (None, "")}
    if not ids:
        return {}
    from apps.node_mgmt.models.cloud_region import CloudRegion

    return {row.id: row.name for row in CloudRegion.objects.filter(id__in=ids)}


def _choice_list(value, allowed: set[str], label: str) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, (list, tuple)):
        items = [str(part).strip() for part in value if str(part).strip()]
    else:
        raise GenericQueryError(f"{label}格式错误")
    unknown = [item for item in items if item not in allowed]
    if unknown:
        raise GenericQueryError(f"{label}不受支持")
    chosen = []
    for item in items:
        if item not in chosen:
            chosen.append(item)
    return chosen


def _filter_alerts(queryset, level, status, alert_type, instance_ids, time_field, time_range):
    levels = _choice_list(level, ALERT_LEVELS, "级别")
    statuses = _choice_list(status, ALERT_STATUSES, "状态")
    types = _choice_list(alert_type, ALERT_TYPES, "告警类型")
    if levels:
        queryset = queryset.filter(level__in=levels)
    if statuses:
        queryset = queryset.filter(status__in=statuses)
    if types:
        queryset = queryset.filter(alert_type__in=types)
    ids = _id_list(instance_ids)
    if ids:
        queryset = queryset.filter(monitor_instance_id__in=ids)
    if time_range in (None, "", [], {}):
        if time_field not in (None, ""):
            raise GenericQueryError("时间范围不能为空")
        return queryset
    if time_field not in ALERT_TIME_FIELDS:
        raise GenericQueryError("时间字段不受支持")
    start, end = _parse_range(time_range)
    if (end - start).total_seconds() > ALERT_RANGE_MAX_SECONDS:
        raise GenericQueryError("监控告警时间范围最长 90 天")
    return queryset.filter(**{f"{time_field}__gte": start, f"{time_field}__lt": end})


def _annotate_monitor_object(queryset):
    from apps.monitor.models.monitor_policy import MonitorPolicy

    object_id = MonitorPolicy.objects.filter(pk=OuterRef("policy_id")).values("monitor_object_id")[:1]
    return queryset.annotate(_monitor_object_id=Subquery(object_id))


def _severity_rank(value) -> int:
    return _SEVERITY_RANK.get(str(value or ""), 0)


def _order_alerts(queryset, order_text: str):
    descending = order_text.startswith("-")
    field = order_text[1:] if descending else order_text
    if field == "level":
        whens = [When(level=level, then=Value(rank)) for level, rank in _SEVERITY_RANK.items()]
        rank = Case(*whens, default=Value(0), output_field=IntegerField())
        direction = "-_severity_rank" if descending else "_severity_rank"
        return queryset.annotate(_severity_rank=rank).order_by(direction, "id")
    prefix = "-" if descending else ""
    return queryset.order_by(f"{prefix}{field}", "id")


def _object_labels(object_ids, locale: str | None) -> dict[str, str]:
    from apps.monitor.models.monitor_object import MonitorObject

    ids = []
    for item in object_ids:
        if item in (None, ""):
            continue
        text = str(item)
        if text not in ids:
            ids.append(text)
    if not ids:
        return {}
    loader = LanguageLoader(app=LanguageConstants.APP, default_lang=locale or "en")
    labels = {}
    for obj in MonitorObject.objects.filter(id__in=ids).only("id", "name", "display_name"):
        translated = loader.get(f"{LanguageConstants.MONITOR_OBJECT}.{obj.name}")
        if isinstance(translated, str) and translated.strip():
            labels[str(obj.id)] = translated.strip()
            continue
        stored = (obj.display_name or "").strip()
        labels[str(obj.id)] = stored or obj.name
    return labels


def _present_object(object_id, labels: dict[str, str]) -> tuple[str, str]:
    if object_id in (None, ""):
        return "", _ORPHAN_OBJECT_LABEL
    identity = str(object_id)
    return identity, labels.get(identity) or identity


def _alert_distribution(queryset, group_by: str, order_by, order_dir, limit: int | None, locale: str | None) -> dict:
    if group_by == "monitor_object_id":
        grouped = _annotate_monitor_object(queryset).values("_monitor_object_id").annotate(alert_count=Count("id"))
    elif group_by == "monitor_instance_id":
        grouped = queryset.values("monitor_instance_id").annotate(
            alert_count=Count("id"),
            monitor_instance_name=Max("monitor_instance_name"),
        )
    else:
        grouped = queryset.values(group_by).annotate(alert_count=Count("id"))
    _ensure_groups(grouped.count())
    rows = list(grouped)
    labels = {}
    if group_by == "monitor_object_id":
        labels = _object_labels([row["_monitor_object_id"] for row in rows], locale)
    items = [_distribution_item(group_by, row, labels) for row in rows]
    sort_key, descending = _alert_distribution_order(order_by, order_dir, group_by)
    items.sort(key=lambda item: _distribution_sort_key(item, sort_key), reverse=descending)
    shown = items if limit is None else items[:limit]
    _label_alert_groups(shown, group_by)
    return {
        "items": shown,
    }


def _distribution_item(group_by: str, row: dict, labels: dict[str, str]) -> dict:
    count = row["alert_count"]
    if group_by == "monitor_object_id":
        identity, name = _present_object(row.get("_monitor_object_id"), labels)
        return {"monitor_object_id": identity, "monitor_object_name": name, "alert_count": count}
    if group_by == "monitor_instance_id":
        identity = str(row.get("monitor_instance_id") or "")
        name = str(row.get("monitor_instance_name") or "").strip() or identity
        return {"monitor_instance_id": identity, "monitor_instance_name": name, "alert_count": count}
    return {group_by: row.get(group_by), "alert_count": count}


def _distribution_sort_key(item: dict, field: str):
    if field == "alert_count":
        return (item.get("alert_count") is None, item.get("alert_count") or 0)
    if field == "level":
        return (_severity_rank(item.get("level")), str(item.get("level") or ""))
    if field == "monitor_instance_id":
        return (str(item.get("monitor_instance_name") or ""), str(item.get("monitor_instance_id") or ""))
    if field == "monitor_object_id":
        return (str(item.get("monitor_object_name") or ""), str(item.get("monitor_object_id") or ""))
    return (item.get(field) is None, item.get(field))


def _monitor_object_label(queryset, locale: str | None) -> str:
    """与监控对象列表相同：语言包，否则库里的展示名，否则英文名。"""
    object_id = queryset.order_by().values_list("monitor_object_id", flat=True).first()
    if not object_id:
        return ""
    from apps.monitor.models.monitor_object import MonitorObject

    obj = MonitorObject.objects.filter(id=object_id).only("name", "display_name").first()
    if obj is None:
        return ""
    translated = LanguageLoader(app=LanguageConstants.APP, default_lang=locale or "en").get(f"{LanguageConstants.MONITOR_OBJECT}.{obj.name}")
    if isinstance(translated, str) and translated.strip():
        return translated.strip()
    stored = (obj.display_name or "").strip()
    return stored or obj.name


def _instance_row(instance, region_names: dict | None = None, object_label: str = "") -> dict:
    region_id = instance.cloud_region_id
    region_name = ""
    if region_id not in (None, ""):
        region_name = (region_names or {}).get(region_id) or str(region_id)
    return {
        "instance_id": instance.id,
        "name": instance.name,
        "ip": resolve_resource_ip(instance.summary_facts, instance.ip),
        "cloud_region": region_name,
        "cmdb_id": instance.cmdb_id or "",
        "monitor_object_id": object_label,
        "status": _INSTANCE_STATUS_LABEL[bool(instance.is_active)],
    }


def _alert_row(alert, object_labels: dict[str, str]) -> dict:
    identity, name = _present_object(getattr(alert, "_monitor_object_id", None), object_labels)
    return {
        "content": alert.content or "",
        "monitor_instance_name": alert.monitor_instance_name,
        "monitor_object_name": name,
        "monitor_instance_id": alert.monitor_instance_id,
        "id": alert.id,
        "monitor_object_id": identity,
        "level": _label_alert_choice("level", alert.level),
        "status": _label_alert_choice("status", alert.status),
        "alert_type": _label_alert_choice("alert_type", alert.alert_type),
        "value": alert.value,
        "start_event_time": _iso(alert.start_event_time),
        "end_event_time": _iso(alert.end_event_time),
        "created_at": _iso(alert.created_at),
    }


def _label_alert_choice(field: str, value) -> str:
    text = "" if value is None else str(value)
    return _ALERT_CHOICE_LABELS.get(field, {}).get(text, text)


def _label_alert_groups(items: list[dict], group_by: str) -> None:
    if group_by not in _ALERT_CHOICE_LABELS:
        return
    for item in items:
        item[group_by] = _label_alert_choice(group_by, item.get(group_by))


def _value(value, *, field: str) -> dict:
    return {field: value}


def _table(rows, total, page, page_size) -> dict:
    return {
        "items": rows,
        "count": total,
        "page": page,
        "page_size": page_size,
    }


def _reduce(numbers: list[float], aggregation: str):
    op = str(aggregation or "avg").lower()
    if op == "sum":
        return sum(numbers)
    if op == "min":
        return min(numbers)
    if op == "max":
        return max(numbers)
    if op in {"avg", "average"}:
        return sum(numbers) / len(numbers)
    if op == "count":
        return float(len(numbers))
    raise GenericQueryError("聚合方式不受支持")


def _mode(value, allowed) -> str:
    mode = str(value or "").strip()
    if not mode:
        raise GenericQueryError("分析方式不能为空")
    if mode not in allowed:
        raise GenericQueryError("分析方式不受支持")
    return mode


def _ensure_groups(count: int) -> None:
    if count > STAT_GROUP_MAX:
        raise GenericQueryError(f"统计分组超过 {STAT_GROUP_MAX} 组")


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


def _distribution_return_limit(page_size) -> int | None:
    """分布只看返回条数。页码不读。空条数表示全部，显式条数仍受每页上限约束。"""
    if page_size in (None, ""):
        return None
    size = _as_int(page_size, "page_size")
    if size < 1 or size > DETAIL_PAGE_SIZE_MAX:
        raise GenericQueryError(f"每页最多 {DETAIL_PAGE_SIZE_MAX} 条")
    return size


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


def _checked_sort(order_by, order_dir, allowed: set[str]) -> tuple[str, bool] | None:
    requested = _sort_request(order_by, order_dir)
    if requested is None:
        return None
    field, descending = requested
    if field not in allowed:
        raise GenericQueryError(f"不支持的排序字段: {field}")
    return field, descending


def _instance_order(order_by, order_dir) -> str:
    requested = _checked_sort(order_by, order_dir, {"name", "ip", "id"})
    if requested is None:
        return "id"
    field, descending = requested
    return f"-{field}" if descending else field


def _alert_detail_order(order_by, order_dir) -> str:
    requested = _checked_sort(order_by, order_dir, ALERT_SORT_FIELDS)
    if requested is None:
        return "id"
    field, descending = requested
    return f"-{field}" if descending else field


def _alert_distribution_order(order_by, order_dir, group_by: str) -> tuple[str, bool]:
    requested = _checked_sort(order_by, order_dir, {group_by, "alert_count"})
    if requested is None:
        return "alert_count", True
    return requested


def _id_list(value) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    raise GenericQueryError("实例范围格式错误")


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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
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


def _epoch_name(value) -> str:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(value)


def _as_int(value, name: str) -> int:
    try:
        if isinstance(value, bool):
            raise ValueError
        return int(value)
    except (TypeError, ValueError) as exc:
        raise GenericQueryError(f"{name} 必须是整数") from exc
