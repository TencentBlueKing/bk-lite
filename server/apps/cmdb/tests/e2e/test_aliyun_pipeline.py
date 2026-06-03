"""Aliyun ECS 采集端到端流水线测试 —— cloud 大类代表。

Aliyun 大类特点：
  - 一个 plugin (AliyunAccountCollectionPlugin) 同时采多个 model_id（bucket/clb/ecs/...）
  - metric_name 形如 "aliyun_ecs_info_gauge"，runner 按 "_info_gauge" 后缀拆 model_id
  - 跳过 check_task_id 检查，专注业务字段流转
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


def test_step1_raw_matches_schema(load_fixture, load_schema):
    raw = load_fixture("aliyun/01_raw_collector.json")
    schema = load_schema("aliyun/01_raw_collector.schema.json")
    jsonschema.validate(raw, schema)


@pytest.mark.django_db
def test_aliyun_ecs_pipeline_end_to_end(load_fixture, load_schema, monkeypatch):
    from apps.cmdb.collection.collect_plugin.aliyun import AliyunCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.aliyun import AliyunAccountCollectionPlugin

    raw = load_fixture("aliyun/01_raw_collector.json")
    expected = load_fixture("aliyun/04_expected_cmdb_result.json")

    # check_task_id 在生产里用来过滤 instance_id 命名空间，简化掉
    monkeypatch.setattr(AliyunCollectMetrics, "check_task_id", lambda self, iid: True)

    # AliyunCollectMetrics._metrics 用 plugin_cls._metrics.fget(self)，会陷入递归
    # （plugin 没 override _metrics）。直接读 plugin.metric_names。
    monkeypatch.setattr(
        AliyunCollectMetrics, "_metrics",
        property(lambda self: list(AliyunAccountCollectionPlugin.metric_names)),
    )

    # model_field_mapping 来自 plugin.field_mappings[model_id]，每个 sub-model 各自 bind
    from apps.cmdb.collection.plugins.base import bind_collection_mapping

    monkeypatch.setattr(
        AliyunCollectMetrics, "model_field_mapping",
        property(lambda self: {
            mid: bind_collection_mapping(self, m)
            for mid, m in AliyunAccountCollectionPlugin.field_mappings.items()
        }),
    )

    # plugin 注入 field_mapping (单数) 兼容 generic 驱动里取的 plugin.field_mapping
    monkeypatch.setattr(
        AliyunAccountCollectionPlugin, "field_mapping",
        AliyunAccountCollectionPlugin.field_mappings["aliyun_ecs"],
        raising=False,
    )

    run = pipeline.run_full_pipeline_generic(
        raw_items=raw,
        runner_cls=AliyunCollectMetrics,
        plugin_cls=AliyunAccountCollectionPlugin,
        model_id="aliyun_ecs",
        task_id=5001,
        instances=[{"inst_name": "aliyun-account-01"}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"]["aliyun_ecs"]
    assert len(instances) >= expected["instance_count_min"]

    inst_schema = load_schema("aliyun/04_cmdb_instance.schema.json")
    for inst in instances:
        jsonschema.validate(inst, inst_schema)

    actual = instances[0]
    for field, expected_value in expected["expected_instance_subset"].items():
        assert actual.get(field) == expected_value, \
            f"字段 {field}：期望 {expected_value!r}，实际 {actual.get(field)!r}"


def test_drift_detection(load_schema):
    bad = {"resource_name": "x", "resource_id": "wrong-format", "region": "cn-hangzhou", "status": "Running"}
    schema = load_schema("aliyun/01_raw_collector.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
