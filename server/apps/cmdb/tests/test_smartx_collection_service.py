# -*- coding: utf-8 -*-
"""SmartX server 端采集插件测试：字段对齐 + belong 集群关联（按隐藏 cluster_id，单集群回退）。

覆盖：平台→集群；虚拟机/虚拟卷 belong 集群（隐藏 cluster_id 匹配 cluster.resource_id）。
smartx_host 无关联（模型未定义）。数值字段按模型 int 类型转换（to_int，兼容 round 浮点串）。
"""
import time
import pytest


def _vm_vector():
    ts = int(time.time()) - 60  # 距今 60 秒，避免被 timestamp_gt_one_day_ago 过滤
    return {
        "result": [
            {
                "metric": {
                    "__name__": "smartx_info_gauge",
                    "collect_status": "success",
                    "global_domain_name": "smartx.example.com",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "smartx_cluster_info_gauge",
                    "collect_status": "success",
                    "resource_name": "cluster-01",
                    "resource_id": "cls-001",
                    "cluster_type": "compute",
                    "cpu_vendor": "Intel",
                    "hypervisor": "ELF",
                    "version": "5.0.0",
                    "datacenter": "dc-bj",
                    "storage_gb": "10240",
                    "cache_gb": "512",
                    "vcpus": "128",
                    "memory_mb": "524288",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "smartx_host_info_gauge",
                    "collect_status": "success",
                    "resource_name": "host-01",
                    "resource_id": "host-001",
                    "ip_addr": "10.0.0.100",
                    "data_ip": "10.1.0.100",
                    "cpu_brand": "Xeon Gold 6230",
                    "cpu_arch": "x86_64",
                    "cpu_sockets": "2",
                    "storage_gb": "5120",
                    "cache_gb": "256",
                    "vcpus": "64",
                    "memory_mb": "262144",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "smartx_vm_info_gauge",
                    "collect_status": "success",
                    "resource_name": "vm-01",
                    "resource_id": "vm-001",
                    "status": "running",
                    "vcpus": "4",
                    "memory_mb": "8192",
                    "ip_addr": "10.0.0.10",
                    "os": "CentOS 7.9",
                    # 隐藏字段：命中 cluster.resource_id
                    "cluster_id": "cls-001",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "smartx_vmvolume_info_gauge",
                    "collect_status": "success",
                    "resource_name": "vol-01",
                    "resource_id": "vol-001",
                    "storage_gb": "100",
                    # 隐藏字段：命中 cluster.resource_id
                    "cluster_id": "cls-001",
                },
                "value": [ts, "1"],
            },
        ]
    }


def _make_runner(monkeypatch, inst_name="SmartX生产"):
    from apps.cmdb.collection.collect_plugin.smartx import SmartXCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.smartx import SmartXCollectionPlugin

    class _FakeInst:
        model_id = "smartx"
        instances = [{"inst_name": inst_name}]

    monkeypatch.setattr(SmartXCollectMetrics, "get_collect_inst", lambda self: _FakeInst())
    return SmartXCollectionPlugin(inst_name=inst_name, inst_id=1, task_id=9201)


@pytest.mark.django_db
def test_smartx_platform_and_cluster_fields(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    platform = runner.result["smartx"][0]
    assert platform["global_domain_name"] == "smartx.example.com"

    cluster = runner.result["smartx_cluster"][0]
    assert cluster["resource_id"] == "cls-001"
    assert cluster["inst_name"] == "cluster-01_cls-001"
    # 数值字段对齐模型 int 类型
    assert cluster["storage_gb"] == 10240
    assert cluster["cache_gb"] == 512
    assert cluster["vcpus"] == 128
    assert cluster["memory_mb"] == 524288
    assert cluster["cluster_type"] == "compute"
    assert cluster["cpu_vendor"] == "Intel"
    assert cluster["hypervisor"] == "ELF"
    assert cluster["version"] == "5.0.0"
    assert cluster["datacenter"] == "dc-bj"

    # cluster belong smartx (平台=self.inst_name)
    assert cluster["assos"] == [
        {
            "model_id": "smartx",
            "inst_name": "SmartX生产",
            "asst_id": "belong",
            "model_asst_id": "smartx_cluster_belong_smartx",
        }
    ]


@pytest.mark.django_db
def test_smartx_host_fields_and_no_assos(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    host = runner.result["smartx_host"][0]
    assert host["resource_id"] == "host-001"
    assert host["inst_name"] == "host-01_host-001"
    assert host["ip_addr"] == "10.0.0.100"
    assert host["data_ip"] == "10.1.0.100"
    assert host["cpu_brand"] == "Xeon Gold 6230"
    assert host["cpu_arch"] == "x86_64"
    assert host["cpu_sockets"] == 2
    assert host["storage_gb"] == 5120
    assert host["cache_gb"] == 256
    assert host["vcpus"] == 64
    assert host["memory_mb"] == 262144
    # 无关联：host 实例 dict 不含 assos key
    assert "assos" not in host


@pytest.mark.django_db
def test_smartx_vm_belong_cluster(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    vm = runner.result["smartx_vm"][0]
    assert vm["resource_id"] == "vm-001"
    assert vm["inst_name"] == "vm-01_vm-001"
    assert vm["status"] == "running"
    assert vm["vcpus"] == 4
    assert vm["memory_mb"] == 8192
    assert vm["ip_addr"] == "10.0.0.10"
    assert vm["os"] == "CentOS 7.9"

    cluster = runner.result["smartx_cluster"][0]
    assert vm["assos"] == [
        {
            "model_id": "smartx_cluster",
            "inst_name": cluster["inst_name"],
            "asst_id": "belong",
            "model_asst_id": "smartx_vm_belong_smartx_cluster",
        }
    ]


@pytest.mark.django_db
def test_smartx_vmvolume_belong_cluster(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    vol = runner.result["smartx_vmvolume"][0]
    assert vol["resource_id"] == "vol-001"
    assert vol["storage_gb"] == 100

    cluster = runner.result["smartx_cluster"][0]
    assert vol["assos"] == [
        {
            "model_id": "smartx_cluster",
            "inst_name": cluster["inst_name"],
            "asst_id": "belong",
            "model_asst_id": "smartx_vmvolume_belong_smartx_cluster",
        }
    ]


@pytest.mark.django_db
def test_smartx_single_cluster_fallback(monkeypatch):
    """vm 的 cluster_id 为空但只有一个集群 → 仍 belong 该集群。"""
    runner = _make_runner(monkeypatch)
    ts = int(time.time()) - 60
    vector = {
        "result": [
            {
                "metric": {
                    "__name__": "smartx_cluster_info_gauge",
                    "collect_status": "success",
                    "resource_name": "cluster-01",
                    "resource_id": "cls-001",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "smartx_vm_info_gauge",
                    "collect_status": "success",
                    "resource_name": "vm-99",
                    "resource_id": "vm-099",
                    # cluster_id 缺失，单集群回退
                },
                "value": [ts, "1"],
            },
        ]
    }
    runner.format_data(vector)
    runner.format_metrics()

    vm = runner.result["smartx_vm"][0]
    assert vm["assos"] == [
        {
            "model_id": "smartx_cluster",
            "inst_name": "cluster-01_cls-001",
            "asst_id": "belong",
            "model_asst_id": "smartx_vm_belong_smartx_cluster",
        }
    ]


@pytest.mark.django_db
def test_smartx_belong_miss_multi_cluster(monkeypatch):
    """cluster_id 查不到且集群非唯一 → 不建关联（返回 []）。"""
    runner = _make_runner(monkeypatch)
    ts = int(time.time()) - 60
    vector = {
        "result": [
            {
                "metric": {
                    "__name__": "smartx_cluster_info_gauge",
                    "collect_status": "success",
                    "resource_name": "cluster-01",
                    "resource_id": "cls-001",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "smartx_cluster_info_gauge",
                    "collect_status": "success",
                    "resource_name": "cluster-02",
                    "resource_id": "cls-002",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "smartx_vm_info_gauge",
                    "collect_status": "success",
                    "resource_name": "vm-99",
                    "resource_id": "vm-099",
                    "cluster_id": "nonexistent",
                },
                "value": [ts, "1"],
            },
        ]
    }
    runner.format_data(vector)
    runner.format_metrics()

    vm = runner.result["smartx_vm"][0]
    assert vm["assos"] == []


def test_smartx_field_mappings_cover_model_attrs():
    from apps.cmdb.collection.plugins.community.cloud.smartx import SmartXCollectionPlugin

    fm = SmartXCollectionPlugin.field_mappings

    # 平台对象：仅 attr 字段，无 inst_name/assos
    assert set(fm["smartx"].keys()) == {"global_domain_name"}

    def business_fields(model_id):
        return {k for k in fm[model_id] if k not in ("inst_name", "assos")}

    assert business_fields("smartx_cluster") == {
        "resource_name", "resource_id", "cluster_type", "cpu_vendor", "hypervisor",
        "version", "datacenter", "storage_gb", "cache_gb", "vcpus", "memory_mb",
    }
    assert business_fields("smartx_host") == {
        "resource_name", "resource_id", "ip_addr", "data_ip", "cpu_brand", "cpu_arch",
        "cpu_sockets", "storage_gb", "cache_gb", "vcpus", "memory_mb",
    }
    assert business_fields("smartx_vm") == {
        "resource_name", "resource_id", "status", "vcpus", "memory_mb", "ip_addr", "os",
    }
    assert business_fields("smartx_vmvolume") == {
        "resource_name", "resource_id", "storage_gb",
    }

    # smartx_host 无 assos
    assert "assos" not in fm["smartx_host"]


def test_smartx_in_collect_obj_tree():
    from apps.cmdb.services.collect_object_tree import get_collect_obj_tree

    tree = get_collect_obj_tree()
    cloud = next(g for g in tree if g.get("id") == "cloud")
    model_ids = {c.get("model_id") for c in cloud.get("children", [])}
    assert "smartx" in model_ids


def test_smartx_plugin_registered():
    from apps.cmdb.collection.plugins import get_collection_plugin
    from apps.cmdb.constants.constants import CollectPluginTypes
    from apps.cmdb.collection.plugins.community.cloud.smartx import SmartXCollectionPlugin

    cls = get_collection_plugin(CollectPluginTypes.CLOUD, "smartx")
    assert cls is SmartXCollectionPlugin
