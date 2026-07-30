"""补齐监控实例上报时间到健康状态的边界契约。"""

from datetime import datetime, timezone

import pytest

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
