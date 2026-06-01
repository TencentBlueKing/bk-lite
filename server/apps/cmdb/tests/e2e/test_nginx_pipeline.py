"""Nginx 采集端到端流水线测试 —— middleware 大类代表。

流水线：
  Stargazer nginx 脚本输出 → Stargazer 标准化 (model_id=nginx) → push 到 VM
  → CMDB MiddlewareCollectMetrics + NginxCollectionPlugin → 实例字典

中间件类与 host 的差异：
  - VM 响应里业务字段通过 `metric.result` JSON 字符串编码（runner 解码后合入 index_dict）
  - 调用真实 NginxCollectionPlugin.field_mapping
  - 自动绑定（bind_collection_mapping）pick_value/get_inst_name 等方法到 runner 实例
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


# ============================================================================
# 段 1: 采集脚本原始输出契约
# ============================================================================


def test_step1_raw_matches_schema(load_fixture, load_schema):
    raw = load_fixture("nginx/01_raw_collector.json")
    schema = load_schema("nginx/01_raw_collector.schema.json")
    jsonschema.validate(raw, schema)


# ============================================================================
# 段 4 + e2e: 真实跑 MiddlewareCollectMetrics + NginxCollectionPlugin
# ============================================================================


@pytest.mark.django_db
def test_nginx_pipeline_end_to_end(load_fixture, load_schema, monkeypatch):
    from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
    from apps.cmdb.collection.plugins.community.middleware.nginx import NginxCollectionPlugin

    raw = load_fixture("nginx/01_raw_collector.json")
    expected = load_fixture("nginx/04_expected_cmdb_result.json")

    run = pipeline.run_full_pipeline_generic(
        raw_items=raw,
        runner_cls=MiddlewareCollectMetrics,
        plugin_cls=NginxCollectionPlugin,
        model_id="nginx",
        task_id=2001,
        instances=[{"inst_name": "nginx-prod-01", "ip_addr": "10.0.0.21"}],
        extra_payload_keys={"result": True},  # 走 middleware metric.result JSON 编码
        monkeypatch=monkeypatch,
    )

    # 实例数 & 实例 schema
    nginx_instances = run["cmdb_result"]["nginx"]
    assert len(nginx_instances) >= expected["instance_count_min"]

    inst_schema = load_schema("nginx/04_cmdb_instance.schema.json")
    for inst in nginx_instances:
        jsonschema.validate(inst, inst_schema)

    # 字段值对齐预期（容许 expected 是 subset：只校验关键字段）
    actual = nginx_instances[0]
    for field, expected_value in expected["expected_instance_subset"].items():
        assert actual.get(field) == expected_value, \
            f"字段 {field}：期望 {expected_value!r}，实际 {actual.get(field)!r}"


# ============================================================================
# 漂移检测：raw 字段类型变了 → schema 拦截
# ============================================================================


def test_drift_detection_bad_raw_caught_by_schema(load_schema):
    bad = {"ip_addr": "10.0.0.21", "port": 80, "version": "1.24"}  # port 应为 string
    schema = load_schema("nginx/01_raw_collector.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
