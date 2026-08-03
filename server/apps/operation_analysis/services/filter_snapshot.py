"""Filter Snapshot 规范化（D1 / A4）。

将前端 appliedFilterValues 分类为 filter_snapshot 语义结构。
归属 Subscription Service；不进入 Orchestrator。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone as dt_timezone
from typing import Any

from rest_framework.exceptions import ValidationError

FILTER_SNAPSHOT_VERSION = 1

VALUE_KIND_STATIC = "static"
VALUE_KIND_DYNAMIC_DATE_RANGE = "dynamic_date_range"
VALUE_KIND_DYNAMIC_TIME_RANGE = "dynamic_time_range"

DATE_RANGE_TYPES = frozenset(
    {
        "today",
        "yesterday",
        "this_week",
        "last_week",
        "this_month",
        "last_month",
        "last_7_days",
        "last_30_days",
        "last_90_days",
        "custom",
    }
)
QUICK_DATE_RANGE_TYPES = DATE_RANGE_TYPES - {"custom"}

DATE_PATTERN = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")


class FilterSnapshotError(ValueError):
    """规范化或解析失败；执行期映射为 filter_invalid。"""


def _is_strict_date(value: Any) -> bool:
    if not isinstance(value, str) or not DATE_PATTERN.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _definitions_by_id(dashboard_filters: Any) -> dict[str, dict]:
    if dashboard_filters is None:
        return {}
    if not isinstance(dashboard_filters, list):
        raise ValidationError(
            {"applied_filter_values": "仪表盘筛选定义格式无效"}
        )
    result: dict[str, dict] = {}
    for item in dashboard_filters:
        if not isinstance(item, dict):
            continue
        filter_id = item.get("id")
        if filter_id is None:
            continue
        result[str(filter_id)] = item
    return result


def _classify_filter_value(value: Any) -> dict:
    if value is None or isinstance(value, (str, int, float)):
        if isinstance(value, bool):
            raise FilterSnapshotError("筛选值类型不支持 boolean")
        return {"value_kind": VALUE_KIND_STATIC, "value": value}

    if not isinstance(value, dict):
        raise FilterSnapshotError("筛选值必须是标量、对象或 null")

    if "rangeType" in value:
        range_type = value.get("rangeType")
        if range_type not in DATE_RANGE_TYPES:
            raise FilterSnapshotError(f"未知 dateRange 类型: {range_type}")
        if range_type == "custom":
            start = value.get("startDate")
            end = value.get("endDate")
            if not _is_strict_date(start) or not _is_strict_date(end):
                raise FilterSnapshotError(
                    "custom dateRange 需要合法 YYYY-MM-DD"
                )
            if start > end:
                raise FilterSnapshotError(
                    "custom dateRange startDate 不能晚于 endDate"
                )
            extra_keys = set(value) - {"rangeType", "startDate", "endDate"}
            if extra_keys:
                raise FilterSnapshotError(
                    "custom dateRange 含非法字段"
                )
            return {
                "value_kind": VALUE_KIND_STATIC,
                "value": {
                    "rangeType": "custom",
                    "startDate": start,
                    "endDate": end,
                },
            }
        extra_keys = set(value) - {"rangeType"}
        if extra_keys:
            raise FilterSnapshotError("快捷 dateRange 不得含自定义字段")
        return {
            "value_kind": VALUE_KIND_DYNAMIC_DATE_RANGE,
            "date_range_type": range_type,
        }

    if "start" in value or "end" in value or "selectValue" in value:
        select_value = value.get("selectValue")
        if (
            isinstance(select_value, (int, float))
            and not isinstance(select_value, bool)
            and select_value > 0
        ):
            minutes = int(select_value)
            return {
                "value_kind": VALUE_KIND_DYNAMIC_TIME_RANGE,
                "time_range_select_minutes": minutes,
            }
        start = value.get("start")
        end = value.get("end")
        if not isinstance(start, str) or not isinstance(end, str):
            raise FilterSnapshotError("自定义 timeRange 需要 ISO start/end")
        if not start or not end:
            raise FilterSnapshotError("自定义 timeRange start/end 不能为空")
        return {
            "value_kind": VALUE_KIND_STATIC,
            "value": {"start": start, "end": end},
        }

    raise FilterSnapshotError("无法识别的筛选值结构")


def normalize_applied_filter_values(
    applied: Any,
    dashboard_filters: Any = None,
    *,
    captured_at: datetime | None = None,
) -> dict:
    """将 appliedFilterValues 规范化为 config.filter_snapshot。"""
    if applied is None:
        applied = {}
    if not isinstance(applied, dict):
        raise ValidationError(
            {"applied_filter_values": "已应用筛选必须是对象"}
        )

    definitions = _definitions_by_id(dashboard_filters)
    entries: dict[str, dict] = {}
    for raw_id, raw_value in applied.items():
        filter_id = str(raw_id)
        if definitions and filter_id not in definitions:
            raise ValidationError(
                {
                    "applied_filter_values": (
                        f"筛选定义不存在: {filter_id}"
                    )
                }
            )
        try:
            entries[filter_id] = _classify_filter_value(raw_value)
        except FilterSnapshotError as exc:
            raise ValidationError(
                {"applied_filter_values": str(exc)}
            ) from exc

        if definitions:
            expected_type = definitions[filter_id].get("type")
            kind = entries[filter_id]["value_kind"]
            static_value = entries[filter_id].get("value")
            if expected_type == "dateRange":
                is_custom_static = (
                    kind == VALUE_KIND_STATIC
                    and isinstance(static_value, dict)
                    and static_value.get("rangeType") == "custom"
                )
                if kind != VALUE_KIND_DYNAMIC_DATE_RANGE and not is_custom_static:
                    if not (
                        kind == VALUE_KIND_STATIC and static_value is None
                    ):
                        raise ValidationError(
                            {
                                "applied_filter_values": (
                                    f"筛选 {filter_id} 类型与 dateRange 定义不匹配"
                                )
                            }
                        )
            elif expected_type == "timeRange":
                is_custom_static = (
                    kind == VALUE_KIND_STATIC
                    and isinstance(static_value, dict)
                    and "start" in static_value
                    and "end" in static_value
                )
                if (
                    kind != VALUE_KIND_DYNAMIC_TIME_RANGE
                    and not is_custom_static
                    and not (
                        kind == VALUE_KIND_STATIC and static_value is None
                    )
                ):
                    raise ValidationError(
                        {
                            "applied_filter_values": (
                                f"筛选 {filter_id} 类型与 timeRange 定义不匹配"
                            )
                        }
                    )
            elif expected_type == "string":
                if kind != VALUE_KIND_STATIC or isinstance(static_value, dict):
                    raise ValidationError(
                        {
                            "applied_filter_values": (
                                f"筛选 {filter_id} 类型与 string 定义不匹配"
                            )
                        }
                    )

    moment = captured_at or datetime.now(dt_timezone.utc)
    return {
        "version": FILTER_SNAPSHOT_VERSION,
        "captured_at": moment.isoformat().replace("+00:00", "Z"),
        "entries": entries,
    }


def load_filter_snapshot(subscription_config: dict | None) -> dict:
    """读取 filter_snapshot；旧 filter_values 视为已解析静态袋。"""
    config = subscription_config or {}
    snap = config.get("filter_snapshot")
    if isinstance(snap, dict) and isinstance(snap.get("entries"), dict):
        return deepcopy(snap)

    legacy = config.get("filter_values")
    if isinstance(legacy, dict):
        return {
            "version": FILTER_SNAPSHOT_VERSION,
            "captured_at": None,
            "entries": {
                str(fid): {
                    "value_kind": VALUE_KIND_STATIC,
                    "value": deepcopy(value),
                }
                for fid, value in legacy.items()
            },
        }

    if "filter_values" in config and not isinstance(legacy, dict):
        raise FilterSnapshotError("filter_values 必须是对象")

    return {
        "version": FILTER_SNAPSHOT_VERSION,
        "captured_at": None,
        "entries": {},
    }
