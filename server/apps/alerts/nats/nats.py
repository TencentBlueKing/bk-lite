# -- coding: utf-8 --
# @File: nats.py
# @Time: 2025/7/22 15:30
# @Author: windyzhao
"""
告警对外的nats的接口
"""

import datetime
import os
from types import SimpleNamespace
from typing import Any, Dict
from zoneinfo import ZoneInfo

from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour, TruncMinute, TruncMonth, TruncWeek
from django.utils import timezone

import nats_client
from apps.alerts.common.source_adapter.base import AlertSourceAdapterFactory
from apps.alerts.constants.constants import PERMISSION_ALERT, AlertsSourceTypes, AlertStatus, EventLevel, LevelType
from apps.alerts.models.alert_operator import NotifyResult
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event, Incident, Level
from apps.alerts.utils.permission_scope import apply_team_scope_with_group_ids
from apps.core.logger import alert_logger as logger
from apps.core.utils.permission_utils import get_permission_rules
from apps.core.utils.viewset_utils import GenericViewSetFun

ALERT_LEVEL_DISPLAY_MAP = dict(EventLevel.CHOICES)
TRUSTED_INTERNAL_PUSHERS = {"lite-monitor", "lite-log"}

# 各粒度允许的最大时间跨度（秒）；可通过环境变量调整（保守默认值）
_MAX_SPAN_SECONDS = {
    "minute": int(os.getenv("ALERT_TREND_MAX_SPAN_MINUTE", str(7 * 24 * 3600))),  # 7 天 → 10,080 点
    "hour": int(os.getenv("ALERT_TREND_MAX_SPAN_HOUR", str(90 * 24 * 3600))),  # 90 天 → 2,160 点
    "day": int(os.getenv("ALERT_TREND_MAX_SPAN_DAY", str(730 * 24 * 3600))),  # 2 年 → 730 点
    "week": int(os.getenv("ALERT_TREND_MAX_SPAN_WEEK", str(730 * 24 * 3600))),  # 2 年 → ~104 点
    "month": int(os.getenv("ALERT_TREND_MAX_SPAN_MONTH", str(730 * 24 * 3600))),  # 2 年 → 24 点
}
_MAX_SPAN_LABEL = {
    "minute": "7 天",
    "hour": "90 天",
    "day": "2 年",
    "week": "2 年",
    "month": "2 年",
}


def _get_alert_level_display_map():
    level_map = {str(lv.level_id): lv.level_display_name for lv in Level.objects.filter(level_type=LevelType.ALERT)}
    level_map.update({key: value for key, value in ALERT_LEVEL_DISPLAY_MAP.items() if key not in level_map})
    return level_map


def _has_alerts_view_permission(user_info: dict) -> bool:
    if (user_info or {}).get("is_superuser"):
        return True

    permission_data = (user_info or {}).get("permission", {})
    if isinstance(permission_data, dict):
        app_permissions = permission_data.get("alarm", [])
    elif isinstance(permission_data, (set, list, tuple)):
        app_permissions = permission_data
    else:
        app_permissions = []
    return "Alarms-View" in set(app_permissions)


def _build_permission_user(user_info: dict):
    user = (user_info or {}).get("user")
    if hasattr(user, "username") and hasattr(user, "domain"):
        return user
    domain = (user_info or {}).get("domain")
    if not isinstance(user, str) or not user.strip() or not isinstance(domain, str) or not domain.strip():
        return None
    return SimpleNamespace(username=user.strip(), domain=domain.strip())


def _get_authorized_alert_queryset(user_info: dict):
    user_info = user_info or {}
    current_team = user_info.get("team")
    if not current_team:
        return None, {"result": False, "data": [], "message": "缺少组织信息"}

    if not _has_alerts_view_permission(user_info):
        return None, {"result": False, "data": [], "message": "Insufficient permissions"}

    team_ids = [int(current_team)]
    if user_info.get("include_children"):
        group_tree = user_info.get("group_tree", [])
        child_group_ids = GenericViewSetFun.extract_child_group_ids(group_tree, int(current_team))
        if child_group_ids:
            team_ids = child_group_ids

    if user_info.get("is_superuser"):
        return apply_team_scope_with_group_ids(Alert.objects.all(), team_ids), None

    permission_user = _build_permission_user(user_info)
    if not permission_user:
        return None, {"result": False, "data": [], "message": "缺少用户信息"}

    permission_data = get_permission_rules(
        permission_user,
        int(current_team),
        "alerts",
        PERMISSION_ALERT,
        user_info.get("include_children", False),
    )
    instance_ids = [item["id"] for item in permission_data.get("instance", []) if isinstance(item, dict) and item.get("id") is not None]
    permission_team_ids = permission_data.get("team", [])

    if not instance_ids and not permission_team_ids:
        return Alert.objects.none(), None

    normalized_permission_team_ids = []
    for team_id in permission_team_ids:
        try:
            normalized_permission_team_ids.append(int(team_id))
        except (TypeError, ValueError):
            logger.warning("Invalid alert permission team id: %s", team_id)

    authorized_queryset = apply_team_scope_with_group_ids(
        Alert.objects.all(), normalized_permission_team_ids
    )
    if instance_ids:
        authorized_queryset = Alert.objects.filter(
            Q(id__in=authorized_queryset.values("id")) | Q(id__in=instance_ids)
        )
    return authorized_queryset.distinct(), None


def _get_authorized_alert_notify_queryset(user_info: dict):
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return None, error

    alert_ids = queryset.values_list("alert_id", flat=True)
    return NotifyResult.objects.filter(notify_type="alert", notify_object__in=alert_ids), None


def group_dy_date_format(group_by):
    if group_by == "minute":
        trunc_func = TruncMinute
        date_format = "%Y-%m-%d %H:%M"
    elif group_by == "hour":
        trunc_func = TruncHour
        date_format = "%Y-%m-%d %H:00"
    elif group_by == "day":
        trunc_func = TruncDate
        date_format = "%Y-%m-%d"
    elif group_by == "week":
        trunc_func = TruncWeek
        date_format = "%Y-%m-%d"
    elif group_by == "month":
        trunc_func = TruncMonth
        date_format = "%Y-%m-%d"
    else:
        trunc_func = TruncDate
        date_format = "%Y-%m-%d"

    return trunc_func, date_format


def _resolve_target_timezone(timezone_name=None):
    if isinstance(timezone_name, str) and timezone_name:
        try:
            return ZoneInfo(timezone_name)
        except Exception:
            logger.warning("Invalid timezone provided for alert trend: %s", timezone_name)
    return timezone.get_current_timezone()


def _parse_client_datetime(value, target_tz):
    text = str(value).strip()
    try:
        parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")

    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, target_tz)
    return parsed.astimezone(target_tz)


def _format_period_value(value, target_tz):
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        value = datetime.datetime.combine(value, datetime.time.min, tzinfo=target_tz)
    elif timezone.is_naive(value):
        value = timezone.make_aware(value, target_tz)
    else:
        value = value.astimezone(target_tz)

    return value.isoformat()


def _generate_time_periods(group_by, start_dt, end_dt):
    """生成完整的时间序列周期列表"""
    all_periods = []
    if group_by == "minute":
        current = start_dt.replace(second=0, microsecond=0)
        while current < end_dt:
            all_periods.append(current)
            current += datetime.timedelta(minutes=1)
    elif group_by == "hour":
        current = start_dt.replace(minute=0, second=0, microsecond=0)
        while current < end_dt:
            all_periods.append(current)
            current += datetime.timedelta(hours=1)
    elif group_by == "day":
        num_periods = (end_dt.date() - start_dt.date()).days + 1
        all_periods = [start_dt.date() + datetime.timedelta(days=i) for i in range(num_periods)]
    elif group_by == "week":
        current = start_dt
        while current < end_dt:
            week_start = current - datetime.timedelta(days=current.weekday())
            all_periods.append(week_start.date())
            current += datetime.timedelta(weeks=1)
    elif group_by == "month":
        current = start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while current < end_dt:
            all_periods.append(current.date())
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
    return all_periods


def _build_period_series(queryset, time_field, trunc_func, target_tz, aware_start, aware_end, all_periods, extra_filter=None):
    """对给定queryset按时间分组统计，返回 [[period_str, count], ...] 的时间序列"""
    time_conditions = Q(**{f"{time_field}__gte": aware_start, f"{time_field}__lt": aware_end})
    if extra_filter:
        time_conditions &= extra_filter

    qs = (
        queryset.filter(time_conditions)
        .annotate(period=trunc_func(time_field, tzinfo=target_tz))
        .values("period")
        .annotate(count=Count("id"))
        .order_by("period")
    )

    period_counts = {}
    for item in qs:
        if item["period"]:
            period_key = _format_period_value(item["period"], target_tz)
            period_counts[period_key] = item["count"]

    result = []
    for period in all_periods:
        period_str = _format_period_value(period, target_tz)
        result.append([period_str, period_counts.get(period_str, 0)])
    return result


@nats_client.register
def get_alert_trend_data(*args, **kwargs) -> Dict[str, Any]:
    """
    获取告警趋势数据 获取指定时间内，告警的数据
    例如：获取7天内，每天的告警数量
    根据group_by参数分组统计告警数据

    :param group_by: 分组方式，支持 "minute", "hour", "day", "week", "month"

    return:
        {
            "result": True,
            "data": {
                "alert_count": [["2025-02-02T00:00:00+08:00", 5], ...],
                "event_count": [["2025-02-02T00:00:00+08:00", 12], ...],
                "recovered_count": [["2025-02-02T00:00:00+08:00", 3], ...]
            }
        }
    """
    logger.info("[AlertNatsRPC] === get_alert_trend_data ===, args=%s, kwargs=%s", args, kwargs)
    user_info = kwargs.pop("user_info", {})
    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.pop("timezone", None))
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error

    time = kwargs.pop("time", [])
    if not time:
        return {
            "result": False,
            "data": [],
            "message": "start_time and end_time are required.",
        }
    start_time, end_time = time
    aware_start = _parse_client_datetime(start_time, target_tz)
    aware_end = _parse_client_datetime(end_time, target_tz)
    start_dt = aware_start.astimezone(target_tz)
    end_dt = aware_end.astimezone(target_tz)

    group_by = kwargs.pop("group_by", "day")
    trunc_func, _ = group_dy_date_format(group_by)

    # 时间跨度上界校验，防止大跨度 minute/hour 请求撑爆 Worker 内存
    span_seconds = (aware_end - aware_start).total_seconds()
    max_span = _MAX_SPAN_SECONDS.get(group_by, _MAX_SPAN_SECONDS["day"])
    if span_seconds > max_span:
        label = _MAX_SPAN_LABEL.get(group_by, "2 年")
        logger.warning(
            "[AlertNatsRPC] get_alert_trend_data 时间跨度 %.0f 秒超过 %s 粒度上限 %d 秒，已拒绝",
            span_seconds,
            group_by,
            max_span,
        )
        return {
            "result": False,
            "data": [],
            "message": f"时间跨度超过 {group_by} 粒度的最大限制（{label}），请缩短查询范围或改用更粗粒度。",
        }

    # 构建告警过滤条件
    alert_filter = Q()
    alert_model_fields = set(Alert.model_fields())
    for key, value in kwargs.items():
        if key not in alert_model_fields:
            logger.warning("[AlertNatsRPC] 过滤条件包含非法字段 '%s'，已忽略", key)
            continue
        alert_filter &= Q(**{key: value})

    # 生成时间序列
    all_periods = _generate_time_periods(group_by, start_dt, end_dt)

    # 固定返回三条系列：告警数、事件数、已恢复告警数
    alert_qs = queryset.filter(alert_filter) if alert_filter else queryset

    data = {
        "告警数": _build_period_series(alert_qs, "created_at", trunc_func, target_tz, aware_start, aware_end, all_periods),
        "事件数": _build_period_series(
            Event.objects.filter(alert__in=queryset).distinct(), "received_at", trunc_func, target_tz, aware_start, aware_end, all_periods
        ),
        "已恢复告警数": _build_period_series(
            alert_qs,
            "updated_at",
            trunc_func,
            target_tz,
            aware_start,
            aware_end,
            all_periods,
            extra_filter=Q(status=AlertStatus.AUTO_RECOVERY),
        ),
    }

    return {"result": True, "data": data, "message": ""}


@nats_client.register
def get_alert_source_event_top(*args, **kwargs) -> Dict[str, Any]:
    """
    获取告警源事件数 TOP N
    按告警源分组统计事件数量，返回前 N 名

    :param limit: 返回条数，默认 5

    return:
        {
            "result": True,
            "data": [
                {"source_name": "Zabbix", "count": 42156},
                {"source_name": "Prometheus", "count": 31245},
                ...
            ]
        }
    """
    logger.info("[AlertNatsRPC] === get_alert_source_event_top ===, args=%s, kwargs=%s", args, kwargs)
    user_info = kwargs.pop("user_info", {})
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error

    limit = int(kwargs.pop("limit", 5))

    # 通过告警权限过滤事件
    event_qs = Event.objects.filter(alert__in=queryset).distinct()

    # 按告警源名称分组统计
    top_sources = event_qs.values("source__name").annotate(count=Count("id")).order_by("-count")[:limit]

    data = [{"source_name": item["source__name"] or "--", "count": item["count"]} for item in top_sources]
    return {"result": True, "data": data, "message": ""}


@nats_client.register
def get_alert_source_distribution(*args, **kwargs) -> Dict[str, Any]:
    """Return the full authorized Alert distribution grouped by source_name."""
    logger.info("[AlertNatsRPC] === get_alert_source_distribution ===, args=%s, kwargs=%s", args, kwargs)
    user_info = kwargs.pop("user_info", {})
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error

    counts = {}
    unknown_count = 0
    for source_name in queryset.values_list("source_name", flat=True):
        name = source_name.strip() if isinstance(source_name, str) and source_name.strip() else None
        if name is None:
            unknown_count += 1
            continue
        counts[name] = counts.get(name, 0) + 1

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    data = [{"name": name, "value": value} for name, value in ordered]
    if unknown_count:
        data.append({"name": "未知来源", "value": unknown_count})

    return {"result": True, "data": data, "message": ""}


@nats_client.register
def get_alert_source_statistics(*args, **kwargs) -> Dict[str, Any]:
    """
    获取告警源统计数据

    :param time: 时间范围 [start, end]，用于判断活跃告警源

    return:
        {
            "result": True,
            "data": {
                "total_count": 56,
                "active_count": 43,
                "enabled_count": 50,
                "enabled_rate": 89.3
            }
        }
    """
    logger.info("[AlertNatsRPC] === get_alert_source_statistics ===, args=%s, kwargs=%s", args, kwargs)
    user_info = kwargs.pop("user_info", {})
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error
    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.pop("timezone", None))

    time = kwargs.pop("time", [])

    event_qs = Event.objects.filter(alert__in=queryset).distinct()
    visible_source_ids = event_qs.values_list("source_id", flat=True).distinct()
    visible_sources = AlertSource.objects.filter(id__in=visible_source_ids)

    total_count = visible_sources.count()
    enabled_count = visible_sources.filter(is_active=True).count()
    enabled_rate = round((enabled_count / total_count * 100), 1) if total_count > 0 else 0

    # 活跃告警源：当前授权告警范围内，时间窗口中实际收到过事件的来源。
    if time and len(time) == 2:
        aware_start = _parse_client_datetime(time[0], target_tz)
        aware_end = _parse_client_datetime(time[1], target_tz)
        active_source_ids = event_qs.filter(received_at__gte=aware_start, received_at__lt=aware_end).values_list("source_id", flat=True).distinct()
        active_count = visible_sources.filter(id__in=active_source_ids).count()
    else:
        active_count = total_count

    return {
        "result": True,
        "data": {
            "total_count": total_count,
            "active_count": active_count,
            "enabled_count": enabled_count,
            "enabled_rate": enabled_rate,
        },
        "message": "",
    }


@nats_client.register
def get_notification_statistics(*args, **kwargs) -> Dict[str, Any]:
    """
    获取通知效果统计

    :param time: 时间范围 [start, end]

    return:
        {
            "result": True,
            "data": {
                "total_count": 98765,
                "success_count": 91234,
                "failed_count": 7531,
                "success_rate": 92.6,
                "failed_rate": 7.4
            }
        }
    """
    logger.info("[AlertNatsRPC] === get_notification_statistics ===, args=%s, kwargs=%s", args, kwargs)
    user_info = kwargs.pop("user_info", {})
    qs, error = _get_authorized_alert_notify_queryset(user_info)
    if error:
        return error
    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.pop("timezone", None))

    time = kwargs.pop("time", [])

    if time and len(time) == 2:
        aware_start = _parse_client_datetime(time[0], target_tz)
        aware_end = _parse_client_datetime(time[1], target_tz)
        qs = qs.filter(notify_time__gte=aware_start, notify_time__lt=aware_end)

    from apps.alerts.constants.constants import NotifyResultStatus

    total_count = qs.count()
    success_count = qs.filter(notify_result=NotifyResultStatus.SUCCESS).count()
    failed_count = qs.filter(notify_result=NotifyResultStatus.FAILED).count()
    success_rate = round((success_count / total_count * 100), 1) if total_count > 0 else 0
    failed_rate = round((failed_count / total_count * 100), 1) if total_count > 0 else 0

    return {
        "result": True,
        "data": {
            "total_count": total_count,
            "success_count": success_count,
            "failed_count": failed_count,
            "success_rate": success_rate,
            "failed_rate": failed_rate,
        },
        "message": "",
    }


@nats_client.register
def get_notification_channel_stats(*args, **kwargs) -> Dict[str, Any]:
    """
    获取按渠道分组的通知成功率（柱状图用）

    :param time: 时间范围 [start, end]

    return:
        {
            "result": True,
            "data": [
                {"name": "邮件", "value": 96.3},
                {"name": "企业微信", "value": 92.1},
                ...
            ]
        }
    """
    logger.info("[AlertNatsRPC] === get_notification_channel_stats ===, args=%s, kwargs=%s", args, kwargs)
    user_info = kwargs.pop("user_info", {})
    qs, error = _get_authorized_alert_notify_queryset(user_info)
    if error:
        return error
    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.pop("timezone", None))

    time = kwargs.pop("time", [])

    if time and len(time) == 2:
        aware_start = _parse_client_datetime(time[0], target_tz)
        aware_end = _parse_client_datetime(time[1], target_tz)
        qs = qs.filter(notify_time__gte=aware_start, notify_time__lt=aware_end)

    from apps.alerts.constants.constants import NotifyResultStatus

    channel_stats = (
        qs.values("notify_channel", "notify_channel_name")
        .annotate(
            total=Count("id"),
            success=Count("id", filter=Q(notify_result=NotifyResultStatus.SUCCESS)),
        )
        .order_by("-total")
    )

    data = []
    for item in channel_stats:
        channel_total = item["total"]
        channel_success = item["success"]
        rate = round((channel_success / channel_total * 100), 1) if channel_total > 0 else 0
        name = item["notify_channel_name"] or item["notify_channel"] or "--"
        data.append({"name": name, "value": rate})

    return {"result": True, "data": data, "message": ""}


@nats_client.register
def get_alert_data_quality(*args, **kwargs) -> Dict[str, Any]:
    """
    获取数据完整性概览

    :param time: 时间范围 [start, end]

    return:
        {
            "result": True,
            "data": {
                "total_count": 500,
                "missing_resource_id_rate": 3.21,
                "missing_service_rate": 2.87,
                "missing_rule_id_rate": 1.32,
                "missing_item_rate": 1.05,
                "missing_external_id_rate": 2.16
            }
        }
    """
    logger.info("[AlertNatsRPC] === get_alert_data_quality ===, args=%s, kwargs=%s", args, kwargs)
    user_info = kwargs.pop("user_info", {})
    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.pop("timezone", None))
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error

    time = kwargs.pop("time", [])
    if time and len(time) == 2:
        aware_start = _parse_client_datetime(time[0], target_tz)
        aware_end = _parse_client_datetime(time[1], target_tz)
        queryset = queryset.filter(created_at__gte=aware_start, created_at__lt=aware_end)

    total_count = queryset.count()
    if total_count == 0:
        return {
            "result": True,
            "data": {
                "total_count": 0,
                "missing_resource_id_rate": 0,
                "missing_service_rate": 0,
                "missing_rule_id_rate": 0,
                "missing_item_rate": 0,
                "missing_external_id_rate": 0,
            },
            "message": "",
        }

    missing_resource_id = queryset.filter(Q(resource_id__isnull=True) | Q(resource_id="")).count()
    missing_rule_id = queryset.filter(Q(rule_id__isnull=True) | Q(rule_id="")).count()

    # service/item/external_id 字段在 Event 上，统计关联事件缺失率
    event_qs = Event.objects.filter(alert__in=queryset).distinct()
    event_total = event_qs.count()
    missing_service = event_qs.filter(Q(service__isnull=True) | Q(service="")).count() if event_total > 0 else 0
    missing_item = event_qs.filter(Q(item__isnull=True) | Q(item="")).count() if event_total > 0 else 0
    missing_external_id = event_qs.filter(Q(external_id__isnull=True) | Q(external_id="")).count() if event_total > 0 else 0

    def rate(count, total):
        return round((count / total * 100), 2) if total > 0 else 0

    return {
        "result": True,
        "data": {
            "total_count": total_count,
            "missing_resource_id_rate": rate(missing_resource_id, total_count),
            "missing_service_rate": rate(missing_service, event_total),
            "missing_rule_id_rate": rate(missing_rule_id, total_count),
            "missing_item_rate": rate(missing_item, event_total),
            "missing_external_id_rate": rate(missing_external_id, event_total),
        },
        "message": "",
    }


@nats_client.register
def receive_alert_events(*args, **kwargs) -> Dict[str, Any]:
    """
    通过 NATS 接收告警事件数据

    内部 NATS 传递数据，无需认证。记录推送来源以便追踪。

    Args:
        kwargs: 包含以下字段
            - source_id: 告警源ID（可选 默认nats）
            - events: 事件列表（必填）
            - pusher: 推送者标识，如系统名称或服务名（必填）如 lite-monitor、lite-log

    Returns:
        {
            "result": bool,
            "data": dict,
            "message": str
        }

    Example NATS 调用:
        subject: "default.receive_alert_events"
        payload: {
              "args": [],
              "kwargs": {
                "source_id": "nats",
                "pusher": "lite-monitor",
                "events": [
                  {
                    "title": "服务响应超时",
                    "description": "API网关响应时间超过5秒",
                    "level": "1",
                    "item": "response_time",
                    "value": 5200,
                    "start_time": "1751964596",
                    "action": "created",
                    "external_id": "alert-timeout-gateway-20250708",
                    "service": "api-gateway",
                    "location": "北京机房",
                    "labels": {
                      "resource_id": "gateway-01",
                      "resource_type": "service",
                      "resource_name": "API网关"
                    }
                  },
                  {
                    "title": "服务响应超时",
                    "description": "API网关响应恢复正常",
                    "level": "3",
                    "action": "recovery",
                    "external_id": "alert-timeout-gateway-20250708",
                    "start_time": "1751965000"
                  }
                ]
              }
            }
    """
    logger.info(
        "[AlertEvent] receive_alert_events source_id=%s pusher=%s event_count=%s",
        kwargs.get("source_id", ""),
        kwargs.get("pusher"),
        len(kwargs.get("events") or []),
    )

    try:
        # 提取参数
        source_id = kwargs.pop("source_id", "")
        events = kwargs.pop("events", [])
        pusher = kwargs.pop("pusher", None)

        # 参数校验
        if not source_id:
            logger.warning("[AlertEvent] NATS 告警事件缺少 source_id")
            return {"result": False, "data": {}, "message": "Missing source_id."}

        if not events:
            logger.warning("[AlertEvent] source_id=%s pusher=%s 未携带 events", source_id, pusher)
            return {"result": False, "data": {}, "message": "Missing events."}

        if not pusher:
            logger.warning("[AlertEvent] source_id=%s 缺少 pusher 标识", source_id)
            return {
                "result": False,
                "data": {},
                "message": "Missing pusher identifier.",
            }

        event_source = AlertSource.objects.filter(
            source_id=source_id,
            source_type=AlertsSourceTypes.NATS,
            is_active=True,
            is_effective=True,
        ).first()
        if not event_source:
            logger.error("[AlertEvent] 无效的 NATS source_id=%s pusher=%s（未找到生效的告警源）", source_id, pusher)
            return {
                "result": False,
                "data": {},
                "message": "Invalid source_id or source type.",
            }

        normalized_events = []
        for event in events:
            normalized_event = dict(event or {})
            normalized_event.setdefault("push_source_id", pusher)
            normalized_events.append(normalized_event)

        # 内部约定：NATS 生效源（event_source 已校验）+ 明确允许的内部推送方，双重判断为可信内部推送。
        # 此时采信每个 event 自带的 organizations 作为归属组织，无需走组织级 secret。
        trusted_internal = pusher in TRUSTED_INTERNAL_PUSHERS

        # 创建适配器（内部调用无需密钥验证）
        adapter_class = AlertSourceAdapterFactory.get_adapter(event_source)
        # 传递空密钥，因为不需要认证
        adapter = adapter_class(alert_source=event_source, secret="", events=normalized_events, trusted_internal=trusted_internal)

        # 记录推送来源信息
        logger.info("[AlertEvent] 开始处理 %s 条事件 source_id=%s pusher=%s", len(events), source_id, pusher)

        # 处理告警事件
        ingestion = adapter.main() or {
            "received": len(events),
            "accepted": len(events),
            "skipped": 0,
            "errored": 0,
        }

        logger.info("[AlertEvent] 成功处理 %s 条事件 pusher=%s source_id=%s", len(events), pusher, source_id)

        fully_accepted = ingestion.get("skipped", 0) == 0 and ingestion.get("errored", 0) == 0
        return {
            "result": fully_accepted,
            "data": {
                "processed_events": ingestion.get("accepted", 0),
                "ingestion": ingestion,
                "source_id": source_id,
                "pusher": pusher,
                "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "message": (
                "Events received and processed successfully."
                if fully_accepted
                else "Alert events were only partially accepted."
            ),
        }

    except Exception as e:
        logger.error(
            "[AlertEvent] 处理 NATS 告警事件失败 pusher=%s source_id=%s：%s",
            kwargs.get("pusher", "unknown"),
            kwargs.get("source_id", "unknown"),
            e,
            exc_info=True,
        )
        return {"result": False, "data": {}, "message": f"Error: {str(e)}"}


@nats_client.register
def alert_test(*args, **kwargs):
    """
    测试nats的告警接口
    """
    logger.info("[AlertNatsRPC] === alert_test ===, args=%s, kwargs=%s", args, kwargs)
    return {"result": True, "data": "alert_test success", "message": ""}


@nats_client.register
def get_alert_statistics(**kwargs):
    """
    获取告警统计数据

    Returns:
        {
            "result": True,
            "data": {
                "total_count": 500,
                "active_count": 45,
                "pending_count": 20,
                "processing_count": 25,
                "event_count": 1200,
                "incident_count": 8
            },
            "message": ""
        }
    """
    user_info = kwargs.get("user_info", {})
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error

    total_count = queryset.count()
    active_count = queryset.filter(status__in=AlertStatus.ACTIVATE_STATUS).count()
    pending_count = queryset.filter(status=AlertStatus.PENDING).count()
    processing_count = queryset.filter(status=AlertStatus.PROCESSING).count()
    auto_recovery_count = queryset.filter(status=AlertStatus.AUTO_RECOVERY).count()
    session_alert_count = queryset.filter(is_session_alert=True).count()
    event_count = Event.objects.filter(alert__in=queryset).distinct().count()
    incident_count = Incident.objects.filter(alert__in=queryset).distinct().count()

    # 计算比率字段
    aggregation_ratio = round(event_count / total_count, 2) if total_count > 0 else 0
    session_alert_rate = round(session_alert_count / total_count * 100, 1) if total_count > 0 else 0
    auto_recovery_rate = round(auto_recovery_count / total_count * 100, 1) if total_count > 0 else 0

    return {
        "result": True,
        "data": {
            "total_count": total_count,
            "active_count": active_count,
            "pending_count": pending_count,
            "processing_count": processing_count,
            "auto_recovery_count": auto_recovery_count,
            "session_alert_count": session_alert_count,
            "event_count": event_count,
            "incident_count": incident_count,
            "aggregation_ratio": aggregation_ratio,
            "session_alert_rate": session_alert_rate,
            "auto_recovery_rate": auto_recovery_rate,
        },
        "message": "",
    }


@nats_client.register
def get_alert_today_status_summary(**kwargs):
    """
    获取今日告警状态摘要：今日产生、今日关闭、当前处理中。
    """
    user_info = kwargs.get("user_info", {})
    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.get("timezone"))
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error

    now = timezone.now().astimezone(target_tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + datetime.timedelta(days=1)

    return {
        "result": True,
        "data": {
            "today_created_count": queryset.filter(
                created_at__gte=today_start,
                created_at__lt=tomorrow_start,
            ).count(),
            "today_closed_count": queryset.filter(
                status__in=AlertStatus.CLOSED_STATUS,
                updated_at__gte=today_start,
                updated_at__lt=tomorrow_start,
            ).count(),
            "processing_count": queryset.filter(status=AlertStatus.PROCESSING).count(),
        },
        "message": "",
    }


@nats_client.register
def get_alert_status_distribution(**kwargs):
    """
    获取活跃告警状态分布，供饼图展示。
    """
    user_info = kwargs.get("user_info", {})
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error

    status_labels = dict(AlertStatus.CHOICES)
    status_order = [AlertStatus.UNASSIGNED, AlertStatus.PENDING, AlertStatus.PROCESSING]
    status_counts = queryset.filter(status__in=status_order).values("status").annotate(count=Count("id"))
    counts = {item["status"]: item["count"] for item in status_counts}

    return {
        "result": True,
        "data": [{"name": status_labels.get(status, status), "value": counts.get(status, 0)} for status in status_order],
        "message": "",
    }


@nats_client.register
def get_alert_level_trend(**kwargs):
    """
    获取指定时间范围内按告警等级分组的趋势数据。
    """
    logger.info("[AlertNatsRPC] === get_alert_level_trend ===, kwargs=%s", kwargs)
    user_info = kwargs.get("user_info", {})
    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.get("timezone"))
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error

    time = kwargs.get("time", [])
    if not time or len(time) != 2:
        return {
            "result": False,
            "data": {},
            "message": "start_time and end_time are required.",
        }

    aware_start = _parse_client_datetime(time[0], target_tz)
    aware_end = _parse_client_datetime(time[1], target_tz)
    start_dt = aware_start.astimezone(target_tz)
    end_dt = aware_end.astimezone(target_tz)
    group_by = kwargs.get("group_by", "day")
    trunc_func, _ = group_dy_date_format(group_by)
    all_periods = _generate_time_periods(group_by, start_dt, end_dt)
    level_map = _get_alert_level_display_map()

    levels = queryset.filter(created_at__gte=aware_start, created_at__lt=aware_end).values_list("level", flat=True).distinct()

    data = {}
    for level in levels:
        display_name = level_map.get(level, level)
        data[display_name] = _build_period_series(
            queryset.filter(level=level),
            "created_at",
            trunc_func,
            target_tz,
            aware_start,
            aware_end,
            all_periods,
        )

    return {"result": True, "data": data, "message": ""}


@nats_client.register
def get_alert_level_distribution(status_filter=None, **kwargs):
    """
    获取告警等级分布（饼状图用）

    Args:
        status_filter: "active" | None - 可选，仅统计活跃告警

    Returns:
        {
            "result": True,
            "data": [
                {"name": "致命", "value": 10},
                {"name": "严重", "value": 25}
            ],
            "message": ""
        }
    """
    level_map = _get_alert_level_display_map()

    user_info = kwargs.get("user_info", {})
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error

    if status_filter == "active":
        queryset = queryset.filter(status__in=AlertStatus.ACTIVATE_STATUS)

    # Alert.Meta.ordering 包含 updated_at；聚合前必须清除默认排序，否则部分
    # 数据库会把排序列加入 GROUP BY，导致同一等级被拆成多条。
    level_counts = queryset.order_by().values("level").annotate(count=Count("id"))

    result_data = []
    for item in level_counts:
        level = item["level"]
        display_name = level_map.get(level, level)
        result_data.append({"name": display_name, "value": item["count"]})

    result_data.sort(key=lambda x: x["value"], reverse=True)

    return {"result": True, "data": result_data, "message": ""}


@nats_client.register
def get_active_alert_top(limit=10, **kwargs):
    """
    获取活跃告警持续时间 TOP N

    Args:
        limit: int - 返回数量，默认 10

    Returns:
        {
            "result": True,
            "data": [
                {
                    "alert_id": "ALERT-ABC123",
                    "title": "CPU使用率过高",
                    "level": "严重",
                    "status": "pending",
                    "duration_seconds": 86400,
                    "created_at": "2026-04-19 10:00:00",
                    "resource_name": "web-server-01"
                }
            ],
            "message": ""
        }
    """
    limit = int(limit) if limit else 10
    if limit <= 0:
        limit = 10
    if limit > 100:
        limit = 100

    user_info = kwargs.get("user_info", {})
    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.get("timezone"))
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error

    active_alerts = queryset.filter(status__in=AlertStatus.ACTIVATE_STATUS).order_by("created_at")[:limit]

    level_map = _get_alert_level_display_map()
    status_map = dict(AlertStatus.CHOICES)

    now = timezone.now()
    alerts_with_duration = []
    for alert in active_alerts:
        duration_seconds = int((now - alert.created_at).total_seconds())
        alerts_with_duration.append(
            {
                "alert_id": alert.alert_id,
                "title": alert.title,
                "level": level_map.get(alert.level, alert.level),
                "status": status_map.get(alert.status, alert.status),
                "duration_seconds": duration_seconds,
                "created_at": timezone.localtime(alert.created_at, target_tz).isoformat(),
                "resource_name": alert.resource_name or "",
            }
        )

    return {"result": True, "data": alerts_with_duration, "message": ""}
