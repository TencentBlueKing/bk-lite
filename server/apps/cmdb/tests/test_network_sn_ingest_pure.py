# -*- coding: utf-8 -*-
"""网络设备 SN 表从 VictoriaMetrics 行归并到设备实例，不落入接口。"""
import json
from collections import defaultdict

import pytest

from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics
from apps.cmdb.collection.plugins.base import bind_collection_mapping
from apps.cmdb.collection.plugins.community.network.plugins import NETWORK_DEVICE_MAPPING, NETWORK_INTERFACE_MAPPING

pytestmark = pytest.mark.unit

HOST = "10.10.69.248"
OID = "1.3.6.1.4.1.9.1.3210"


def _metric(name, **labels):
    return {"metric": {"__name__": name, "instance_id": "cmdb_1", **labels}, "value": [9999999999, "1"]}


def _plugin(monkeypatch):
    plugin = CollectNetworkMetrics.__new__(CollectNetworkMetrics)
    plugin.timestamp_gt = False
    plugin.sn_rows = {}
    plugin.instance_id_map = {}
    plugin.result = {}
    plugin.interfaces_data = {}
    plugin.interface_index_map = {}
    plugin.interface_name_map = defaultdict(dict)
    plugin.is_topo = False
    plugin.interface_status_map = {"1": "UP", "2": "Down", "3": "Testing"}
    plugin.oid_map = {OID: {"model": "C1200-8T-D", "oid": OID, "brand": "Cisco", "device_type": "switch", "built_in": True}}
    plugin.collection_metrics_dict = {
        "network_system_info_gauge": [],
        "network_interfaces_info_gauge": [],
        "network_sn_info_gauge": [],
    }
    plugin._device_map = bind_collection_mapping(plugin, NETWORK_DEVICE_MAPPING)
    plugin._interface_map = bind_collection_mapping(plugin, NETWORK_INTERFACE_MAPPING)
    monkeypatch.setattr(CollectNetworkMetrics, "device_map", property(lambda self: self._device_map))
    monkeypatch.setattr(CollectNetworkMetrics, "model_field_mapping", property(lambda self: self._interface_map))
    return plugin


def _system(**extra):
    labels = {"host": HOST, "ip_addr": HOST, "sysobjectid": OID, "port": "161", "sn_collected": "true"}
    labels.update(extra)
    return _metric("network_system_info_gauge", **labels)


def test_collected_serial_rows_become_device_table_not_interfaces(monkeypatch):
    plugin = _plugin(monkeypatch)
    plugin.format_data(
        {
            "result": [
                _system(),
                _metric(
                    "network_sn_info_gauge",
                    host=HOST,
                    oid="1.3.6.1.2.1.47.1.1.1.1.11.67109120",
                    serial="PSZ27281ATF",
                    entity="chassis / C1200-8T-D",
                    index="67109120",
                ),
                _metric(
                    "network_sn_info_gauge",
                    host=HOST,
                    oid="1.3.6.1.2.1.47.1.1.1.1.11.8",
                    serial="   ",
                    entity="Board",
                ),
                _metric("network_interfaces_info_gauge", host=HOST, index="1", description="Gi1", oper_status="1"),
            ]
        }
    )
    plugin.format_metrics()

    device = plugin.result["switch"][0]
    assert json.loads(device["sn"]) == [
        {
            "oid": "1.3.6.1.2.1.47.1.1.1.1.11.67109120",
            "serial": "PSZ27281ATF",
            "entity": "chassis / C1200-8T-D",
        }
    ]
    assert [item["name"] for item in plugin.result["interface"]] == ["Gi1"]


def test_duplicate_serial_on_different_entities_stays_two_rows(monkeypatch):
    plugin = _plugin(monkeypatch)
    plugin.format_data(
        {
            "result": [
                _system(host="10.10.69.247", ip_addr="10.10.69.247"),
                _metric(
                    "network_sn_info_gauge",
                    host="10.10.69.247",
                    oid="1.3.6.1.2.1.47.1.1.1.1.11.67108867",
                    serial="4E2480048371",
                    entity="chassis / HUAWEI S5735 Routing Switch",
                ),
                _metric(
                    "network_sn_info_gauge",
                    host="10.10.69.247",
                    oid="1.3.6.1.2.1.47.1.1.1.1.11.67108873",
                    serial="4E2480048371",
                    entity="MPU Board 0",
                ),
            ]
        }
    )
    plugin.format_metrics()

    rows = json.loads(plugin.result["switch"][0]["sn"])
    assert [row["entity"] for row in rows] == ["chassis / HUAWEI S5735 Routing Switch", "MPU Board 0"]
    assert {row["serial"] for row in rows} == {"4E2480048371"}


def test_failed_entity_walk_omits_sn_field(monkeypatch):
    plugin = _plugin(monkeypatch)
    plugin.format_data({"result": [_system(sn_collected="false")]})
    plugin.format_metrics()

    assert "sn" not in plugin.result["switch"][0]


def test_successful_walk_with_no_serials_writes_empty_table(monkeypatch):
    plugin = _plugin(monkeypatch)
    plugin.format_data({"result": [_system()]})
    plugin.format_metrics()

    assert plugin.result["switch"][0]["sn"] == "[]"
