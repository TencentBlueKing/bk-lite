"""TimeRangeChecker 测试。

覆盖：
1. 时区行为：每日/每周/每月循环窗口必须按项目本地时区解释（Asia/Shanghai 非 UTC）。
2. to_orm_filter：type=one 返回可用 Q 对象；day/week/month 返回 None（退化到 Python）；
   无配置返回空 Q（全部匹配）。
"""

import datetime

from django.db.models import Q
from django.test import override_settings
from django.utils import timezone

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


# ---------------------------------------------------------------------------
# to_orm_filter 测试（验证修复 #3700 的核心路径）
# ---------------------------------------------------------------------------


@override_settings(TIME_ZONE="Asia/Shanghai", USE_TZ=True)
def test_to_orm_filter_one_returns_q():
    """type=one 必须返回 Q 对象，而非 None，使调用方能跳过 Python 遍历。
    revert to_orm_filter 实现后此测试会因 q is None 而失败。"""
    config = {
        "type": "one",
        "start_time": "2026-06-01 00:00:00",
        "end_time": "2026-06-30 23:59:59",
    }
    q = TimeRangeChecker(config).to_orm_filter("created_at")
    assert q is not None
    assert isinstance(q, Q)
    assert "created_at__range" in str(q)


@override_settings(TIME_ZONE="Asia/Shanghai", USE_TZ=True)
def test_to_orm_filter_day_returns_none():
    """type=day 循环型时段无法下推到 SQL，必须返回 None 触发 Python 退化路径。"""
    config = {"type": "day", "start_time": "09:00:00", "end_time": "17:00:00"}
    q = TimeRangeChecker(config).to_orm_filter("created_at")
    assert q is None


@override_settings(TIME_ZONE="Asia/Shanghai", USE_TZ=True)
def test_to_orm_filter_week_returns_none():
    """type=week 必须返回 None。"""
    config = {"type": "week", "week_month": [1], "start_time": "00:00:00", "end_time": "23:59:59"}
    q = TimeRangeChecker(config).to_orm_filter("created_at")
    assert q is None


@override_settings(TIME_ZONE="Asia/Shanghai", USE_TZ=True)
def test_to_orm_filter_month_returns_none():
    """type=month 必须返回 None。"""
    config = {"type": "month", "week_month": [1], "start_time": "00:00:00", "end_time": "23:59:59"}
    q = TimeRangeChecker(config).to_orm_filter("created_at")
    assert q is None


@override_settings(TIME_ZONE="Asia/Shanghai", USE_TZ=True)
def test_to_orm_filter_empty_config_returns_empty_q():
    """无配置时返回空 Q（等同于无条件过滤，全部匹配）。"""
    q = TimeRangeChecker({}).to_orm_filter("created_at")
    assert q is not None
    assert isinstance(q, Q)
    assert len(q.children) == 0


@override_settings(TIME_ZONE="Asia/Shanghai", USE_TZ=True)
def test_to_orm_filter_one_range_boundaries_consistent_with_is_in_range():
    """to_orm_filter 生成的 Q range 边界与 is_in_range 语义一致。
    revert to_orm_filter 后 q is None，assert q is not None 先失败。"""
    config = {
        "type": "one",
        "start_time": "2026-06-01 00:00:00",
        "end_time": "2026-06-30 23:59:59",
    }
    q = TimeRangeChecker(config).to_orm_filter("created_at")
    assert q is not None  # revert 修复后此断言失败

    inside = timezone.make_aware(datetime.datetime(2026, 6, 15, 12, 0, 0))
    outside = timezone.make_aware(datetime.datetime(2026, 7, 1, 0, 0, 1))

    assert TimeRangeChecker(config, inside).is_in_range() is True
    assert TimeRangeChecker(config, outside).is_in_range() is False

    start, end = q.children[0][1]
    assert start <= inside <= end
    assert not (start <= outside <= end)
