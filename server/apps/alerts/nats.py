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

import nats_client
from apps.alerts.models import Alert


@nats_client.register
def get_alert_trend_data(group_by: str = "day", filters: dict = dict) -> Dict[str, Any]:
    """
    获取告警趋势数据 获取制定时间内，告警的数据
    例如：获取7天内，每天的告警数量
    根据group_by参数分组统计告警数据
    :param group_by: 分组方式，支持 "minute", "hour", "day", "week", "month"
    :param filters: 过滤条件，字典格式
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

    start_time = filters.get("start_time")
    end_time = filters.get("end_time")
    if not start_time or not end_time:
        return {
            "result": False,
            "data": [],
            "message": "start_time and end_time are required."
        }

    # 解析时间字符串
    start_dt = datetime.datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
    end_dt = datetime.datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')

    # 根据group_by选择截断函数和日期格式
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

    # 构建查询条件
    query_conditions = Q(created_at__gte=start_dt, created_at__lt=end_dt)

    # 应用过滤条件
    for key, value in filters.items():
        if key == "level" and isinstance(value, list):
            query_conditions &= Q(level__in=value)
        elif key == "status" and isinstance(value, list):
            query_conditions &= Q(status__in=value)
        elif key == "source_name" and isinstance(value, list):
            query_conditions &= Q(source_name__in=value)
        elif key == "resource_type":
            query_conditions &= Q(resource_type=value)
        elif key == "resource_id":
            query_conditions &= Q(resource_id=value)

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
