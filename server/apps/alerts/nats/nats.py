# -- coding: utf-8 --
# @File: nats.py
# @Time: 2025/7/22 15:30
# @Author: windyzhao
"""
告警对外的nats的接口
"""

import datetime
from types import SimpleNamespace
from typing import Any, Dict
from zoneinfo import ZoneInfo

from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour, TruncMinute, TruncMonth, TruncWeek
from django.utils import timezone
from rest_framework import serializers

import nats_client
from apps.alerts.common.source_adapter.base import AlertSourceAdapterFactory
from apps.alerts.constants.constants import (
    AlertsSourceTypes,
    AlertStatus,
    EventLevel,
    LevelType,
    LogAction,
    LogTargetType,
)
from apps.alerts.models.alert_operator import AlarmStrategy, NotifyResult
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event, Incident, Level
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.serializers import AlarmStrategySerializer
from apps.alerts.utils.permission_scope import apply_team_scope_with_group_ids
from apps.core.logger import alert_logger as logger
from apps.core.utils.viewset_utils import GenericViewSetFun

ALERT_LEVEL_DISPLAY_MAP = dict(EventLevel.CHOICES)


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

    team_query = Q()
    for team_id in team_ids:
        team_query |= Q(team__contains=team_id)

    return Alert.objects.filter(team_query), None


def _nats_failure(message: str, data=None):
    return {"result": False, "data": [] if data is None else data, "message": message}


def _nats_success(data):
    return {"result": True, "data": data, "message": ""}


def _flatten_error_message(detail, field_name: str = "") -> list[str]:
    if isinstance(detail, dict):
        items = []
        for key, value in detail.items():
            next_field = f"{field_name}.{key}" if field_name else str(key)
            items.extend(_flatten_error_message(value, next_field))
        return items
    if isinstance(detail, list):
        items = []
        for value in detail:
            items.extend(_flatten_error_message(value, field_name))
        return items
    message = str(detail)
    return [f"{field_name}: {message}" if field_name else message]


def _build_validation_message(exc: Exception) -> str:
    detail = getattr(exc, "detail", exc)
    messages = _flatten_error_message(detail)
    return "; ".join(dict.fromkeys(messages)) if messages else str(exc)


def _extract_alert_permissions(user_info: dict) -> set:
    permission_data = (user_info or {}).get("permission", {})
    if isinstance(permission_data, dict):
        app_permissions = permission_data.get("alarm", [])
    elif isinstance(permission_data, (set, list, tuple)):
        app_permissions = permission_data
    else:
        app_permissions = []
    return set(app_permissions)


def _has_alarm_strategy_permission(user_info: dict, permission_name: str) -> bool:
    if (user_info or {}).get("is_superuser"):
        return True
    return permission_name in _extract_alert_permissions(user_info)


def _get_nats_group_ids(user_info: dict):
    user_info = user_info or {}
    current_team = user_info.get("team")
    if not current_team:
        return [], _nats_failure("缺少组织信息")
    try:
        team_id = int(current_team)
    except (TypeError, ValueError):
        return [], _nats_failure("组织信息非法")

    group_ids = [team_id]
    if user_info.get("include_children"):
        child_group_ids = GenericViewSetFun.extract_child_group_ids(
            user_info.get("group_tree", []),
            team_id,
        )
        if child_group_ids:
            group_ids = child_group_ids
    return group_ids, None


def _authorize_alarm_strategy(user_info: dict, permission_name: str):
    if not isinstance(user_info, dict):
        return _nats_failure("缺少用户信息")
    if not _has_alarm_strategy_permission(user_info, permission_name):
        return _nats_failure("Insufficient permissions")
    _, error = _get_nats_group_ids(user_info)
    return error


def _get_alarm_strategy_queryset(user_info: dict):
    error = _authorize_alarm_strategy(user_info, "correlation_rules-View")
    if error:
        return None, error

    queryset = AlarmStrategy.objects.all()
    if (user_info or {}).get("is_superuser"):
        return queryset, None

    group_ids, error = _get_nats_group_ids(user_info)
    if error:
        return None, error
    return apply_team_scope_with_group_ids(queryset, group_ids, field_name="team"), None


def _get_scoped_alarm_strategy(strategy_id, user_info: dict, permission_name: str):
    error = _authorize_alarm_strategy(user_info, permission_name)
    if error:
        return None, error

    queryset = AlarmStrategy.objects.all()
    if not (user_info or {}).get("is_superuser"):
        group_ids, error = _get_nats_group_ids(user_info)
        if error:
            return None, error
        queryset = apply_team_scope_with_group_ids(queryset, group_ids, field_name="team")

    try:
        return queryset.get(id=strategy_id), None
    except AlarmStrategy.DoesNotExist:
        return None, _nats_failure("Alarm strategy not found")


def _resolve_alarm_strategy_operator(user_info: dict) -> str:
    user_value = (user_info or {}).get("user")
    return getattr(user_value, "username", None) or (
        user_value if isinstance(user_value, str) and user_value else "api"
    )


def _normalize_nats_user(user_info: dict):
    group_ids, _ = _get_nats_group_ids(user_info)
    user_value = (user_info or {}).get("user")
    username = _resolve_alarm_strategy_operator(user_info)
    domain = (
        (user_info or {}).get("domain")
        or getattr(user_value, "domain", None)
        or "domain.com"
    )
    return SimpleNamespace(
        username=username,
        domain=domain,
        is_superuser=bool((user_info or {}).get("is_superuser")),
        group_list=[{"id": group_id} for group_id in group_ids],
        group_tree=(user_info or {}).get("group_tree", []),
    )


def _build_nats_serializer_context(user_info: dict):
    return {
        "request": SimpleNamespace(
            user=_normalize_nats_user(user_info),
            COOKIES={
                "current_team": str((user_info or {}).get("team") or ""),
                "include_children": "1" if (user_info or {}).get("include_children") else "0",
            },
        )
    }


def _create_alarm_strategy_operator_log(
    action: str,
    action_text: str,
    strategy: AlarmStrategy,
    user_info: dict,
):
    OperatorLog.objects.create(
        action=action,
        target_type=LogTargetType.SYSTEM,
        operator=_resolve_alarm_strategy_operator(user_info),
        operator_object=f"告警策略-{action_text}",
        target_id=strategy.id,
        overview=f"{action_text}: 策略名称:{strategy.name}",
    )


def _create_alarm_strategy_payload(data: dict, user_info: dict):
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典")
    serializer = AlarmStrategySerializer(
        data=dict(data),
        context=_build_nats_serializer_context(user_info),
    )
    serializer.is_valid(raise_exception=True)
    strategy = serializer.save()
    _create_alarm_strategy_operator_log(LogAction.ADD, "创建告警策略", strategy, user_info)
    return strategy, AlarmStrategySerializer(strategy).data


def _is_session_strategy(strategy: AlarmStrategy) -> bool:
    params = strategy.params or {}
    try:
        time_minutes = int(params.get("time_minutes") or 0)
    except (TypeError, ValueError):
        time_minutes = 0
    return bool(params.get("time_out")) and time_minutes > 0


def _update_alarm_strategy_payload(
    strategy: AlarmStrategy,
    data: dict,
    user_info: dict,
    partial=True,
):
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典")
    old_is_session = _is_session_strategy(strategy)
    serializer = AlarmStrategySerializer(
        strategy,
        data=dict(data),
        partial=partial,
        context=_build_nats_serializer_context(user_info),
    )
    serializer.is_valid(raise_exception=True)
    updated = serializer.save()
    if old_is_session and not _is_session_strategy(updated):
        from apps.alerts.aggregation.recovery.timeout_checker import TimeoutChecker

        TimeoutChecker.confirm_observing_alerts_by_strategy(updated.id)
    _create_alarm_strategy_operator_log(LogAction.MODIFY, "修改告警策略", updated, user_info)
    return updated, AlarmStrategySerializer(updated).data


def _execute_alarm_strategy_write(write_func, data, user_info: dict):
    try:
        _, result_data = write_func(data, user_info)
        return _nats_success(result_data)
    except (serializers.ValidationError, ValueError) as exc:
        return _nats_failure(_build_validation_message(exc))
    except Exception as exc:
        logger.exception("alert strategy NATS write failed, error=%s", exc)
        return _nats_failure(str(exc))


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


@nats_client.register
def list_alarm_strategies(query_data=None, *args, **kwargs):
    """查询告警策略列表。"""
    user_info = kwargs.get("user_info", {}) or {}
    queryset, error = _get_alarm_strategy_queryset(user_info)
    if error:
        return error

    query_data = query_data or {}
    if not isinstance(query_data, dict):
        return _nats_failure("query_data 必须是字典")

    if query_data.get("name"):
        queryset = queryset.filter(name__icontains=query_data["name"])
    if query_data.get("created_at_after"):
        queryset = queryset.filter(created_at__gte=query_data["created_at_after"])
    if query_data.get("created_at_before"):
        queryset = queryset.filter(created_at__lte=query_data["created_at_before"])

    try:
        page = int(query_data.get("page", 1) or 1)
        page_size = int(query_data.get("page_size", 20) or 20)
    except (TypeError, ValueError):
        return _nats_failure("page 和 page_size 必须是整数")
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    total_count = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = AlarmStrategySerializer(queryset.order_by("-created_at")[start:end], many=True).data
    return _nats_success(
        {"count": total_count, "page": page, "page_size": page_size, "items": items}
    )


@nats_client.register
def get_alarm_strategy(strategy_id, *args, **kwargs):
    """查询告警策略详情。"""
    strategy, error = _get_scoped_alarm_strategy(
        strategy_id,
        kwargs.get("user_info", {}) or {},
        "correlation_rules-View",
    )
    if error:
        return error
    return _nats_success(AlarmStrategySerializer(strategy).data)


@nats_client.register
def create_alarm_strategy(data: dict, *args, **kwargs):
    """创建告警策略。"""
    user_info = kwargs.get("user_info", {}) or {}
    error = _authorize_alarm_strategy(user_info, "correlation_rules-Add")
    if error:
        return error
    return _execute_alarm_strategy_write(_create_alarm_strategy_payload, data, user_info)


@nats_client.register
def update_alarm_strategy(strategy_id, data: dict, partial=True, *args, **kwargs):
    """更新告警策略。"""
    user_info = kwargs.get("user_info", {}) or {}
    strategy, error = _get_scoped_alarm_strategy(strategy_id, user_info, "correlation_rules-Edit")
    if error:
        return error
    return _execute_alarm_strategy_write(
        lambda payload, context_user_info: _update_alarm_strategy_payload(
            strategy,
            payload,
            context_user_info,
            partial=partial,
        ),
        data,
        user_info,
    )


@nats_client.register
def delete_alarm_strategy(strategy_id, *args, **kwargs):
    """删除告警策略。"""
    user_info = kwargs.get("user_info", {}) or {}
    strategy, error = _get_scoped_alarm_strategy(strategy_id, user_info, "correlation_rules-Delete")
    if error:
        return error

    deleted_id = strategy.id
    deleted_name = strategy.name
    try:
        if _is_session_strategy(strategy):
            from apps.alerts.aggregation.recovery.timeout_checker import TimeoutChecker

            TimeoutChecker.close_observing_session_alerts_by_strategy(strategy.id)
        strategy.delete()
        OperatorLog.objects.create(
            action=LogAction.DELETE,
            target_type=LogTargetType.SYSTEM,
            operator=_resolve_alarm_strategy_operator(user_info),
            operator_object="告警策略-删除告警策略",
            target_id=deleted_id,
            overview=f"删除告警策略: 策略名称:{deleted_name}",
        )
        return _nats_success({"deleted_id": deleted_id})
    except Exception as exc:
        logger.exception("alert strategy NATS delete failed, error=%s", exc)
        return _nats_failure(str(exc))


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
    logger.info("=== get_alert_trend_data ===, args={}, kwargs={}".format(args, kwargs))
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

    # 构建告警过滤条件
    alert_filter = Q()
    alert_model_fields = set(Alert.model_fields())
    for key, value in kwargs.items():
        if key not in alert_model_fields:
            logger.warning(f"Invalid field '{key}' in filter conditions.")
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
            "data": [["Zabbix", 42156], ["Prometheus", 31245], ...]
        }
    """
    logger.info("=== get_alert_source_event_top ===, args={}, kwargs={}".format(args, kwargs))
    user_info = kwargs.pop("user_info", {})
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error

    limit = int(kwargs.pop("limit", 5))

    # 通过告警权限过滤事件
    event_qs = Event.objects.filter(alert__in=queryset).distinct()

    # 按告警源名称分组统计
    top_sources = event_qs.values("source__name").annotate(count=Count("id")).order_by("-count")[:limit]

    data = [[item["source__name"] or "--", item["count"]] for item in top_sources]
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
    logger.info("=== get_alert_source_statistics ===, args={}, kwargs={}".format(args, kwargs))
    user_info = kwargs.pop("user_info", {})
    if not _has_alerts_view_permission(user_info):
        return {"result": False, "data": {}, "message": "Insufficient permissions"}
    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.pop("timezone", None))

    time = kwargs.pop("time", [])

    total_count = AlertSource.objects.count()
    enabled_count = AlertSource.objects.filter(is_active=True).count()
    enabled_rate = round((enabled_count / total_count * 100), 1) if total_count > 0 else 0

    # 活跃告警源：在时间范围内有 last_active_time
    if time and len(time) == 2:
        aware_start = _parse_client_datetime(time[0], target_tz)
        aware_end = _parse_client_datetime(time[1], target_tz)
        active_count = AlertSource.objects.filter(
            last_active_time__gte=aware_start,
            last_active_time__lt=aware_end,
        ).count()
    else:
        active_count = AlertSource.objects.filter(last_active_time__isnull=False).count()

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
    logger.info("=== get_notification_statistics ===, args={}, kwargs={}".format(args, kwargs))
    user_info = kwargs.pop("user_info", {})
    if not _has_alerts_view_permission(user_info):
        return {"result": False, "data": {}, "message": "Insufficient permissions"}
    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.pop("timezone", None))

    time = kwargs.pop("time", [])

    qs = NotifyResult.objects.all()
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
    logger.info("=== get_notification_channel_stats ===, args={}, kwargs={}".format(args, kwargs))
    user_info = kwargs.pop("user_info", {})
    if not _has_alerts_view_permission(user_info):
        return {"result": False, "data": [], "message": "Insufficient permissions"}
    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.pop("timezone", None))

    time = kwargs.pop("time", [])

    qs = NotifyResult.objects.all()
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
    logger.info("=== get_alert_data_quality ===, args={}, kwargs={}".format(args, kwargs))
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
            - pusher: 推送者标识，如系统名称或服务名（必填）如 lite-monitor

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
    logger.info(f"=== receive_alert_events via NATS ===, kwargs={kwargs}")

    try:
        # 提取参数
        source_id = kwargs.pop("source_id", "")
        events = kwargs.pop("events", [])
        pusher = kwargs.pop("pusher", None)

        # 参数校验
        if not source_id:
            logger.warning("Missing source_id in NATS alert event")
            return {"result": False, "data": {}, "message": "Missing source_id."}

        if not events:
            logger.warning(f"Missing events from source_id: {source_id}, pusher: {pusher}")
            return {"result": False, "data": {}, "message": "Missing events."}

        if not pusher:
            logger.warning(f"Missing pusher identifier from source_id: {source_id}")
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
            logger.error(f"Invalid NATS source_id: {source_id}, pusher: {pusher}")
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

        # 创建适配器（内部调用无需密钥验证）
        adapter_class = AlertSourceAdapterFactory.get_adapter(event_source)
        # 传递空密钥，因为不需要认证
        adapter = adapter_class(alert_source=event_source, secret="", events=normalized_events)

        # 记录推送来源信息
        logger.info(f"Processing {len(events)} events from source_id: {source_id}, pusher: {pusher}")

        # 处理告警事件
        adapter.main()

        logger.info(f"Successfully processed {len(events)} events from {pusher} (source_id: {source_id})")

        return {
            "result": True,
            "data": {
                "processed_events": len(events),
                "source_id": source_id,
                "pusher": pusher,
                "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "message": "Events received and processed successfully.",
        }

    except Exception as e:
        logger.error(
            f"Error processing alert events via NATS from pusher: {kwargs.get('pusher', 'unknown')}, "
            f"source_id: {kwargs.get('source_id', 'unknown')}, error: {e}",
            exc_info=True,
        )
        return {"result": False, "data": {}, "message": f"Error: {str(e)}"}


@nats_client.register
def alert_test(*args, **kwargs):
    """
    测试nats的告警接口
    """
    logger.info("=== alert_test ===, args={}, kwargs={}".format(args, kwargs))
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

    level_counts = queryset.values("level").annotate(count=Count("id"))

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
