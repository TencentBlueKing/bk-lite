# -*- coding: utf-8 -*-
"""OpenStack server 端采集插件测试：字段对齐 + 多层级关联。

覆盖：平台→节点；存储池关联(平台/节点)；卷组关联(节点/虚拟机/存储池)。
关联键用 stargazer 输出的隐藏字段：vm/sp/vg 带 node_name(匹配 node.resource_name)，
vg 带 vm_id/sp_id(匹配 vm/sp 的 resource_id)。
openstack_vm 不建关联：模型 asso 为自引用疑似笔误，跳过并告警。
"""
import time
import pytest


def _vm_vector():
    ts = int(time.time()) - 60  # 距今 60 秒，避免被 timestamp_gt_one_day_ago 过滤
    return {
        "result": [
            {
                "metric": {
                    "__name__": "openstack_info_gauge",
                    "collect_status": "success",
                    "global_domain_name": "openstack.example.com",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "openstack_node_info_gauge",
                    "collect_status": "success",
                    "resource_name": "compute-01",
                    "resource_id": "node-001",
                    "ip_addr": "10.0.0.100",
                    "ram_mb": "262144",
                    "vcpus": "64",
                    "disk_gb": "2048",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "openstack_vm_info_gauge",
                    "collect_status": "success",
                    "resource_name": "vm-01",
                    "resource_id": "vm-001",
                    "ip_addr": "10.0.0.10",
                    "ram_mb": "8192",
                    "vcpus": "4",
                    "disk_gb": "80",
                    "status": "ACTIVE",
                    "os_name": "",
                    "zone": "nova",
                    "region": "RegionOne",
                    "project_name": "admin",
                    # 隐藏字段
                    "node_name": "compute-01",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "openstack_sp_info_gauge",
                    "collect_status": "success",
                    "resource_name": "sp-01",
                    "resource_id": "sp-001",
                    "size_gb": "10240",
                    "region": "RegionOne",
                    "project_name": "admin",
                    "storage_protocol": "iSCSI",
                    "driver_version": "1.2.3",
                    # 隐藏字段
                    "node_name": "compute-01",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "openstack_vg_info_gauge",
                    "collect_status": "success",
                    "resource_name": "vg-01",
                    "resource_id": "vg-001",
                    "size_gb": "100",
                    "zone": "nova",
                    "region": "RegionOne",
                    "project_name": "admin",
                    "status": "in-use",
                    # 隐藏字段：三键全部命中
                    "node_name": "compute-01",
                    "vm_id": "vm-001",
                    "sp_id": "sp-001",
                },
                "value": [ts, "1"],
            },
        ]
    }


def _make_runner(monkeypatch, inst_name="OpenStack生产"):
    from apps.cmdb.collection.collect_plugin.openstack import OpenStackCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.openstack import OpenStackCollectionPlugin

    class _FakeInst:
        model_id = "openstack"
        instances = [{"inst_name": inst_name}]

    monkeypatch.setattr(OpenStackCollectMetrics, "get_collect_inst", lambda self: _FakeInst())
    return OpenStackCollectionPlugin(inst_name=inst_name, inst_id=1, task_id=9101)


@pytest.mark.django_db
def test_openstack_platform_and_node_fields(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    platform = runner.result["openstack"][0]
    assert platform["global_domain_name"] == "openstack.example.com"

    node = runner.result["openstack_node"][0]
    assert node["resource_id"] == "node-001"
    assert node["inst_name"] == "compute-01_node-001"
    assert node["ram_mb"] == 262144
    assert node["vcpus"] == 64
    assert node["disk_gb"] == 2048

    # node belong openstack
    assert node["assos"] == [
        {
            "model_id": "openstack",
            "inst_name": "OpenStack生产",
            "asst_id": "belong",
            "model_asst_id": "openstack_node_belong_openstack",
        }
    ]


@pytest.mark.django_db
def test_openstack_vm_fields_and_no_assos(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    vm = runner.result["openstack_vm"][0]
    assert vm["resource_id"] == "vm-001"
    assert vm["inst_name"] == "vm-01_vm-001"
    assert vm["ram_mb"] == "8192"
    assert vm["vcpus"] == "4"
    assert vm["disk_gb"] == "80"
    assert vm["status"] == "ACTIVE"
    assert vm["zone"] == "nova"
    assert vm["region"] == "RegionOne"
    assert vm["project_name"] == "admin"
    # os_name 为空可缺省（tuple 转换不进；普通字符串取回退 "")，这里是普通映射，落回空串
    assert vm.get("os_name", "") == ""

    # 自关联笔误：vm 关联跳过
    assert vm["assos"] == []


@pytest.mark.django_db
def test_openstack_sp_double_belong(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    sp = runner.result["openstack_sp"][0]
    assert sp["size_gb"] == 10240
    assert sp["storage_protocol"] == "iSCSI"
    assert sp["driver_version"] == "1.2.3"

    node = runner.result["openstack_node"][0]
    assert sp["assos"] == [
        {
            "model_id": "openstack",
            "inst_name": "OpenStack生产",
            "asst_id": "belong",
            "model_asst_id": "openstack_sp_belong_openstack",
        },
        {
            "model_id": "openstack_node",
            "inst_name": node["inst_name"],
            "asst_id": "belong",
            "model_asst_id": "openstack_sp_belong_openstack_node",
        },
    ]


@pytest.mark.django_db
def test_openstack_vg_triple_belong(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    vg = runner.result["openstack_vg"][0]
    assert vg["size_gb"] == 100
    assert vg["status"] == "in-use"

    node = runner.result["openstack_node"][0]
    vm = runner.result["openstack_vm"][0]
    sp = runner.result["openstack_sp"][0]
    assert vg["assos"] == [
        {
            "model_id": "openstack_node",
            "inst_name": node["inst_name"],
            "asst_id": "belong",
            "model_asst_id": "openstack_vg_belong_openstack_node",
        },
        {
            "model_id": "openstack_vm",
            "inst_name": vm["inst_name"],
            "asst_id": "belong",
            "model_asst_id": "openstack_vg_belong_openstack_vm",
        },
        {
            "model_id": "openstack_sp",
            "inst_name": sp["inst_name"],
            "asst_id": "belong",
            "model_asst_id": "openstack_vg_belong_openstack_sp",
        },
    ]


@pytest.mark.django_db
def test_openstack_vg_partial_belong_misses(monkeypatch):
    """隐藏键查不到时不建对应关联。"""
    runner = _make_runner(monkeypatch)
    ts = int(time.time()) - 60
    vector = {
        "result": [
            {
                "metric": {
                    "__name__": "openstack_node_info_gauge",
                    "collect_status": "success",
                    "resource_name": "compute-01",
                    "resource_id": "node-001",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "openstack_vg_info_gauge",
                    "collect_status": "success",
                    "resource_name": "vg-99",
                    "resource_id": "vg-099",
                    # 仅 node_name 命中；vm_id/sp_id 不存在
                    "node_name": "compute-01",
                    "vm_id": "nonexistent",
                    "sp_id": "nonexistent",
                },
                "value": [ts, "1"],
            },
        ]
    }
    runner.format_data(vector)
    runner.format_metrics()

    vg = runner.result["openstack_vg"][0]
    assert vg["assos"] == [
        {
            "model_id": "openstack_node",
            "inst_name": "compute-01_node-001",
            "asst_id": "belong",
            "model_asst_id": "openstack_vg_belong_openstack_node",
        }
    ]


def test_openstack_field_mappings_cover_model_attrs():
    from apps.cmdb.collection.plugins.community.cloud.openstack import OpenStackCollectionPlugin

    fm = OpenStackCollectionPlugin.field_mappings

    # 平台对象：仅 attr 字段，无 inst_name/assos
    assert set(fm["openstack"].keys()) == {"global_domain_name"}

    def business_fields(model_id):
        return {k for k in fm[model_id] if k not in ("inst_name", "assos")}

    assert business_fields("openstack_node") == {
        "resource_name", "resource_id", "ip_addr", "ram_mb", "vcpus", "disk_gb",
    }
    assert business_fields("openstack_vm") == {
        "resource_name", "resource_id", "ip_addr", "ram_mb", "vcpus", "disk_gb",
        "status", "os_name", "zone", "region", "project_name",
    }
    assert business_fields("openstack_sp") == {
        "resource_name", "resource_id", "size_gb", "region", "project_name",
        "storage_protocol", "driver_version",
    }
    assert business_fields("openstack_vg") == {
        "resource_name", "resource_id", "size_gb", "zone", "region",
        "project_name", "status",
    }


def test_openstack_in_collect_obj_tree():
    from apps.cmdb.services.collect_object_tree import get_collect_obj_tree

    tree = get_collect_obj_tree()
    cloud = next(g for g in tree if g.get("id") == "cloud")
    model_ids = {c.get("model_id") for c in cloud.get("children", [])}
    assert "openstack" in model_ids


def test_openstack_plugin_registered():
    from apps.cmdb.collection.plugins import get_collection_plugin
    from apps.cmdb.constants.constants import CollectPluginTypes
    from apps.cmdb.collection.plugins.community.cloud.openstack import OpenStackCollectionPlugin

    cls = get_collection_plugin(CollectPluginTypes.CLOUD, "openstack")
    assert cls is OpenStackCollectionPlugin
