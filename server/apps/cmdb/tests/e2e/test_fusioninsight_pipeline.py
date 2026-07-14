"""FusionInsight 云采集端到端流水线测试 — cloud 大类(2 子对象:cluster + host)。

【v5 Task 3.3】2026-07-14
- fusioninsight plugin 支持 2 sub-model:cluster + host
- plugin 端:FusionInsightCollectMetrics + FusionInsightCollectionPlugin(plugins/community/cloud/fusioninsight.py)
- pipeline:cloud runner 走 FusionInsightCollectMetrics
- cluster 用单 cluster fallback 模式(host belong cluster)
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


FUSIONINSIGHT_MODEL_IDS = [
    "fusioninsight_cluster",  # 平台对象(无业务字段,只有 inst_name + belong 关联)
    "fusioninsight_host",     # 主机对象(vcpus/memory_mb/storage_gb/status/os_name)
]


def _patch_fusioninsight_runner(monkeypatch, runner_cls, plugin_cls):
    """monkeypatch FusionInsightCollectMetrics 的 _metrics / model_field_mapping 从 plugin 取。"""
    monkeypatch.setattr(
        runner_cls, "_metrics",
        property(lambda self: list(plugin_cls.metric_names)),
    )
    from apps.cmdb.collection.plugins.base import bind_collection_mapping
    monkeypatch.setattr(
        runner_cls, "model_field_mapping",
        property(lambda self: {
            mid: bind_collection_mapping(self, m)
            for mid, m in plugin_cls.field_mappings.items()
        }),
    )


@pytest.mark.parametrize("model_id", FUSIONINSIGHT_MODEL_IDS)
def test_step1_stargazer_raw_matches_schema(load_fixture, load_schema, model_id):
    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    schema = load_schema(f"{model_id}/01_stargazer_raw.schema.json")
    jsonschema.validate(raw, schema)


@pytest.mark.parametrize("model_id", FUSIONINSIGHT_MODEL_IDS)
def test_drift_detection(load_schema, model_id):
    bad = {"resource_name": "x", "resource_id": "abc"}  # 缺必需字段
    schema = load_schema(f"{model_id}/01_stargazer_raw.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


@pytest.mark.django_db
@pytest.mark.parametrize("model_id", FUSIONINSIGHT_MODEL_IDS)
def test_pipeline_end_to_end(load_fixture, load_schema, monkeypatch, model_id):
    """fusioninsight {model_id} 端到端流水线测试。"""
    from apps.cmdb.collection.collect_plugin.fusioninsight import FusionInsightCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.fusioninsight import FusionInsightCollectionPlugin

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    expected = load_fixture(f"{model_id}/04_expected_cmdb_result.json")

    _patch_fusioninsight_runner(monkeypatch, FusionInsightCollectMetrics, FusionInsightCollectionPlugin)

    # fusioninsight 父 plugin 处理 2 sub-model,fixture 形态是单 sub-model
    # 注:实际跑会同时处理 cluster + host 两组 metric,但 fixture 里只放了对应 model_id 的 metric
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw,
        runner_cls=FusionInsightCollectMetrics,
        plugin_cls=FusionInsightCollectionPlugin,
        model_id=model_id,
        task_id=33031,
        instances=[{"inst_name": "fusioninsight-account-prod-01"}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"].get(model_id, [])
    assert len(instances) >= expected["instance_count_min"]

    inst_schema = load_schema(f"{model_id}/04_cmdb_instance.schema.json")
    for inst in instances:
        jsonschema.validate(inst, inst_schema)

    actual = instances[0]
    for field, expected_value in expected["expected_instance_subset"].items():
        assert actual.get(field) == expected_value, \
            f"字段 {field}:期望 {expected_value!r},实际 {actual.get(field)!r}"


# ============================================================================
# A 端 + B 端对齐全覆盖测试
# ============================================================================


@pytest.mark.django_db
@pytest.mark.parametrize("model_id", FUSIONINSIGHT_MODEL_IDS)
def test_a_b_alignment(load_fixture, load_schema, monkeypatch, model_id):
    """fusioninsight {model_id} A 端 + B 端对齐全覆盖测试。"""
    from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def
    from apps.cmdb.collection.collect_plugin.fusioninsight import FusionInsightCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.fusioninsight import FusionInsightCollectionPlugin

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    expected = load_fixture(f"{model_id}/04_expected_cmdb_result.json")

    # A 端:02 → 03
    raw_items = [raw] if isinstance(raw, dict) else raw
    p2 = pipeline.step1_stargazer_normalize_generic(raw_items, model_id=model_id)
    p3 = pipeline.step2_push_to_vm(p2, task_id=33031)

    for result_item in p3["data"]["result"]:
        assert result_item["metric"]["__name__"].endswith("_info_gauge")
        assert result_item["metric"]["instance_id"] == "cmdb_33031"
        model_fields = get_model_field_def(model_id)
        required = {f.name for f in model_fields.values() if f.is_required}
        labels = set(result_item["metric"].keys())
        exclude = {"__name__", "instance_id", "collect_status", "inst_name",
                   "model_id", "id", "create_time", "update_time", "assos"}
        missing = required - labels - exclude
        assert not missing, f"A 端 03 metric 缺 model 必填字段: {missing}"

    # B 端:03 → 04
    _patch_fusioninsight_runner(monkeypatch, FusionInsightCollectMetrics, FusionInsightCollectionPlugin)

    raw_items_first = raw if isinstance(raw, list) else raw
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items_first,
        runner_cls=FusionInsightCollectMetrics,
        plugin_cls=FusionInsightCollectionPlugin,
        model_id=model_id,
        task_id=33031,
        instances=[{"inst_name": "fusioninsight-account-prod-01",
                    "ip_addr": raw_items_first.get("ip_addr", "127.0.0.1")}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"].get(model_id, [])
    assert len(instances) >= expected["instance_count_min"]

    inst = instances[0]
    model_fields = get_model_field_def(model_id)
    system_fields = {
        "inst_name", "model_id", "id", "create_time", "update_time",
        "_placeholder_reason", "license_status", "assos",
    }
    model_field_names = set(model_fields.keys()) - system_fields
    inst_fields = set(inst.keys())
    missing = model_field_names - inst_fields
    assert not missing, f"B 端 04 实例缺 model 字段: {missing}"
