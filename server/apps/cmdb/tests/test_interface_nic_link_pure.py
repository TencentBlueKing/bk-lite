# -*- coding: utf-8 -*-
"""网络拓扑关系计算 Step-2：FDB 学到的 MAC 匹配 physcial_server nic。

锁定：
- 匹配的是 FDB 学到的 MAC，不是交换机端口自身 MAC
- 命中已入库 nic 后写出 interface_connect_nic，不把 nic 改成 interface
- 未命中 MAC 丢弃并计数，不编造 nic/interface
- 交换机 interface↔interface 仍走原路径
- 不把逻辑主机 host 混进 nic 查找
- LLDP/CDP 未解析邻居若带 nic MAC，可顺带连上
"""
import logging
from unittest import mock

import pandas as pd
import pytest

from apps.cmdb.collection.common import Management
from apps.cmdb.collection.interface_nic_link import (
    _ENSURE_FAILED_TEMPLATE,
    INTERFACE_CONNECT_NIC,
    bind_fdb_learned_macs_to_nics,
    bind_unresolved_neighbors_to_nics,
    candidate_nic_lookup_macs,
    ensure_interface_connect_nic_association,
    inventory_interface_macs,
    nic_index_from_instances,
)
from apps.cmdb.tests.test_collect_management_service import FakeGraph, _patch_common
from apps.cmdb.tests.test_network_topology_pipeline import _make_plugin
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.unit

MODEL_CONFIG = "apps/cmdb/support-files/model_config.xlsx"
SERVER_NIC_MAC = "cc:cc:cc:cc:cc:cc"
SWITCH_B_MAC = "bb:bb:bb:bb:bb:01"
UNKNOWN_MAC = "dd:dd:dd:dd:dd:dd"
SOURCE_IFACE = "10.0.0.1-switch-Gi0/0/7"
PEER_IFACE = "10.0.0.2-switch-Gi0/0/9"


def _normalized(*, fdb=None, ports=None):
    return {
        "ports": ports
        or [
            {"device_id": "dev-a", "port_id": "dev-a:7", "ifindex": "7", "mac": "aa:aa:aa:aa:aa:01"},
            {"device_id": "dev-b", "port_id": "dev-b:9", "ifindex": "9", "mac": SWITCH_B_MAC},
        ],
        "fdb_observations": fdb or [],
    }


def _learned(mac, local_port_id="dev-a:7", status="learned"):
    return {
        "status": status,
        "source_device_id": "dev-a",
        "local_port_id": local_port_id,
        "mac": mac,
        "vlan": "10",
        "evidence_key": f"dev-a:fdb:{mac}",
    }


def _resolve(port_id):
    return {
        "dev-a:7": SOURCE_IFACE,
        "dev-b:9": PEER_IFACE,
    }.get(port_id)


def _nic_index(*macs):
    return {mac: {"inst_name": mac, "model_id": "nic"} for mac in macs}


def test_model_config_allows_interface_connect_nic():
    rows = pd.read_excel(MODEL_CONFIG, sheet_name="asso-interface", header=1)
    records = rows[["src_model_id", "dst_model_id", "asst_id", "mapping"]].dropna(how="all").to_dict("records")
    assert {
        "src_model_id": "interface",
        "dst_model_id": "nic",
        "asst_id": "connect",
        "mapping": "n:n",
    } in records
    assert {
        "src_model_id": "interface",
        "dst_model_id": "interface",
        "asst_id": "connect",
        "mapping": "n:n",
    } in records
    assert not any(row["dst_model_id"] == "host" and row["asst_id"] == "connect" for row in records)


def test_model_config_does_not_add_peer_mac_field_on_interface():
    attrs = pd.read_excel(MODEL_CONFIG, sheet_name="attr-interface", header=1)
    attr_ids = set(attrs["attr_id"].dropna().astype(str))
    assert "peer_mac" not in attr_ids
    assert "对端MAC" not in attr_ids
    assert "peer_mac_address" not in attr_ids


def test_nic_index_ignores_host_even_when_mac_matches():
    index = nic_index_from_instances(
        [
            {"model_id": "host", "inst_name": SERVER_NIC_MAC, "nic_mac": SERVER_NIC_MAC},
            {"model_id": "nic", "inst_name": SERVER_NIC_MAC, "nic_mac": SERVER_NIC_MAC},
            {"model_id": "interface", "inst_name": SERVER_NIC_MAC, "mac": SERVER_NIC_MAC},
        ]
    )
    assert list(index) == [SERVER_NIC_MAC]
    assert index[SERVER_NIC_MAC]["model_id"] == "nic"


def test_fdb_learned_mac_binds_existing_nic_not_switch_port_mac():
    normalized = _normalized(
        fdb=[
            _learned(SERVER_NIC_MAC),
            _learned("aa:aa:aa:aa:aa:01"),  # 交换机端口自身 MAC，不得当成对端
        ]
    )
    rels, unmatched, dropped = bind_fdb_learned_macs_to_nics(
        normalized=normalized,
        nic_index=_nic_index(SERVER_NIC_MAC),
        resolve_source_inst_name=_resolve,
    )
    assert rels == [
        {
            "source_inst_name": SOURCE_IFACE,
            "target_inst_name": SERVER_NIC_MAC,
            "model_id": "nic",
            "asst_id": "connect",
            "model_asst_id": INTERFACE_CONNECT_NIC,
        }
    ]
    assert unmatched == set()
    assert dropped == []
    assert inventory_interface_macs(normalized) == {"aa:aa:aa:aa:aa:01", SWITCH_B_MAC}


def test_unmatched_fdb_mac_is_dropped_and_counted_without_fabricating_nic():
    normalized = _normalized(fdb=[_learned(UNKNOWN_MAC), _learned(UNKNOWN_MAC)])
    rels, unmatched, dropped = bind_fdb_learned_macs_to_nics(
        normalized=normalized,
        nic_index={},
        resolve_source_inst_name=_resolve,
    )
    assert rels == []
    assert unmatched == {UNKNOWN_MAC}
    assert {item["drop_reason"] for item in dropped} == {"unmatched_mac"}


def test_fdb_mac_matching_inventory_interface_is_not_unmatched_or_nic():
    """交换机对端已经是 interface：保持原路径，不改写成 nic，也不计入 unmatched。"""
    normalized = _normalized(fdb=[_learned(SWITCH_B_MAC)])
    rels, unmatched, dropped = bind_fdb_learned_macs_to_nics(
        normalized=normalized,
        nic_index=_nic_index(SWITCH_B_MAC),
        resolve_source_inst_name=_resolve,
    )
    assert rels == []
    assert unmatched == set()
    assert dropped == []


def test_non_learned_fdb_status_is_ignored():
    normalized = _normalized(fdb=[_learned(SERVER_NIC_MAC, status="2")])
    rels, unmatched, dropped = bind_fdb_learned_macs_to_nics(
        normalized=normalized,
        nic_index=_nic_index(SERVER_NIC_MAC),
        resolve_source_inst_name=_resolve,
    )
    assert rels == []
    assert unmatched == set()
    assert dropped == []


def test_candidate_lookup_excludes_interface_macs_and_host_names():
    normalized = _normalized(fdb=[_learned(SERVER_NIC_MAC), _learned(SWITCH_B_MAC), _learned("aa:aa:aa:aa:aa:01")])
    unresolved = [
        {
            "protocol": "lldp",
            "resolution_state": "unresolved_remote",
            "remote_device_name": "ghost-host",
            "raw_remote_fields": {"LLDP-RemChassisId": SERVER_NIC_MAC.replace(":", "")},
        }
    ]
    assert candidate_nic_lookup_macs(normalized, unresolved) == {SERVER_NIC_MAC}


def test_lldp_unresolved_chassis_mac_binds_nic_as_bonus():
    rels = bind_unresolved_neighbors_to_nics(
        unresolved_neighbors=[
            {
                "protocol": "lldp",
                "resolution_state": "unresolved_remote",
                "source_port_id": "dev-a:7",
                "remote_device_name": "srv-1",
                "raw_remote_fields": {"LLDP-RemChassisId": "0xcccccccccccc"},
            }
        ],
        nic_index=_nic_index(SERVER_NIC_MAC),
        interface_macs={"aa:aa:aa:aa:aa:01"},
        resolve_source_inst_name=_resolve,
    )
    assert rels == [
        {
            "source_inst_name": SOURCE_IFACE,
            "target_inst_name": SERVER_NIC_MAC,
            "model_id": "nic",
            "asst_id": "connect",
            "model_asst_id": INTERFACE_CONNECT_NIC,
        }
    ]


def _fdb_rows(*, learned_mac_oid, peer_interface=False):
    def row(instance_id, tag, ifindex, val, group):
        return {"instance_id": instance_id, "tag": tag, "ifindex": ifindex, "val": val, "group": group}

    rows = [
        row("dev-a", "IFTable-IfDescr", "7", "Gi0/0/7", "interfaces"),
        row("dev-a", "IFTable-PhysAddress", "7", "0xaaaaaaaaaa01", "interfaces"),
        row("dev-a", "BRIDGE-BasePortIfIndex", "5", "7", "bridge"),
        row("dev-a", "FDB-Port", learned_mac_oid, "5", "fdb"),
        row("dev-a", "FDB-Status", learned_mac_oid, "3", "fdb"),
    ]
    if peer_interface:
        rows.extend(
            [
                row("dev-b", "IFTable-IfDescr", "9", "Gi0/0/9", "interfaces"),
                row("dev-b", "IFTable-PhysAddress", "9", "0xbbbbbbbbbb01", "interfaces"),
            ]
        )
    return rows


def test_pipeline_fdb_mac_writes_interface_connect_nic_on_source():
    plugin = _make_plugin()
    plugin.interfaces_data = {SOURCE_IFACE: {"inst_name": SOURCE_IFACE, "assos": []}}
    plugin.load_nic_mac_index = lambda macs: _nic_index(SERVER_NIC_MAC) if SERVER_NIC_MAC in macs else {}
    captured = {}
    rows = _fdb_rows(learned_mac_oid="204.204.204.204.204.204")
    with mock.patch.object(
        plugin,
        "save_topology_snapshot",
        side_effect=lambda snapshot: captured.update(snapshot),
    ), mock.patch(
        "apps.cmdb.collection.collect_plugin.network.ensure_interface_connect_nic_association",
        return_value=True,
    ):
        relationships = plugin.collect_topology_relationships([], rows)
        plugin.add_interface_assos(relationships)
        second = plugin.collect_topology_relationships([], rows)

    assert relationships == [
        {
            "source_inst_name": SOURCE_IFACE,
            "target_inst_name": SERVER_NIC_MAC,
            "model_id": "nic",
            "asst_id": "connect",
            "model_asst_id": INTERFACE_CONNECT_NIC,
        }
    ]
    assert plugin.interfaces_data[SOURCE_IFACE]["assos"] == [
        {
            "asst_id": "connect",
            "inst_name": SERVER_NIC_MAC,
            "model_asst_id": INTERFACE_CONNECT_NIC,
            "model_id": "nic",
        }
    ]
    assert captured["summary"]["unmatched_macs"] == 0
    assert captured["summary"]["nic_connects"] == 1
    assert second == relationships


def test_pipeline_unmatched_mac_increments_counter_and_creates_no_nic():
    plugin = _make_plugin()
    plugin.load_nic_mac_index = lambda macs: {}
    captured = {}
    with mock.patch.object(
        plugin,
        "save_topology_snapshot",
        side_effect=lambda snapshot: captured.update(snapshot),
    ):
        relationships = plugin.collect_topology_relationships([], _fdb_rows(learned_mac_oid="221.221.221.221.221.221"))
    assert relationships == []
    assert captured["summary"]["unmatched_macs"] == 1
    assert captured["summary"]["nic_connects"] == 0
    assert any(item.get("drop_reason") == "unmatched_mac" for item in captured["dropped"])


def test_pipeline_keeps_switch_switch_interface_connect_alongside_nic():
    plugin = _make_plugin()
    plugin.load_nic_mac_index = lambda macs: _nic_index(SERVER_NIC_MAC)
    captured = {}
    rows = _fdb_rows(learned_mac_oid="204.204.204.204.204.204", peer_interface=True)
    rows.extend(_fdb_rows(learned_mac_oid="187.187.187.187.187.1", peer_interface=False)[3:])
    # 上面第二段 FDB 的 OID 187.187.187.187.187.1 = bb:bb:bb:bb:bb:01，对端已是 interface
    with mock.patch.object(
        plugin,
        "save_topology_snapshot",
        side_effect=lambda snapshot: captured.update(snapshot),
    ), mock.patch(
        "apps.cmdb.collection.collect_plugin.network.ensure_interface_connect_nic_association",
        return_value=True,
    ):
        relationships = plugin.collect_topology_relationships([], rows)

    asst_ids = {(item["model_asst_id"], item["target_inst_name"]) for item in relationships}
    assert ("interface_connect_interface", PEER_IFACE) in asst_ids
    assert ("interface_connect_nic", SERVER_NIC_MAC) in asst_ids
    assert captured["summary"]["unmatched_macs"] == 0


def test_pipeline_does_not_create_or_link_host():
    plugin = _make_plugin()
    plugin.result = {}
    plugin.load_nic_mac_index = lambda macs: nic_index_from_instances(
        [{"model_id": "host", "inst_name": SERVER_NIC_MAC, "mac_address": SERVER_NIC_MAC}]
    )
    captured = {}
    with mock.patch.object(
        plugin,
        "save_topology_snapshot",
        side_effect=lambda snapshot: captured.update(snapshot),
    ):
        relationships = plugin.collect_topology_relationships([], _fdb_rows(learned_mac_oid="204.204.204.204.204.204"))
    assert relationships == []
    assert "host" not in getattr(plugin, "result", {})
    assert captured["summary"]["unmatched_macs"] == 1


def test_setting_assos_interface_connect_nic_visible_both_ends_and_idempotent(monkeypatch):
    created_edges = []

    def query_entity(_label, conds):
        fields = {item["field"]: item.get("value") for item in conds}
        if fields.get("model_id") == "nic":
            return ([{"_id": 99, "inst_name": SERVER_NIC_MAC, "model_id": "nic"}], 1)
        return ([], 0)

    def create_edge(*args, **kwargs):
        payload = args[5] if len(args) > 5 else kwargs.get("data") or {}
        ident = (payload.get("model_asst_id"), payload.get("src_inst_id"), payload.get("dst_inst_id"))
        if any(item[:3] == ident for item in created_edges):
            raise Exception("edge already exists")
        created_edges.append(
            (
                payload.get("model_asst_id"),
                payload.get("src_inst_id"),
                payload.get("dst_inst_id"),
                payload.get("src_model_id"),
                payload.get("dst_model_id"),
                args[1],
                args[3],
            )
        )
        return {}

    fake = FakeGraph()
    fake.query_entity = query_entity
    fake.create_edge = create_edge
    _patch_common(monkeypatch, fake, attrs=[{"attr_id": "inst_name", "attr_name": "实例名", "is_only": True}])

    current = {"model_id": "interface", "_id": 10, "inst_name": SOURCE_IFACE}
    listed = [
        {
            "model_id": "nic",
            "inst_name": SERVER_NIC_MAC,
            "asst_id": "connect",
            "model_asst_id": INTERFACE_CONNECT_NIC,
        }
    ]
    management = Management(
        organization=[1],
        inst_name="sw",
        model_id="interface",
        old_data=[],
        new_data=[],
        unique_keys=["inst_name"],
        collect_time="2026-08-27",
        task_id=9,
    )
    first = management.setting_assos(current, listed)
    assert len(first["success"]) == 1
    assert first["success"][0]["src_model_id"] == "interface"
    assert first["success"][0]["dst_model_id"] == "nic"
    assert first["success"][0]["model_asst_id"] == INTERFACE_CONNECT_NIC
    assert created_edges == [(INTERFACE_CONNECT_NIC, 10, 99, "interface", "nic", 10, 99)]

    second = management.setting_assos(current, listed)
    assert len(second["success"]) == 1
    assert len(created_edges) == 1


def test_ensure_interface_connect_nic_is_idempotent(monkeypatch):
    creates = []

    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_info_search",
        lambda mid: {} if not creates else {"model_asst_id": mid},
    )
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: {"_id": 1, "model_id": mid} if mid == "interface" else {"_id": 2, "model_id": mid},
    )

    def create(**payload):
        if creates:
            raise BaseAppException("model association repetition")
        creates.append(payload)
        return payload

    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.model_association_create", create)
    assert ensure_interface_connect_nic_association() is True
    assert creates[0]["model_asst_id"] == INTERFACE_CONNECT_NIC
    assert creates[0]["src_model_id"] == "interface"
    assert creates[0]["dst_model_id"] == "nic"
    assert ensure_interface_connect_nic_association() is True
    assert len(creates) == 1


_NIC_INDEX_LOAD_FAILED_TEMPLATE = "event=network_topology_nic_index_load_failed task_id=%s failed_stage=%s error_type=%s"
_SECRET_SENTINEL = "secret-token-do-not-log"


def _warning_records(caplog, template):
    return [record for record in caplog.records if record.msg == template]


def test_ensure_returns_false_and_logs_when_models_missing(monkeypatch, caplog):
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.model_association_info_search", lambda _mid: {})
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_info", lambda _mid: None)
    create = mock.Mock()
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.model_association_create", create)

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        result = ensure_interface_connect_nic_association(task_id=7001)

    assert result is False
    create.assert_not_called()
    records = _warning_records(caplog, _ENSURE_FAILED_TEMPLATE)
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.args == (7001, "ensure_interface_connect_nic_association", "model_not_found")
    rendered = record.getMessage()
    assert rendered == (
        "event=network_topology_nic_association_ensure_failed "
        "task_id=7001 failed_stage=ensure_interface_connect_nic_association error_type=model_not_found"
    )
    assert record.exc_info is None


def test_ensure_returns_false_and_logs_without_secret_on_non_repetition(monkeypatch, caplog):
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.model_association_info_search", lambda _mid: {})
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: {"_id": 1, "model_id": mid},
    )

    def create(**_payload):
        raise BaseAppException(_SECRET_SENTINEL)

    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.model_association_create", create)

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        result = ensure_interface_connect_nic_association(task_id=7001)

    assert result is False
    records = _warning_records(caplog, _ENSURE_FAILED_TEMPLATE)
    assert len(records) == 1
    record = records[0]
    assert record.args == (7001, "ensure_interface_connect_nic_association", "BaseAppException")
    rendered = record.getMessage()
    assert "error_type=BaseAppException" in rendered
    assert _SECRET_SENTINEL not in rendered
    assert _SECRET_SENTINEL not in str(record.args)
    assert record.exc_info is None


def test_pipeline_ensure_exception_logs_and_still_writes_nic_connect(caplog):
    plugin = _make_plugin()
    plugin.interfaces_data = {SOURCE_IFACE: {"inst_name": SOURCE_IFACE, "assos": []}}
    plugin.load_nic_mac_index = lambda macs: _nic_index(SERVER_NIC_MAC) if SERVER_NIC_MAC in macs else {}
    captured = {}
    rows = _fdb_rows(learned_mac_oid="204.204.204.204.204.204")
    with mock.patch.object(
        plugin,
        "save_topology_snapshot",
        side_effect=lambda snapshot: captured.update(snapshot),
    ), mock.patch(
        "apps.cmdb.collection.collect_plugin.network.ensure_interface_connect_nic_association",
        side_effect=RuntimeError(_SECRET_SENTINEL),
    ), caplog.at_level(logging.WARNING, logger="cmdb"):
        relationships = plugin.collect_topology_relationships([], rows)
        plugin.add_interface_assos(relationships)

    assert relationships == [
        {
            "source_inst_name": SOURCE_IFACE,
            "target_inst_name": SERVER_NIC_MAC,
            "model_id": "nic",
            "asst_id": "connect",
            "model_asst_id": INTERFACE_CONNECT_NIC,
        }
    ]
    assert plugin.interfaces_data[SOURCE_IFACE]["assos"][0]["model_asst_id"] == INTERFACE_CONNECT_NIC
    assert captured["summary"]["nic_connects"] == 1
    records = _warning_records(caplog, _ENSURE_FAILED_TEMPLATE)
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.args == (7001, "ensure_interface_connect_nic_association", "RuntimeError")
    rendered = record.getMessage()
    assert rendered == (
        "event=network_topology_nic_association_ensure_failed "
        "task_id=7001 failed_stage=ensure_interface_connect_nic_association error_type=RuntimeError"
    )
    assert _SECRET_SENTINEL not in rendered
    assert _SECRET_SENTINEL not in str(record.args)
    assert record.exc_info is None
    assert not any(item.exc_info for item in caplog.records)


def test_pipeline_nic_query_failure_logs_drops_mac_and_does_not_fabricate(caplog):
    plugin = _make_plugin()
    captured = {}
    with mock.patch(
        "apps.cmdb.collection.collect_plugin.network.load_nic_instances_by_mac",
        side_effect=RuntimeError(_SECRET_SENTINEL),
    ), mock.patch.object(
        plugin,
        "save_topology_snapshot",
        side_effect=lambda snapshot: captured.update(snapshot),
    ), caplog.at_level(
        logging.WARNING, logger="cmdb"
    ):
        relationships = plugin.collect_topology_relationships([], _fdb_rows(learned_mac_oid="204.204.204.204.204.204"))

    assert relationships == []
    assert captured["summary"]["unmatched_macs"] == 1
    assert captured["summary"]["nic_connects"] == 0
    assert any(item.get("drop_reason") == "unmatched_mac" for item in captured["dropped"])
    records = _warning_records(caplog, _NIC_INDEX_LOAD_FAILED_TEMPLATE)
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.msg == _NIC_INDEX_LOAD_FAILED_TEMPLATE
    assert record.args == (7001, "load_nic_mac_index", "RuntimeError")
    rendered = record.getMessage()
    assert rendered == ("event=network_topology_nic_index_load_failed task_id=7001 failed_stage=load_nic_mac_index error_type=RuntimeError")
    assert _SECRET_SENTINEL not in rendered
    assert _SECRET_SENTINEL not in str(record.args)
    assert record.exc_info is None
    assert not any(item.levelno >= logging.ERROR for item in caplog.records)
