"""运营分析时间趋势图的聚合粒度推导。

对齐监控 Web「约按时间窗控制点数」的思路，但 OA 趋势接口使用离散
minute/hour/day/week/month 桶，因此按窗长映射到这些档位。
"""

from __future__ import annotations

from datetime import datetime

SIX_HOURS_SECONDS = 6 * 3600
SEVEN_DAYS_SECONDS = 7 * 24 * 3600
NINETY_DAYS_SECONDS = 90 * 24 * 3600
TWO_YEARS_SECONDS = 730 * 24 * 3600

# 运营分析趋势数据源：聚合粒度由服务端按时间窗推导，参数 schema 不再声明 group_by。
TREND_GROUP_BY_AUTO_REST_APIS = frozenset(
    {
        "alert/get_alert_trend_data",
        "alert/get_alert_level_trend",
        "cmdb/get_change_trend",
    }
)


def resolve_trend_group_by(span_seconds: float) -> str:
    """按时间窗长度选择趋势聚合粒度。

    - ≤6h → minute
    - ≤7d → hour
    - ≤90d → day
    - ≤2y → week
    - >2y → month
    """
    if not isinstance(span_seconds, (int, float)) or span_seconds <= 0:
        return "minute"

    if span_seconds <= SIX_HOURS_SECONDS:
        return "minute"
    if span_seconds <= SEVEN_DAYS_SECONDS:
        return "hour"
    if span_seconds <= NINETY_DAYS_SECONDS:
        return "day"
    if span_seconds <= TWO_YEARS_SECONDS:
        return "week"
    return "month"


def resolve_trend_group_by_from_range(start: datetime, end: datetime) -> str:
    return resolve_trend_group_by((end - start).total_seconds())
