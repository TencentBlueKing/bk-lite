# -- coding: utf-8 --
# @File: nats.py
# @Time: 2025/7/22 15:30
# @Author: windyzhao
"""
告警对外的nats的接口
"""

import datetime
from typing import Dict, Any
from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth, TruncHour, TruncMinute
from django.utils import timezone

import nats_client
from apps.alerts.models.models import Alert
from apps.core.logger import alert_logger as logger
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.common.source_adapter.base import AlertSourceAdapterFactory


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
    time = kwargs.pop("time", [])  # 默认7天
    if not time:
        return {
            "result": False,
            "data": [],
            "message": "start_time and end_time are required."
        }
    start_time, end_time = time
    # 解析时间字符串
    start_dt = datetime.datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
    end_dt = datetime.datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
    # 转换为时区感知时间
    aware_start = timezone.make_aware(start_dt)
    aware_end = timezone.make_aware(end_dt)

    # 根据group_by选择截断函数和日期格式
    group_by = kwargs.pop("group_by", "day")
    trunc_func, date_format = group_dy_date_format(group_by)

    # 构建查询条件
    query_conditions = Q(created_at__gte=aware_start, created_at__lt=aware_end)

    alert_model_fields = Alert.model_fields()
    # 应用过滤条件
    for key, value in kwargs.items():
        if key not in alert_model_fields:
            logger.warning(f"Invalid field '{key}' in filter conditions.")
            continue
        query_conditions &= Q(**{key: value})

    # 查询并按时间分组统计
    queryset = (
        Alert.objects.filter(query_conditions)
        .annotate(period=trunc_func("created_at"))
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
            period_key = item["period"].strftime(date_format)
            period_counts[period_key] = item["count"]

    # 构建完整结果，包含0值
    result = []
    for period in all_periods:
        if isinstance(period, datetime.date):
            period_str = period.strftime(date_format)
        else:  # datetime对象
            period_str = period.strftime(date_format)

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
                "pusher": "monitoring-service",
                "events": [
                    {
                        "title": "CPU使用率过高",
                        "level": "2",
                        "message": "主机CPU使用率超过90%",
                        ...
                    }
                ]
            }
        }
    """
    logger.info(f"=== receive_alert_events via NATS ===, kwargs={kwargs}")

    try:
        # 提取参数
        source_id = kwargs.pop("source_id", "nats")
        events = kwargs.pop("events", [])
        pusher = kwargs.pop("pusher", None)

        # 参数校验
        if not source_id:
            logger.warning("Missing source_id in NATS alert event")
            return {
                "result": False,
                "data": {},
                "message": "Missing source_id."
            }

        if not events:
            logger.warning(f"Missing events from source_id: {source_id}, pusher: {pusher}")
            return {
                "result": False,
                "data": {},
                "message": "Missing events."
            }

        if not pusher:
            logger.warning(f"Missing pusher identifier from source_id: {source_id}")
            return {
                "result": False,
                "data": {},
                "message": "Missing pusher identifier."
            }

        event_source = AlertSource.objects.filter(source_id=source_id).first()
        if not event_source:
            logger.error(f"Invalid source_id: {source_id}, pusher: {pusher}")
            return {
                "result": False,
                "data": {},
                "message": f"Invalid source_id: {source_id}"
            }

        # 创建适配器（内部调用无需密钥验证）
        adapter_class = AlertSourceAdapterFactory.get_adapter(event_source)
        # 传递空密钥，因为不需要认证
        adapter = adapter_class(alert_source=event_source, secret="", events=events)

        # 记录推送来源信息
        logger.info(
            f"Processing {len(events)} events from source_id: {source_id}, "
            f"pusher: {pusher}"
        )

        # 处理告警事件
        adapter.main()

        logger.info(
            f"Successfully processed {len(events)} events from {pusher} "
            f"(source_id: {source_id})"
        )

        return {
            "result": True,
            "data": {
                "processed_events": len(events),
                "source_id": source_id,
                "pusher": pusher,
                "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "message": "Events received and processed successfully."
        }

    except Exception as e:
        logger.error(
            f"Error processing alert events via NATS from pusher: {kwargs.get('pusher', 'unknown')}, "
            f"source_id: {kwargs.get('source_id', 'unknown')}, error: {e}",
            exc_info=True
        )
        return {
            "result": False,
            "data": {},
            "message": f"Error: {str(e)}"
        }


@nats_client.register
def alert_test(*args, **kwargs):
    """
    测试nats的告警接口
    """
    logger.info("=== alert_test ===, args={}, kwargs={}".format(args, kwargs))
    return {"result": True, "data": "alert_test success", "message": ""}
