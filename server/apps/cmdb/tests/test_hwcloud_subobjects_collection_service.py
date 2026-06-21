# -*- coding: utf-8 -*-
"""华为云 9 个新子对象 server 端落库测试（Phase A · A4）：
mock VM 指标向量，断言字段对齐 attr-<model> + 关联（evs→ecs install_on、subnet→vpc belong、
其余 belong 平台）+ 数值类型转换 + DCS/官方字段。"""
import time
import pytest


def _ts():
    return int(time.time()) - 60


def _m(name, **labels):
    return {"metric": {"__name__": name, "collect_status": "success", **labels}, "value": [_ts(), "1"]}


def _vector():
    return {"result": [
        _m("hwcloud_info_gauge", endpoint="https://ecs.cn-north-4.myhuaweicloud.com"),
        _m("hwcloud_ecs_info_gauge", resource_name="web-01", resource_id="ecs-001",
           ip_addr="192.168.1.10", public_ip="1.2.3.4", region="cn-north-4", zone="az1",
           vpc="v-1", status="ACTIVE", instance_type="s6", os_name="CentOS", vcpus="2",
           memory_mb="4096", charge_type="postPaid", create_time="t", expired_time=""),
        _m("hwcloud_vpc_info_gauge", resource_name="vpc1", resource_id="v-1", status="OK",
           cidr="10.0.0.0/16", is_default="False", region="cn-north-4"),
        _m("hwcloud_evs_info_gauge", resource_name="disk-1", resource_id="d-1", disk_size="40",
           disk_type="SYSTEM_DISK", category="SSD", status="in-use", charge_type="POSTPAID",
           zone="az1", region="cn-north-4", create_time="t", server_id="ecs-001"),
        _m("hwcloud_obs_info_gauge", resource_name="b1", resource_id="b1", bucket_type="STANDARD",
           region="cn-north-4", create_time=""),
        _m("hwcloud_subnet_info_gauge", resource_name="sub1", resource_id="s-1", status="ACTIVE",
           cidr="10.0.1.0/24", gateway="10.0.1.1", zone="az1", region="cn-north-4", vpc="v-1"),
        _m("hwcloud_eip_info_gauge", resource_name="eip1", resource_id="e-1", ip_addr="1.2.3.4",
           status="DOWN", bandwidth="5", charge_type="POSTPAID", region="cn-north-4", create_time="t"),
        _m("hwcloud_sg_info_gauge", resource_name="sg1", resource_id="sg-1", is_default="True",
           region="cn-north-4"),
        _m("hwcloud_elb_info_gauge", resource_name="lb1", resource_id="lb-1", status="True",
           ip_version="IPV4", ipv6_addr="", charge_type="", region="cn-north-4", create_time="t"),
        _m("hwcloud_rds_info_gauge", resource_name="mysql-1", resource_id="rds-1", ip_addr="10.0.1.5",
           public_ip="1.2.3.5", status="ACTIVE", db_type="Ha", engine="MySQL", engine_version="8.0",
           volume_type="CLOUDSSD", volume_size="100", vcpus="4", memory_gb="8", port="3306",
           region="cn-north-4", charge_type="prePaid", create_time="t"),
        _m("hwcloud_dcs_info_gauge", resource_name="redis-1", resource_id="dcs-1", ip_addr="10.0.1.6",
           port="6379", status="RUNNING", engine="Redis", engine_version="5.0", capacity_gb="4",
           cache_mode="ha", charge_type="0", region="cn-north-4", create_time="t"),
    ]}


def _runner(monkeypatch):
    from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin

    class _FakeInst:
        model_id = "hwcloud"
        instances = [{"inst_name": "华为云生产"}]

    monkeypatch.setattr(HwCloudCollectionPlugin, "get_collect_inst", lambda self: _FakeInst())
    r = HwCloudCollectionPlugin(inst_name="华为云生产", inst_id=1, task_id=8101)
    r.format_data(_vector())
    r.format_metrics()
    return r


@pytest.mark.django_db
def test_all_11_models_present_and_existing_ecs_unchanged(monkeypatch):
    r = _runner(monkeypatch)
    assert set(r.result.keys()) == {
        "hwcloud", "hwcloud_ecs", "hwcloud_vpc", "hwcloud_evs", "hwcloud_obs",
        "hwcloud_subnet", "hwcloud_eip", "hwcloud_sg", "hwcloud_elb", "hwcloud_rds", "hwcloud_dcs"}
    ecs = r.result["hwcloud_ecs"][0]
    assert ecs["inst_name"] == "web-01_ecs-001" and ecs["vcpus"] == 2
    assert ecs["assos"] == [{"model_id": "hwcloud", "inst_name": "华为云生产",
                             "asst_id": "belong", "model_asst_id": "hwcloud_ecs_belong_hwcloud"}]


@pytest.mark.django_db
def test_evs_install_on_ecs_and_int(monkeypatch):
    r = _runner(monkeypatch)
    evs = r.result["hwcloud_evs"][0]
    assert evs["disk_size"] == 40 and evs["inst_name"] == "disk-1_d-1"
    assert {"model_id": "hwcloud", "asst_id": "belong",
            "model_asst_id": "hwcloud_evs_belong_hwcloud", "inst_name": "华为云生产"} in evs["assos"]
    assert {"model_id": "hwcloud_ecs", "asst_id": "install_on",
            "model_asst_id": "hwcloud_evs_install_on_hwcloud_ecs",
            "inst_name": "web-01_ecs-001"} in evs["assos"]


@pytest.mark.django_db
def test_subnet_belong_vpc(monkeypatch):
    r = _runner(monkeypatch)
    sub = r.result["hwcloud_subnet"][0]
    assert sub["assos"] == [{"model_id": "hwcloud_vpc", "inst_name": "vpc1_v-1",
                             "asst_id": "belong", "model_asst_id": "hwcloud_subnet_belong_hwcloud_vpc"}]


@pytest.mark.django_db
def test_rds_and_dcs_fields_types(monkeypatch):
    r = _runner(monkeypatch)
    rds = r.result["hwcloud_rds"][0]
    assert rds["engine"] == "MySQL" and rds["engine_version"] == "8.0"
    assert rds["volume_size"] == 100 and rds["vcpus"] == 4 and rds["memory_gb"] == 8 and rds["port"] == 3306
    assert rds["charge_type"] == "prePaid"
    assert rds["assos"][0]["model_asst_id"] == "hwcloud_rds_belong_hwcloud"
    dcs = r.result["hwcloud_dcs"][0]
    assert dcs["capacity_gb"] == 4 and dcs["port"] == 6379
    assert dcs["charge_type"] == "0" and dcs["cache_mode"] == "ha"


@pytest.mark.django_db
def test_subnet_unmatched_vpc_skips_assoc(monkeypatch):
    """VPC 未命中时 subnet 不建关联（返回空 assos）。"""
    from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin

    class _FakeInst:
        model_id = "hwcloud"
        instances = [{"inst_name": "华为云生产"}]

    monkeypatch.setattr(HwCloudCollectionPlugin, "get_collect_inst", lambda self: _FakeInst())
    r = HwCloudCollectionPlugin(inst_name="华为云生产", inst_id=1, task_id=8102)
    r.format_data({"result": [
        _m("hwcloud_subnet_info_gauge", resource_name="sub9", resource_id="s-9",
           status="ACTIVE", cidr="x", gateway="y", zone="az", region="r", vpc="missing"),
    ]})
    r.format_metrics()
    assert r.result["hwcloud_subnet"][0]["assos"] == []
