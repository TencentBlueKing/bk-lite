from apps.cmdb.nats import nats as N


class QueryMustNotRun:
    def filter(self, **kwargs):
        raise AssertionError("invalid range must be rejected before querying")


def test_get_change_trend_rejects_oversized_range_before_query(monkeypatch):
    monkeypatch.setitem(N._CHANGE_TREND_MAX_SPAN_SECONDS, "hour", 3600)
    monkeypatch.setattr(N.ChangeRecord, "objects", QueryMustNotRun())

    result = N.get_change_trend(
        time=["2026-01-01 00:00:00", "2026-01-01 02:00:00"],
        group_by="hour",
    )

    assert result["result"] is False
    assert result["data"] == {}
    assert "maximum limit" in result["message"]


def test_get_change_trend_rejects_invalid_group_by_before_query(monkeypatch):
    monkeypatch.setattr(N.ChangeRecord, "objects", QueryMustNotRun())

    result = N.get_change_trend(
        time=["2026-01-01 00:00:00", "2026-01-02 00:00:00"],
        group_by="minute",
    )

    assert result == {
        "result": False,
        "data": {},
        "message": "group_by must be one of: hour, day, week, month",
    }
