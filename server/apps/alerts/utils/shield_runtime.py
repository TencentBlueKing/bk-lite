# -- coding: utf-8 --
"""屏蔽策略在列表上的当前结果。

启用开关和生效时段是两件事。这里只读 TimeRangeChecker 的判断，
按创建人时区区分：未启用、屏蔽中、未开始、已结束、时段外。
"""

import datetime

from django.utils import timezone

from apps.alerts.notification_templates.timefmt import coerce_display_timezone, resolve_display_timezone
from apps.alerts.utils.time_range_checker import TimeRangeChecker

RUNTIME_DISABLED = "disabled"
RUNTIME_SHIELDING = "shielding"
RUNTIME_NOT_STARTED = "not_started"
RUNTIME_EXPIRED = "expired"
RUNTIME_OUTSIDE = "outside"

_ONE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def classify_shield_runtime(is_active, suppression_time, created_by, now=None):
    """返回当前结果码。now 缺省为当前时刻。"""
    if not is_active:
        return RUNTIME_DISABLED

    config = suppression_time if isinstance(suppression_time, dict) else {}
    tz_name = resolve_display_timezone([created_by])
    check_time = now or timezone.now()
    checker = TimeRangeChecker(config, check_time, tz_name)
    if checker.is_in_range():
        return RUNTIME_SHIELDING
    if config.get("type") != "one":
        return RUNTIME_OUTSIDE

    bounds = _one_time_bounds(config, tz_name)
    if bounds is None:
        return RUNTIME_OUTSIDE
    start, end = bounds
    try:
        if check_time < start:
            return RUNTIME_NOT_STARTED
        if check_time > end:
            return RUNTIME_EXPIRED
    except TypeError:
        return RUNTIME_OUTSIDE
    return RUNTIME_OUTSIDE


def _one_time_bounds(config, tz_name):
    start_raw = config.get("start_time")
    end_raw = config.get("end_time")
    if not start_raw or not end_raw:
        return None
    try:
        start = datetime.datetime.strptime(start_raw, _ONE_TIME_FORMAT)
        end = datetime.datetime.strptime(end_raw, _ONE_TIME_FORMAT)
    except (TypeError, ValueError):
        return None
    zone = coerce_display_timezone(tz_name)
    return timezone.make_aware(start, zone), timezone.make_aware(end, zone)
