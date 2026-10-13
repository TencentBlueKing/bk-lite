import time

from apps.monitor.services.metric_trend_summary import linear_slope_per_day, summarize_trend_rows


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


def test_summary_keeps_only_series_that_hit_within_horizon():
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
    assert ids == ["1_10.10.60.11", "1_10.10.60.13"]
    assert out["rows"][0]["days_to_threshold"] < out["rows"][1]["days_to_threshold"]
    assert out["rows"][0]["labels"]["path"] == "/"
    assert "values" not in out["rows"][0]


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
    assert "1_10.10.60.11" in captured["query"]
    assert "1_10.10.60.14" in captured["query"]
    assert [row["instance_id"] for row in out["data"]["rows"]] == ["1_10.10.60.11"]
    assert out["data"]["instance_count"] == 2
    assert out["data"]["scanned_series"] == 2
