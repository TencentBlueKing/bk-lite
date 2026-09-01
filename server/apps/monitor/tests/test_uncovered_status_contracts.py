"""补齐监控实例上报时间到健康状态的边界契约。"""

from datetime import datetime, timezone

import pytest

from apps.monitor.services.monitor_instance import InstanceSearch
from apps.monitor.utils import instance


pytestmark = pytest.mark.unit


class _FixedDatetime:
    @classmethod
    def now(cls, tz):
        assert tz is timezone.utc
        return datetime.fromtimestamp(10_000, timezone.utc)


@pytest.mark.parametrize(
    ("data_time", "expected"),
    [
        (0, ""),
        (9_701, "normal"),
        (9_700, "inactive"),
        (6_401, "inactive"),
        (6_400, "unavailable"),
    ],
)
def test_calculation_status_has_stable_five_minute_and_one_hour_boundaries(
    monkeypatch, data_time, expected
):
    monkeypatch.setattr(instance, "datetime", _FixedDatetime)
    assert instance.calculation_status(data_time) == expected


@pytest.mark.parametrize(
    ("data_time", "expected"),
    [
        (0, "unavailable"),
        ("", "unavailable"),
        (None, "unavailable"),
        (9_401, "normal"),
        (9_400, "unavailable"),
        (9_701, "normal"),
        (6_400, "unavailable"),
        (9_850.4, "normal"),
        ("9401", "normal"),
    ],
)
def test_list_reporting_status_uses_last_report_time_with_two_states(
    monkeypatch, data_time, expected
):
    monkeypatch.setattr(instance, "datetime", _FixedDatetime)
    assert instance.list_reporting_status(data_time) == expected


def test_status_filter_keeps_fresh_samples_and_drops_stale_ones(monkeypatch):
    monkeypatch.setattr(instance, "datetime", _FixedDatetime)
    items = [
        {"instance_id": "fresh", "time": 9_850},
        {"instance_id": "stale", "time": 9_300},
        {"instance_id": "missing", "time": ""},
    ]

    assert [item["instance_id"] for item in InstanceSearch.apply_status_filter_to_items(items, "normal")] == ["fresh"]
    assert [item["instance_id"] for item in InstanceSearch.apply_status_filter_to_items(items, "unavailable")] == [
        "stale",
        "missing",
    ]
