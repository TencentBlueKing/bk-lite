# -- coding: utf-8 --
# network.py 拓扑关系发现新流水线的单元测试（mock DB 访问）。
from types import SimpleNamespace
from unittest import mock

import pytest

from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics

pytestmark = [pytest.mark.unit]


def _make_plugin(min_confidence=0.0, snapshot=None):
    plugin = CollectNetworkMetrics.__new__(CollectNetworkMetrics)
    plugin.collect_inst = SimpleNamespace(
        topology_contract={
            "has_network_topo": True,
            "topology_protocols": ["lldp", "cdp", "fdb", "arp"],
            "topology_fallback_strategy": "prefer_neighbors_then_fdb_then_arp",
            "min_confidence": min_confidence,
        },
        topology_snapshot=snapshot or {},
    )
    plugin.task_id = 7001
    plugin.interface_index_map = {
        ("dev-a", "7"): "10.0.0.1-switch-Gi0/0/7",
        ("dev-b", "9"): "10.0.0.2-switch-Gi0/0/9",
    }
    return plugin


def _topo_rows():
    def row(instance_id, tag, ifindex, val, group):
        return {"instance_id": instance_id, "tag": tag, "ifindex": ifindex, "val": val, "group": group}

    return [
        # dev-a 接口与 MAC，ARP 看到 dev-b
        row("dev-a", "IFTable-IfDescr", "7", "Gi0/0/7", "interfaces"),
        row("dev-a", "IFTable-PhysAddress", "7", "0xaaaaaaaaaa01", "interfaces"),
        row("dev-a", "ARP-IfIndex", "10.0.0.2", "7", "arp"),
        row("dev-a", "ARP-PhysAddress", "10.0.0.2", "0xbbbbbbbbbb01", "arp"),
        # dev-b 接口与 MAC
        row("dev-b", "IFTable-IfDescr", "9", "Gi0/0/9", "interfaces"),
        row("dev-b", "IFTable-PhysAddress", "9", "0xbbbbbbbbbb01", "interfaces"),
    ]


def test_pipeline_produces_interface_relationships():
    plugin = _make_plugin()
    with mock.patch.object(CollectNetworkMetrics, "save_topology_snapshot") as save:
        relationships = plugin.collect_topology_relationships([], _topo_rows())
    assert relationships == [
        {
            "source_inst_name": "10.0.0.1-switch-Gi0/0/7",
            "target_inst_name": "10.0.0.2-switch-Gi0/0/9",
            "model_id": "interface",
            "asst_id": "connect",
            "model_asst_id": "interface_connect_interface",
        }
    ]
    save.assert_called_once()


def test_min_confidence_filters_inferred_links():
    plugin = _make_plugin(min_confidence=0.9)  # arp 推断 confidence=50，应被过滤
    with mock.patch.object(CollectNetworkMetrics, "save_topology_snapshot"):
        relationships = plugin.collect_topology_relationships([], _topo_rows())
    assert relationships == []


def test_unmappable_port_is_dropped_not_crash():
    plugin = _make_plugin()
    plugin.interface_index_map = {("dev-a", "7"): "10.0.0.1-switch-Gi0/0/7"}  # dev-b 接口不在 CMDB 实例里
    with mock.patch.object(CollectNetworkMetrics, "save_topology_snapshot"):
        relationships = plugin.collect_topology_relationships([], _topo_rows())
    assert relationships == []


def test_snapshot_written_with_links_and_process_data():
    plugin = _make_plugin()
    captured = {}
    with mock.patch.object(
        plugin, "save_topology_snapshot",
        side_effect=lambda snapshot: captured.update(snapshot),
    ):
        plugin.collect_topology_relationships([], _topo_rows())
    assert captured["summary"]["devices"] == 2
    assert len(captured["links"]) == 1
    assert captured["links"][0]["evidence_source"] == "arp"
    assert "supporting_evidence" not in captured["links"][0]  # 快照瘦身
    assert "unresolved_neighbors" in captured
    assert "stale_links" in captured
    assert "dropped" in captured


def test_previous_snapshot_marks_missing_link_stale():
    previous = {
        "links": [
            {
                "relationship_id": "auth:dev-x:lldp:Gi1",
                "relationship_type": "authoritative",
                "evidence_source": "lldp",
                "confidence": 100,
                "source_device": "dev-x",
                "source_port_id": "dev-x:1",
                "target_port_id": "dev-y:2",
                "source_inst_name": "x-Gi1",
                "target_inst_name": "y-Gi2",
            }
        ]
    }
    plugin = _make_plugin(snapshot=previous)
    captured = {}
    with mock.patch.object(
        plugin, "save_topology_snapshot",
        side_effect=lambda snapshot: captured.update(snapshot),
    ):
        plugin.collect_topology_relationships([], _topo_rows())
    stale_ids = {item.get("relationship_id") for item in captured["stale_links"]}
    assert "auth:dev-x:lldp:Gi1" in stale_ids


def _lldp_authoritative_rows():
    """LLDP 邻居证据：dev-a Gi0/0/7 <-> dev-b Gi0/0/9，可产出 authoritative 链路"""

    def row(instance_id, tag, ifindex, val, group):
        return {"instance_id": instance_id, "tag": tag, "ifindex": ifindex, "val": val, "group": group}

    return [
        row("dev-a", "System-SysName", "", "dev-a", "system"),
        row("dev-a", "IFXTable-IfName", "7", "Gi0/0/7", "interfaces"),
        row("dev-a", "LLDP-RemSysName", "0.7.1", "dev-b", "neighbors"),
        row("dev-a", "LLDP-RemPortId", "0.7.1", "Gi0/0/9", "neighbors"),
        row("dev-a", "LLDP-RemPortIdSubtype", "0.7.1", "5", "neighbors"),
        row("dev-a", "LLDP-LocPortId", "7", "Gi0/0/7", "neighbors"),
        row("dev-a", "LLDP-LocPortIdSubtype", "7", "5", "neighbors"),
        row("dev-b", "System-SysName", "", "dev-b", "system"),
        row("dev-b", "IFXTable-IfName", "9", "Gi0/0/9", "interfaces"),
    ]


def test_authoritative_link_bypasses_min_confidence():
    # min_confidence=0.99（→99）远高于常规推断阈值，authoritative 链路仍应产出关系
    plugin = _make_plugin(min_confidence=0.99)
    with mock.patch.object(CollectNetworkMetrics, "save_topology_snapshot"):
        relationships = plugin.collect_topology_relationships([], _lldp_authoritative_rows())
    assert relationships == [
        {
            "source_inst_name": "10.0.0.1-switch-Gi0/0/7",
            "target_inst_name": "10.0.0.2-switch-Gi0/0/9",
            "model_id": "interface",
            "asst_id": "connect",
            "model_asst_id": "interface_connect_interface",
        }
    ]


def test_snapshot_unresolved_neighbors_are_slimmed():
    def row(instance_id, tag, ifindex, val, group):
        return {"instance_id": instance_id, "tag": tag, "ifindex": ifindex, "val": val, "group": group}

    # 远端 sysname "ghost" 无对应设备，邻居无法解析 → 进入 unresolved_neighbors
    rows = [
        row("dev-a", "System-SysName", "", "dev-a", "system"),
        row("dev-a", "IFXTable-IfName", "7", "Gi0/0/7", "interfaces"),
        row("dev-a", "LLDP-RemSysName", "0.7.1", "ghost", "neighbors"),
        row("dev-a", "LLDP-RemPortId", "0.7.1", "Gi0/0/99", "neighbors"),
        row("dev-a", "LLDP-RemPortIdSubtype", "0.7.1", "5", "neighbors"),
        row("dev-a", "LLDP-LocPortId", "7", "Gi0/0/7", "neighbors"),
        row("dev-a", "LLDP-LocPortIdSubtype", "7", "5", "neighbors"),
    ]
    plugin = _make_plugin()
    captured = {}
    with mock.patch.object(
        plugin, "save_topology_snapshot",
        side_effect=lambda snapshot: captured.update(snapshot),
    ):
        plugin.collect_topology_relationships([], rows)
    unresolved = captured["unresolved_neighbors"]
    assert unresolved  # 确实触发 unresolved 分支
    assert all("raw_remote_fields" not in item for item in unresolved)
