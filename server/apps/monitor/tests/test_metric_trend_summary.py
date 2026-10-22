import json
import logging
import time
from types import SimpleNamespace

import pytest

from apps.monitor.services.metric_trend_summary import MAX_TREND_ROWS, linear_slope_per_day, summarize_trend_rows
from apps.monitor.services.metrics import MetricsQueryBudgetExceeded


def _points(instance_id: str, path: str, current: float, daily: float, days: int = 14) -> dict:
    end = time.time()
    values = []
    for index in range(days + 1):
        age = days - index
        ts = end - age * 86400
        values.append([ts, str(current - daily * age)])
    return {"metric": {"instance_id": instance_id, "path": path, "fstype": "xfs"}, "values": values}


def test_linear_slope_matches_daily_rise():
    end = 1_700_000_000
    points = [(end - (4 - index) * 86400, 10 + index * 2) for index in range(5)]
    slope = linear_slope_per_day(points)
    assert slope is not None
    assert abs(slope - 2) < 0.01


def test_summary_returns_current_and_slope_even_when_not_within_horizon():
    series = [
        _points("1_10.10.60.11", "/", 90, 2.5),
        _points("1_10.10.60.14", "/", 88, 0.1),
        _points("1_10.10.60.16", "/", 32, 0.2),
        _points("1_10.10.60.13", "/", 65, 5),
    ]
    out = summarize_trend_rows(series, threshold=100, horizon_days=7)
    assert out["scanned_series"] == 4
    assert out["hit_count"] == 2
    assert out["truncated"] is False
    ids = [row["instance_id"] for row in out["rows"]]
    assert ids[:2] == ["1_10.10.60.11", "1_10.10.60.13"]
    assert set(ids) == {"1_10.10.60.11", "1_10.10.60.13", "1_10.10.60.14", "1_10.10.60.16"}
    assert out["rows"][0]["days_to_threshold"] < out["rows"][1]["days_to_threshold"]
    assert out["rows"][0]["labels"]["path"] == "/"
    flat = next(row for row in out["rows"] if row["instance_id"] == "1_10.10.60.14")
    assert flat["within_horizon"] is False
    assert flat["current"] == 88
    assert flat["slope_per_day"] > 0
    assert "values" not in out["rows"][0]


def test_summary_truncation_counts_only_omitted_hits_not_non_hits():
    """非命中占满 MAX 窗口时不应误报 truncated。"""
    hits = [_points(f"hit-{index}", "/", 90, 5) for index in range(3)]
    non_hits = [_points(f"flat-{index}", "/", 40, 0.05) for index in range(MAX_TREND_ROWS + 5)]
    out = summarize_trend_rows(hits + non_hits, threshold=100, horizon_days=7)
    assert out["hit_count"] == 3
    assert out["truncated"] is False
    assert out["omitted_count"] == 0
    returned_hits = [row for row in out["rows"] if row["within_horizon"]]
    assert len(returned_hits) == 3
    assert all(row["instance_id"].startswith("hit-") for row in returned_hits)


def test_summary_truncates_when_hits_exceed_max_rows():
    hits = [_points(f"hit-{index}", "/", 92, 4) for index in range(MAX_TREND_ROWS + 7)]
    out = summarize_trend_rows(hits, threshold=100, horizon_days=7)
    assert out["hit_count"] == len(hits)
    assert out["truncated"] is True
    assert out["omitted_count"] == 7
    assert len(out["rows"]) == MAX_TREND_ROWS
    assert all(row["within_horizon"] for row in out["rows"])


def test_summary_marks_already_full_as_zero_days():
    series = [_points("full", "/", 120, 0)]
    out = summarize_trend_rows(series, threshold=100, horizon_days=7)
    assert out["rows"][0]["days_to_threshold"] == 0
    assert out["hit_count"] == 1


def test_handler_empty_instance_ids_covers_authorized_hosts(monkeypatch):
    from types import SimpleNamespace

    from apps.monitor.nats import monitor as nm

    metric = SimpleNamespace(query='disk_used_percent{instance_type="os", __$labels__}', instance_id_keys=["instance_id"])
    monitor_obj = SimpleNamespace(id=12, instance_id_keys=["instance_id"])

    class _QS(list):
        def select_related(self, *_args):
            return self

        def order_by(self, *_args):
            return self

    class _Authorized:
        def filter(self, **_kwargs):
            return [
                SimpleNamespace(id="1_10.10.60.11"),
                SimpleNamespace(id="1_10.10.60.14"),
            ]

    captured = {}

    class _VM:
        def query_range(self, query, start, end, step):
            captured["query"] = query
            return {
                "status": "success",
                "data": {
                    "result": [
                        _points("1_10.10.60.11", "/", 90, 2.5),
                        _points("1_10.10.60.14", "/", 88, 0.1),
                    ]
                },
            }

    monkeypatch.setattr(nm, "_get_monitor_instance_permission", lambda *_args, **_kwargs: (object(), None))
    monkeypatch.setattr(nm.MonitorObject.objects, "get", lambda **_kwargs: monitor_obj)
    monkeypatch.setattr(nm.Metric.objects, "filter", lambda **_kwargs: _QS([metric]))
    monkeypatch.setattr(nm, "_get_authorized_instance_queryset", lambda _permission: _Authorized())
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _VM)

    out = nm.summarize_metric_trend(
        {"monitor_obj_id": "12", "metric": "disk_used_percent"},
        user_info={"user": "u", "team": 1},
    )

    assert out["result"] is True
    assert captured["query"].startswith(f"limitk({nm.Metrics.RANGE_QUERY_MAX_SERIES + 1},")
    assert "1_10.10.60.11" in captured["query"]
    assert "1_10.10.60.14" in captured["query"]
    ids = [row["instance_id"] for row in out["data"]["rows"]]
    assert ids[0] == "1_10.10.60.11"
    assert set(ids) == {"1_10.10.60.11", "1_10.10.60.14"}
    assert out["data"]["hit_count"] == 1
    assert out["data"]["instance_count"] == 2
    assert out["data"]["scanned_series"] == 2
    assert "values" not in out["data"]["rows"][0]


def _install_trend_handler(monkeypatch, query_range, instances=None):
    from apps.monitor.nats import monitor as nm

    metric = SimpleNamespace(query='disk_used_percent{instance_type="os", __$labels__}', instance_id_keys=["instance_id"])
    monitor_obj = SimpleNamespace(id=12, instance_id_keys=["instance_id"])
    instances = instances or [SimpleNamespace(id="1_10.10.60.11")]

    class _QS(list):
        def select_related(self, *_args):
            return self

        def order_by(self, *_args):
            return self

    class _Authorized:
        def filter(self, **_kwargs):
            return instances

    class _VM:
        def query_range(self, query, start, end, step):
            return query_range(query, start, end, step)

    monkeypatch.setattr(nm, "_get_monitor_instance_permission", lambda *_args, **_kwargs: (object(), None))
    monkeypatch.setattr(nm.MonitorObject.objects, "get", lambda **_kwargs: monitor_obj)
    monkeypatch.setattr(nm.Metric.objects, "filter", lambda **_kwargs: _QS([metric]))
    monkeypatch.setattr(nm, "_get_authorized_instance_queryset", lambda _permission: _Authorized())
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _VM)


def test_handler_budget_failure_does_not_return_raw_points(monkeypatch):
    from apps.monitor.nats import monitor as nm

    sentinel = "RAW_POINT_SENTINEL_9f3c"
    captured = {}
    summarized = []

    def query_range(query, start, end, step):
        captured["query"] = query
        return {
            "status": "success",
            "data": {
                "result": [
                    {"metric": {"instance_id": "1_10.10.60.11", "path": "/"}, "values": [[1, sentinel]]},
                    {"metric": {"instance_id": "1_10.10.60.11", "path": "/data"}, "values": [[1, sentinel]]},
                ]
            },
        }

    def _summarize(*_args, **_kwargs):
        summarized.append(True)
        raise AssertionError("超预算时不应把原始点交给汇总")

    monkeypatch.setattr(nm.Metrics, "RANGE_QUERY_MAX_SERIES", 1)
    monkeypatch.setattr(nm, "summarize_trend_rows", _summarize)
    _install_trend_handler(monkeypatch, query_range)

    out = nm.summarize_metric_trend(
        {"monitor_obj_id": "12", "metric": "disk_used_percent"},
        user_info={"user": "u", "team": 1},
    )

    assert summarized == []
    assert out["result"] is False
    assert out["data"] == []
    assert out["message"] == MetricsQueryBudgetExceeded.MESSAGE
    assert out["code"] == "MONITOR_RANGE_QUERY_BUDGET_EXCEEDED"
    assert out["budget"]["reason"] == "series"
    assert captured["query"].startswith("limitk(2,")
    assert "1_10.10.60.11" in captured["query"]
    rendered = json.dumps(out, ensure_ascii=False)
    assert sentinel not in rendered


def test_query_trend_series_rejects_tiny_step_before_vm(monkeypatch):
    from apps.monitor.nats import monitor as nm

    called = {"count": 0}

    class _VM:
        def query_range(self, *_args, **_kwargs):
            called["count"] += 1
            return {"status": "success", "data": {"result": [{"values": [[1, "1"]]}]}}

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _VM)
    end = 1_700_000_000
    start = end - 2 * 86400
    with pytest.raises(MetricsQueryBudgetExceeded) as raised:
        nm._query_trend_series(
            [(None, ["instance_id"], "disk_used_percent{__$labels__}")],
            ["host-a"],
            start,
            end,
            "1s",
        )

    assert called["count"] == 0
    assert raised.value.data["reason"] == "points_per_series"
    assert raised.value.data["code"] == "MONITOR_RANGE_QUERY_BUDGET_EXCEEDED"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("lookback_days", 31, "lookback_days 必须在 1 到 30 之间"),
        ("horizon_days", 0, "horizon_days 必须在 1 到 90 之间"),
        ("threshold", -1, "threshold 必须在 0 到 1e+06 之间"),
    ],
)
def test_handler_rejects_illegal_trend_span(monkeypatch, field, value, message):
    from apps.monitor.nats import monitor as nm

    called = {"count": 0}

    def query_range(*_args, **_kwargs):
        called["count"] += 1
        return {"status": "success", "data": {"result": []}}

    _install_trend_handler(monkeypatch, query_range)
    payload = {"monitor_obj_id": "12", "metric": "disk_used_percent", field: value}
    out = nm.summarize_metric_trend(payload, user_info={"user": "u", "team": 1})

    assert out == {"result": False, "data": {}, "message": message}
    assert called["count"] == 0


def test_handler_mixed_unresolved_skips_and_returns_summary(monkeypatch):
    from apps.monitor.nats import monitor as nm

    captured = {}

    def query_range(query, start, end, step):
        captured["query"] = query
        return {
            "status": "success",
            "data": {"result": [_points("1_10.10.60.11", "/", 90, 2.5)]},
        }

    _install_trend_handler(
        monkeypatch,
        query_range,
        instances=[SimpleNamespace(id="1_10.10.60.11", name="db-1")],
    )
    out = nm.summarize_metric_trend(
        {
            "monitor_obj_id": "12",
            "metric": "disk_used_percent",
            "instance_ids": ["1_10.10.60.11", "gz-db-server-04-172.16.178.232"],
        },
        user_info={"user": "u", "team": 1},
    )

    assert out["result"] is True
    assert out["message"] == ""
    assert "1_10.10.60.11" in captured["query"]
    assert "gz-db-server-04-172.16.178.232" not in captured["query"]
    assert out["data"]["skipped_instance_ids"] == ["gz-db-server-04-172.16.178.232"]
    assert out["data"]["instance_count"] == 1
    assert [row["instance_id"] for row in out["data"]["rows"]] == ["1_10.10.60.11"]
    assert "values" not in out["data"]["rows"][0]


def test_vm_error_returns_stable_message_and_omits_body(monkeypatch, caplog):
    from apps.monitor.nats import monitor as nm

    sentinel = 'VM_ERROR_BODY_sentinel_9f3c disk_used_percent{token="SECRET"}'
    template = "event=metric_trend_query_failed monitor_obj_id=%s failed_stage=query_range error_type=%s"

    def query_range(*_args, **_kwargs):
        return {"status": "error", "errorType": f"execution\n{sentinel}", "error": sentinel}

    _install_trend_handler(monkeypatch, query_range)
    caplog.set_level(logging.DEBUG, logger="nats")
    out = nm.summarize_metric_trend(
        {"monitor_obj_id": "12", "metric": "disk_used_percent", "instance_ids": ["1_10.10.60.11"]},
        user_info={"user": "u", "team": 1},
    )

    assert out == {"result": False, "data": {}, "message": "指标趋势汇总失败"}
    records = [record for record in caplog.records if record.msg == template]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.args == ("12", "vm_status_error")
    assert record.exc_info is None
    assert record.getMessage() == ("event=metric_trend_query_failed monitor_obj_id=12 failed_stage=query_range error_type=vm_status_error")
    assert sentinel not in record.msg
    assert sentinel not in str(record.args)
    assert sentinel not in record.getMessage()
    assert sentinel not in caplog.text
    assert not [item for item in caplog.records if item.levelno >= logging.ERROR]
