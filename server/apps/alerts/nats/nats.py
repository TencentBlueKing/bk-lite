# -- coding: utf-8 --
# @File: nats.py
# @Time: 2025/7/22 15:30
# @Author: windyzhao
"""
告警对外的nats的接口
"""

import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo

from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour, TruncMinute, TruncMonth, TruncWeek
from django.utils import timezone

import nats_client
from apps.alerts.common.source_adapter.base import AlertSourceAdapterFactory
from apps.alerts.constants.constants import AlertStatus, EventLevel, LevelType
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event, Incident, Level
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
def get_alert_trend_data(*args, **kwargs) -> Dict[str, Any]:
    """
    获取告警趋势数据 获取制定时间内，告警的数据
    例如：获取7天内，每天的告警数量
    根据group_by参数分组统计告警数据
    :param group_by: 分组方式，支持 "minute", "hour", "day", "week", "month"
    return:
        {
        "result": True,
        "data": [
          [
            "2025-02-02 10:00:00",
            5
          ]],
          }

    """
    logger.info("=== get_alert_trend_data ===, args={}, kwargs={}".format(args, kwargs))
    user_info = kwargs.pop("user_info", {})
    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.pop("timezone", None))
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error

    time = kwargs.pop("time", [])  # 默认7天
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

    # 根据group_by选择截断函数和日期格式
    group_by = kwargs.pop("group_by", "day")
    trunc_func, _ = group_dy_date_format(group_by)

    # 构建查询条件
    query_conditions = Q(created_at__gte=aware_start, created_at__lt=aware_end)

    alert_model_fields = set(Alert.model_fields())
    # 应用过滤条件
    for key, value in kwargs.items():
        if key not in alert_model_fields:
            logger.warning(f"Invalid field '{key}' in filter conditions.")
            continue
        query_conditions = Q(query_conditions, Q(**{key: value}))

    # 查询并按时间分组统计
    queryset = (
        queryset.filter(query_conditions)
        .annotate(period=trunc_func("created_at", tzinfo=target_tz))
        .values("period")
        .annotate(count=Count("id"))
        .order_by("period")
    )

    # 生成完整的时间序列
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
            # 获取该周的第一天
            week_start = current - datetime.timedelta(days=current.weekday())
            all_periods.append(week_start.date())
            current += datetime.timedelta(weeks=1)
    elif group_by == "month":
        current = start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while current < end_dt:
            all_periods.append(current.date())
            # 下个月
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

    # 创建时间-数量映射
    period_counts = {}
    for item in queryset:
        if item["period"]:
            period_key = _format_period_value(item["period"], target_tz)
            period_counts[period_key] = item["count"]

    # 构建完整结果，包含0值
    result = []
    for period in all_periods:
        period_str = _format_period_value(period, target_tz)

        result.append([period_str, period_counts.get(period_str, 0)])

    return {"result": True, "data": result, "message": ""}


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

        event_source = AlertSource.objects.filter(source_id=source_id).first()
        if not event_source:
            logger.error(f"Invalid source_id: {source_id}, pusher: {pusher}")
            return {
                "result": False,
                "data": {},
                "message": f"Invalid source_id: {source_id}",
            }

        # 创建适配器（内部调用无需密钥验证）
        adapter_class = AlertSourceAdapterFactory.get_adapter(event_source)
        # 传递空密钥，因为不需要认证
        adapter = adapter_class(alert_source=event_source, secret="", events=events)

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
    event_count = Event.objects.filter(alert__in=queryset).distinct().count()
    incident_count = Incident.objects.filter(alert__in=queryset).distinct().count()

    return {
        "result": True,
        "data": {
            "total_count": total_count,
            "active_count": active_count,
            "pending_count": pending_count,
            "processing_count": processing_count,
            "event_count": event_count,
            "incident_count": incident_count,
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
