"""Redis 采集端到端流水线测试 —— db 大类代表。

【Phase 2.4】2026-07-10 — 第四闭环
- 原 3 个测试(step1_raw / pipeline_end_to_end / drift_detection)
- 新增 test_redis_pipeline_fixture_driven: **用 stargazer 真实落盘的 fixture 驱动全链路**

DB 大类与 middleware 的差异：format_data 不解析 metric.result，业务字段直接平铺到 labels。
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


def test_step1_raw_matches_schema(load_fixture, load_schema):
    raw = load_fixture("redis/01_raw_collector.json")
    schema = load_schema("redis/01_raw_collector.schema.json")
    jsonschema.validate(raw, schema)


@pytest.mark.django_db
def test_redis_pipeline_end_to_end(load_fixture, load_schema, monkeypatch):
    from apps.cmdb.collection.collect_plugin.databases import DBCollectCollectMetrics
    from apps.cmdb.collection.plugins.community.db.redis import RedisCollectionPlugin

    raw = load_fixture("redis/01_raw_collector.json")
    expected = load_fixture("redis/04_expected_cmdb_result.json")

    run = pipeline.run_full_pipeline_generic(
        raw_items=raw,
        runner_cls=DBCollectCollectMetrics,
        plugin_cls=RedisCollectionPlugin,
        model_id="redis",
        task_id=3001,
        instances=[{"inst_name": "redis-prod-01", "ip_addr": "10.0.0.31"}],
        extra_payload_keys=None,  # db 平铺模式（不走 metric.result）
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"]["redis"]
    assert len(instances) >= expected["instance_count_min"]

    inst_schema = load_schema("redis/04_cmdb_instance.schema.json")
    for inst in instances:
        jsonschema.validate(inst, inst_schema)

    actual = instances[0]
    for field, expected_value in expected["expected_instance_subset_end_to_end"].items():
        assert actual.get(field) == expected_value, \
            f"end_to_end 字段 {field}：期望 {expected_value!r}，实际 {actual.get(field)!r}"


def test_drift_detection(load_schema):
    bad = {"ip_addr": "1.1.1.1", "port": 6379, "version": "7"}  # port should be string
    schema = load_schema("redis/01_raw_collector.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


# =============================================================================
# Phase 2.4:fixture 驱动的真实链路验证
# =============================================================================


@pytest.mark.django_db
def test_redis_pipeline_fixture_driven(monkeypatch, load_fixture, load_schema):
    """Phase 2.4 第四闭环：用 stargazer 真实落盘的 fixture 驱动 4 段流水线。

    db runner 差异:
    - extra_payload_keys=None(平铺模式,业务字段直接进 labels)
    - runner format_data 不解析 metric.result
    - stargazer 真实 fixture 含 slaves(list) / master(dict) 而非 string(01_raw_collector.json 是 string)

    验证三层:
      1) 契约层:fixture 命中 01_stargazer_raw schema
      2) 流水线层:cmdb_result["redis"] 至少 1 个实例
      3) 字段对齐层:实例关键字段与 expected_instance_subset_fixture_driven 一致
    """
    from apps.cmdb.collection.collect_plugin.databases import DBCollectCollectMetrics
    from apps.cmdb.collection.plugins.community.db.redis import RedisCollectionPlugin

    # 1) 契约层
    stargazer_raw = load_fixture("redis/01_stargazer_raw.json")
    raw_schema = load_schema("redis/01_stargazer_raw.schema.json")
    jsonschema.validate(stargazer_raw, raw_schema)

    # redis stargazer raw_stdout 是平铺 dict,直接喂 raw_items
    raw_items = stargazer_raw["raw_stdout"]
    ip_addr = raw_items["ip_addr"]

    # 2) 流水线层(db 平铺)
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=DBCollectCollectMetrics,
        plugin_cls=RedisCollectionPlugin,
        model_id="redis",
        task_id=13001,
        instances=[{"inst_name": "redis-fixture-01", "ip_addr": ip_addr}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )
    instances = run["cmdb_result"]["redis"]
    assert len(instances) >= 1, "fixture 驱动流水线应至少产出 1 个实例"

    # 3) 字段对齐层
    expected_doc = load_fixture("redis/04_expected_cmdb_result.json")
    expected_subset = expected_doc["expected_instance_subset_fixture_driven"]
    inst_schema = load_schema("redis/04_cmdb_instance.schema.json")

    inst = instances[0]
    jsonschema.validate(inst, inst_schema)
    for field, want in expected_subset.items():
        got = inst.get(field)
        assert got == want, f"fixture_driven 字段 {field}：期望 {want!r}，实际 {got!r}"

    # inst_name 规则 {ip}-{model_id}-{port} 兜底校验
    assert inst["inst_name"] == f"{ip_addr}-redis-{raw_items['port']}", \
        f"inst_name 规则违反：{inst['inst_name']}"