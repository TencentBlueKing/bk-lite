"""rpc.monitor 转发契约测试。

覆盖 Monitor（permission/NATS 形态）与 MonitorOperationAnaRpc（OperationAnalysisRpc）
两个客户端的方法名 + 参数转发契约。替换 self.client 为记录器，不触达真实 NATS。
"""
import pydantic.root_model  # noqa

import pytest

from apps.rpc.monitor import Monitor, MonitorOperationAnaRpc

pytestmark = pytest.mark.unit


class _Recorder:
    def __init__(self):
        self.calls = []

    def run(self, method_name, *args, **kwargs):
        self.calls.append((method_name, args, kwargs))
        return {"result": True}


def _last(rec):
    return rec.calls[-1]


@pytest.fixture
def monitor(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    m = Monitor(is_local_client=False)
    m.client = _Recorder()
    return m


@pytest.fixture
def ana_rpc():
    rpc = MonitorOperationAnaRpc()
    rpc.client = _Recorder()
    return rpc


def test_monitor_get_module_data(monitor):
    monitor.get_module_data(module="cpu", page=1)
    assert _last(monitor.client) == ("get_monitor_module_data", (), {"module": "cpu", "page": 1})


def test_monitor_get_module_list(monitor):
    monitor.get_module_list(module="cpu")
    assert _last(monitor.client) == ("get_monitor_module_list", (), {"module": "cpu"})


def test_monitor_local_client_appclient_path(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    m = Monitor(is_local_client=True)
    assert m.client.path == "apps.monitor.nats.permission"


def test_create_monitor_object_type(ana_rpc):
    ana_rpc.create_monitor_object_type({"name": "t"}, user_info={"team": 1})
    assert _last(ana_rpc.client) == (
        "create_monitor_object_type",
        (),
        {"data": {"name": "t"}, "user_info": {"team": 1}},
    )


def test_create_monitor_object(ana_rpc):
    ana_rpc.create_monitor_object({"x": 1})
    assert _last(ana_rpc.client) == ("create_monitor_object", (), {"data": {"x": 1}})


def test_create_monitor_plugin(ana_rpc):
    ana_rpc.create_monitor_plugin({"p": 1})
    assert _last(ana_rpc.client) == ("create_monitor_plugin", (), {"data": {"p": 1}})


def test_create_metric_group(ana_rpc):
    ana_rpc.create_metric_group({"g": 1})
    assert _last(ana_rpc.client) == ("create_metric_group", (), {"data": {"g": 1}})


def test_create_metric(ana_rpc):
    ana_rpc.create_metric({"m": 1})
    assert _last(ana_rpc.client) == ("create_metric", (), {"data": {"m": 1}})


def test_create_monitor_policy(ana_rpc):
    ana_rpc.create_monitor_policy({"pol": 1})
    assert _last(ana_rpc.client) == ("create_monitor_policy", (), {"data": {"pol": 1}})


def test_monitor_objects(ana_rpc):
    ana_rpc.monitor_objects(user_info={"team": 2})
    assert _last(ana_rpc.client) == ("monitor_objects", (), {"user_info": {"team": 2}})


def test_monitor_object_instance_count(ana_rpc):
    ana_rpc.monitor_object_instance_count()
    assert _last(ana_rpc.client) == ("monitor_object_instance_count", (), {})


def test_monitor_metrics_具名monitor_obj_id(ana_rpc):
    ana_rpc.monitor_metrics("obj1", extra=1)
    assert _last(ana_rpc.client) == ("monitor_metrics", (), {"monitor_obj_id": "obj1", "extra": 1})


def test_monitor_object_instances(ana_rpc):
    ana_rpc.monitor_object_instances("obj2", user_info={"team": 1})
    assert _last(ana_rpc.client) == (
        "monitor_object_instances",
        (),
        {"monitor_obj_id": "obj2", "user_info": {"team": 1}},
    )


def test_monitor_instance_metrics(ana_rpc):
    qd = {"monitor_obj_id": "o", "instance_id": "i"}
    ana_rpc.monitor_instance_metrics(qd)
    assert _last(ana_rpc.client) == ("monitor_instance_metrics", (), {"query_data": qd})


def test_query_monitor_data_by_metric(ana_rpc):
    qd = {"metric": "cpu"}
    ana_rpc.query_monitor_data_by_metric(qd)
    assert _last(ana_rpc.client) == ("query_monitor_data_by_metric", (), {"query_data": qd})


def test_query_range_默认step(ana_rpc):
    ana_rpc.query_range("up", "1h")
    assert _last(ana_rpc.client) == ("mm_query_range", (), {"query": "up", "time_range": "1h", "step": "5m"})


def test_query_默认step(ana_rpc):
    ana_rpc.query("up")
    assert _last(ana_rpc.client) == ("mm_query", (), {"query": "up", "step": "5m"})


def test_query_monitor_alert_segments(ana_rpc):
    qd = {"monitor_obj_id": "o"}
    ana_rpc.query_monitor_alert_segments(qd)
    assert _last(ana_rpc.client) == ("query_monitor_alert_segments", (), {"query_data": qd})


def test_query_latest_active_alerts(ana_rpc):
    qd = {"limit": 5}
    ana_rpc.query_latest_active_alerts(qd)
    assert _last(ana_rpc.client) == ("query_latest_active_alerts", (), {"query_data": qd})
