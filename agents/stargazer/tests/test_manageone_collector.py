# -*- coding: utf-8 -*-
"""ManageOne 采集器单测：mock 驱动 list_* 返回，断言输出结构与字段严格对齐模型设计。"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))


# ---- 驱动 list_* 真实返回结构：{"result": True, "data": [...], "total": N} ----
FAKE_BIZ = {
    "result": True,
    "data": [
        {
            "resource_name": "region-A",
            "resource_id": "biz-001",
            "cloud_version": "8.0",
            "brand": "Huawei",
            "vcpus": "100",
            "memory_mb": "204800",
            "storage_gb": "10240",
        }
    ],
    "total": 1,
}

FAKE_VMS = {
    "result": True,
    "data": [
        {
            "resource_name": "vm-01",
            "resource_id": "vm-001",
            "inner_ip": "10.0.0.1",
            "status": "RUNNING",
            "region": "region-A",
            "os_name": "CentOS 7.6",
            "vcpus": "4",
            "create_time": "2025-01-01 00:00:00",
            "host_id": "host-001",
        }
    ],
    "total": 1,
}

FAKE_HOSTS = {
    "result": True,
    "data": [
        {
            "resource_name": "host-01",
            "resource_id": "host-001",
            "ip_addr": "172.16.0.1",
            "hypervisor_type": "KVM",
            "cpu": "64",
            "memory": "262144",
        }
    ],
    "total": 1,
}

FAKE_DS = {
    "result": True,
    "data": [
        {
            "resource_name": "ds-01",
            "resource_id": "ds-001",
            "ip_addr": "172.16.0.2",
            "storage_gb": "51200",
        }
    ],
    "total": 1,
}

FAKE_ELB = {
    "result": True,
    "data": [
        {
            # 原始 obj，使用回退键验证多键兜底
            "name": "elb-01",
            "id": "elb-001",
            "eip": "1.2.3.4",
            "spec": "shared",
        }
    ],
    "total": 1,
}


def _make_fake_driver():
    drv = MagicMock()
    drv.list_biz_regions.return_value = FAKE_BIZ
    drv.list_vms.return_value = FAKE_VMS
    drv.list_hosts.return_value = FAKE_HOSTS
    drv.list_ds.return_value = FAKE_DS
    drv.list_elb.return_value = FAKE_ELB
    return drv


def _make_manager():
    from plugins.inputs.manageone.manageone_info import ManageOneManager

    return ManageOneManager(
        params={
            "username": "ak",
            "password": "sk",
            "region": "region-A",
            "host": "https://manageone.example.com",
        }
    )


def test_list_all_resources_success_and_platform():
    mgr = _make_manager()
    with patch.object(mgr, "_driver", return_value=_make_fake_driver()):
        out = mgr.list_all_resources()

    assert out["success"] is True
    result = out["result"]
    plat = result["manageone"][0]
    assert plat["global_domain_name"] == "https://manageone.example.com"
    assert plat["region"] == "region-A"
    assert set(plat.keys()) == {"global_domain_name", "region"}


def test_cloud_fields_exact():
    mgr = _make_manager()
    with patch.object(mgr, "_driver", return_value=_make_fake_driver()):
        out = mgr.list_all_resources()
    cloud = out["result"]["manageone_cloud"]
    assert len(cloud) >= 1
    assert set(cloud[0].keys()) == {
        "resource_name", "resource_id", "cloud_version", "brand",
        "vcpus", "memory_mb", "storage_gb",
    }
    assert cloud[0]["resource_id"] == "biz-001"


def test_server_fields_exact_and_self_host_ip():
    mgr = _make_manager()
    with patch.object(mgr, "_driver", return_value=_make_fake_driver()):
        out = mgr.list_all_resources()
    servers = out["result"]["manageone_server"]
    assert len(servers) >= 1
    s = servers[0]
    assert set(s.keys()) == {
        "resource_name", "resource_id", "ip_addr", "region", "status",
        "os_name", "vcpus", "create_time", "self_host_ip", "expired_time",
    }
    assert s["ip_addr"] == "10.0.0.1"          # inner_ip 映射
    assert s["self_host_ip"] == "172.16.0.1"   # 由 host_id 命中宿主机映射
    assert s["expired_time"] == ""             # 驱动未给，留空


def test_host_fields_exact():
    mgr = _make_manager()
    with patch.object(mgr, "_driver", return_value=_make_fake_driver()):
        out = mgr.list_all_resources()
    hosts = out["result"]["manageone_host"]
    assert len(hosts) >= 1
    h = hosts[0]
    assert set(h.keys()) == {
        "resource_name", "resource_id", "ip_addr", "hypervisor_type",
        "vcpus", "memory_mb",
    }
    assert h["vcpus"] == "64"        # cpu 映射
    assert h["memory_mb"] == "262144"  # memory 映射


def test_ds_fields_exact():
    mgr = _make_manager()
    with patch.object(mgr, "_driver", return_value=_make_fake_driver()):
        out = mgr.list_all_resources()
    ds = out["result"]["manageone_ds"]
    assert len(ds) >= 1
    assert set(ds[0].keys()) == {
        "resource_name", "resource_id", "ip_addr", "storage_gb",
    }


def test_elb_fields_exact_and_fallbacks():
    mgr = _make_manager()
    with patch.object(mgr, "_driver", return_value=_make_fake_driver()):
        out = mgr.list_all_resources()
    elb = out["result"]["manageone_elb"]
    assert len(elb) >= 1
    e = elb[0]
    assert set(e.keys()) == {
        "resource_name", "resource_id", "ip_addr", "instance_type",
    }
    assert e["resource_name"] == "elb-01"   # name 回退
    assert e["resource_id"] == "elb-001"    # id 回退
    assert e["ip_addr"] == "1.2.3.4"        # eip 回退
    assert e["instance_type"] == "shared"   # spec 回退


def test_error_branch_sets_success_false():
    mgr = _make_manager()
    fake = _make_fake_driver()
    fake.list_vms.side_effect = RuntimeError("boom")
    with patch.object(mgr, "_driver", return_value=fake):
        out = mgr.list_all_resources()
    assert out["success"] is False
    assert "cmdb_collect_error" in out["result"]


def test_server_self_host_ip_not_found():
    """vm.host_id 不在宿主机映射中时，self_host_ip 应为空串。"""
    mgr = _make_manager()
    fake = MagicMock()
    # hosts 里没有 id=host-999 的宿主机
    fake.list_hosts.return_value = {
        "result": True,
        "data": [
            {
                "resource_name": "h1",
                "resource_id": "host-001",
                "ip_addr": "10.0.0.1",
                "hypervisor_type": "KVM",
                "cpu": "32",
                "memory": "65536",
            }
        ],
        "total": 1,
    }
    fake.list_vms.return_value = {
        "result": True,
        "data": [
            {
                "resource_name": "vm1",
                "resource_id": "vm-1",
                "inner_ip": "10.0.1.1",
                "region": "r1",
                "status": "active",
                "os_name": "CentOS",
                "vcpus": "2",
                "host_id": "host-999",
                "create_time": "2025-01-01",
            }
        ],
        "total": 1,
    }
    # 其余 list_* 返回空，避免干扰
    fake.list_biz_regions.return_value = {"result": True, "data": [], "total": 0}
    fake.list_ds.return_value = {"result": True, "data": [], "total": 0}
    fake.list_elb.return_value = {"result": True, "data": [], "total": 0}
    with patch.object(mgr, "_driver", return_value=fake):
        out = mgr.list_all_resources()
    server = out["result"]["manageone_server"][0]
    assert server["self_host_ip"] == ""


def test_list_failed_result_raises_into_error_branch():
    mgr = _make_manager()
    fake = _make_fake_driver()
    fake.list_biz_regions.return_value = {"result": False, "message": "auth failed"}
    with patch.object(mgr, "_driver", return_value=fake):
        out = mgr.list_all_resources()
    assert out["success"] is False
    assert "cmdb_collect_error" in out["result"]
