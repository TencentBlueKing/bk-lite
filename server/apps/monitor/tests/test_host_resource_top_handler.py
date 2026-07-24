from types import SimpleNamespace
import time

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
                "data": {"result": [{"metric": {"instance_id": "host-1"}, "value": [time.time(), "42"]}]},
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
