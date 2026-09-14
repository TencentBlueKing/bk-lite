"""CMDB 许可用量计数：只统计原生自动发现的收费模型。"""

import pytest

from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.constants.license_catalog import (
    CMDB_LICENSE_MODEL_IDS,
    CMDB_LICENSE_OS_MODEL_ID,
    CMDB_LICENSE_VM_MODEL_IDS,
)
from apps.cmdb.services.instance import InstanceManage

EXPECTED_CMDB_LICENSE_MODEL_IDS = frozenset(
    {
        "host",
        "physcial_server",
        "k8s_node",
        "vmware_esxi",
        "vmware_vm",
        "aliyun_ecs",
        "qcloud_cvm",
        "hwcloud_ecs",
        "aws_ec2",
        "azure_vm",
        "fusioninsight_host",
        "fusioncompute_host",
        "fusioncompute_vm",
        "h3c_cas_host",
        "h3c_cas_vm",
        "nutanixhci_host",
        "nutanixhci_vm",
        "openstack_node",
        "openstack_vm",
        "sangforscp_host",
        "sangforscp_vm",
        "sangforhci_vm",
        "smartx_host",
        "smartx_vm",
        "winsphere_host",
        "winsphere_vm",
        "manageone_host",
        "manageone_server",
        "inspurincloudrail_vm",
        "switch",
        "router",
        "firewall",
        "loadbalance",
        "security_device",
        "storage",
    }
)

EXPECTED_CMDB_LICENSE_VM_MODEL_IDS = frozenset(
    {
        "vmware_vm",
        "aliyun_ecs",
        "qcloud_cvm",
        "hwcloud_ecs",
        "aws_ec2",
        "azure_vm",
        "fusioncompute_vm",
        "h3c_cas_vm",
        "nutanixhci_vm",
        "openstack_vm",
        "sangforscp_vm",
        "sangforhci_vm",
        "smartx_vm",
        "winsphere_vm",
        "inspurincloudrail_vm",
    }
)


@pytest.mark.unit
def test_cmdb_license_catalog_covers_infrastructure_and_excludes_software():
    assert CMDB_LICENSE_MODEL_IDS == EXPECTED_CMDB_LICENSE_MODEL_IDS
    assert CMDB_LICENSE_OS_MODEL_ID == "host"
    assert CMDB_LICENSE_VM_MODEL_IDS == EXPECTED_CMDB_LICENSE_VM_MODEL_IDS
    assert CMDB_LICENSE_VM_MODEL_IDS <= CMDB_LICENSE_MODEL_IDS
    assert CMDB_LICENSE_OS_MODEL_ID in CMDB_LICENSE_MODEL_IDS
    assert CMDB_LICENSE_OS_MODEL_ID not in CMDB_LICENSE_VM_MODEL_IDS
    assert "vmware_esxi" not in CMDB_LICENSE_VM_MODEL_IDS
    assert "k8s_node" not in CMDB_LICENSE_VM_MODEL_IDS
    assert "physcial_server" not in CMDB_LICENSE_VM_MODEL_IDS

    assert "mysql" not in CMDB_LICENSE_MODEL_IDS
    assert "k8s_cluster" not in CMDB_LICENSE_MODEL_IDS
    assert "k8s_pod" not in CMDB_LICENSE_MODEL_IDS
    assert "vmware_vc" not in CMDB_LICENSE_MODEL_IDS
    assert "aliyun_account" not in CMDB_LICENSE_MODEL_IDS
    assert "fusioncompute" not in CMDB_LICENSE_MODEL_IDS
    assert "sangforscp" not in CMDB_LICENSE_MODEL_IDS
    assert "storage_pool" not in CMDB_LICENSE_MODEL_IDS
    assert "pc" not in CMDB_LICENSE_MODEL_IDS
    assert "tape_library" not in CMDB_LICENSE_MODEL_IDS
    assert "server_bmc" not in CMDB_LICENSE_MODEL_IDS


@pytest.mark.unit
def test_license_instance_count_filters_auto_collect_and_catalog(monkeypatch):
    captured = {}

    def fake_group(cls, group_by_attr, permissions_map, params=None, creator=""):
        captured["group_by_attr"] = group_by_attr
        captured["permissions_map"] = permissions_map
        captured["params"] = params
        captured["creator"] = creator
        return {"k8s_node": 3, "switch": 1}

    def fake_os_vm(cls):
        return {"host": 2, "vmware_vm": 1}

    monkeypatch.setattr(InstanceManage, "group_inst_count", classmethod(fake_group))
    monkeypatch.setattr(InstanceManage, "_license_os_vm_instance_count", classmethod(fake_os_vm))

    result = InstanceManage.license_instance_count()

    assert result == {"k8s_node": 3, "switch": 1, "host": 2, "vmware_vm": 1}
    assert captured["group_by_attr"] == "model_id"
    assert captured["permissions_map"] == {}
    assert captured["creator"] == ""
    assert {"field": "auto_collect", "type": "bool", "value": True} in captured["params"]
    model_filter = next(item for item in captured["params"] if item["field"] == "model_id")
    assert model_filter["type"] == "str[]"
    other_model_ids = CMDB_LICENSE_MODEL_IDS - CMDB_LICENSE_VM_MODEL_IDS - {CMDB_LICENSE_OS_MODEL_ID}
    assert set(model_filter["value"]) == other_model_ids
    assert "host" not in model_filter["value"]
    assert "vmware_vm" not in model_filter["value"]
    assert "k8s_node" in model_filter["value"]
    assert "vmware_esxi" in model_filter["value"]


@pytest.mark.unit
def test_query_license_os_vm_instances_filters_auto_collect_and_os_vm(monkeypatch):
    captured = {}

    class FakeGraphClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def query_entity(self, label, params, **kwargs):
            captured["label"] = label
            captured["params"] = params
            return [{"model_id": "host", "ip_addr": "10.0.0.1"}], 1

    monkeypatch.setattr("apps.cmdb.services.instance.GraphClient", FakeGraphClient)

    result = InstanceManage._query_license_os_vm_instances()

    assert result == [{"model_id": "host", "ip_addr": "10.0.0.1"}]
    assert captured["label"] == INSTANCE
    assert {"field": "auto_collect", "type": "bool", "value": True} in captured["params"]
    model_filter = next(item for item in captured["params"] if item["field"] == "model_id")
    assert model_filter["type"] == "str[]"
    assert set(model_filter["value"]) == {CMDB_LICENSE_OS_MODEL_ID, *CMDB_LICENSE_VM_MODEL_IDS}


@pytest.mark.unit
def test_count_license_os_vm_same_ip_keeps_host_drops_vm():
    counts = InstanceManage._count_license_os_vm_instances(
        [
            {"model_id": "host", "ip_addr": "10.0.0.8"},
            {"model_id": "vmware_vm", "ip_addr": "10.0.0.8"},
            {"model_id": "aliyun_ecs", "ip_addr": "10.0.0.9"},
        ]
    )
    assert counts == {"host": 1, "aliyun_ecs": 1}


@pytest.mark.unit
def test_count_license_os_vm_multi_ip_any_hit_drops_vm():
    counts = InstanceManage._count_license_os_vm_instances(
        [
            {"model_id": "host", "ip_addr": "10.0.0.5,10.0.0.6"},
            {"model_id": "qcloud_cvm", "ip_addr": " 10.0.0.6 , 10.0.0.7 "},
            {"model_id": "aws_ec2", "ip_addr": "10.0.0.8"},
        ]
    )
    assert counts == {"host": 1, "aws_ec2": 1}


@pytest.mark.unit
def test_count_license_os_vm_empty_ip_and_no_overlap_both_count():
    counts = InstanceManage._count_license_os_vm_instances(
        [
            {"model_id": "host", "ip_addr": "10.0.0.1"},
            {"model_id": "host", "ip_addr": ""},
            {"model_id": "vmware_vm", "ip_addr": ""},
            {"model_id": "vmware_vm", "ip_addr": None},
            {"model_id": "azure_vm", "ip_addr": "10.0.0.2"},
            {"model_id": "switch", "ip_addr": "10.0.0.1"},
        ]
    )
    assert counts == {"host": 2, "vmware_vm": 2, "azure_vm": 1}


@pytest.mark.unit
def test_count_license_os_vm_list_ip_addr_and_duplicate_hosts():
    counts = InstanceManage._count_license_os_vm_instances(
        [
            {"model_id": "host", "ip_addr": ["10.0.0.10", "10.0.0.11"]},
            {"model_id": "host", "ip_addr": "10.0.0.10"},
            {"model_id": "smartx_vm", "ip_addr": ["10.0.0.11"]},
            {"model_id": "smartx_vm", "ip_addr": "10.0.0.12"},
        ]
    )
    assert counts == {"host": 2, "smartx_vm": 1}
