"""Aliyun ECS 采集端到端流水线测试 —— cloud 大类代表。

Aliyun 大类特点：
  - 一个 plugin (AliyunAccountCollectionPlugin) 同时采多个 model_id（bucket/clb/ecs/...）
  - metric_name 形如 "aliyun_ecs_info_gauge"，runner 按 "_info_gauge" 后缀拆 model_id
  - 跳过 check_task_id 检查，专注业务字段流转

Task 2.1 新增 test_aliyun_ecs_a_b_alignment:
  - 真实形态 01 fixture(100+ 行,补 image_id / security_group / vswitch / bandwidth 等)
  - A 端对齐:03 metric 必填字段 ⊇ model 必填字段
  - B 端对齐:04 实例字段 ⊆ model 字段定义
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


def test_step1_raw_matches_schema(load_fixture, load_schema):
    raw = load_fixture("aliyun/01_raw_collector.json")
    schema = load_schema("aliyun/01_raw_collector.schema.json")
    jsonschema.validate(raw, schema)


def test_step1_stargazer_raw_matches_schema(load_fixture, load_schema):
    """Task 2.1 新增:验证真实形态 01_stargazer_raw.json 符合 schema。"""
    raw = load_fixture("aliyun_ecs/01_stargazer_raw.json")
    schema = load_schema("aliyun_ecs/01_stargazer_raw.schema.json")
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


# ============================================================================
# Task 2.1: aliyun_ecs A 端 + B 端对齐全覆盖测试
# ============================================================================


@pytest.mark.django_db
def test_aliyun_ecs_a_b_alignment(load_fixture, load_schema, monkeypatch):
    """aliyun_ecs A 端 + B 端对齐全覆盖测试。

    验证:
      - A 端:02 → 03 metric.__name__ = 'aliyun_ecs_info_gauge',label 集合 ⊇ model 必填字段
      - B 端:04 实例字段 ⊆ model 字段定义,vcpus / memory_mb 是 int
    """
    from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def
    from apps.cmdb.collection.collect_plugin.aliyun import AliyunCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.aliyun import AliyunAccountCollectionPlugin
    from apps.cmdb.collection.plugins.base import bind_collection_mapping

    raw = load_fixture("aliyun_ecs/01_stargazer_raw.json")
    expected = load_fixture("aliyun/04_expected_cmdb_result.json")

    # A 端:02 → 03
    raw_items = [raw] if isinstance(raw, dict) else raw
    p2 = pipeline.step1_stargazer_normalize_generic(raw_items, model_id="aliyun_ecs")
    p3 = pipeline.step2_push_to_vm(p2, task_id=88888)

    for result_item in p3["data"]["result"]:
        assert result_item["metric"]["__name__"].endswith("_info_gauge")
        assert result_item["metric"]["instance_id"] == "cmdb_88888"
        # 业务 label 集合 ⊇ model 必填字段(排除 inst_name / model_id / assos 等 derived 字段)
        model_fields = get_model_field_def("aliyun_ecs")
        required = {f.name for f in model_fields.values() if f.is_required}
        labels = set(result_item["metric"].keys())
        exclude = {"__name__", "instance_id", "collect_status", "inst_name",
                   "model_id", "id", "create_time", "update_time", "assos"}
        missing = required - labels - exclude
        assert not missing, f"A 端 03 metric 缺 model 必填字段: {missing}"

    # B 端:03 → 04
    monkeypatch.setattr(AliyunCollectMetrics, "check_task_id", lambda self, iid: True)
    monkeypatch.setattr(
        AliyunCollectMetrics, "_metrics",
        property(lambda self: list(AliyunAccountCollectionPlugin.metric_names)),
    )
    monkeypatch.setattr(
        AliyunCollectMetrics, "model_field_mapping",
        property(lambda self: {
            mid: bind_collection_mapping(self, m)
            for mid, m in AliyunAccountCollectionPlugin.field_mappings.items()
        }),
    )
    monkeypatch.setattr(
        AliyunAccountCollectionPlugin, "field_mapping",
        AliyunAccountCollectionPlugin.field_mappings["aliyun_ecs"],
        raising=False,
    )

    raw_items = raw if isinstance(raw, list) else raw
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=AliyunCollectMetrics,
        plugin_cls=AliyunAccountCollectionPlugin,
        model_id="aliyun_ecs",
        task_id=88888,
        instances=[{"inst_name": "aliyun-account-01", "ip_addr": raw.get("ip_addr", "172.16.0.11")}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"]["aliyun_ecs"]
    assert len(instances) >= expected["instance_count_min"]

    inst = instances[0]
    # B 端:实例字段 ⊆ model 字段定义
    model_fields = get_model_field_def("aliyun_ecs")
    system_fields = {
        "inst_name", "model_id", "id", "create_time", "update_time",
        "_placeholder_reason", "license_status", "assos",
    }
    model_field_names = set(model_fields.keys()) - system_fields
    inst_fields = set(inst.keys())
    missing = model_field_names - inst_fields
    assert not missing, f"B 端 04 实例缺 model 字段: {missing}"

    # B 端:vcpus / memory_mb 是 int(plugin 里有 (int, "vcpus") / (int, "memory") 转换)
    assert isinstance(inst.get("vcpus"), int), f"vcpus 应该是 int,实际 {type(inst.get('vcpus'))}"
    assert isinstance(inst.get("memory_mb"), int), f"memory_mb 应该是 int,实际 {type(inst.get('memory_mb'))}"
