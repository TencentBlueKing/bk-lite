# -*- coding: utf-8 -*-
"""接口缺 description 标签时不应整轮 KeyError。

FortiGate 等设备部分接口 ifDescr 为空。Prometheus 会丢掉空标签，采集结果里
就没有 description。旧代码 `data.get("alias", data["description"])` 的 default
会立即求值，即使 alias 存在也会 KeyError，format_metrics 中断；celery 把整轮
result 换成 {}，图库 0 条。
"""
from collections import defaultdict

import pytest

from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics
from apps.cmdb.collection.plugins.base import bind_collection_mapping
from apps.cmdb.collection.plugins.community.network.plugins import NETWORK_INTERFACE_MAPPING

pytestmark = pytest.mark.unit

DEVICE_ID = "10.0.0.8"
DEVICE_ROW = {
    "instance_id": DEVICE_ID,
    "ip_addr": DEVICE_ID,
    "device_type": "firewall",
}


def _plugin(monkeypatch):
    plugin = CollectNetworkMetrics.__new__(CollectNetworkMetrics)
    plugin.interface_status_map = {"1": "UP", "2": "Down", "3": "Testing"}
    plugin.instance_id_map = {DEVICE_ID: dict(DEVICE_ROW)}
    plugin.result = {}
    plugin.interfaces_data = {}
    plugin.interface_index_map = {}
    plugin.interface_name_map = defaultdict(dict)
    plugin.is_topo = False
    mapping = bind_collection_mapping(plugin, NETWORK_INTERFACE_MAPPING)
    monkeypatch.setattr(CollectNetworkMetrics, "model_field_mapping", property(lambda self: mapping))
    return plugin


def _iface(**metric):
    row = {"instance_id": DEVICE_ID, "index": "5", "mac_address": "aabbccddeeff", "oper_status": "1"}
    row.update(metric)
    return row


def test_dict_get_default_is_eager_even_when_alias_exists():
    data = {"alias": "wan1"}
    with pytest.raises(KeyError, match="description"):
        data.get("alias", data["description"])


def test_interface_name_prefers_ifdescr_over_alias():
    assert CollectNetworkMetrics.interface_name({"alias": "上联核心", "description": "GigabitEthernet0/0/1", "index": "7"}) == "GigabitEthernet0/0/1"


def test_interface_name_keeps_alias_when_description_label_dropped():
    assert CollectNetworkMetrics.interface_name({"alias": "wan1", "index": "5"}) == "wan1"


def test_interface_name_empty_alias_uses_ifdescr():
    assert CollectNetworkMetrics.interface_name({"alias": "", "description": "port1", "index": "7"}) == "port1"


def test_interface_name_blank_ifdescr_falls_back_to_index():
    assert CollectNetworkMetrics.interface_name({"index": "12"}) == "if12"


def test_interface_description_is_ifalias_only():
    assert CollectNetworkMetrics.interface_description({"alias": "上联核心", "description": "GigabitEthernet0/0/1"}) == "上联核心"
    assert CollectNetworkMetrics.interface_description({"description": "GigabitEthernet0/0/1"}) == ""
    assert CollectNetworkMetrics.interface_description({"alias": ""}) == ""


def test_set_interface_inst_name_reuses_interface_name(monkeypatch):
    plugin = _plugin(monkeypatch)
    assert plugin.set_interface_inst_name(_iface(alias="上联核心", description="GigabitEthernet0/0/1")) == "10.0.0.8-firewall-GigabitEthernet0/0/1"
    assert plugin.set_interface_inst_name(_iface(alias="wan1")) == "10.0.0.8-firewall-wan1"
    assert plugin.set_interface_inst_name(_iface(index="12")) == "10.0.0.8-firewall-if12"


def test_format_metrics_keeps_healthy_interfaces_when_one_missing_description(monkeypatch):
    plugin = _plugin(monkeypatch)
    plugin.collection_metrics_dict = {
        "network_interfaces_info_gauge": [
            _iface(index="1", alias="上联核心", description="GigabitEthernet0/0/1"),
            _iface(index="2", alias="ssl.root"),
            _iface(index="3"),
        ]
    }

    plugin.format_metrics()

    interfaces = plugin.result["interface"]
    assert [item["name"] for item in interfaces] == ["GigabitEthernet0/0/1", "ssl.root", "if3"]
    assert [item["description"] for item in interfaces] == ["上联核心", "ssl.root", ""]
    assert [item["inst_name"] for item in interfaces] == [
        "10.0.0.8-firewall-GigabitEthernet0/0/1",
        "10.0.0.8-firewall-ssl.root",
        "10.0.0.8-firewall-if3",
    ]
