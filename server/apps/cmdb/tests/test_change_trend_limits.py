import datetime

import pytest

from apps.cmdb.models.change_record import UPDATE_INST, ChangeRecord
from apps.cmdb.nats import nats as N


class QueryMustNotRun:
    def filter(self, **kwargs):
        raise AssertionError("invalid range must be rejected before querying")


class QueryStarted(Exception):
    pass


class QueryProbe:
    def filter(self, **kwargs):
        raise QueryStarted


def test_internal_nats_datetime_keeps_collector_naive_input_contract():
    parsed = N._parse_nats_datetime("2026-08-03 12:17:25")

    assert parsed.tzinfo is not None
    assert parsed.replace(tzinfo=None) == datetime.datetime(2026, 8, 3, 12, 17, 25)


def test_get_change_trend_rejects_oversized_range_before_query(monkeypatch):
    # 2h 窗会推导为 minute；把 minute 上限压到 1h 以触发跨度拒绝。
    monkeypatch.setitem(N._CHANGE_TREND_MAX_SPAN_SECONDS, "minute", 3600)
    monkeypatch.setattr(N.ChangeRecord, "objects", QueryMustNotRun())

    result = N.get_change_trend(
        time=["2026-01-01T00:00:00Z", "2026-01-01T02:00:00Z"],
    )

    assert result["result"] is False
    assert result["data"] == {}
    assert "maximum limit" in result["message"]


def test_get_change_trend_allows_range_at_maximum_limit(monkeypatch):
    monkeypatch.setitem(N._CHANGE_TREND_MAX_SPAN_SECONDS, "minute", 3600)
    monkeypatch.setattr(N.ChangeRecord, "objects", QueryProbe())

    with pytest.raises(QueryStarted):
        N.get_change_trend(
            time=["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
        )


def test_get_change_trend_short_window_uses_minute(monkeypatch):
    seen = {}
    real_resolve = N.resolve_trend_group_by_from_range

    def _capture_resolve(start, end):
        group_by = real_resolve(start, end)
        seen["group_by"] = group_by
        return group_by

    monkeypatch.setattr(N, "resolve_trend_group_by_from_range", _capture_resolve)
    monkeypatch.setattr(N.ChangeRecord, "objects", QueryProbe())

    with pytest.raises(QueryStarted):
        N.get_change_trend(
            time=["2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z"],
            group_by="day",
        )

    assert seen["group_by"] == "minute"


def test_get_change_trend_rejects_timezone_less_range_before_query(monkeypatch):
    monkeypatch.setattr(N.ChangeRecord, "objects", QueryMustNotRun())

    result = N.get_change_trend(
        time=["2026-07-04 04:17:25", "2026-08-03 04:17:25"],
        user_info={"timezone": "Asia/Shanghai"},
    )

    assert result["result"] is False
    assert "RFC3339" in result["message"]


@pytest.mark.django_db
def test_get_change_trend_includes_current_day_update_in_user_timezone():
    record = ChangeRecord.objects.create(
        inst_id=123,
        model_id="aliyun_account",
        label="instance",
        type=UPDATE_INST,
    )
    ChangeRecord.objects.filter(pk=record.pk).update(
        created_at=datetime.datetime(2026, 8, 3, 3, 26, 51, tzinfo=datetime.timezone.utc),
    )

    result = N.get_change_trend(
        time=["2026-07-04T04:17:25.885Z", "2026-08-03T04:17:25.885Z"],
        user_info={"timezone": "Asia/Shanghai"},
    )

    assert result["result"] is True
    assert result["data"]["修改"][-1] == ["2026-08-03T00:00:00+08:00", 1]
