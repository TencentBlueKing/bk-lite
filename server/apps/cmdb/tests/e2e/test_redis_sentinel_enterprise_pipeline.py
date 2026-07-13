"""redis_sentinel_enterprise 商业版 Redis Sentinel 端到端测试 — 复用 redis_sentinel plugin。

【v5 Task 3.7】2026-07-14
- 商业版 redis_sentinel_enterprise 复用社区版 redis_sentinel(plugin 类:RedisCollectionPlugin,model_id=redis)
- fixture 形态 C(redis 主 6379 + sentinel 26379 双实例,共 2 个)
- 复用 test_redis_sentinel_pipeline.py 全部断言(同 plugin 类 + 同 fixture 结构)
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


@pytest.mark.django_db
def test_redis_sentinel_enterprise_pipeline_fixture_driven(monkeypatch, load_fixture, load_schema):
    """redis_sentinel_enterprise → 复用 redis plugin,验证 2 实例(主 + sentinel)全过。

    与 redis_sentinel 区别:model_id 走 redis_sentinel_enterprise(商业版命名空间),
    但 plugin 类仍是 RedisCollectionPlugin(bk_obj_id 都是 'redis')。
    """
    from apps.cmdb.collection.collect_plugin.databases import DBCollectCollectMetrics
    from apps.cmdb.collection.plugins.community.db.redis import RedisCollectionPlugin

    # 1) 契约层
    stargazer_raw = load_fixture("redis_sentinel_enterprise/01_stargazer_raw.json")
    raw_schema = load_schema("redis_sentinel_enterprise/01_stargazer_raw.schema.json")
    jsonschema.validate(stargazer_raw, raw_schema)

    # fixture 是 list of 2 dicts(形态 C)
    raw_items = stargazer_raw  # list of 2 dicts

    # 2) 流水线层
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=DBCollectCollectMetrics,
        plugin_cls=RedisCollectionPlugin,
        model_id="redis",  # 复用 redis plugin(redis_sentinel_enterprise 的 bk_obj_id 都是 'redis')
        task_id=18889,
        instances=[{"inst_name": "redis-sentinel-ent-01", "ip_addr": "127.0.0.1"}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )
    instances = run["cmdb_result"]["redis"]
    assert len(instances) >= 2, (
        f"redis_sentinel_enterprise 应产出至少 2 个实例(redis 主 + sentinel),实际 {len(instances)}"
    )

    # 3) 字段对齐层(复用 redis_sentinel 的 04 schema)
    expected_doc = load_fixture("redis_sentinel/04_expected_cmdb_result.json")
    expected_subsets = expected_doc["expected_instance_subset_fixture_driven"]
    inst_schema = load_schema("redis_sentinel/04_cmdb_instance.schema.json")

    inst_by_port = {inst.get("port"): inst for inst in instances}
    for want in expected_subsets:
        port = want.get("port")
        inst = inst_by_port.get(port)
        assert inst is not None, f"port={port} 的实例未产出,实际 ports: {list(inst_by_port.keys())}"
        jsonschema.validate(inst, inst_schema)
        for field, expected_value in want.items():
            actual = inst.get(field)
            assert actual == expected_value, (
                f"redis_sentinel_enterprise port={port} 字段 {field}: 期望 {expected_value!r}, 实际 {actual!r}"
            )


def test_redis_sentinel_enterprise_alias_resolves_to_redis_sentinel():
    """redis_sentinel_enterprise 复用 redis_sentinel schema 目录(SCHEMA_DIR_ALIAS)。"""
    from apps.cmdb.tests.e2e.utils.model_reflection import SCHEMA_DIR_ALIAS
    assert SCHEMA_DIR_ALIAS.get("redis_sentinel_enterprise") == "redis_sentinel"


def test_redis_sentinel_enterprise_in_factory_map():
    """redis_sentinel_enterprise 在 conftest._MODEL_RUNNER_MAP 注册(middleware 复用 redis_sentinel)。"""
    from apps.cmdb.tests.e2e.conftest import _MODEL_RUNNER_MAP
    assert "redis_sentinel_enterprise" in _MODEL_RUNNER_MAP
    # middleware runner + result: True(同 redis_sentinel)
    runner_type, extra = _MODEL_RUNNER_MAP["redis_sentinel_enterprise"]
    assert runner_type == "middleware"
    assert extra == {"result": True}
