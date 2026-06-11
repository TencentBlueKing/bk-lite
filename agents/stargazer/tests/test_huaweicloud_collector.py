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
    from plugins.inputs.huaweicloud.huaweicloud_info import HuaweiCloudManager

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
    assert expected_keys.issubset(set(ecs.keys()))
    assert ecs["resource_id"] == "ecs-001"


def test_list_all_resources_handles_driver_error():
    mgr = _make_manager()
    with patch.object(mgr, "get_ecs", side_effect=RuntimeError("boom")):
        out = mgr.list_all_resources()
    assert out["success"] is False
    assert "cmdb_collect_error" in out["result"]
