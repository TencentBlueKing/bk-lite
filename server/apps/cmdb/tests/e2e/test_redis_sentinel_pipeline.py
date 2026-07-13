"""redis_sentinel 采集端到端流水线测试 — 复用 redis plugin。

【v4 Phase 6 补 redis_sentinel】2026-07-10 — 此前因 catalog entry_type=shell 无 plugin 类被跳过
- redis_sentinel 的 stargazer 端 entry_type=shell,无 plugin
- CMDB 端复用 redis plugin(model_id='redis',Runner=DBCollectCollectMetrics)
- fixture 形态 C:list-of-dict 2 实例(redis 主 6379 + sentinel 26379)
- bk_obj_id 都是 'redis',所以 plugin 走 redis
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


@pytest.mark.django_db
def test_redis_sentinel_pipeline_fixture_driven(monkeypatch, load_fixture, load_schema):
    """redis_sentinel → 复用 redis plugin,验证 2 实例(主 + sentinel)全过。"""
    from apps.cmdb.collection.collect_plugin.databases import DBCollectCollectMetrics
    from apps.cmdb.collection.plugins.community.db.redis import RedisCollectionPlugin

    # 1) 契约层
    stargazer_raw = load_fixture("redis_sentinel/01_stargazer_raw.json")
    raw_schema = load_schema("redis_sentinel/01_stargazer_raw.schema.json")
    jsonschema.validate(stargazer_raw, raw_schema)

    # redis_sentinel 复用 redis plugin:model_id='redis',fixture 形态 C list-of-dict
    raw_items = stargazer_raw["raw_stdout"]  # list of 2 dicts

    # 2) 流水线层
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=DBCollectCollectMetrics,
        plugin_cls=RedisCollectionPlugin,
        model_id="redis",  # 复用 redis plugin(redis_sentinel 的 bk_obj_id 都是 'redis')
        task_id=18888,
        instances=[{"inst_name": "redis-sentinel-01", "ip_addr": "127.0.0.1"}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )
    instances = run["cmdb_result"]["redis"]
    assert len(instances) >= 2, (
        f"redis_sentinel 应产出至少 2 个实例(redis 主 + sentinel),实际 {len(instances)}"
    )

    # 3) 字段对齐层
    expected_doc = load_fixture("redis_sentinel/04_expected_cmdb_result.json")
    expected_subsets = expected_doc["expected_instance_subset_fixture_driven"]
    inst_schema = load_schema("redis_sentinel/04_cmdb_instance.schema.json")

    # 关键断言:2 个实例的 inst_name + port + database_role 都对得上
    inst_by_port = {inst.get("port"): inst for inst in instances}
    for want in expected_subsets:
        port = want.get("port")
        inst = inst_by_port.get(port)
        assert inst is not None, f"port={port} 的实例未产出,实际 ports: {list(inst_by_port.keys())}"
        jsonschema.validate(inst, inst_schema)
        for field, expected_value in want.items():
            actual = inst.get(field)
            assert actual == expected_value, (
                f"redis_sentinel port={port} 字段 {field}: 期望 {expected_value!r}, 实际 {actual!r}"
            )