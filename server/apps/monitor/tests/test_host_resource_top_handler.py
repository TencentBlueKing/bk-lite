import time
from types import SimpleNamespace

from apps.monitor.nats import monitor as nm


def test_host_resource_top_handler_returns_data(monkeypatch):
    instance = SimpleNamespace(id="host-1", name="host-1", ip="10.0.0.1", interval=300)
    monkeypatch.setattr(
        nm,
        "_get_nats_actor_scope",
        lambda user_info: (None, 1, False, frozenset({1}), False, None),
    )
    monkeypatch.setattr(
        nm,
        "_get_authorized_monitor_instances",
        lambda user_info, scope_ids: ({"host-1": instance}, None),
    )

    class FakeVM:
        def query(self, query):
            return {
                "status": "success",
                "data": {"result": [{"metric": {"instance_id": "host-1"}, "value": [time.time(), "58"]}]},
            }

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    out = nm.get_host_resource_top("cpu", user_info={"user": "u", "team": 1})

    assert out["result"] is True
    assert out["data"][0]["usage_percent"] == 42.0


def test_host_resource_top_handler_rejects_invalid_type(monkeypatch):
    class FailVM:
        def __init__(self):
            raise AssertionError("VM must not be initialized")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    out = nm.get_host_resource_top("network", user_info={"user": "u", "team": 1})

    assert out["result"] is False


def test_host_resource_top_handler_narrows_to_requested_authorized_hosts(monkeypatch):
    allowed = SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)
    other = SimpleNamespace(id="host-2", name="web-2", ip="10.0.0.2", interval=300)
    monkeypatch.setattr(
        nm,
        "_get_nats_actor_scope",
        lambda user_info: (None, 1, False, frozenset({1}), False, None),
    )
    monkeypatch.setattr(
        nm,
        "_get_authorized_monitor_instances",
        lambda user_info, scope_ids: ({"host-1": allowed, "host-2": other}, None),
    )

    class FakeVM:
        def query(self, query, **kwargs):
            return {
                "status": "success",
                "data": {
                    "result": [
                        {"metric": {"instance_id": "host-1"}, "value": [time.time(), "58"]},
                        {"metric": {"instance_id": "host-2"}, "value": [time.time(), "10"]},
                    ]
                },
            }

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    out = nm.get_host_resource_top(
        "cpu",
        instance_ids=["host-1", "host-unauthorized"],
        user_info={"user": "u", "team": 1},
    )

    assert out["result"] is True
    assert [row["instance_id"] for row in out["data"]] == ["host-1"]


def test_host_resource_top_handler_empty_instance_ids_does_not_fallback(monkeypatch):
    class FailVM:
        def __init__(self):
            raise AssertionError("empty selection must not query")

    monkeypatch.setattr(
        nm,
        "_get_nats_actor_scope",
        lambda user_info: (None, 1, False, frozenset({1}), False, None),
    )
    monkeypatch.setattr(
        nm,
        "_get_authorized_monitor_instances",
        lambda user_info, scope_ids: ({"host-1": SimpleNamespace(id="host-1")}, None),
    )
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    out = nm.get_host_resource_top("cpu", instance_ids=[], user_info={"user": "u", "team": 1})
    assert out == {"result": True, "data": [], "message": ""}
