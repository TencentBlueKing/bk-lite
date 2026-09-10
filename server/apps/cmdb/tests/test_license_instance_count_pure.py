"""CMDB 许可用量计数：只统计原生自动发现的收费模型。"""

import pytest

from apps.cmdb.constants.license_catalog import CMDB_LICENSE_MODEL_IDS
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


@pytest.mark.unit
def test_cmdb_license_catalog_covers_infrastructure_and_excludes_software():
    assert CMDB_LICENSE_MODEL_IDS == EXPECTED_CMDB_LICENSE_MODEL_IDS

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
        return {"host": 2, "k8s_node": 3}

    monkeypatch.setattr(InstanceManage, "group_inst_count", classmethod(fake_group))

    result = InstanceManage.license_instance_count()

    assert result == {"host": 2, "k8s_node": 3}
    assert captured["group_by_attr"] == "model_id"
    assert captured["permissions_map"] == {}
    assert captured["creator"] == ""
    assert {"field": "auto_collect", "type": "bool", "value": True} in captured["params"]
    model_filter = next(item for item in captured["params"] if item["field"] == "model_id")
    assert model_filter["type"] == "str[]"
    assert set(model_filter["value"]) == set(CMDB_LICENSE_MODEL_IDS)
