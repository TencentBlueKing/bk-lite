from datetime import datetime, timedelta, timezone

from apps.core.utils.trend_granularity import resolve_trend_group_by, resolve_trend_group_by_from_range


def test_resolve_trend_group_by_thresholds():
    assert resolve_trend_group_by(30 * 60) == "minute"
    assert resolve_trend_group_by(6 * 3600) == "minute"
    assert resolve_trend_group_by(6 * 3600 + 1) == "hour"
    assert resolve_trend_group_by(7 * 24 * 3600) == "hour"
    assert resolve_trend_group_by(7 * 24 * 3600 + 1) == "day"
    assert resolve_trend_group_by(90 * 24 * 3600) == "day"
    assert resolve_trend_group_by(90 * 24 * 3600 + 1) == "week"
    assert resolve_trend_group_by(730 * 24 * 3600) == "week"
    assert resolve_trend_group_by(730 * 24 * 3600 + 1) == "month"


def test_resolve_trend_group_by_from_range():
    start = datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    assert resolve_trend_group_by_from_range(start, end) == "minute"
