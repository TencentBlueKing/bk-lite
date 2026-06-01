"""Redis 采集端到端流水线测试 —— db 大类代表。

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
    for field, expected_value in expected["expected_instance_subset"].items():
        assert actual.get(field) == expected_value, \
            f"字段 {field}：期望 {expected_value!r}，实际 {actual.get(field)!r}"


def test_drift_detection(load_schema):
    bad = {"ip_addr": "1.1.1.1", "port": 6379, "version": "7"}  # port should be string
    schema = load_schema("redis/01_raw_collector.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
