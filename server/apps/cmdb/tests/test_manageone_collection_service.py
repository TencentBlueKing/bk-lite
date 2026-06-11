# -*- coding: utf-8 -*-
"""ManageOne server 端采集插件测试：字段对齐 + 多层级关联。

覆盖：平台→云平台→(云服务器/宿主机/数据存储/ELB) 的字段映射与关联建立。
关联键策略：cloud belong 平台(self.inst_name)；子资源 belong 单云回退；
host install_on server 用 host.ip_addr == server.self_host_ip 匹配。
"""
import time
import pytest


def _vm_vector():
    ts = int(time.time()) - 60  # 距今 60 秒，避免被 timestamp_gt_one_day_ago 过滤
    return {
        "result": [
            {
                "metric": {
                    "__name__": "manageone_info_gauge",
                    "collect_status": "success",
                    "global_domain_name": "manageone.example.com",
                    "region": "region-01",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "manageone_cloud_info_gauge",
                    "collect_status": "success",
                    "resource_name": "cloud-A",
                    "resource_id": "cloud-001",
                    "cloud_version": "8.3.0",
                    "brand": "FusionSphere",
                    "vcpus": "256",
                    "memory_mb": "1048576",
                    "storage_gb": "20480",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "manageone_server_info_gauge",
                    "collect_status": "success",
                    "resource_name": "vm-01",
                    "resource_id": "server-001",
                    "ip_addr": "10.0.0.10",
                    "region": "region-01",
                    "status": "ACTIVE",
                    "os_name": "CentOS 7.6",
                    "vcpus": "4",
                    "self_host_ip": "10.0.0.100",
                    "create_time": "2025-01-01T00:00:00Z",
                    "expired_time": "2026-12-31T23:59:59Z",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "manageone_host_info_gauge",
                    "collect_status": "success",
                    "resource_name": "host-01",
                    "resource_id": "host-001",
                    "ip_addr": "10.0.0.100",
                    "hypervisor_type": "KVM",
                    "memory_mb": "262144",
                    "vcpus": "64",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "manageone_ds_info_gauge",
                    "collect_status": "success",
                    "resource_name": "ds-01",
                    "resource_id": "ds-001",
                    "ip_addr": "10.0.0.200",
                    "storage_gb": "40960",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "manageone_elb_info_gauge",
                    "collect_status": "success",
                    "resource_name": "elb-01",
                    "resource_id": "elb-001",
                    "ip_addr": "10.0.0.250",
                    "instance_type": "shared",
                },
                "value": [ts, "1"],
            },
        ]
    }


def _make_runner(monkeypatch, inst_name="ManageOne生产"):
    from apps.cmdb.collection.collect_plugin.manageone import ManageOneCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.manageone import ManageOneCollectionPlugin

    class _FakeInst:
        model_id = "manageone"
        instances = [{"inst_name": inst_name}]

    monkeypatch.setattr(ManageOneCollectMetrics, "get_collect_inst", lambda self: _FakeInst())
    return ManageOneCollectionPlugin(inst_name=inst_name, inst_id=1, task_id=9001)


@pytest.mark.django_db
def test_manageone_platform_and_cloud_fields(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    platform = runner.result["manageone"][0]
    assert platform["global_domain_name"] == "manageone.example.com"
    assert platform["region"] == "region-01"

    cloud = runner.result["manageone_cloud"][0]
    assert cloud["resource_id"] == "cloud-001"
    assert cloud["inst_name"] == "cloud-A_cloud-001"
    assert cloud["vcpus"] == 256
    assert cloud["memory_mb"] == 1048576
    assert cloud["storage_gb"] == 20480
    # cloud belong 平台
    assert cloud["assos"] == [
        {
            "model_id": "manageone",
            "inst_name": "ManageOne生产",
            "asst_id": "belong",
            "model_asst_id": "manageone_cloud_belong_manageone",
        }
    ]


@pytest.mark.django_db
def test_manageone_single_cloud_belong(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    assert runner.single_cloud_inst_name == "cloud-A_cloud-001"

    for model_id in ("manageone_server", "manageone_ds", "manageone_elb"):
        inst = runner.result[model_id][0]
        belong = [a for a in inst["assos"] if a["asst_id"] == "belong"]
        assert belong == [
            {
                "model_id": "manageone_cloud",
                "inst_name": "cloud-A_cloud-001",
                "asst_id": "belong",
                "model_asst_id": f"{model_id}_belong_manageone_cloud",
            }
        ]


@pytest.mark.django_db
def test_manageone_host_install_on_server(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    host = runner.result["manageone_host"][0]
    assert host["vcpus"] == 64
    assert host["memory_mb"] == "262144"

    # host belong cloud
    belong = [a for a in host["assos"] if a["asst_id"] == "belong"]
    assert belong == [
        {
            "model_id": "manageone_cloud",
            "inst_name": "cloud-A_cloud-001",
            "asst_id": "belong",
            "model_asst_id": "manageone_host_belong_manageone_cloud",
        }
    ]

    # host install_on server (host.ip_addr == server.self_host_ip == 10.0.0.100)
    server = runner.result["manageone_server"][0]
    install = [a for a in host["assos"] if a["asst_id"] == "install_on"]
    assert install == [
        {
            "model_id": "manageone_server",
            "inst_name": server["inst_name"],
            "asst_id": "install_on",
            "model_asst_id": "manageone_host_install_on_manageone_server",
        }
    ]


@pytest.mark.django_db
def test_manageone_multi_cloud_no_belong(monkeypatch):
    """多云场景：single_cloud 回退为空，子资源不建 belong 关联。"""
    runner = _make_runner(monkeypatch)
    ts = int(time.time()) - 60
    vector = {
        "result": [
            {
                "metric": {
                    "__name__": "manageone_cloud_info_gauge",
                    "collect_status": "success",
                    "resource_name": "cloud-A",
                    "resource_id": "cloud-001",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "manageone_cloud_info_gauge",
                    "collect_status": "success",
                    "resource_name": "cloud-B",
                    "resource_id": "cloud-002",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "manageone_server_info_gauge",
                    "collect_status": "success",
                    "resource_name": "vm-01",
                    "resource_id": "server-001",
                },
                "value": [ts, "1"],
            },
        ]
    }
    runner.format_data(vector)
    runner.format_metrics()

    assert runner.single_cloud_inst_name == ""
    server = runner.result["manageone_server"][0]
    assert server["assos"] == []


def test_manageone_field_mappings_cover_model_attrs():
    from apps.cmdb.collection.plugins.community.cloud.manageone import ManageOneCollectionPlugin

    fm = ManageOneCollectionPlugin.field_mappings

    # 平台对象：仅 attr 字段，无 inst_name/assos
    assert set(fm["manageone"].keys()) == {"global_domain_name", "region"}

    def business_fields(model_id):
        return {k for k in fm[model_id] if k not in ("inst_name", "assos")}

    assert business_fields("manageone_cloud") == {
        "resource_name", "resource_id", "cloud_version", "brand",
        "vcpus", "memory_mb", "storage_gb",
    }
    assert business_fields("manageone_server") == {
        "resource_name", "resource_id", "ip_addr", "region", "status",
        "os_name", "vcpus", "self_host_ip", "create_time", "expired_time",
    }
    assert business_fields("manageone_host") == {
        "resource_name", "resource_id", "ip_addr", "hypervisor_type",
        "memory_mb", "vcpus",
    }
    assert business_fields("manageone_ds") == {
        "resource_name", "resource_id", "ip_addr", "storage_gb",
    }
    assert business_fields("manageone_elb") == {
        "resource_name", "resource_id", "ip_addr", "instance_type",
    }


def test_manageone_in_collect_obj_tree():
    from apps.cmdb.services.collect_object_tree import get_collect_obj_tree

    tree = get_collect_obj_tree()
    cloud = next(g for g in tree if g.get("id") == "cloud")
    model_ids = {c.get("model_id") for c in cloud.get("children", [])}
    assert "manageone" in model_ids


def test_manageone_plugin_registered():
    from apps.cmdb.collection.plugins import get_collection_plugin
    from apps.cmdb.constants.constants import CollectPluginTypes
    from apps.cmdb.collection.plugins.community.cloud.manageone import ManageOneCollectionPlugin

    cls = get_collection_plugin(CollectPluginTypes.CLOUD, "manageone")
    assert cls is ManageOneCollectionPlugin
