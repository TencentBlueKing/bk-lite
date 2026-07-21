"""hwcloud 云采集端到端流水线测试 — cloud 大类代表(2 核心子对象:ecs + vpc)。

【v5 Task 3.1】2026-07-14
- hwcloud 是多 sub-model 父 plugin(MODEL_ORDER:hwcloud→ecs→vpc→...),本测试只覆盖 ecs + vpc
- 9 个其他 hwcloud 子对象(evs/obs/subnet/eip/sg/elb/rds/dcs)推迟到下期 follow-up
- plugin 端:HwCloudCollectMetrics + HwCloudCollectionPlugin(plugins/community/cloud/hwcloud.py)
- pipeline:cloud runner 走 HwCloudCollectMetrics(自定义,不是 protocol/db/middleware)
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


# hwcloud plugin field_mappings 复用(plugin.field_mappings['hwcloud_ecs'] 等)
HWCLOUD_FIELD_MAPPINGS = {
    "hwcloud_ecs": {
        "inst_name": "inst_name",  # runner 会重写为 {name}_{id}
        "resource_name": "resource_name",
        "resource_id": "resource_id",
        "ip_addr": "ip_addr",
        "public_ip": "public_ip",
        "region": "region",
        "zone": "zone",
        "vpc": "vpc",
        "status": "status",
        "instance_type": "instance_type",
        "os_name": "os_name",
        "vcpus": (int, "vcpus"),
        "memory_mb": (int, "memory_mb"),
        "charge_type": "charge_type",
        "create_time": "create_time",
        "expired_time": "expired_time",
    },
    "hwcloud_vpc": {
        "inst_name": "inst_name",
        "resource_name": "resource_name",
        "resource_id": "resource_id",
        "region": "region",
        "status": "status",
        "cidr": "cidr",
        "is_default": "is_default",
    },
}


def test_step1_hwcloud_ecs_stargazer_raw_matches_schema(load_fixture, load_schema):
    raw = load_fixture("hwcloud_ecs/01_stargazer_raw.json")
    schema = load_schema("hwcloud_ecs/01_stargazer_raw.schema.json")
    jsonschema.validate(raw, schema)


def test_step1_hwcloud_vpc_stargazer_raw_matches_schema(load_fixture, load_schema):
    raw = load_fixture("hwcloud_vpc/01_stargazer_raw.json")
    schema = load_schema("hwcloud_vpc/01_stargazer_raw.schema.json")
    jsonschema.validate(raw, schema)


@pytest.mark.django_db
def test_hwcloud_ecs_pipeline_end_to_end(load_fixture, load_schema, monkeypatch):
    """hwcloud_ecs 端到端流水线测试。

    hwcloud 父 plugin 处理多 sub-model,本测试 fixture 是单 sub-model 01(只含 hwcloud_ecs 数据),
    runner.format_data 解析后 format_metrics 按 MODEL_ORDER 处理,只产出 hwcloud_ecs 实例。
    """
    from apps.cmdb.collection.collect_plugin.hwcloud import HwCloudCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin
    from apps.cmdb.collection.plugins.base import bind_collection_mapping

    raw = load_fixture("hwcloud_ecs/01_stargazer_raw.json")
    expected = load_fixture("hwcloud_ecs/04_expected_cmdb_result.json")

    # cloud runner._metrics / model_field_mapping 都从 plugin 取
    monkeypatch.setattr(
        HwCloudCollectMetrics, "_metrics",
        property(lambda self: list(HwCloudCollectionPlugin.metric_names)),
    )
    monkeypatch.setattr(
        HwCloudCollectMetrics, "model_field_mapping",
        property(lambda self: {
            mid: bind_collection_mapping(self, m)
            for mid, m in HwCloudCollectionPlugin.field_mappings.items()
        }),
    )

    run = pipeline.run_full_pipeline_generic(
        raw_items=raw,
        runner_cls=HwCloudCollectMetrics,
        plugin_cls=HwCloudCollectionPlugin,
        model_id="hwcloud_ecs",
        task_id=33001,
        instances=[{"inst_name": "hwcloud-account-prod-01"}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"]["hwcloud_ecs"]
    assert len(instances) >= expected["instance_count_min"]

    inst_schema = load_schema("hwcloud_ecs/04_cmdb_instance.schema.json")
    for inst in instances:
        jsonschema.validate(inst, inst_schema)

    actual = instances[0]
    for field, expected_value in expected["expected_instance_subset"].items():
        assert actual.get(field) == expected_value, \
            f"字段 {field}:期望 {expected_value!r},实际 {actual.get(field)!r}"


@pytest.mark.django_db
def test_hwcloud_vpc_pipeline_end_to_end(load_fixture, load_schema, monkeypatch):
    """hwcloud_vpc 端到端流水线测试。"""
    from apps.cmdb.collection.collect_plugin.hwcloud import HwCloudCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin
    from apps.cmdb.collection.plugins.base import bind_collection_mapping

    raw = load_fixture("hwcloud_vpc/01_stargazer_raw.json")
    expected = load_fixture("hwcloud_vpc/04_expected_cmdb_result.json")

    monkeypatch.setattr(
        HwCloudCollectMetrics, "_metrics",
        property(lambda self: list(HwCloudCollectionPlugin.metric_names)),
    )
    monkeypatch.setattr(
        HwCloudCollectMetrics, "model_field_mapping",
        property(lambda self: {
            mid: bind_collection_mapping(self, m)
            for mid, m in HwCloudCollectionPlugin.field_mappings.items()
        }),
    )

    run = pipeline.run_full_pipeline_generic(
        raw_items=raw,
        runner_cls=HwCloudCollectMetrics,
        plugin_cls=HwCloudCollectionPlugin,
        model_id="hwcloud_vpc",
        task_id=33002,
        instances=[{"inst_name": "hwcloud-account-prod-01"}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"]["hwcloud_vpc"]
    assert len(instances) >= expected["instance_count_min"]

    inst_schema = load_schema("hwcloud_vpc/04_cmdb_instance.schema.json")
    for inst in instances:
        jsonschema.validate(inst, inst_schema)

    actual = instances[0]
    for field, expected_value in expected["expected_instance_subset"].items():
        assert actual.get(field) == expected_value, \
            f"字段 {field}:期望 {expected_value!r},实际 {actual.get(field)!r}"


def test_hwcloud_ecs_drift_detection(load_schema):
    """hwcloud_ecs schema 拒绝缺关键字段的坏数据。"""
    bad = {"resource_name": "x", "resource_id": "ecs-bp1abc"}  # 缺 region / status
    schema = load_schema("hwcloud_ecs/01_stargazer_raw.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_hwcloud_vpc_drift_detection(load_schema):
    """hwcloud_vpc schema 拒绝缺 cidr 的坏数据。"""
    bad = {"resource_name": "x", "resource_id": "vpc-bp1abc", "region": "cn-north-4", "status": "ACTIVE"}  # 缺 cidr
    schema = load_schema("hwcloud_vpc/01_stargazer_raw.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


# ============================================================================
# Task 3.1: hwcloud_ecs + hwcloud_vpc A 端 + B 端对齐全覆盖测试
# ============================================================================


@pytest.mark.django_db
def test_hwcloud_ecs_a_b_alignment(load_fixture, load_schema, monkeypatch):
    """hwcloud_ecs A 端 + B 端对齐全覆盖测试。

    验证:
      - A 端:03 metric.__name__ = 'hwcloud_ecs_info_gauge',instance_id = 'cmdb_<task_id>',labels ⊇ model 必填
      - B 端:04 实例字段 ⊆ model 字段定义,vcpus/memory_mb 是 int
    """
    from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def
    from apps.cmdb.collection.collect_plugin.hwcloud import HwCloudCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin
    from apps.cmdb.collection.plugins.base import bind_collection_mapping

    raw = load_fixture("hwcloud_ecs/01_stargazer_raw.json")
    expected = load_fixture("hwcloud_ecs/04_expected_cmdb_result.json")

    # A 端:02 → 03
    raw_items = [raw] if isinstance(raw, dict) else raw
    p2 = pipeline.step1_stargazer_normalize_generic(raw_items, model_id="hwcloud_ecs")
    p3 = pipeline.step2_push_to_vm(p2, task_id=33001)

    for result_item in p3["data"]["result"]:
        assert result_item["metric"]["__name__"].endswith("_info_gauge")
        assert result_item["metric"]["instance_id"] == "cmdb_33001"
        model_fields = get_model_field_def("hwcloud_ecs")
        required = {f.name for f in model_fields.values() if f.is_required}
        labels = set(result_item["metric"].keys())
        exclude = {"__name__", "instance_id", "collect_status", "inst_name",
                   "model_id", "id", "create_time", "update_time", "assos"}
        missing = required - labels - exclude
        assert not missing, f"A 端 03 metric 缺 model 必填字段: {missing}"

    # B 端:03 → 04
    monkeypatch.setattr(
        HwCloudCollectMetrics, "_metrics",
        property(lambda self: list(HwCloudCollectionPlugin.metric_names)),
    )
    monkeypatch.setattr(
        HwCloudCollectMetrics, "model_field_mapping",
        property(lambda self: {
            mid: bind_collection_mapping(self, m)
            for mid, m in HwCloudCollectionPlugin.field_mappings.items()
        }),
    )

    raw_items_first = raw if isinstance(raw, list) else raw
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items_first,
        runner_cls=HwCloudCollectMetrics,
        plugin_cls=HwCloudCollectionPlugin,
        model_id="hwcloud_ecs",
        task_id=33001,
        instances=[{"inst_name": "hwcloud-account-prod-01", "ip_addr": "192.168.1.10"}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"]["hwcloud_ecs"]
    assert len(instances) >= expected["instance_count_min"]

    inst = instances[0]
    model_fields = get_model_field_def("hwcloud_ecs")
    system_fields = {
        "inst_name", "model_id", "id", "create_time", "update_time",
        "_placeholder_reason", "license_status", "assos",
    }
    model_field_names = set(model_fields.keys()) - system_fields
    inst_fields = set(inst.keys())
    missing = model_field_names - inst_fields
    assert not missing, f"B 端 04 实例缺 model 字段: {missing}"

    # B 端:vcpus / memory_mb 是 int
    assert isinstance(inst.get("vcpus"), int), f"vcpus 应该是 int,实际 {type(inst.get('vcpus'))}"
    assert isinstance(inst.get("memory_mb"), int), f"memory_mb 应该是 int,实际 {type(inst.get('memory_mb'))}"


@pytest.mark.django_db
def test_hwcloud_vpc_a_b_alignment(load_fixture, load_schema, monkeypatch):
    """hwcloud_vpc A 端 + B 端对齐全覆盖测试。"""
    from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def
    from apps.cmdb.collection.collect_plugin.hwcloud import HwCloudCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin
    from apps.cmdb.collection.plugins.base import bind_collection_mapping

    raw = load_fixture("hwcloud_vpc/01_stargazer_raw.json")
    expected = load_fixture("hwcloud_vpc/04_expected_cmdb_result.json")

    # A 端
    raw_items = [raw] if isinstance(raw, dict) else raw
    p2 = pipeline.step1_stargazer_normalize_generic(raw_items, model_id="hwcloud_vpc")
    p3 = pipeline.step2_push_to_vm(p2, task_id=33002)

    for result_item in p3["data"]["result"]:
        assert result_item["metric"]["__name__"].endswith("_info_gauge")
        assert result_item["metric"]["instance_id"] == "cmdb_33002"
        model_fields = get_model_field_def("hwcloud_vpc")
        required = {f.name for f in model_fields.values() if f.is_required}
        labels = set(result_item["metric"].keys())
        exclude = {"__name__", "instance_id", "collect_status", "inst_name",
                   "model_id", "id", "create_time", "update_time", "assos"}
        missing = required - labels - exclude
        assert not missing, f"A 端 03 metric 缺 model 必填字段: {missing}"

    # B 端
    monkeypatch.setattr(
        HwCloudCollectMetrics, "_metrics",
        property(lambda self: list(HwCloudCollectionPlugin.metric_names)),
    )
    monkeypatch.setattr(
        HwCloudCollectMetrics, "model_field_mapping",
        property(lambda self: {
            mid: bind_collection_mapping(self, m)
            for mid, m in HwCloudCollectionPlugin.field_mappings.items()
        }),
    )

    raw_items_first = raw if isinstance(raw, list) else raw
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items_first,
        runner_cls=HwCloudCollectMetrics,
        plugin_cls=HwCloudCollectionPlugin,
        model_id="hwcloud_vpc",
        task_id=33002,
        instances=[{"inst_name": "hwcloud-account-prod-01"}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"]["hwcloud_vpc"]
    assert len(instances) >= expected["instance_count_min"]

    inst = instances[0]
    model_fields = get_model_field_def("hwcloud_vpc")
    system_fields = {
        "inst_name", "model_id", "id", "create_time", "update_time",
        "_placeholder_reason", "license_status", "assos",
    }
    model_field_names = set(model_fields.keys()) - system_fields
    inst_fields = set(inst.keys())
    missing = model_field_names - inst_fields
    assert not missing, f"B 端 04 实例缺 model 字段: {missing}"

    # B 端:cidr / is_default 是 string
    assert inst.get("cidr") == "192.168.0.0/16"
    assert inst.get("is_default") == "false"
