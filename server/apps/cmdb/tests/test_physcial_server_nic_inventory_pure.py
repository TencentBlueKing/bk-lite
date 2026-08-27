# -*- coding: utf-8 -*-
"""物理服务器 SSH 采集 Step-1：网卡解析 + 幂等 upsert。

锁定：
- lo / 空 MAC 不入库；MAC 规范为小写冒号分隔，并作为 nic.inst_name
- 同一台机器采集两次不产生重复 nic
- contains 图边 src=physcial_server、dst=nic（父 → 网卡），不是 nic → 父
- 不走 IPMI/BMC 网卡清单；不改 physcial_server 拼写
"""
import pandas as pd
import pytest

from apps.cmdb.collection.common import Management
from apps.cmdb.collection.nic_inventory import is_ingestible_nic, normalize_nic_mac, parse_nic_record
from apps.cmdb.collection.plugins.community.host.host import HostCollectionPlugin
from apps.cmdb.collection.plugins.community.host.physical_server import PhysicalServerCollectionPlugin
from apps.cmdb.collection.plugins.community.protocol.physical_server import PhysicalServerIPMICollectionPlugin
from apps.cmdb.tests.test_collect_management_service import FakeGraph, _patch_common

pytestmark = pytest.mark.unit

MODEL_CONFIG = "apps/cmdb/support-files/model_config.xlsx"


def _nic_metric(**labels):
    metric = {
        "__name__": "nic_info_gauge",
        "collect_status": "success",
        "self_device": "10.0.0.8",
    }
    metric.update(labels)
    return {
        "index_key": "nic_info_gauge",
        **metric,
    }


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setattr(
        PhysicalServerCollectionPlugin,
        "model_id",
        property(lambda self: "physcial_server"),
    )
    plugin = PhysicalServerCollectionPlugin("srv-1", "cmdb_1", 1)
    plugin.inst_name = "srv-1"
    return plugin


# --------------------------------------------------------------------------
# MAC / 接口名解析
# --------------------------------------------------------------------------


def test_normalize_nic_mac_lowercase_colon():
    assert normalize_nic_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"
    assert normalize_nic_mac("AA:BB:CC:DD:EE:FF") == "aa:bb:cc:dd:ee:ff"
    assert normalize_nic_mac("aabbccddeeff") == "aa:bb:cc:dd:ee:ff"
    assert normalize_nic_mac("aabb.ccdd.eeff") == "aa:bb:cc:dd:ee:ff"


def test_normalize_nic_mac_drops_empty_and_invalid():
    assert normalize_nic_mac("") == ""
    assert normalize_nic_mac(None) == ""
    assert normalize_nic_mac("N/A") == ""
    assert normalize_nic_mac("n/a") == ""
    assert normalize_nic_mac("00:00:00:00:00:00") == ""
    assert normalize_nic_mac("not-a-mac") == ""


def test_skip_loopback_and_empty_mac():
    assert is_ingestible_nic("lo", "aa:bb:cc:dd:ee:ff") is False
    assert is_ingestible_nic("LO", "aa:bb:cc:dd:ee:ff") is False
    assert is_ingestible_nic("lo:0", "aa:bb:cc:dd:ee:ff") is False
    assert is_ingestible_nic("eth0", "") is False
    assert is_ingestible_nic("eth0", "N/A") is False
    assert is_ingestible_nic("eth0", "aa:bb:cc:dd:ee:ff") is True
    assert is_ingestible_nic("N/A", "aa:bb:cc:dd:ee:ff") is True


def test_parse_nic_record_uses_normalized_mac_as_identity():
    parsed = parse_nic_record(
        {
            "nic_iface": "enp1s0",
            "nic_mac": "B0-4F-A6-2C-B7-60",
            "nic_pci_addr": "7d:00.0",
        }
    )
    assert parsed == {
        "nic_iface": "enp1s0",
        "nic_mac": "b0:4f:a6:2c:b7:60",
        "nic_pci_addr": "7d:00.0",
        "inst_name": "b0:4f:a6:2c:b7:60",
    }


def test_parse_nic_record_drops_lo_and_empty_mac():
    assert parse_nic_record({"nic_iface": "lo", "nic_mac": "aa:bb:cc:dd:ee:ff"}) is None
    assert parse_nic_record({"nic_iface": "eth0", "nic_mac": "N/A"}) is None
    assert parse_nic_record({"nic_iface": "eth0", "nic_mac": ""}) is None


# --------------------------------------------------------------------------
# 采集格式化：SSH JOB / host plugin 路径
# --------------------------------------------------------------------------


def test_format_data_then_metrics_simulates_one_ssh_collect(runner):
    now = 1_800_000_000
    vm_rows = {
        "result": [
            {
                "metric": {
                    "__name__": "nic_info_gauge",
                    "collect_status": "success",
                    "nic_iface": "lo",
                    "nic_mac": "00:11:22:33:44:55",
                    "self_device": "10.0.0.8",
                },
                "value": [now, "1"],
            },
            {
                "metric": {
                    "__name__": "nic_info_gauge",
                    "collect_status": "success",
                    "nic_iface": "eth0",
                    "nic_mac": "AA-BB-CC-DD-EE-01",
                    "self_device": "10.0.0.8",
                },
                "value": [now, "1"],
            },
            {
                "metric": {
                    "__name__": "nic_info_gauge",
                    "collect_status": "success",
                    "nic_iface": "eth1",
                    "nic_mac": "",
                    "self_device": "10.0.0.8",
                },
                "value": [now, "1"],
            },
        ]
    }
    runner.format_data(vm_rows)
    runner.format_metrics()
    nics = runner.result["nic"]
    assert [item["inst_name"] for item in nics] == ["aa:bb:cc:dd:ee:01"]
    assert nics[0]["assos"][0]["model_asst_id"] == "physcial_server_contains_nic"
    assert nics[0]["assos"][0]["inst_name"] == "srv-1"


def test_format_metrics_ingests_nics_with_mac_identity(runner):
    runner.collection_metrics_dict["nic_info_gauge"] = [
        _nic_metric(nic_iface="lo", nic_mac="00:11:22:33:44:55"),
        _nic_metric(nic_iface="eth0", nic_mac=""),
        _nic_metric(nic_iface="eth1", nic_mac="N/A"),
        _nic_metric(
            nic_iface="enp125s0f0",
            nic_mac="B0-4F-A6-2C-B7-60",
            nic_pci_addr="7d:00.0",
            nic_type="Ethernet controller",
            nic_vendor="Huawei",
            nic_model="HNS",
        ),
        _nic_metric(
            nic_iface="enp125s0f1",
            nic_mac="B0:4F:A6:2C:B7:61",
            nic_pci_addr="7d:00.1",
        ),
    ]
    runner.format_metrics()

    nics = runner.result["nic"]
    assert [item["inst_name"] for item in nics] == [
        "b0:4f:a6:2c:b7:60",
        "b0:4f:a6:2c:b7:61",
    ]
    assert nics[0]["nic_mac"] == "b0:4f:a6:2c:b7:60"
    assert nics[0]["nic_iface"] == "enp125s0f0"
    assert nics[0]["assos"] == [
        {
            "model_id": "physcial_server",
            "inst_name": "srv-1",
            "asst_id": "contains",
            "model_asst_id": "physcial_server_contains_nic",
        }
    ]


def test_format_metrics_second_pass_same_nic_identity(runner):
    rows = [
        _nic_metric(nic_iface="eth0", nic_mac="AA:BB:CC:DD:EE:FF"),
        _nic_metric(nic_iface="lo", nic_mac="11:22:33:44:55:66"),
    ]
    runner.collection_metrics_dict["nic_info_gauge"] = rows
    runner.format_metrics()
    first = [dict(item) for item in runner.result["nic"]]

    runner.result = {}
    runner.collection_metrics_dict["nic_info_gauge"] = rows
    runner.format_metrics()
    second = runner.result["nic"]

    assert len(first) == 1
    assert [item["inst_name"] for item in first] == [item["inst_name"] for item in second]
    assert first[0]["inst_name"] == "aa:bb:cc:dd:ee:ff"


def test_host_plugin_does_not_ingest_nic_components():
    assert "nic" not in HostCollectionPlugin.related_field_mappings
    assert "nic_info_gauge" not in HostCollectionPlugin.metric_names


def test_ipmi_plugin_does_not_emit_nic_metrics():
    assert "nic_info_gauge" not in PhysicalServerIPMICollectionPlugin.metric_names
    assert "nic" not in getattr(PhysicalServerIPMICollectionPlugin, "related_field_mappings", {})


def test_model_config_already_has_physcial_server_contains_nic():
    rows = pd.read_excel(MODEL_CONFIG, sheet_name="asso-physcial_server", header=1)
    records = rows[["src_model_id", "dst_model_id", "asst_id"]].to_dict("records")
    assert {
        "src_model_id": "physcial_server",
        "dst_model_id": "nic",
        "asst_id": "contains",
    } in records


# --------------------------------------------------------------------------
# 幂等 upsert + contains
# --------------------------------------------------------------------------


def _nic_instance(mac, iface="eth0"):
    return {
        "inst_name": mac,
        "nic_mac": mac,
        "nic_iface": iface,
        "self_device": "srv-1",
        "assos": [
            {
                "model_id": "physcial_server",
                "inst_name": "srv-1",
                "asst_id": "contains",
                "model_asst_id": "physcial_server_contains_nic",
            }
        ],
    }


def test_second_collect_does_not_duplicate_nics_and_keeps_contains(monkeypatch):
    created_ids = {"next": 10}
    existing_nics = {}
    created_edges = []

    def create_entity(label, info, check_attr_map, exist_items):
        key = info["inst_name"]
        if key in existing_nics:
            raise AssertionError(f"duplicate nic create: {key}")
        created_ids["next"] += 1
        ent = dict(info)
        ent["_id"] = created_ids["next"]
        existing_nics[key] = ent
        return ent

    def query_entity(label, conds):
        fields = {item["field"]: item.get("value") for item in conds}
        if fields.get("model_id") == "physcial_server":
            return ([{"_id": 1, "inst_name": "srv-1", "model_id": "physcial_server"}], 1)
        return ([], 0)

    def create_edge(*args, **kwargs):
        payload = args[5] if len(args) > 5 else kwargs.get("data") or {}
        src_node = args[1] if len(args) > 1 else None
        dst_node = args[3] if len(args) > 3 else None
        edge_key = (
            payload.get("model_asst_id"),
            payload.get("src_inst_id"),
            payload.get("dst_inst_id"),
            payload.get("src_model_id"),
            payload.get("dst_model_id"),
            src_node,
            dst_node,
        )
        ident = edge_key[:3]
        if any(item[:3] == ident for item in created_edges):
            raise Exception("edge already exists")
        created_edges.append(edge_key)
        return {}

    fake = FakeGraph()
    fake.create_entity = create_entity
    fake.returns["query_entity"] = query_entity
    fake.create_edge = create_edge
    _patch_common(monkeypatch, fake, attrs=[{"attr_id": "inst_name", "attr_name": "实例名", "is_only": True}])

    collected = [
        _nic_instance("aa:bb:cc:dd:ee:01", "eth0"),
        _nic_instance("aa:bb:cc:dd:ee:02", "eth1"),
    ]

    first = Management(
        organization=[1],
        inst_name="srv-1",
        model_id="nic",
        old_data=[],
        new_data=[dict(item) for item in collected],
        unique_keys=["inst_name"],
        collect_time="2026-08-27",
        task_id=9,
    )
    first_result = first.controller()
    assert len(first_result["add"]["success"]) == 2
    assert len(existing_nics) == 2
    assert len(created_edges) == 2
    assert all(edge[0] == "physcial_server_contains_nic" for edge in created_edges)
    # src = 父 physcial_server(_id=1)，dst = nic（非父 id）
    assert all(edge[1] == 1 for edge in created_edges)
    assert all(edge[2] != 1 for edge in created_edges)
    assert all(edge[3] == "physcial_server" for edge in created_edges)
    assert all(edge[4] == "nic" for edge in created_edges)
    assert all(edge[5] == 1 and edge[6] != 1 for edge in created_edges)
    # 旧实现把 nic 当 src、父机当 dst；下列方向不得再被当成正确
    assert not any(edge[1] != 1 and edge[2] == 1 for edge in created_edges)

    old_data = [
        {
            "inst_name": mac,
            "_id": ent["_id"],
            "nic_mac": mac,
            "nic_iface": collected[idx]["nic_iface"],
            "self_device": "srv-1",
        }
        for idx, (mac, ent) in enumerate(existing_nics.items())
    ]
    second = Management(
        organization=[1],
        inst_name="srv-1",
        model_id="nic",
        old_data=old_data,
        new_data=[dict(item) for item in collected],
        unique_keys=["inst_name"],
        collect_time="2026-08-27",
        task_id=9,
    )
    second_result = second.controller()
    assert second_result["add"]["success"] == []
    assert len(existing_nics) == 2
    assert set(existing_nics) == {"aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"}
    assert len(created_edges) == 2
    assert all(item["assos_result"]["success"] for item in second_result["update"]["success"])
