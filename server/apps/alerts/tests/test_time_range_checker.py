"""TimeRangeChecker 时区行为测试。

复现并锁定缺陷：每日/每周/每月循环屏蔽窗口必须按项目本地时区
（settings.TIME_ZONE）解释，而不是 UTC。否则当 TIME_ZONE 非 UTC 时，
屏蔽生效时段会整体偏移时区差（如 Asia/Shanghai 偏移 8 小时）。
"""

import datetime

from django.test import override_settings

from apps.alerts.utils.time_range_checker import TimeRangeChecker

UTC = datetime.timezone.utc


@override_settings(TIME_ZONE="Asia/Shanghai", USE_TZ=True)
def test_daily_window_uses_local_timezone():
    # 02:00 UTC == 10:00 Asia/Shanghai，应落在本地 09:00-17:00 屏蔽窗口内
    check_time = datetime.datetime(2026, 6, 6, 2, 0, 0, tzinfo=UTC)
    config = {"type": "day", "start_time": "09:00:00", "end_time": "17:00:00"}

    assert TimeRangeChecker(config, check_time).is_in_range() is True


@override_settings(TIME_ZONE="Asia/Shanghai", USE_TZ=True)
def test_daily_window_excludes_when_local_time_outside():
    # 23:00 UTC == 次日 07:00 Asia/Shanghai，落在本地 09:00-17:00 窗口外
    check_time = datetime.datetime(2026, 6, 6, 23, 0, 0, tzinfo=UTC)
    config = {"type": "day", "start_time": "09:00:00", "end_time": "17:00:00"}

    assert TimeRangeChecker(config, check_time).is_in_range() is False


@override_settings(TIME_ZONE="Asia/Shanghai", USE_TZ=True)
def test_weekly_window_uses_local_weekday():
    # 2026-06-07 是周日(UTC)，但 22:00 UTC == 2026-06-08 06:00(周一) Asia/Shanghai
    # 屏蔽配置为周一 00:00-23:59，应按本地的"周一"匹配
    check_time = datetime.datetime(2026, 6, 7, 22, 0, 0, tzinfo=UTC)
    config = {
        "type": "week",
        "week_month": [1],  # 周一
        "start_time": "00:00:00",
        "end_time": "23:59:59",
    }

    assert TimeRangeChecker(config, check_time).is_in_range() is True


@override_settings(TIME_ZONE="Asia/Shanghai", USE_TZ=True)
def test_monthly_window_uses_local_day():
    # 2026-06-30 22:00 UTC == 2026-07-01 06:00 Asia/Shanghai，本地日为 1 号
    check_time = datetime.datetime(2026, 6, 30, 22, 0, 0, tzinfo=UTC)
    config = {
        "type": "month",
        "week_month": [1],  # 每月 1 号
        "start_time": "00:00:00",
        "end_time": "23:59:59",
    }

    assert TimeRangeChecker(config, check_time).is_in_range() is True
