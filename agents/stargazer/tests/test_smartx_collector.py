# -*- coding: utf-8 -*-
"""SmartX 采集器单测：不真连 HTTP，mock list_* / 喂原始 API item 给 _map_* 纯函数，
断言输出业务字段集合恰好对齐模型 attr 表，并校验隐藏关联字段 cluster_id 存在。"""
import sys
from pathlib import Path
from unittest.mock import patch

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))


# ----------------------------------------------------------------------------
# 原始 API item（移植自 old cw_smartx 的 list_* 字段过滤结果）
# ----------------------------------------------------------------------------
RAW_CLUSTER = {
    "id": "cluster-001",
    "name": "cluster-a",
    "type": "SMTX_OS",
    "architecture": "x86_64",
    "hypervisor": "KVM",
    "version": "5.0",
    "total_data_capacity": 1073741824 * 100,  # 100 GiB
    "total_cache_capacity": 1073741824 * 10,  # 10 GiB
    "total_cpu_cores": 64,
    "total_memory_bytes": 2147483648,  # 2 GiB -> memory_mb 2048.0
    "datacenters": [{"name": "dc1"}, {"name": "dc2"}],
}

RAW_HOST = {
    "id": "host-001",
    "name": "host-a",
    # list_hosts 把 cluster 替换为完整 cluster 对象（含 architecture、id）
    "cluster": RAW_CLUSTER,
    "management_ip": "10.0.0.11",
    "data_ip": "10.0.1.11",
    "cpu_brand": "Intel Xeon",
    "total_cpu_sockets": 2,
    "total_data_capacity": 1073741824 * 50,
    "total_cache_capacity": 1073741824 * 5,
    "total_cpu_cores": 32,
    "total_memory_bytes": 2147483648,
}

RAW_VM = {
    "id": "vm-001",
    "name": "vm-web-01",
    "host": {"id": "host-001"},
    "cluster": {"id": "cluster-001"},
    "status": "RUNNING",
    "vcpu": 4,
    "memory": 2147483648,  # 2 GiB -> 2048.0
    "ips": ["192.168.1.10", "192.168.1.11"],
    "os": "CentOS 7",
}

RAW_VOLUME = {
    "id": "vol-001",
    "name": "vol-data-01",
    "cluster": {"id": "cluster-001"},
    "vm_disks": [],
    "size": 1073741824 * 20,  # 20 GiB
}


def _make_manager():
    from plugins.inputs.smartx.smartx_info import SmartXManager

    return SmartXManager(
        params={
            "username": "admin",
            "password": "secret",
            "region": "RegionOne",
            "host": "10.0.0.1",
        }
    )


# ----------------------------------------------------------------------------
# 纯函数字段重命名 + 换算测试
# ----------------------------------------------------------------------------
def test_map_cluster_fields():
    mgr = _make_manager()
    out = mgr._map_cluster(RAW_CLUSTER)
    assert set(out.keys()) == {
        "resource_name", "resource_id", "cluster_type", "cpu_vendor",
        "hypervisor", "version", "datacenter", "storage_gb", "cache_gb",
        "vcpus", "memory_mb",
    }
    assert out["resource_name"] == "cluster-a"
    assert out["resource_id"] == "cluster-001"
    assert out["cluster_type"] == "SMTX_OS"
    assert out["cpu_vendor"] == "x86_64"
    assert out["hypervisor"] == "KVM"
    assert out["version"] == "5.0"
    assert out["datacenter"] == "dc1,dc2"
    assert out["storage_gb"] == "100.0"
    assert out["cache_gb"] == "10.0"
    assert out["vcpus"] == "64"
    assert out["memory_mb"] == "2048.0"


def test_map_cluster_none_cpu_cores_is_empty():
    """API 显式返回 None 时 vcpus 应为空串而非字符串 'None'。"""
    mgr = _make_manager()
    raw = dict(RAW_CLUSTER, total_cpu_cores=None)
    out = mgr._map_cluster(raw)
    assert out["vcpus"] == ""


def test_map_host_fields():
    mgr = _make_manager()
    out = mgr._map_host(RAW_HOST)
    assert set(out.keys()) == {
        "resource_name", "resource_id", "ip_addr", "data_ip", "cpu_brand",
        "cpu_arch", "cpu_sockets", "storage_gb", "cache_gb", "vcpus", "memory_mb",
    }
    assert out["resource_name"] == "host-a"
    assert out["resource_id"] == "host-001"
    assert out["ip_addr"] == "10.0.0.11"
    assert out["data_ip"] == "10.0.1.11"
    assert out["cpu_brand"] == "Intel Xeon"
    assert out["cpu_arch"] == "x86_64"  # cluster["architecture"]
    assert out["cpu_sockets"] == "2"
    assert out["storage_gb"] == "50.0"
    assert out["cache_gb"] == "5.0"
    assert out["vcpus"] == "32"
    assert out["memory_mb"] == "2048.0"


def test_map_host_none_int_fields_are_empty():
    """total_cpu_sockets / total_cpu_cores 为 None 时应为空串。"""
    mgr = _make_manager()
    raw = dict(RAW_HOST, total_cpu_sockets=None, total_cpu_cores=None)
    out = mgr._map_host(raw)
    assert out["cpu_sockets"] == ""
    assert out["vcpus"] == ""


def test_map_vm_fields_with_hidden():
    mgr = _make_manager()
    out = mgr._map_vm(RAW_VM, cluster_id="cluster-001")
    business_keys = {
        "resource_name", "resource_id", "status", "vcpus", "memory_mb",
        "ip_addr", "os",
    }
    assert (set(out.keys()) - business_keys) == {"cluster_id"}  # 隐藏字段
    assert out["resource_name"] == "vm-web-01"
    assert out["resource_id"] == "vm-001"
    assert out["status"] == "RUNNING"
    assert out["vcpus"] == "4"
    assert out["memory_mb"] == "2048.0"
    assert out["ip_addr"] == "192.168.1.10,192.168.1.11"  # ips 列表 join
    assert out["os"] == "CentOS 7"
    assert out["cluster_id"] == "cluster-001"


def test_map_vm_ips_string_passthrough():
    mgr = _make_manager()
    raw = dict(RAW_VM, ips="192.168.1.99", os=None)
    out = mgr._map_vm(raw, cluster_id="")
    assert out["ip_addr"] == "192.168.1.99"  # 非列表原值
    assert out["os"] == ""  # os None -> ""
    assert out["cluster_id"] == ""


def test_map_vm_none_vcpu_is_empty():
    """vcpu 为 None 时 vcpus 应为空串而非字符串 'None'。"""
    mgr = _make_manager()
    raw = dict(RAW_VM, vcpu=None)
    out = mgr._map_vm(raw, cluster_id="cluster-001")
    assert out["vcpus"] == ""


def test_map_volume_fields_with_hidden():
    mgr = _make_manager()
    out = mgr._map_volume(RAW_VOLUME)
    business_keys = {"resource_name", "resource_id", "storage_gb"}
    assert (set(out.keys()) - business_keys) == {"cluster_id"}
    assert out["resource_name"] == "vol-data-01"
    assert out["resource_id"] == "vol-001"
    assert out["storage_gb"] == "20.0"
    assert out["cluster_id"] == "cluster-001"  # cluster.id


# ----------------------------------------------------------------------------
# get_* 聚合测试（mock list_* 返回原始 data）
# ----------------------------------------------------------------------------
def test_get_platform():
    mgr = _make_manager()
    assert mgr.get_platform() == [{"global_domain_name": "10.0.0.1"}]


def test_get_clusters_via_mock_list():
    mgr = _make_manager()
    with patch.object(mgr, "list_clusters", return_value={"result": True, "data": [RAW_CLUSTER]}):
        clusters = mgr.get_clusters()
    assert len(clusters) == 1
    assert clusters[0]["resource_name"] == "cluster-a"


def test_get_vms_uses_host_cluster_map():
    """vm 的隐藏 cluster_id 通过 host_id->cluster_id 映射填充。"""
    mgr = _make_manager()
    with patch.object(mgr, "list_hosts", return_value={"result": True, "data": [RAW_HOST]}), \
            patch.object(mgr, "list_vms", return_value={"result": True, "data": [RAW_VM]}):
        mgr.get_hosts()  # 建立 host_id->cluster_id 映射
        vms = mgr.get_vms()
    assert vms[0]["cluster_id"] == "cluster-001"


# ----------------------------------------------------------------------------
# list_all_resources 聚合 + 错误兜底
# ----------------------------------------------------------------------------
def test_list_all_resources_success():
    mgr = _make_manager()
    with patch.object(mgr, "get_clusters", return_value=[mgr._map_cluster(RAW_CLUSTER)]), \
            patch.object(mgr, "get_hosts", return_value=[mgr._map_host(RAW_HOST)]), \
            patch.object(mgr, "get_vms", return_value=[mgr._map_vm(RAW_VM, cluster_id="cluster-001")]), \
            patch.object(mgr, "get_volumes", return_value=[mgr._map_volume(RAW_VOLUME)]):
        out = mgr.list_all_resources()

    assert out["success"] is True
    result = out["result"]
    assert set(result.keys()) == {
        "smartx", "smartx_cluster", "smartx_host", "smartx_vm", "smartx_vmvolume",
    }
    assert result["smartx"][0]["global_domain_name"] == "10.0.0.1"
    assert result["smartx_cluster"][0]["resource_name"] == "cluster-a"
    assert result["smartx_vm"][0]["cluster_id"] == "cluster-001"
    assert result["smartx_vmvolume"][0]["cluster_id"] == "cluster-001"


def test_list_all_resources_error_branch():
    mgr = _make_manager()
    with patch.object(mgr, "get_clusters", side_effect=RuntimeError("boom")):
        out = mgr.list_all_resources()
    assert out["success"] is False
    assert "cmdb_collect_error" in out["result"]


def test_missing_requests_reports_clear_error(monkeypatch):
    """requests 未安装时应返回清晰错误而非崩溃。"""
    from plugins.inputs.smartx import smartx_info
    monkeypatch.setattr(smartx_info, "requests", None)
    mgr = smartx_info.SmartXManager(params={
        "username": "u", "password": "p", "region": "r",
        "host": "smartx.example.com",
    })
    out = mgr.list_all_resources()
    assert out["success"] is False
    assert "requests" in out["result"]["cmdb_collect_error"]
