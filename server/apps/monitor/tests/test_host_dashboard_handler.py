from types import SimpleNamespace

from apps.monitor.nats import monitor as nm


def _patch_scope(monkeypatch, instances):
    monkeypatch.setattr(
        nm,
        "_get_nats_actor_scope",
        lambda user_info: (None, 1, False, frozenset({1}), False, None),
    )
    monkeypatch.setattr(
        nm,
        "_get_authorized_monitor_instances",
        lambda user_info, scope_ids, monitor_obj_id=None: (instances, None),
    )


def test_host_instance_list_returns_authorized_hosts_only(monkeypatch):
    class FakeManager:
        def filter(self, **kwargs):
            assert kwargs == {"name": "Host"}
            return self

        def first(self):
            return SimpleNamespace(id=7)

    monkeypatch.setattr(nm, "MonitorObject", SimpleNamespace(objects=FakeManager()))
    captured = {}

    def fake_auth(user_info, scope_ids, monitor_obj_id=None):
        captured["monitor_obj_id"] = monitor_obj_id
        return {
            "host-1": SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1"),
            "switch-1": SimpleNamespace(id="switch-1", name="sw", ip="10.0.0.9"),
        }, None

    monkeypatch.setattr(nm, "_get_nats_actor_scope", lambda user_info: (None, 1, False, frozenset({1}), False, None))
    monkeypatch.setattr(nm, "_get_authorized_monitor_instances", fake_auth)

    out = nm.get_host_instance_list(user_info={"user": "u", "team": 1})

    assert captured["monitor_obj_id"] == 7
    assert out["result"] is True
    assert out["data"] == [
        {"instance_id": "switch-1", "display_name": "sw (10.0.0.9)"},
        {"instance_id": "host-1", "display_name": "web-1 (10.0.0.1)"},
    ]


def test_host_metric_range_empty_selection_does_not_query(monkeypatch):
    class FailVM:
        def __init__(self):
            raise AssertionError("empty selection must not query")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    out = nm.get_host_metric_range(
        metric_type="cpu",
        instance_ids=[],
        time=["2026-08-20T00:00:00.000Z", "2026-08-20T01:00:00.000Z"],
        user_info={"user": "u", "team": 1},
    )
    assert out == {"result": True, "data": {}, "message": ""}


def test_host_metric_range_drops_unauthorized_and_folds(monkeypatch):
    allowed = SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)
    _patch_scope(monkeypatch, {"host-1": allowed})

    class FakeVM:
        def query_range(self, query, start, end, step):
            return {
                "status": "success",
                "data": {
                    "result": [
                        {"metric": {"instance_id": "host-1", "path": "/"}, "values": [[1, "40"]]},
                        {"metric": {"instance_id": "host-1", "path": "/data"}, "values": [[1, "90"]]},
                        {"metric": {"instance_id": "host-2"}, "values": [[1, "1"]]},
                    ]
                },
            }

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    out = nm.get_host_metric_range(
        metric_type="disk",
        instance_ids=["host-1", "host-2"],
        time=["2026-08-20T00:00:00.000Z", "2026-08-20T01:00:00.000Z"],
        user_info={"user": "u", "team": 1},
    )
    assert out["result"] is True
    assert out["data"] == {"web-1 (10.0.0.1)": [[1.0, 90.0]]}


def test_host_resource_snapshot_empty_selection_skips_query(monkeypatch):
    class FailVM:
        def __init__(self):
            raise AssertionError("empty selection must not query")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    out = nm.get_host_resource_snapshot(instance_ids=[], user_info={"user": "u", "team": 1})
    assert out["result"] is True
    assert out["data"]["host_count"] == 0
    assert "healthy" not in out["data"]


def test_host_resource_snapshot_returns_avg_max_without_health(monkeypatch):
    allowed = SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)
    _patch_scope(monkeypatch, {"host-1": allowed})
    monkeypatch.setattr(
        nm,
        "HostResourceSnapshotService",
        lambda **kwargs: SimpleNamespace(
            run=lambda instances: {
                "host_count": 1,
                "avg_cpu": 40.0,
                "avg_memory": 20.0,
                "avg_disk": 70.0,
                "max_cpu": 40.0,
                "max_cpu_host": "web-1 (10.0.0.1)",
                "max_memory": 20.0,
                "max_memory_host": "web-1 (10.0.0.1)",
            }
        ),
    )
    out = nm.get_host_resource_snapshot(instance_ids=["host-1"], user_info={"user": "u", "team": 1})
    assert out["result"] is True
    assert out["data"]["host_count"] == 1
    assert "healthy" not in out["data"]
    assert "unhealthy" not in out["data"]
