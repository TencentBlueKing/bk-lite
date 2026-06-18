"""Dashboard 统计时间范围解析（_resolve_date_range）的纯逻辑测试。

不触达数据库：仅校验 days 回退、上限裁剪、自定义闭区间的格式/边界/未来日期处理。
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.job_mgmt.views.dashboard import DEFAULT_RANGE_DAYS, MAX_DAYS_PARAM, MAX_RANGE_DAYS, _resolve_date_range

pytestmark = pytest.mark.unit


class _StubRequest:
    """最小请求桩：仅提供 query_params.get(key[, default])。"""

    def __init__(self, **params):
        self.query_params = params


def test_days_default_returns_recent_week():
    today = timezone.localdate()
    start, end, error = _resolve_date_range(_StubRequest())
    assert error is None
    assert end == today
    assert start == today - timedelta(days=DEFAULT_RANGE_DAYS - 1)


def test_days_is_capped_at_max_days_param():
    today = timezone.localdate()
    start, end, error = _resolve_date_range(_StubRequest(days="999"))
    assert error is None
    assert end == today
    assert (end - start).days + 1 == MAX_DAYS_PARAM


def test_invalid_days_falls_back_to_default():
    today = timezone.localdate()
    start, _end, error = _resolve_date_range(_StubRequest(days="abc"))
    assert error is None
    assert start == today - timedelta(days=DEFAULT_RANGE_DAYS - 1)


def test_custom_range_is_inclusive():
    start, end, error = _resolve_date_range(_StubRequest(start_date="2026-01-01", end_date="2026-01-07"))
    assert error is None
    assert start.isoformat() == "2026-01-01"
    assert end.isoformat() == "2026-01-07"


def test_custom_range_requires_both_ends():
    _start, _end, error = _resolve_date_range(_StubRequest(start_date="2026-01-01"))
    assert error is not None


def test_custom_range_rejects_bad_format():
    _start, _end, error = _resolve_date_range(_StubRequest(start_date="2026/01/01", end_date="2026-01-07"))
    assert error is not None


def test_custom_range_rejects_reversed():
    _start, _end, error = _resolve_date_range(_StubRequest(start_date="2026-01-07", end_date="2026-01-01"))
    assert error is not None


def test_custom_range_accepts_max_span():
    today = timezone.localdate()
    start = today - timedelta(days=MAX_RANGE_DAYS - 1)
    resolved_start, resolved_end, error = _resolve_date_range(_StubRequest(start_date=start.isoformat(), end_date=today.isoformat()))
    assert error is None
    assert (resolved_end - resolved_start).days + 1 == MAX_RANGE_DAYS


def test_custom_range_rejects_too_long():
    _start, _end, error = _resolve_date_range(_StubRequest(start_date="2026-01-01", end_date="2026-12-31"))
    assert error is not None


def test_custom_range_clamps_future_end_to_today():
    today = timezone.localdate()
    start = today - timedelta(days=2)
    future = today + timedelta(days=10)
    resolved_start, resolved_end, error = _resolve_date_range(_StubRequest(start_date=start.isoformat(), end_date=future.isoformat()))
    assert error is None
    assert resolved_end == today
    assert resolved_start == start


def test_custom_range_rejects_fully_future():
    today = timezone.localdate()
    future = today + timedelta(days=5)
    _start, _end, error = _resolve_date_range(_StubRequest(start_date=future.isoformat(), end_date=future.isoformat()))
    assert error is not None
