# -*- coding: utf-8 -*-
"""KeepAlive 采集模型对齐修复测试。"""
import pytest


def test_keepalive_plugin_registered_under_model_id_keepalive():
    from apps.cmdb.collection.plugins import get_collection_plugin
    from apps.cmdb.constants.constants import CollectPluginTypes

    plugin_cls = get_collection_plugin(CollectPluginTypes.MIDDLEWARE, "keepalive")
    assert plugin_cls.supported_model_id == "keepalive"
    assert tuple(plugin_cls.metric_names) == ("keepalived_info_gauge",)


@pytest.mark.django_db
def test_keepalive_format_metrics_lands_under_keepalive(monkeypatch):
    from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics

    class _FakeInst:
        model_id = "keepalive"
        instances = [{"inst_name": "10.0.0.5-keepalive-51"}]

    monkeypatch.setattr(MiddlewareCollectMetrics, "get_collect_inst", lambda self: _FakeInst())

    runner = MiddlewareCollectMetrics(inst_name="10.0.0.5-keepalive-51", inst_id=1, task_id=9001)

    import time
    ts = int(time.time()) - 60  # 距今 1 分钟，避免被 timestamp_gt_one_day_ago 过滤
    vm_response = {
        "result": [
            {
                "metric": {
                    "__name__": "keepalived_info_gauge",
                    "collect_status": "success",
                    "ip_addr": "10.0.0.5",
                    "version": "2.2.4",
                    "priority": "100",
                    "state": "MASTER",
                    "virtual_router_id": "51",
                    "user_name": "root",
                    "install_path": "/usr/local/keepalived",
                    "config_file": "/etc/keepalived/keepalived.conf",
                },
                "value": [ts, "1"],
            }
        ]
    }
    runner.format_data(vm_response)
    runner.format_metrics()

    assert "keepalive" in runner.result
    inst = runner.result["keepalive"][0]
    assert inst["ip_addr"] == "10.0.0.5"
    assert inst["virtual_router_id"] == "51"
    assert inst["state"] == "MASTER"
    assert inst["inst_name"] == "10.0.0.5-keepalive-51"


def test_keepalive_in_collect_obj_tree():
    from apps.cmdb.services.collect_object_tree import get_collect_obj_tree

    tree = get_collect_obj_tree()
    middleware = next(g for g in tree if g.get("id") == "middleware")
    model_ids = {c.get("model_id") for c in middleware.get("children", [])}
    assert "keepalive" in model_ids


def test_keepalive_metric_map_has_key():
    from apps.cmdb.collection.constants import MIDDLEWARE_METRIC_MAP

    assert MIDDLEWARE_METRIC_MAP.get("keepalive") == ["keepalived_info_gauge"]
