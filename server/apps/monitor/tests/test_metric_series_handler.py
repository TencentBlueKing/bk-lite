from types import SimpleNamespace

from apps.monitor.nats import monitor as nm
from apps.monitor.nats.contracts import MONITOR_NATS_HANDLER_NAMES
from nats_client.registry import default_registry

TIME_RANGE = ["2026-08-20T00:00:00.000Z", "2026-08-20T01:00:00.000Z"]
USER = {"user": "u", "team": 1}


def test_flow_handlers_are_registered_on_nats_contract():
    assert {"get_monitor_instance_list", "query_metric_series"} <= MONITOR_NATS_HANDLER_NAMES
    runtime = {
        registration["name"]
        for registration in default_registry.registry.values()
        if registration["func"].__module__.startswith("apps.monitor.nats.")
    }
    assert {"get_monitor_instance_list", "query_metric_series"} <= runtime


def _object(object_id, name):
    return SimpleNamespace(id=object_id, name=name, instance_id_keys=["instance_id"])


def _instance(instance_id, obj, *, protocols=("netflow",), name="", ip="10.0.0.1"):
    return SimpleNamespace(
        id=instance_id,
        name=name or instance_id,
        ip=ip,
        enabled_protocols=list(protocols),
        monitor_object=obj,
        monitor_object_id=obj.id,
    )


def _metric(query, *, dimensions=None, collect_type="netflow"):
    return SimpleNamespace(
        query=query,
        dimensions=dimensions or [],
        instance_id_keys=["instance_id"],
        monitor_plugin=SimpleNamespace(collect_type=collect_type),
    )


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


def _patch_metrics(monkeypatch, catalog):
    class Manager:
        def filter(self, **kwargs):
            items = catalog.get((kwargs.get("monitor_object_id"), kwargs.get("name")), [])
            return SimpleNamespace(select_related=lambda *args, **kw: items)

    monkeypatch.setattr(nm, "Metric", SimpleNamespace(objects=Manager()))


def test_instance_list_filters_object_protocol_and_empty_enabled(monkeypatch):
    switch = _object(1, "Switch")
    router = _object(2, "Router")
    host = _object(3, "Host")
    _patch_scope(
        monkeypatch,
        {
            "sw-1": _instance("sw-1", switch, name="core-a", ip="10.0.0.1"),
            "sw-2": _instance("sw-2", switch, protocols=("sflow",), name="core-b", ip="10.0.0.2"),
            "sw-empty": _instance("sw-empty", switch, protocols=(), name="core-empty"),
            "rt-1": _instance("rt-1", router, name="edge-a", ip="10.0.0.8"),
            "host-1": _instance("host-1", host, name="web-1", ip="10.0.0.9"),
        },
    )

    out = nm.get_monitor_instance_list(protocol="netflow", user_info=USER)

    assert out["result"] is True
    assert [row["instance_id"] for row in out["data"]] == ["sw-1", "rt-1"]
    assert out["data"][0]["object_name"] == "Switch"
    assert out["data"][0]["enabled_protocols"] == ["netflow"]
    assert out["data"][0]["display_name"] == "core-a (10.0.0.1)"


def test_query_metric_series_empty_selection_does_not_query(monkeypatch):
    class FailVM:
        def __init__(self):
            raise AssertionError("empty selection must not query")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    out = nm.query_metric_series(
        metric="device_flow_bytes_rate",
        mode="range",
        instance_ids=[],
        time=TIME_RANGE,
        user_info=USER,
    )
    assert out == {"result": True, "data": {}, "message": ""}


def test_query_metric_series_rejects_illegal_params():
    out = nm.query_metric_series(metric="device_flow_bytes_rate", mode="batch", instance_ids=["sw-1"])
    assert out["result"] is False
    assert "mode" in out["message"]

    out = nm.query_metric_series(mode="instant", instance_ids=["sw-1"])
    assert out["result"] is False
    assert "metric" in out["message"]

    out = nm.query_metric_series(
        metric="device_flow_bytes_rate",
        mode="instant",
        instance_ids=["sw-1"] * 201,
    )
    assert out["result"] is False
    assert "200" in out["message"]


def test_query_metric_series_drops_unauthorized_and_folds_range(monkeypatch):
    switch = _object(1, "Switch")
    router = _object(2, "Router")
    _patch_scope(
        monkeypatch,
        {
            "sw-1": _instance("sw-1", switch),
            "rt-1": _instance("rt-1", router),
        },
    )
    _patch_metrics(
        monkeypatch,
        {
            (1, "device_flow_bytes_rate"): [
                _metric("sum(netflow_in_bytes{instance_type='switch', collect_type='netflow', __$labels__}) by (instance_id)")
            ],
            (2, "device_flow_bytes_rate"): [
                _metric("sum(netflow_in_bytes{instance_type='router', collect_type='netflow', __$labels__}) by (instance_id)")
            ],
        },
    )
    captured = []

    class FakeVM:
        def query_range(self, query, start, end, step):
            captured.append(query)
            assert "topk" not in query.lower()
            if "instance_type='switch'" in query:
                result = [{"metric": {"instance_id": "sw-1"}, "values": [[1, "10"], [2, "20"]]}]
            else:
                result = [{"metric": {"instance_id": "rt-1"}, "values": [[1, "5"], [2, "7"]]}]
            return {"status": "success", "data": {"result": result}}

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    out = nm.query_metric_series(
        metric="device_flow_bytes_rate",
        mode="range",
        instance_ids=["sw-1", "rt-1", "sw-denied"],
        time=TIME_RANGE,
        user_info=USER,
    )
    assert out["result"] is True
    assert out["data"] == {"total": [[1.0, 15.0], [2.0, 27.0]]}
    assert any("instance_type='switch'" in query for query in captured)
    assert any("instance_type='router'" in query for query in captured)


def test_query_metric_series_instant_unwraps_topk_and_maps_conversation(monkeypatch):
    switch = _object(1, "Switch")
    _patch_scope(monkeypatch, {"sw-1": _instance("sw-1", switch)})
    _patch_metrics(
        monkeypatch,
        {
            (1, "device_flow_top_conversation_bytes_rate"): [
                _metric(
                    "topk(10, sum(netflow_in_bytes{instance_type='switch', __$labels__}) by (instance_id, src, dst, protocol, dst_port))",
                    dimensions=[
                        {"name": "src"},
                        {"name": "dst"},
                        {"name": "protocol"},
                        {"name": "dst_port"},
                    ],
                )
            ]
        },
    )

    class FakeVM:
        def query(self, query, step="5m", time=None, lookback_delta=None):
            assert "topk" not in query.lower()
            assert "avg_over_time" in query
            assert "[3600s]" in query
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {
                                "src": "10.1.1.23",
                                "dst": "172.16.8.20",
                                "protocol": "6",
                                "dst_port": "443",
                            },
                            "value": [1, "80"],
                        }
                    ]
                },
            }

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    out = nm.query_metric_series(
        metric="device_flow_top_conversation_bytes_rate",
        mode="instant",
        instance_ids=["sw-1"],
        time=TIME_RANGE,
        user_info=USER,
    )
    assert out["result"] is True
    assert out["data"][0]["name"] == "10.1.1.23 → 172.16.8.20:443"
    assert out["data"][0]["protocol"] == "TCP"
    assert out["data"][0]["value"] == 80.0


def test_query_metric_series_collect_type_filters_plugins(monkeypatch):
    switch = _object(1, "Switch")
    _patch_scope(monkeypatch, {"sw-1": _instance("sw-1", switch, protocols=("netflow", "sflow"))})
    _patch_metrics(
        monkeypatch,
        {
            (1, "device_flow_bytes_rate"): [
                _metric("sum(sflow_bytes{__$labels__}) by (instance_id)", collect_type="sflow"),
                _metric("sum(netflow_in_bytes{__$labels__}) by (instance_id)", collect_type="netflow"),
            ]
        },
    )
    captured = []

    class FakeVM:
        def query(self, query, step="5m", time=None, lookback_delta=None):
            captured.append(query)
            return {"status": "success", "data": {"result": [{"metric": {}, "value": [1, "3"]}]}}

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    out = nm.query_metric_series(
        metric="device_flow_bytes_rate",
        mode="instant",
        collect_type="netflow",
        instance_ids=["sw-1"],
        time=TIME_RANGE,
        user_info=USER,
    )
    assert out["result"] is True
    assert out["data"] == [{"rank": 1, "name": "total", "value": 3.0}]
    assert captured and "netflow" in captured[0]
    assert all("sflow" not in query for query in captured)


def test_query_metric_series_missing_metric_fails(monkeypatch):
    switch = _object(1, "Switch")
    _patch_scope(monkeypatch, {"sw-1": _instance("sw-1", switch)})
    _patch_metrics(monkeypatch, {})

    class FailVM:
        def __init__(self):
            raise AssertionError("missing metric must not query")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    out = nm.query_metric_series(
        metric="device_flow_bytes_rate",
        mode="instant",
        instance_ids=["sw-1"],
        time=TIME_RANGE,
        user_info=USER,
    )
    assert out["result"] is False
    assert "指标不存在" in out["message"]


def test_query_metric_series_vm_failure_returns_generic_message(monkeypatch):
    switch = _object(1, "Switch")
    _patch_scope(monkeypatch, {"sw-1": _instance("sw-1", switch)})
    _patch_metrics(
        monkeypatch,
        {(1, "device_flow_bytes_rate"): [_metric("sum(netflow_in_bytes{instance_type='switch', __$labels__}) by (instance_id)")]},
    )

    class BoomVM:
        def query_range(self, query, start, end, step):
            raise RuntimeError(query)

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", BoomVM)
    out = nm.query_metric_series(
        metric="device_flow_bytes_rate",
        mode="range",
        instance_ids=["sw-1"],
        time=TIME_RANGE,
        user_info=USER,
    )
    assert out == {"result": False, "data": {}, "message": "指标查询失败"}
