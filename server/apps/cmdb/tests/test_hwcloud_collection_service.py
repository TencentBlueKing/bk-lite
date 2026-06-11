# -*- coding: utf-8 -*-
"""华为云 server 端采集插件测试：mock VM 查询，断言字段对齐模型 + 关联正确。"""
import time
import pytest


def _vm_vector():
    ts = int(time.time()) - 60  # 距今 60 秒，避免被 timestamp_gt_one_day_ago 过滤
    return {
        "result": [
            {
                "metric": {
                    "__name__": "hwcloud_info_gauge",
                    "collect_status": "success",
                    "endpoint": "https://ecs.cn-north-4.myhuaweicloud.com",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "hwcloud_ecs_info_gauge",
                    "collect_status": "success",
                    "resource_name": "web-01",
                    "resource_id": "ecs-001",
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
                    "expired_time": "2026-12-31T23:59:59Z",
                },
                "value": [ts, "1"],
            },
        ]
    }


@pytest.mark.django_db
def test_hwcloud_format_metrics_fields_and_assoc(monkeypatch):
    # 运行期真正被实例化的是插件类（继承采集映射基类），与生产路径一致
    from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin

    class _FakeInst:
        model_id = "hwcloud"
        instances = [{"inst_name": "华为云生产"}]

    monkeypatch.setattr(HwCloudCollectionPlugin, "get_collect_inst", lambda self: _FakeInst())

    runner = HwCloudCollectionPlugin(inst_name="华为云生产", inst_id=1, task_id=8001)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    assert runner.result["hwcloud"][0]["endpoint"].startswith("https://")
    ecs = runner.result["hwcloud_ecs"][0]
    assert ecs["resource_id"] == "ecs-001"
    assert ecs["vcpus"] == 2
    assert ecs["memory_mb"] == 4096
    assert ecs["inst_name"] == "web-01_ecs-001"
    assert ecs["create_time"] == "2025-01-01T00:00:00Z"
    assert ecs["expired_time"] == "2026-12-31T23:59:59Z"
    assert ecs["assos"] == [
        {
            "model_id": "hwcloud",
            "inst_name": "华为云生产",
            "asst_id": "belong",
            "model_asst_id": "hwcloud_ecs_belong_hwcloud",
        }
    ]


def test_hwcloud_in_collect_obj_tree():
    from apps.cmdb.services.collect_object_tree import get_collect_obj_tree

    tree = get_collect_obj_tree()
    cloud = next(g for g in tree if g.get("id") == "cloud")
    model_ids = {c.get("model_id") for c in cloud.get("children", [])}
    assert "hwcloud" in model_ids


def test_hwcloud_field_mappings_cover_model_attrs():
    from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin

    expected_ecs_fields = {
        "resource_name", "resource_id", "ip_addr", "public_ip", "region", "zone",
        "vpc", "status", "instance_type", "os_name", "vcpus", "memory_mb",
        "charge_type", "create_time", "expired_time",
    }
    mapped = set(HwCloudCollectionPlugin.field_mappings["hwcloud_ecs"].keys())
    missing = expected_ecs_fields - mapped
    assert not missing, f"hwcloud_ecs 缺失字段映射: {missing}"
    assert "endpoint" in HwCloudCollectionPlugin.field_mappings["hwcloud"]


@pytest.mark.django_db
def test_hwcloud_empty_tuple_field_is_omitted(monkeypatch):
    """vcpus 为空字符串时，按设计应从实例 dict 中省略该字段（不报错、不落空值）。"""
    import time
    from apps.cmdb.collection.collect_plugin.hwcloud import HwCloudCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin

    class _FakeInst:
        model_id = "hwcloud"
        instances = [{"inst_name": "华为云生产"}]

    monkeypatch.setattr(HwCloudCollectMetrics, "get_collect_inst", lambda self: _FakeInst())

    ts = int(time.time()) - 60
    vector = {
        "result": [
            {
                "metric": {
                    "__name__": "hwcloud_ecs_info_gauge",
                    "collect_status": "success",
                    "resource_name": "web-02",
                    "resource_id": "ecs-002",
                    "vcpus": "",          # 空：应被省略
                    "memory_mb": "8192",  # 有值：应保留并转 int
                },
                "value": [ts, "1"],
            }
        ]
    }
    runner = HwCloudCollectionPlugin(inst_name="华为云生产", inst_id=1, task_id=8002)
    runner.format_data(vector)
    runner.format_metrics()

    ecs = runner.result["hwcloud_ecs"][0]
    assert "vcpus" not in ecs            # 空 tuple 字段被省略
    assert ecs["memory_mb"] == 8192      # 非空 tuple 字段保留并转 int
    assert ecs["resource_id"] == "ecs-002"
