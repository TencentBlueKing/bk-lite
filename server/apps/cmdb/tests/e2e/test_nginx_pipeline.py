"""Nginx 采集端到端流水线测试 —— middleware 大类代表。

【Phase 2.3】2026-07-10 — 第三闭环
- 原有 3 个测试(step1_raw / pipeline_end_to_end / drift_detection)
- 新增 test_nginx_pipeline_fixture_driven: **用 stargazer 真实落盘的 fixture 驱动全链路**

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

    # 字段值对齐预期(end_to_end 用 01_raw_collector.json → 10.0.0.21 raw)
    actual = nginx_instances[0]
    for field, expected_value in expected["expected_instance_subset_end_to_end"].items():
        assert actual.get(field) == expected_value, \
            f"end_to_end 字段 {field}：期望 {expected_value!r}，实际 {actual.get(field)!r}"


# ============================================================================
# 漂移检测：raw 字段类型变了 → schema 拦截
# ============================================================================


def test_drift_detection_bad_raw_caught_by_schema(load_schema):
    bad = {"ip_addr": "10.0.0.21", "port": 80, "version": "1.24"}  # port 应为 string
    schema = load_schema("nginx/01_raw_collector.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


# =============================================================================
# Phase 2.3:fixture 驱动的真实链路验证
# =============================================================================


@pytest.mark.django_db
def test_nginx_pipeline_fixture_driven(monkeypatch, load_fixture, load_schema):
    """Phase 2.3 第三闭环：用 stargazer 真实落盘的 fixture 驱动 4 段流水线。

    差异点(middleware runner):
    - extra_payload_keys={"result": True}:业务字段经 metric.result JSON 编码
    - runner 解码后合入 index_dict
    - stargazer fixture 的 raw_stdout 含 bk_inst_name / bk_obj_id(v2 标准化字段)

    验证三层:
      1) 契约层:fixture 命中 01_stargazer_raw schema
      2) 流水线层:cmdb_result["nginx"] 至少 1 个实例
      3) 字段对齐层:实例关键字段与 expected_instance_subset_fixture_driven 一致
    """
    from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
    from apps.cmdb.collection.plugins.community.middleware.nginx import NginxCollectionPlugin

    # 1) 契约层
    stargazer_raw = load_fixture("nginx/01_stargazer_raw.json")
    raw_schema = load_schema("nginx/01_stargazer_raw.schema.json")
    jsonschema.validate(stargazer_raw, raw_schema)

    # 抽出 raw_items(nginx 真实落盘是 dict 平铺,直接用 raw_stdout)
    raw_items = stargazer_raw["raw_stdout"]
    ip_addr = raw_items["ip_addr"]

    # 2) 流水线层(middleware runner extra_payload_keys={"result": True})
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=MiddlewareCollectMetrics,
        plugin_cls=NginxCollectionPlugin,
        model_id="nginx",
        task_id=12001,
        instances=[{"inst_name": "nginx-fixture-01", "ip_addr": ip_addr}],
        extra_payload_keys={"result": True},
        monkeypatch=monkeypatch,
    )
    instances = run["cmdb_result"]["nginx"]
    assert len(instances) >= 1, "fixture 驱动流水线应至少产出 1 个实例"

    # 3) 字段对齐层
    expected_doc = load_fixture("nginx/04_expected_cmdb_result.json")
    expected_subset = expected_doc["expected_instance_subset_fixture_driven"]
    inst_schema = load_schema("nginx/04_cmdb_instance.schema.json")

    inst = instances[0]
    jsonschema.validate(inst, inst_schema)
    for field, want in expected_subset.items():
        got = inst.get(field)
        assert got == want, f"fixture_driven 字段 {field}：期望 {want!r}，实际 {got!r}"

    # inst_name 规则 {ip}-{model_id}-{port} 兜底校验
    port = raw_items.get("listen_port") or raw_items.get("port")
    assert inst["inst_name"] == f"{ip_addr}-nginx-{port}", \
        f"inst_name 规则违反：{inst['inst_name']}"