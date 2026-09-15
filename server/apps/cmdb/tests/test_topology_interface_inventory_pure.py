# -*- coding: utf-8 -*-
"""拓扑重放用已入库接口解析/写边：不依赖本轮设备指标窗口。"""
from unittest import mock

import pytest

from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics
from apps.cmdb.collection.constants import NETWORK_INTERFACES_RELATIONS
from apps.cmdb.collection.topology_interface_inventory import (
    apply_topology_relationships,
    match_port_to_inventory_inst_name,
    merge_inventory_port_index,
)
from apps.cmdb.services.topology_replay_service import TopologyReplayCollector
from apps.cmdb.tests.test_collect_management_service import FakeGraph, _patch_common
from apps.cmdb.tests.test_network_topology_pipeline import _lldp_authoritative_rows, _make_plugin
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = [pytest.mark.unit]

IFACE_A = "10.0.0.1-switch-Gi0/0/7"
IFACE_B = "10.0.0.2-switch-Gi0/0/9"


def _iface(inst_name, *, name, ip, mac="", collect_task="7001", _id=1):
    return {
        "_id": _id,
        "model_id": "interface",
        "inst_name": inst_name,
        "name": name,
        "self_device": f"{ip}-switch",
        "mac": mac,
        "collect_task": collect_task,
    }


def test_match_port_by_unique_interface_name():
    port = {"device_id": "10.0.0.1", "ifindex": "7", "ifname": "Gi0/0/7", "ifalias": "", "ifdescr": "GigabitEthernet0/0/7"}
    interfaces = [
        _iface(IFACE_A, name="Gi0/0/7", ip="10.0.0.1"),
        _iface(IFACE_B, name="Gi0/0/9", ip="10.0.0.2", _id=2),
    ]
    assert match_port_to_inventory_inst_name(port, interfaces) == IFACE_A


def test_match_port_cdp_g_digit_to_inventory_gi():
    port = {"device_id": "10.0.0.2", "ifindex": "9", "ifname": "g2/1/1"}
    interfaces = [_iface("10.0.0.2-switch-Gi2/1/1", name="Gi2/1/1", ip="10.0.0.2")]
    assert match_port_to_inventory_inst_name(port, interfaces) == "10.0.0.2-switch-Gi2/1/1"


def test_match_port_uses_inst_name_suffix_when_name_is_alias():
    port = {"device_id": "10.0.0.2", "ifindex": "9", "ifname": "g2/1/1"}
    interfaces = [_iface("10.0.0.2-switch-Gi2/1/1", name="uplink-core", ip="10.0.0.2")]
    assert match_port_to_inventory_inst_name(port, interfaces) == "10.0.0.2-switch-Gi2/1/1"


def test_match_port_does_not_prefix_hit_neighbor_ip():
    port = {"device_id": "10.0.0.1", "ifindex": "7", "ifname": "Gi0/0/7"}
    interfaces = [_iface("10.0.0.10-switch-Gi0/0/7", name="Gi0/0/7", ip="10.0.0.10")]
    assert match_port_to_inventory_inst_name(port, interfaces) is None


def test_match_port_ambiguous_name_returns_none():
    port = {"device_id": "10.0.0.1", "ifindex": "7", "ifname": "Gi0/0/7"}
    interfaces = [
        _iface("10.0.0.1-switch-a", name="Gi0/0/7", ip="10.0.0.1", _id=1),
        _iface("10.0.0.1-switch-b", name="Gi0/0/7", ip="10.0.0.1", _id=2),
    ]
    assert match_port_to_inventory_inst_name(port, interfaces) is None


def test_merge_inventory_port_index_fills_missing_ifindex_keys():
    index_map = {("10.0.0.1", "7"): IFACE_A}
    ports = [
        {"device_id": "10.0.0.1", "ifindex": "7", "ifname": "Gi0/0/7"},
        {"device_id": "10.0.0.2", "ifindex": "9", "ifname": "Gi0/0/9", "ifdescr": "GigabitEthernet0/0/9"},
    ]
    interfaces = [
        _iface(IFACE_A, name="Gi0/0/7", ip="10.0.0.1"),
        _iface(IFACE_B, name="Gi0/0/9", ip="10.0.0.2", _id=2),
    ]
    merge_inventory_port_index(index_map, ports, interfaces)
    assert index_map[("10.0.0.1", "7")] == IFACE_A
    assert index_map[("10.0.0.2", "9")] == IFACE_B


def test_pipeline_resolves_connect_from_inventory_when_round_index_empty():
    plugin = _make_plugin()
    plugin.interface_index_map = {}
    interfaces = [
        _iface(IFACE_A, name="Gi0/0/7", ip="dev-a", mac="aa:aa:aa:aa:aa:01"),
        _iface(IFACE_B, name="Gi0/0/9", ip="dev-b", mac="bb:bb:bb:bb:bb:01", _id=2),
    ]
    with (
        mock.patch("apps.cmdb.collection.collect_plugin.network.load_task_interfaces_safe", return_value=interfaces),
        mock.patch.object(CollectNetworkMetrics, "save_topology_snapshot"),
    ):
        relationships = plugin.collect_topology_relationships([], _lldp_authoritative_rows())
    assert relationships == [
        {
            "source_inst_name": IFACE_A,
            "target_inst_name": IFACE_B,
            "model_id": "interface",
            "asst_id": "connect",
            "model_asst_id": "interface_connect_interface",
        }
    ]


def test_topology_replay_collector_queries_only_topo_gauge():
    collector = TopologyReplayCollector.__new__(TopologyReplayCollector)
    assert list(TopologyReplayCollector._metrics.fget(collector)) == [NETWORK_INTERFACES_RELATIONS]


def _patch_inventory_graph(monkeypatch, fake):
    _patch_common(monkeypatch, fake)
    monkeypatch.setattr("apps.cmdb.graph.drivers.graph_client.GraphClient", lambda *a, **k: fake)


def test_apply_topology_relationships_writes_connect_without_interface_crud(monkeypatch):
    fake = FakeGraph(
        query_entity=lambda _label, _conds: (
            [
                {"_id": 11, "inst_name": IFACE_B, "model_id": "interface"},
            ],
            1,
        )
    )
    fake.query_entity_by_inst_names = lambda names, model_id=None: [
        {"_id": 10, "inst_name": IFACE_A, "model_id": "interface", "collect_task": "7001"}
    ]
    _patch_inventory_graph(monkeypatch, fake)

    result = apply_topology_relationships(
        [
            {
                "source_inst_name": IFACE_A,
                "target_inst_name": IFACE_B,
                "model_id": "interface",
                "asst_id": "connect",
                "model_asst_id": "interface_connect_interface",
            }
        ],
        task_id="7001",
    )
    assert result["success"] == 1
    assert result["failed"] == 0
    args = fake.created_edges[0][0]
    assert {args[1], args[3]} == {10, 11}
    assert args[5]["model_asst_id"] == "interface_connect_interface"


def test_apply_topology_relationships_edge_exists_is_success(monkeypatch):
    fake = FakeGraph(
        query_entity=lambda _label, _conds: ([{"_id": 11, "inst_name": IFACE_B, "model_id": "interface"}], 1),
        create_edge_raises=BaseAppException("edge already exists"),
    )
    fake.query_entity_by_inst_names = lambda names, model_id=None: [
        {"_id": 10, "inst_name": IFACE_A, "model_id": "interface", "collect_task": "7001"}
    ]
    _patch_inventory_graph(monkeypatch, fake)

    result = apply_topology_relationships(
        [
            {
                "source_inst_name": IFACE_A,
                "target_inst_name": IFACE_B,
                "model_id": "interface",
                "asst_id": "connect",
                "model_asst_id": "interface_connect_interface",
            }
        ],
        task_id="7001",
    )
    assert result["success"] == 1
    assert result["failed"] == 0
