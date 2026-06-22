# -*- coding: utf-8 -*-
"""华为云子对象采集器单测（Phase A）：mock 驱动 list_* 返回，
断言 9 个新对象字段对齐模型 + 隐藏关联字段 + RDS/DCS 官方字段归一化；
并守护存量 hwcloud/hwcloud_ecs 输出不变。"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))


def _make_manager():
    from plugins.inputs.hwcloud.huaweicloud_info import HuaweiCloudManager

    return HuaweiCloudManager(
        params={"username": "ak", "password": "sk", "region": "cn-north-4",
                "host": "https://ecs.cn-north-4.myhuaweicloud.com"}
    )


def _fake_driver():
    d = MagicMock()
    d.list_vms.return_value = {"result": True, "data": [
        {"resource_name": "web-01", "resource_id": "ecs-001", "ip_addr": "192.168.1.10",
         "public_ip": "1.2.3.4", "region": "cn-north-4", "zone": "az1", "vpc": "v-1",
         "status": "ACTIVE", "instance_type": "s6", "os_name": "CentOS", "vcpus": 2,
         "memory_mb": 4096, "charge_type": "postPaid", "create_time": "t", "expired_time": ""}]}
    d.list_disks.return_value = {"result": True, "data": [
        {"resource_name": "disk-1", "resource_id": "d-1", "disk_size": 40, "disk_type": "SYSTEM_DISK",
         "category": "SSD", "status": "in-use", "charge_type": "POSTPAID", "zone": "az1",
         "region": "cn-north-4", "create_time": "t", "server_id": "ecs-001"}]}
    d.list_buckets.return_value = {"result": True, "data": [
        {"resource_name": "b1", "resource_id": "b1", "bucket_type": "STANDARD", "region": "cn-north-4", "create_time": ""}]}
    d.list_vpcs.return_value = {"result": True, "data": [
        {"resource_name": "vpc1", "resource_id": "v-1", "status": "OK", "cidr": "10.0.0.0/16",
         "is_default": False, "region": "cn-north-4"}]}
    d.list_subnets.return_value = {"result": True, "data": [
        {"resource_name": "sub1", "resource_id": "s-1", "status": "ACTIVE", "cidr": "10.0.1.0/24",
         "gateway": "10.0.1.1", "zone": "az1", "region": "cn-north-4", "vpc": "v-1"}]}
    d.list_eips.return_value = {"result": True, "data": [
        {"resource_name": "eip1", "resource_id": "e-1", "ip_addr": "1.2.3.4", "status": "DOWN",
         "bandwidth": 5, "charge_type": "POSTPAID", "region": "cn-north-4", "create_time": "t"}]}
    d.list_security_groups.return_value = {"result": True, "data": [
        {"resource_name": "sg1", "resource_id": "sg-1", "is_default": True, "region": "cn-north-4", "vpc": ""}]}
    d.list_load_balancers.return_value = {"result": True, "data": [
        {"resource_name": "lb1", "resource_id": "lb-1", "status": True, "ip_version": "IPV4",
         "ipv6_addr": "", "charge_type": "", "region": "cn-north-4", "create_time": "t", "vpc": "v-1"}]}
    # RDS：官方 ListInstances 形态（嵌套 datastore/volume/charge_info + private_ips/public_ips 列表）
    d.list_rds.return_value = {"result": True, "data": [
        {"id": "rds-1", "name": "mysql-1", "status": "ACTIVE", "type": "Ha",
         "datastore": {"type": "MySQL", "version": "8.0"}, "volume": {"type": "CLOUDSSD", "size": 100},
         "region": "cn-north-4", "vpc_id": "v-1", "subnet_id": "s-1",
         "private_ips": ["10.0.1.5"], "public_ips": ["1.2.3.5"], "cpu": "4", "mem": "8",
         "port": 3306, "created": "2025-01-01", "charge_info": {"charge_mode": "prePaid"}}]}
    # DCS：官方 V2 ListInstances 形态（instance_id / charging_mode / created_at）
    d.list_dcs.return_value = {"result": True, "data": [
        {"instance_id": "dcs-1", "name": "redis-1", "status": "RUNNING", "engine": "Redis",
         "engine_version": "5.0", "capacity": 4, "ip": "10.0.1.6", "port": 6379,
         "vpc_id": "v-1", "subnet_id": "s-1", "charging_mode": 0, "created_at": "2025-01-02", "cache_mode": "ha"}]}
    return d


def test_exec_script_emits_11_keys_existing_untouched():
    mgr = _make_manager()
    with patch.object(mgr, "_driver", return_value=_fake_driver()):
        out = mgr.list_all_resources()
    assert out["success"] is True
    r = out["result"]
    assert set(r.keys()) == {
        "hwcloud", "hwcloud_ecs", "hwcloud_evs", "hwcloud_obs", "hwcloud_vpc",
        "hwcloud_subnet", "hwcloud_eip", "hwcloud_sg", "hwcloud_elb", "hwcloud_rds", "hwcloud_dcs"}
    # 存量快照守护：platform + ECS 与既有契约一致
    assert r["hwcloud"][0]["endpoint"] == "https://ecs.cn-north-4.myhuaweicloud.com"
    assert r["hwcloud_ecs"][0]["resource_id"] == "ecs-001"
    assert r["hwcloud_ecs"][0]["vcpus"] == "2"


def test_evs_fields_and_hidden_server_id():
    mgr = _make_manager()
    with patch.object(mgr, "_driver", return_value=_fake_driver()):
        evs = mgr.get_evs()[0]
    assert evs["resource_id"] == "d-1"
    assert evs["disk_size"] == "40"
    assert evs["server_id"] == "ecs-001"  # 隐藏关联→ECS
    assert set(evs.keys()) == {"resource_name", "resource_id", "disk_size", "disk_type", "category",
                               "status", "charge_type", "zone", "region", "create_time", "server_id"}


def test_subnet_carries_hidden_vpc():
    mgr = _make_manager()
    with patch.object(mgr, "_driver", return_value=_fake_driver()):
        sub = mgr.get_subnet()[0]
    assert sub["vpc"] == "v-1"
    assert sub["cidr"] == "10.0.1.0/24"


def test_rds_official_nested_normalization():
    mgr = _make_manager()
    with patch.object(mgr, "_driver", return_value=_fake_driver()):
        rds = mgr.get_rds()[0]
    assert rds["resource_id"] == "rds-1"
    assert rds["resource_name"] == "mysql-1"
    assert rds["engine"] == "MySQL"          # datastore.type
    assert rds["engine_version"] == "8.0"    # datastore.version
    assert rds["volume_type"] == "CLOUDSSD"  # volume.type
    assert rds["volume_size"] == "100"       # volume.size
    assert rds["ip_addr"] == "10.0.1.5"      # private_ips[0]
    assert rds["public_ip"] == "1.2.3.5"     # public_ips[0]
    assert rds["vcpus"] == "4"               # cpu
    assert rds["memory_gb"] == "8"           # mem
    assert rds["port"] == "3306"
    assert rds["charge_type"] == "prePaid"   # charge_info.charge_mode
    assert rds["create_time"] == "2025-01-01"
    assert rds["vpc_id"] == "v-1" and rds["subnet_id"] == "s-1"


def test_dcs_official_v2_field_names():
    mgr = _make_manager()
    with patch.object(mgr, "_driver", return_value=_fake_driver()):
        dcs = mgr.get_dcs()[0]
    assert dcs["resource_id"] == "dcs-1"     # instance_id
    assert dcs["capacity_gb"] == "4"         # capacity
    assert dcs["charge_type"] == "0"         # charging_mode → str
    assert dcs["create_time"] == "2025-01-02"  # created_at
    assert dcs["cache_mode"] == "ha"
    assert dcs["ip_addr"] == "10.0.1.6"


def test_driver_passes_project_id_only_when_present():
    """华为云 SDK 构造必需 project_id：提供则透传，缺失则不传（保留驱动的明确报错）。"""
    from plugins.inputs.hwcloud.huaweicloud_info import HuaweiCloudManager
    with_pid = HuaweiCloudManager(params={"accessKey": "a", "accessSecret": "b",
                                          "region": "r", "host": "h", "project_id": "p-123"})
    assert with_pid._driver().kwargs.get("project_id") == "p-123"
    without = HuaweiCloudManager(params={"accessKey": "a", "accessSecret": "b", "region": "r", "host": "h"})
    assert "project_id" not in without._driver().kwargs


def test_new_object_failure_is_best_effort_and_does_not_break_collection():
    """新对象采集失败应被吞掉（返回 []），不影响存量 ECS/platform。"""
    mgr = _make_manager()
    d = _fake_driver()
    d.list_vpcs.return_value = {"result": False, "message": "boom"}      # 返回失败
    d.list_disks.side_effect = RuntimeError("driver exploded")           # 抛异常
    with patch.object(mgr, "_driver", return_value=d):
        assert mgr.get_vpc() == []
        assert mgr.get_evs() == []
        out = mgr.list_all_resources()
    assert out["success"] is True                       # 整次采集仍成功
    assert out["result"]["hwcloud_ecs"][0]["resource_id"] == "ecs-001"  # 存量不受影响
    assert out["result"]["hwcloud_vpc"] == [] and out["result"]["hwcloud_evs"] == []
