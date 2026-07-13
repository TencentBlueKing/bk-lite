# -*- coding: utf-8 -*-
import time
import types

from apps.cmdb.constants.constants import CollectPluginTypes


def test_ip_discovery_plugin_registered():
    from apps.cmdb.collection.plugins import get_collection_plugin

    plugin_cls = get_collection_plugin(CollectPluginTypes.IP, "ip")
    assert plugin_cls.supported_model_id == "ip"
    assert plugin_cls.supported_task_type == CollectPluginTypes.IP
    assert tuple(plugin_cls.metric_names) == ("ip_info_gauge", "ip_info")


def test_ip_discovery_plugin_applies_vm_rows(monkeypatch):
    from apps.cmdb.collection.plugins.community.ipam.ip import IPAMDiscoveryCollectionPlugin

    task = types.SimpleNamespace(
        id=7001,
        model_id="ip",
        instances={},
        params={"subnet_ids": [101]},
    )
    applied = {}

    monkeypatch.setattr(IPAMDiscoveryCollectionPlugin, "get_collect_inst", lambda self: task)
    monkeypatch.setattr(
        "apps.cmdb.services.ipam_discovery.apply_ip_discovery_vm_rows",
        lambda collect_task, rows: applied.update({"task": collect_task, "rows": rows}) or {
            "created": 1,
            "updated": 0,
            "offline": 0,
            "format_data": {"add": [{"_status": "success", "ip_addr": "10.0.1.2"}], "update": [], "delete": [], "association": [], "all": 1},
        },
    )

    runner = IPAMDiscoveryCollectionPlugin(inst_name="", inst_id=None, task_id=7001)
    runner.format_data(
        {
            "result": [
                {
                    "metric": {
                        "__name__": "ip_info_gauge",
                        "collect_status": "success",
                        "ip_addr": "10.0.1.2",
                        "ip_status": "online",
                        "subnet_id": "101",
                        "subnet_cidr": "10.0.1.0/24",
                        "mac": "00:0C:29:3A:7B:88",
                        "auto_collect": "true",
                    },
                    "value": [int(time.time()) - 60, "1"],
                }
            ]
        }
    )
    runner.format_metrics()

    assert applied["task"] is task
    assert applied["rows"] == [
        {
            "__name__": "ip_info_gauge",
            "collect_status": "success",
            "ip_addr": "10.0.1.2",
            "ip_status": "online",
            "subnet_id": "101",
            "subnet_cidr": "10.0.1.0/24",
            "mac": "00:0C:29:3A:7B:88",
            "auto_collect": "true",
        }
    ]
    assert runner.result["ip"] == []
    assert runner.result["__task_format_data__"]["all"] == 1
