# -*- coding: utf-8 -*-
"""FusionInsight server 端采集插件测试：字段对齐 + belong 关联。

平台 fusioninsight 无业务字段,不单独采集(=采集任务自身实例);
集群 belong 平台(self.inst_name);主机 belong 集群(隐藏 cluster_id 匹配 cluster.resource_id,单集群回退)。
数值字段(vcpus/memory_mb/storage_gb)按普通字符串映射。
"""
import time
import pytest


def _vector():
    ts = int(time.time()) - 60  # 距今 60 秒，避免被 timestamp_gt_one_day_ago 过滤
    return {
        "result": [
            {
                "metric": {
                    "__name__": "fusioninsight_cluster_info_gauge",
                    "collect_status": "success",
                    "resource_name": "cluster-01",
                    "resource_id": "cls-001",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "fusioninsight_host_info_gauge",
                    "collect_status": "success",
                    "resource_name": "host-01",
                    "resource_id": "host-001",
                    "ip_addr": "10.0.0.100",
                    "vcpus": "64",
                    "memory_mb": "262144",
                    "storage_gb": "5120",
                    "status": "normal",
                    "os_name": "EulerOS 2.0",
                    # 隐藏字段：命中 cluster.resource_id
                    "cluster_id": "cls-001",
                },
                "value": [ts, "1"],
            },
        ]
    }


def _make_runner(monkeypatch, inst_name="FusionInsight生产"):
    from apps.cmdb.collection.collect_plugin.fusioninsight import FusionInsightCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.fusioninsight import FusionInsightCollectionPlugin

    class _FakeInst:
        model_id = "fusioninsight"
        instances = [{"inst_name": inst_name}]

    monkeypatch.setattr(FusionInsightCollectMetrics, "get_collect_inst", lambda self: _FakeInst())
    return FusionInsightCollectionPlugin(inst_name=inst_name, inst_id=1, task_id=9301)


@pytest.mark.django_db
def test_fusioninsight_cluster_fields_and_belong_platform(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vector())
    runner.format_metrics()

    cluster = runner.result["fusioninsight_cluster"][0]
    assert cluster["resource_name"] == "cluster-01"
    assert cluster["resource_id"] == "cls-001"
    assert cluster["inst_name"] == "cluster-01_cls-001"

    # cluster belong fusioninsight (平台=self.inst_name)
    assert cluster["assos"] == [
        {
            "model_id": "fusioninsight",
            "inst_name": "FusionInsight生产",
            "asst_id": "belong",
            "model_asst_id": "fusioninsight_cluster_belong_fusioninsight",
        }
    ]


@pytest.mark.django_db
def test_fusioninsight_host_fields_and_belong_cluster(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vector())
    runner.format_metrics()

    host = runner.result["fusioninsight_host"][0]
    assert host["resource_name"] == "host-01"
    assert host["resource_id"] == "host-001"
    assert host["inst_name"] == "host-01_host-001"
    assert host["ip_addr"] == "10.0.0.100"
    # 数值字段为普通字符串映射，不转 int
    assert host["vcpus"] == "64"
    assert host["memory_mb"] == "262144"
    assert host["storage_gb"] == "5120"
    assert host["status"] == "normal"
    assert host["os_name"] == "EulerOS 2.0"

    cluster = runner.result["fusioninsight_cluster"][0]
    assert host["assos"] == [
        {
            "model_id": "fusioninsight_cluster",
            "inst_name": cluster["inst_name"],
            "asst_id": "belong",
            "model_asst_id": "fusioninsight_host_belong_fusioninsight_cluster",
        }
    ]


@pytest.mark.django_db
def test_fusioninsight_single_cluster_fallback(monkeypatch):
    """host 的 cluster_id 为空但只有一个集群 → 仍 belong 该集群。"""
    runner = _make_runner(monkeypatch)
    ts = int(time.time()) - 60
    vector = {
        "result": [
            {
                "metric": {
                    "__name__": "fusioninsight_cluster_info_gauge",
                    "collect_status": "success",
                    "resource_name": "cluster-01",
                    "resource_id": "cls-001",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "fusioninsight_host_info_gauge",
                    "collect_status": "success",
                    "resource_name": "host-99",
                    "resource_id": "host-099",
                    # cluster_id 缺失，单集群回退
                },
                "value": [ts, "1"],
            },
        ]
    }
    runner.format_data(vector)
    runner.format_metrics()

    host = runner.result["fusioninsight_host"][0]
    assert host["assos"] == [
        {
            "model_id": "fusioninsight_cluster",
            "inst_name": "cluster-01_cls-001",
            "asst_id": "belong",
            "model_asst_id": "fusioninsight_host_belong_fusioninsight_cluster",
        }
    ]


@pytest.mark.django_db
def test_fusioninsight_belong_miss_multi_cluster(monkeypatch):
    """cluster_id 查不到且集群非唯一 → 不建关联（返回 []）。"""
    runner = _make_runner(monkeypatch)
    ts = int(time.time()) - 60
    vector = {
        "result": [
            {
                "metric": {
                    "__name__": "fusioninsight_cluster_info_gauge",
                    "collect_status": "success",
                    "resource_name": "cluster-01",
                    "resource_id": "cls-001",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "fusioninsight_cluster_info_gauge",
                    "collect_status": "success",
                    "resource_name": "cluster-02",
                    "resource_id": "cls-002",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "fusioninsight_host_info_gauge",
                    "collect_status": "success",
                    "resource_name": "host-99",
                    "resource_id": "host-099",
                    "cluster_id": "nonexistent",
                },
                "value": [ts, "1"],
            },
        ]
    }
    runner.format_data(vector)
    runner.format_metrics()

    host = runner.result["fusioninsight_host"][0]
    assert host["assos"] == []


def test_fusioninsight_field_mappings_cover_model_attrs():
    from apps.cmdb.collection.plugins.community.cloud.fusioninsight import FusionInsightCollectionPlugin

    fm = FusionInsightCollectionPlugin.field_mappings

    def business_fields(model_id):
        return {k for k in fm[model_id] if k not in ("inst_name", "assos")}

    assert business_fields("fusioninsight_cluster") == {"resource_name", "resource_id"}
    assert business_fields("fusioninsight_host") == {
        "resource_name", "resource_id", "ip_addr", "vcpus",
        "memory_mb", "storage_gb", "status", "os_name",
    }


def test_fusioninsight_in_collect_obj_tree():
    from apps.cmdb.services.collect_object_tree import get_collect_obj_tree

    tree = get_collect_obj_tree()
    cloud = next(g for g in tree if g.get("id") == "cloud")
    model_ids = {c.get("model_id") for c in cloud.get("children", [])}
    assert "fusioninsight" in model_ids


def test_fusioninsight_plugin_registered():
    from apps.cmdb.collection.plugins import get_collection_plugin
    from apps.cmdb.constants.constants import CollectPluginTypes
    from apps.cmdb.collection.plugins.community.cloud.fusioninsight import FusionInsightCollectionPlugin

    cls = get_collection_plugin(CollectPluginTypes.CLOUD, "fusioninsight")
    assert cls is FusionInsightCollectionPlugin
