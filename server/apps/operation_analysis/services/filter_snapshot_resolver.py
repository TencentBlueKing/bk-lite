"""Filter Snapshot 执行期解析（D1 / A4）。

在 Input Snapshot 创建时解析一次；语义对齐前端 resolveDateRange /
buildRelativeTimeRangeFilterValue。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.operation_analysis.services.filter_snapshot import (
    DATE_RANGE_TYPES,
    QUICK_DATE_RANGE_TYPES,
    VALUE_KIND_DYNAMIC_DATE_RANGE,
    VALUE_KIND_DYNAMIC_TIME_RANGE,
    VALUE_KIND_STATIC,
    FilterSnapshotError,
    load_filter_snapshot,
)


def _ensure_aware(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        return moment.replace(tzinfo=dt_timezone.utc)
    return moment


def _resolve_timezone(timezone_name: str | None) -> ZoneInfo:
    name = (timezone_name or "").strip() or "UTC"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise FilterSnapshotError(f"无效时区: {name}") from exc


def _format_iso(moment: datetime) -> str:
    aware = _ensure_aware(moment).astimezone(dt_timezone.utc)
    return aware.isoformat().replace("+00:00", "Z")


def resolve_date_range(
    range_type: str,
    *,
    reference_at: datetime,
    timezone_name: str | None,
) -> tuple[str, str]:
    """对齐前端 resolveDateRange；返回 (startDate, endDate) YYYY-MM-DD。"""
    if range_type not in QUICK_DATE_RANGE_TYPES:
        raise FilterSnapshotError(f"未知动态 dateRange 类型: {range_type}")

    tz = _resolve_timezone(timezone_name)
    local = _ensure_aware(reference_at).astimezone(tz)
    today = local.replace(hour=0, minute=0, second=0, microsecond=0)
    monday = today - timedelta(days=today.weekday())
    previous_month_anchor = today.replace(day=1) - timedelta(days=1)
    previous_month_start = previous_month_anchor.replace(day=1)

    ranges = {
        "today": (today, today),
        "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
        "this_week": (monday, today),
        "last_week": (
            monday - timedelta(days=7),
            monday - timedelta(days=1),
        ),
        "this_month": (today.replace(day=1), today),
        "last_month": (previous_month_start, previous_month_anchor),
        "last_7_days": (today - timedelta(days=6), today),
        "last_30_days": (today - timedelta(days=29), today),
        "last_90_days": (today - timedelta(days=89), today),
    }
    start, end = ranges[range_type]
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def resolve_time_range(
    minutes: int,
    *,
    reference_at: datetime,
) -> dict:
    if not isinstance(minutes, int) or minutes <= 0:
        raise FilterSnapshotError("dynamic timeRange 分钟数必须为正整数")
    end = _ensure_aware(reference_at)
    start = end - timedelta(minutes=minutes)
    # 写入具体起止，不保留 selectValue，避免渲染页按「现在」重算
    return {"start": _format_iso(start), "end": _format_iso(end)}


def _resolve_entry(
    entry: dict,
    *,
    reference_at: datetime,
    timezone_name: str | None,
) -> object:
    if not isinstance(entry, dict):
        raise FilterSnapshotError("filter_snapshot entry 无效")

    kind = entry.get("value_kind")
    if kind == VALUE_KIND_STATIC:
        if "value" not in entry:
            raise FilterSnapshotError("static entry 缺少 value")
        return deepcopy(entry["value"])

    if kind == VALUE_KIND_DYNAMIC_DATE_RANGE:
        range_type = entry.get("date_range_type")
        if range_type not in QUICK_DATE_RANGE_TYPES:
            raise FilterSnapshotError(
                f"未知动态 dateRange 类型: {range_type}"
            )
        start, end = resolve_date_range(
            range_type,
            reference_at=reference_at,
            timezone_name=timezone_name,
        )
        return {
            "rangeType": "custom",
            "startDate": start,
            "endDate": end,
        }

    if kind == VALUE_KIND_DYNAMIC_TIME_RANGE:
        minutes = entry.get("time_range_select_minutes")
        if not isinstance(minutes, int):
            raise FilterSnapshotError("dynamic timeRange 缺少分钟数")
        return resolve_time_range(minutes, reference_at=reference_at)

    raise FilterSnapshotError(f"未知 value_kind: {kind}")


def resolve_filter_snapshot(
    subscription_config: dict | None,
    *,
    reference_at: datetime,
    timezone_name: str | None,
) -> tuple[dict, dict]:
    """返回 (filter_semantics entries, filter_values 解析袋)。"""
    snapshot = load_filter_snapshot(subscription_config)
    entries = snapshot.get("entries")
    if not isinstance(entries, dict):
        raise FilterSnapshotError("filter_snapshot.entries 必须是对象")

    semantics = deepcopy(entries)
    values: dict = {}
    for filter_id, entry in entries.items():
        values[str(filter_id)] = _resolve_entry(
            entry,
            reference_at=reference_at,
            timezone_name=timezone_name,
        )
    return semantics, values


# 避免未使用导入告警（DATE_RANGE_TYPES 供测试/文档对齐）
assert DATE_RANGE_TYPES
