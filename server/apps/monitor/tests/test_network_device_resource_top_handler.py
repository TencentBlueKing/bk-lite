from types import SimpleNamespace
import time

from apps.monitor.nats import monitor as nm


def test_network_device_resource_top_handler_returns_ranked_traffic(monkeypatch):
    instance = SimpleNamespace(
        id="sw-1", name="Switch A", ip="10.0.0.1", interval=300,
        monitor_object=SimpleNamespace(name="Switch"),
    )
    monkeypatch.setattr(nm, "_get_authorized_monitor_instances", lambda user_info: ({"sw-1": instance}, None))

    class FakeVM:
        def query(self, query, **kwargs):
            value = "10" if "incoming" in query else "5"
            return {"status": "success", "data": {"result": [{"metric": {"instance_id": "sw-1"}, "value": [time.time(), value]}]}}

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    out = nm.get_network_device_resource_top("traffic", user_info={"user": "u", "team": 1})

    assert out["result"] is True
    assert out["data"][0]["value"] == 15.0
    assert out["data"][0]["device_type"] == "Switch"
    assert out["data"][0]["unit"] == "byteps"


def test_network_device_resource_top_handler_rejects_invalid_type(monkeypatch):
    out = nm.get_network_device_resource_top("disk", user_info={"user": "u", "team": 1})
    assert out["result"] is False


def test_network_device_resource_top_handler_rejects_invalid_limit(monkeypatch):
    out = nm.get_network_device_resource_top("cpu", limit=101, user_info={"user": "u", "team": 1})
    assert out["result"] is False
