# -*- coding: utf-8 -*-
"""OpenStack 采集器单测：不真连 HTTP，mock list_* / _map_* 纯函数，
断言输出业务字段集合恰好对齐模型 attr 表，并校验隐藏关联字段存在。"""
import sys
from pathlib import Path
from unittest.mock import patch

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))


# handle_* 风格的原始输出（移植自 old cw_openstackcloud）
RAW_NODE = {
    "hypervisor_hostname": "compute-01",
    "id": "1",
    "memory_mb": "65536",
    "vcpus": "32",
    "local_gb": "1000",
    "host_ip": "10.0.0.11",
}

RAW_VM = {
    "hostname": "vm-web-01",
    "id": "vm-001",
    "power_state": "运行中",
    "zone": "nova",
    "node_name": "compute-01",
    "region": "RegionOne",
    "project_id": "proj-123",
    "ram": 4096,
    "vcpus": 2,
    "disk": 40,
    "addresses": "192.168.1.10",
}

RAW_VOLUME = {
    "name": "vol-data-01",
    "id": "vol-001",
    "size": 100,
    "zone": "nova",
    "region": "RegionOne",
    "project_id": "proj-123",
    "node_name": "compute-01",
    "status": "使用中",
    "vm_id": "vm-001",
    "sp_id": "compute-01@lvm#lvm",
}

RAW_SP = {
    "id": "compute-01@lvm#lvm",
    "node_name": "compute-01",
    "volume_backend_name": "lvm",
    "total_capacity_gb": "2000",
    "storage_protocol": "iSCSI",
    "driver_version": "3.0.0",
    "project_id": "proj-123",
    "region": "RegionOne",
}


def _make_manager():
    from plugins.inputs.openstack.openstack_info import OpenStackManager

    return OpenStackManager(
        params={
            "username": "admin",
            "password": "secret",
            "region": "RegionOne",
            "host": "10.0.0.1",
        }
    )


# ----------------------------------------------------------------------------
# 纯函数字段重命名测试
# ----------------------------------------------------------------------------
def test_map_node_fields():
    mgr = _make_manager()
    out = mgr._map_node(RAW_NODE)
    assert set(out.keys()) == {
        "resource_name", "resource_id", "ip_addr", "ram_mb", "vcpus", "disk_gb",
    }
    assert out["resource_name"] == "compute-01"
    assert out["resource_id"] == "1"
    assert out["ip_addr"] == "10.0.0.11"
    assert out["ram_mb"] == "65536"
    assert out["vcpus"] == "32"
    assert out["disk_gb"] == "1000"


def test_map_vm_fields_with_hidden():
    mgr = _make_manager()
    out = mgr._map_vm(RAW_VM)
    business_keys = {
        "resource_name", "resource_id", "ip_addr", "ram_mb", "vcpus", "disk_gb",
        "status", "os_name", "zone", "region", "project_name",
    }
    # 业务字段恰好对齐 attr
    assert business_keys <= set(out.keys())
    assert (set(out.keys()) - business_keys) == {"node_name"}  # 隐藏字段
    assert out["resource_name"] == "vm-web-01"
    assert out["resource_id"] == "vm-001"
    assert out["ip_addr"] == "192.168.1.10"
    assert out["ram_mb"] == 4096
    assert out["vcpus"] == 2
    assert out["disk_gb"] == 40
    assert out["status"] == "运行中"
    assert out["os_name"] == ""  # 已知缺口：old 未产出
    assert out["zone"] == "nova"
    assert out["region"] == "RegionOne"
    assert out["project_name"] == "proj-123"  # project_id 充当
    # 隐藏关联字段
    assert out["node_name"] == "compute-01"


def test_map_vg_fields_with_hidden():
    mgr = _make_manager()
    out = mgr._map_vg(RAW_VOLUME)
    business_keys = {
        "resource_name", "resource_id", "size_gb", "zone", "region",
        "project_name", "status",
    }
    hidden_keys = {"node_name", "vm_id", "sp_id"}
    assert set(out.keys()) == business_keys | hidden_keys
    assert out["resource_name"] == "vol-data-01"
    assert out["resource_id"] == "vol-001"
    assert out["size_gb"] == 100
    assert out["zone"] == "nova"
    assert out["region"] == "RegionOne"
    assert out["project_name"] == "proj-123"
    assert out["status"] == "使用中"
    # 隐藏关联字段
    assert out["node_name"] == "compute-01"
    assert out["vm_id"] == "vm-001"
    assert out["sp_id"] == "compute-01@lvm#lvm"


def test_map_sp_fields_with_hidden():
    mgr = _make_manager()
    out = mgr._map_sp(RAW_SP)
    business_keys = {
        "resource_name", "resource_id", "size_gb", "region", "project_name",
        "storage_protocol", "driver_version",
    }
    hidden_keys = {"node_name"}
    assert set(out.keys()) == business_keys | hidden_keys
    # 存储池 get_pools 路径字段落对
    assert out["resource_name"] == "lvm"  # volume_backend_name
    assert out["resource_id"] == "compute-01@lvm#lvm"
    assert out["size_gb"] == "2000"  # total_capacity_gb
    assert out["storage_protocol"] == "iSCSI"
    assert out["driver_version"] == "3.0.0"
    assert out["region"] == "RegionOne"
    assert out["project_name"] == "proj-123"
    # 隐藏关联字段
    assert out["node_name"] == "compute-01"


# ----------------------------------------------------------------------------
# get_* 聚合测试（mock list_* 返回 handle_ 风格 data）
# ----------------------------------------------------------------------------
def test_get_platform():
    mgr = _make_manager()
    platform = mgr.get_platform()
    assert platform == [{"global_domain_name": "10.0.0.1"}]


def test_get_nodes_via_mock_list():
    mgr = _make_manager()
    with patch.object(mgr, "list_nodes", return_value={"result": True, "data": [RAW_NODE]}):
        nodes = mgr.get_nodes()
    assert len(nodes) == 1
    assert nodes[0]["resource_name"] == "compute-01"


# ----------------------------------------------------------------------------
# list_all_resources 聚合 + 错误兜底
# ----------------------------------------------------------------------------
def test_list_all_resources_success():
    mgr = _make_manager()
    with patch.object(mgr, "get_nodes", return_value=[mgr._map_node(RAW_NODE)]), \
            patch.object(mgr, "get_vms", return_value=[mgr._map_vm(RAW_VM)]), \
            patch.object(mgr, "get_vg", return_value=[mgr._map_vg(RAW_VOLUME)]), \
            patch.object(mgr, "get_sp", return_value=[mgr._map_sp(RAW_SP)]):
        out = mgr.list_all_resources()

    assert out["success"] is True
    result = out["result"]
    assert set(result.keys()) == {
        "openstack", "openstack_node", "openstack_vm", "openstack_vg", "openstack_sp",
    }
    assert result["openstack"][0]["global_domain_name"] == "10.0.0.1"
    assert result["openstack_node"][0]["resource_name"] == "compute-01"
    assert result["openstack_vm"][0]["os_name"] == ""


def test_list_all_resources_error_branch():
    mgr = _make_manager()
    with patch.object(mgr, "get_nodes", side_effect=RuntimeError("boom")):
        out = mgr.list_all_resources()
    assert out["success"] is False
    assert "cmdb_collect_error" in out["result"]


def test_missing_requests_reports_clear_error(monkeypatch):
    """requests 未安装时应返回清晰错误而非崩溃。"""
    from plugins.inputs.openstack import openstack_info
    monkeypatch.setattr(openstack_info, "requests", None)
    mgr = openstack_info.OpenStackManager(params={
        "username": "u", "password": "p", "region": "r",
        "host": "openstack.example.com",
    })
    out = mgr.list_all_resources()
    assert out["success"] is False
    assert "requests" in out["result"]["cmdb_collect_error"]
