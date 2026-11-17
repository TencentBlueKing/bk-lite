"""未恢复监控告警的严重度排序与持续时长文案。

默认最新告警排序留在 NATS handler。这里只服务显式 order=severity：
等级从高到低，同级按开始时间更早优先，再按创建时间和主键打破平局。
未知级别固定为最低，不能套用 warning 的默认档。
"""

from datetime import datetime, timezone

from django.db.models import Case, DateTimeField, IntegerField, Value, When
from django.db.models.functions import Coalesce

ACTIVE_ALERT_ORDERS = ("latest", "severity")

# MonitorEvent.LEVEL_CHOICES 的用户可见档。no_data 是已知级别，但不是高严重度。
SEVERITY_LEVEL_RANK = {
    "critical": 5,
    "error": 4,
    "warning": 3,
    "info": 2,
    "no_data": 1,
}
UNKNOWN_SEVERITY_RANK = 0

# 开始时间和创建时间都缺失时排到同级末尾，避免空时间被当成「持续最久」。
_MISSING_START = datetime(9999, 12, 31, tzinfo=timezone.utc)


def parse_active_alert_order(value) -> str:
    if value in (None, ""):
        return "latest"
    normalized = str(value).strip().lower()
    if normalized not in ACTIVE_ALERT_ORDERS:
        raise ValueError("order 仅支持 latest 或 severity")
    return normalized


def severity_rank_expression():
    whens = [When(level__iexact=level, then=Value(rank)) for level, rank in SEVERITY_LEVEL_RANK.items()]
    return Case(*whens, default=Value(UNKNOWN_SEVERITY_RANK), output_field=IntegerField())


def order_severity_queryset(queryset):
    """在截断前排序。调用方再取 limit，不能先取最新 N 条再重排。"""
    return queryset.annotate(
        severity_rank=severity_rank_expression(),
        severity_start=Coalesce(
            "start_event_time",
            "created_at",
            Value(_MISSING_START),
            output_field=DateTimeField(),
        ),
    ).order_by("-severity_rank", "severity_start", "created_at", "id")


def format_active_alert_duration(start, now) -> str:
    """把未恢复告警从开始到当前的时长写成可读文案，不回传裸秒数。"""
    if not isinstance(start, datetime) or not isinstance(now, datetime):
        return "--"
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    seconds = int((now - start).total_seconds())
    if seconds < 60:
        return "不到1分钟"
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days and hours:
        return f"{days}天{hours}小时"
    if days:
        return f"{days}天"
    if hours and minutes:
        return f"{hours}小时{minutes}分钟"
    if hours:
        return f"{hours}小时"
    return f"{minutes}分钟"
