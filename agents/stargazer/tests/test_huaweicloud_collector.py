# -*- coding: utf-8 -*-
"""华为云采集器单测：mock 驱动，断言输出结构与字段对齐模型设计。"""
import sys
from pathlib import Path
from unittest.mock import patch

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

FAKE_ECS = [
    {
        "resource_id": "ecs-001",
        "resource_name": "web-01",
        "ip_addr": "192.168.1.10",
        "public_ip": "1.2.3.4",
        "region": "cn-north-4",
        "zone": "cn-north-4a",
        "vpc": "vpc-abc",
        "status": "ACTIVE",
        "instance_type": "s6.large.2",
        "os_name": "CentOS 7.6",
        "vcpus": "2",
        "memory_mb": "4096",
        "charge_type": "postPaid",
        "create_time": "2025-01-01T00:00:00Z",
        "expired_time": "",
    }
]


def _make_manager():
    from plugins.inputs.hwcloud.huaweicloud_info import HuaweiCloudManager

    return HuaweiCloudManager(
        params={
            "username": "ak",
            "password": "sk",
            "region": "cn-north-4",
            "host": "https://ecs.cn-north-4.myhuaweicloud.com",
        }
    )


def test_list_all_resources_structure_and_fields():
    mgr = _make_manager()
    with patch.object(mgr, "get_ecs", return_value=FAKE_ECS):
        out = mgr.list_all_resources()

    assert out["success"] is True
    result = out["result"]
    assert result["hwcloud"][0]["endpoint"] == "https://ecs.cn-north-4.myhuaweicloud.com"
    ecs = result["hwcloud_ecs"][0]
    expected_keys = {
        "resource_name", "resource_id", "ip_addr", "public_ip", "region", "zone",
        "vpc", "status", "instance_type", "os_name", "vcpus", "memory_mb",
        "charge_type", "create_time", "expired_time",
    }
    assert set(ecs.keys()) == expected_keys
    assert ecs["resource_id"] == "ecs-001"


def test_list_all_resources_handles_driver_error():
    mgr = _make_manager()
    with patch.object(mgr, "get_ecs", side_effect=RuntimeError("boom")):
        out = mgr.list_all_resources()
    assert out["success"] is False
    assert "cmdb_collect_error" in out["result"]


def test_get_ecs_field_mapping_and_fallbacks():
    """直接 mock 驱动 list_vms，覆盖 get_ecs 的字段映射、多键回退与类型转换。"""
    from unittest.mock import MagicMock, patch

    mgr = _make_manager()
    driver_response = {
        "result": True,
        "data": [
            {
                # 全部用「回退键」，验证 or 回退路径
                "name": "instance-name",
                "id": "i-12345",
                "private_ip": "10.0.0.1",
                "public_ip": "1.2.3.4",
                "availability_zone": "az1",
                "vpc_id": "vpc-123",
                "status": "RUNNING",
                "flavor": "t1.small",
                "image_name": "Ubuntu 20.04",
                "vcpus": 2,
                "ram": 4096,
                "charge_type": "postPaid",
                "created": "2024-01-01T00:00:00Z",
                # region 不给，验证回退到 self.region
            }
        ],
    }
    fake_driver = MagicMock()
    fake_driver.list_vms.return_value = driver_response
    with patch.object(mgr, "_driver", return_value=fake_driver):
        ecs_list = mgr.get_ecs()

    assert len(ecs_list) == 1
    ecs = ecs_list[0]
    assert ecs["resource_name"] == "instance-name"   # name 回退
    assert ecs["resource_id"] == "i-12345"           # id 回退
    assert ecs["ip_addr"] == "10.0.0.1"              # private_ip 回退
    assert ecs["public_ip"] == "1.2.3.4"
    assert ecs["zone"] == "az1"                      # availability_zone 回退
    assert ecs["vpc"] == "vpc-123"                   # vpc_id 回退
    assert ecs["instance_type"] == "t1.small"        # flavor 回退
    assert ecs["os_name"] == "Ubuntu 20.04"          # image_name 回退
    assert ecs["vcpus"] == "2"                       # 转 str
    assert ecs["memory_mb"] == "4096"                # ram 回退 + 转 str
    assert ecs["region"] == "cn-north-4"             # 回退到 self.region
    assert ecs["status"] == "RUNNING"
    assert ecs["charge_type"] == "postPaid"
    assert ecs["create_time"] == "2024-01-01T00:00:00Z"  # created 回退
    # 恰好 15 字段
    assert set(ecs.keys()) == {
        "resource_name", "resource_id", "ip_addr", "public_ip", "region", "zone",
        "vpc", "status", "instance_type", "os_name", "vcpus", "memory_mb",
        "charge_type", "create_time", "expired_time",
    }


def test_get_ecs_raises_on_failed_result():
    """驱动返回 result=False 时 get_ecs 应抛错（由 list_all_resources 兜底成 success=False）。"""
    from unittest.mock import MagicMock, patch
    import pytest

    mgr = _make_manager()
    fake_driver = MagicMock()
    fake_driver.list_vms.return_value = {"result": False, "message": "auth failed"}
    with patch.object(mgr, "_driver", return_value=fake_driver):
        with pytest.raises(RuntimeError):
            mgr.get_ecs()
