"""qcloud 云采集端到端流水线测试 — cloud 大类(7 子对象代表:cvm/vpc/clb/cdb/redis/bucket/cmq)。

【v5 Task 3.2】2026-07-14
- qcloud plugin 支持 13+ sub-model,本测试只覆盖 7 个代表(cvm/vpc/clb/cdb/redis/bucket/cmq)
- 其他子对象(cmq_topic/domain/eip/filesystem/mongodb/pgsql/plusar_cluster/rocketmq)可作下期 follow-up
- plugin 端:QCloudCollectMetrics + QCloudCollectionPlugin(plugins/community/cloud/qcloud.py)
- pipeline:cloud runner 走 QCloudCollectMetrics
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


# 7 个本测试覆盖的 qcloud 子对象
# 注意:qcloud plugin metric_names 列表中只含 cvm/clb/redis/bucket/cmq/mysql/mongodb 等
# qcloud_vpc / qcloud_cdb 虽在 field_mappings 中有定义,但不在 metric_names 中(无法走完整 pipeline)
# 这两个 vpc/cdb 留作下期 follow-up,本期先覆盖 plugin 完整支持的 7 个子对象
QCLOUD_MODEL_IDS = [
    "qcloud_cvm",     # 云服务器(对标 aliyun_ecs)
    "qcloud_clb",     # 负载均衡
    "qcloud_redis",   # 云 Redis
    "qcloud_bucket",  # 对象存储 COS
    "qcloud_cmq",     # 消息队列 CMQ
    "qcloud_mysql",   # 云数据库 MySQL(与 qcloud_cdb 区别:本对象在 plugin metric_names 中)
    "qcloud_mongodb", # 云 MongoDB
]


def _patch_qcloud_runner(monkeypatch, runner_cls, plugin_cls):
    """monkeypatch QCloudCollectMetrics 的 _metrics / model_field_mapping 从 plugin 取。"""
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


@pytest.mark.parametrize("model_id", QCLOUD_MODEL_IDS)
def test_step1_stargazer_raw_matches_schema(load_fixture, load_schema, model_id):
    """每对象 01 fixture 必符合 schema。"""
    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    schema = load_schema(f"{model_id}/01_stargazer_raw.schema.json")
    jsonschema.validate(raw, schema)


@pytest.mark.parametrize("model_id", QCLOUD_MODEL_IDS)
def test_drift_detection(load_schema, model_id):
    """每对象 schema 拒绝缺关键字段的坏数据。"""
    # 缺 resource_name
    bad = {"model_id": model_id, "resource_id": "abc", "region": "ap-shanghai", "status": "RUNNING"}
    schema = load_schema(f"{model_id}/01_stargazer_raw.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


@pytest.mark.django_db
@pytest.mark.parametrize("model_id", QCLOUD_MODEL_IDS)
def test_pipeline_end_to_end(load_fixture, load_schema, monkeypatch, model_id):
    """qcloud {model_id} 端到端流水线测试。"""
    from apps.cmdb.collection.collect_plugin.qcloud import QCloudCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.qcloud import QCloudCollectionPlugin

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    expected = load_fixture(f"{model_id}/04_expected_cmdb_result.json")

    _patch_qcloud_runner(monkeypatch, QCloudCollectMetrics, QCloudCollectionPlugin)

    run = pipeline.run_full_pipeline_generic(
        raw_items=raw,
        runner_cls=QCloudCollectMetrics,
        plugin_cls=QCloudCollectionPlugin,
        model_id=model_id,
        task_id=33011,
        instances=[{"inst_name": "qcloud-account-prod-01"}],
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
@pytest.mark.parametrize("model_id", QCLOUD_MODEL_IDS)
def test_a_b_alignment(load_fixture, load_schema, monkeypatch, model_id):
    """qcloud {model_id} A 端 + B 端对齐全覆盖测试。"""
    from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def
    from apps.cmdb.collection.collect_plugin.qcloud import QCloudCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.qcloud import QCloudCollectionPlugin

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    expected = load_fixture(f"{model_id}/04_expected_cmdb_result.json")

    # A 端:02 → 03
    raw_items = [raw] if isinstance(raw, dict) else raw
    p2 = pipeline.step1_stargazer_normalize_generic(raw_items, model_id=model_id)
    p3 = pipeline.step2_push_to_vm(p2, task_id=33011)

    for result_item in p3["data"]["result"]:
        assert result_item["metric"]["__name__"].endswith("_info_gauge")
        assert result_item["metric"]["instance_id"] == "cmdb_33011"
        model_fields = get_model_field_def(model_id)
        required = {f.name for f in model_fields.values() if f.is_required}
        labels = set(result_item["metric"].keys())
        exclude = {"__name__", "instance_id", "collect_status", "inst_name",
                   "model_id", "id", "create_time", "update_time", "assos"}
        missing = required - labels - exclude
        assert not missing, f"A 端 03 metric 缺 model 必填字段: {missing}"

    # B 端:03 → 04
    _patch_qcloud_runner(monkeypatch, QCloudCollectMetrics, QCloudCollectionPlugin)

    raw_items_first = raw if isinstance(raw, list) else raw
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items_first,
        runner_cls=QCloudCollectMetrics,
        plugin_cls=QCloudCollectionPlugin,
        model_id=model_id,
        task_id=33011,
        instances=[{"inst_name": "qcloud-account-prod-01",
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
