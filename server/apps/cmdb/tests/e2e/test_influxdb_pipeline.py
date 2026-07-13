"""InfluxDB 采集端到端流水线测试（protocol 大类，协议采集）。

【Phase 2.1】2026-07-10 — 第一闭环
- v2_full / v1_version_only: 原有人造 raw 的协议契约测试
- fixture_driven_pipeline: **用真实 stargazer 落盘的 fixture 驱动全链路**,验证
  采集产物 → step1 标准化 → step2 push VM → step3 CMDB 消费 4 段全通
"""
import json

import pytest

from apps.cmdb.tests.e2e import pipeline


@pytest.mark.django_db
def test_influxdb_pipeline_v2_full(monkeypatch):
    """2.x：/api/v2/config 返回完整配置，字段较全。"""
    from apps.cmdb.collection.collect_plugin.protocol import ProtocolCollectMetrics
    from apps.cmdb.collection.plugins.community.protocol.influxdb import InfluxdbCollectionPlugin

    raw = {
        "ip_addr": "10.0.0.60",
        "port": "8086",
        "version": "2.7.5",
        "data_dir": "/var/lib/influxdb2/engine",
        "wal_dir": "/var/lib/influxdb2/engine",
        "meta_dir": "/var/lib/influxdb2/influxd.bolt",
        "engine": "tsm1",
        "http_bind_address": ":8086",
        "auth_enabled": "true",
        "https_enabled": "false",
        "max_concurrent_queries": "0",
    }
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw,
        runner_cls=ProtocolCollectMetrics,
        plugin_cls=InfluxdbCollectionPlugin,
        model_id="influxdb",
        task_id=8001,
        instances=[{"inst_name": "influxdb-prod-01", "ip_addr": "10.0.0.60"}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )
    inst = run["cmdb_result"]["influxdb"][0]
    for field, value in raw.items():
        assert inst.get(field) == value, \
            f"字段 {field}：期望 {value!r}，实际 {inst.get(field)!r}"
    # inst_name 规则 {ip}-{model_id}-{port}
    assert inst["inst_name"] == "10.0.0.60-influxdb-8086"


@pytest.mark.django_db
def test_influxdb_pipeline_v1_version_only(monkeypatch):
    """1.x：仅 version 可采，路径类字段留空（不报错）。"""
    from apps.cmdb.collection.collect_plugin.protocol import ProtocolCollectMetrics
    from apps.cmdb.collection.plugins.community.protocol.influxdb import InfluxdbCollectionPlugin

    raw = {"ip_addr": "10.0.0.61", "port": "8086", "version": "1.8.10",
           "data_dir": "", "meta_dir": "", "http_bind_address": ""}
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw,
        runner_cls=ProtocolCollectMetrics,
        plugin_cls=InfluxdbCollectionPlugin,
        model_id="influxdb",
        task_id=8002,
        instances=[{"inst_name": "influxdb-v1", "ip_addr": "10.0.0.61"}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )
    inst = run["cmdb_result"]["influxdb"][0]
    assert inst["version"] == "1.8.10"
    assert inst["inst_name"] == "10.0.0.61-influxdb-8086"
    # 路径类字段留空不报错
    assert inst.get("data_dir") == ""


@pytest.mark.django_db
def test_influxdb_pipeline_fixture_driven(monkeypatch, load_fixture, load_schema):
    """Phase 2.1 第一闭环：用 stargazer 真实落盘的 fixture 驱动 4 段流水线。

    链路：stargazer fixture → step1 normalize → step2 push VM → step3 CMDB consume → 字段对齐
    验证三层：
      1) 契约层：fixture 命中 schema(stargazer 原始输出契约稳定)
      2) 流水线层：cmdb_result["influxdb"] 至少 1 个实例
      3) 字段对齐层：实例关键字段与 expected_instance_subset 一致
    """
    import jsonschema

    from apps.cmdb.collection.collect_plugin.protocol import ProtocolCollectMetrics
    from apps.cmdb.collection.plugins.community.protocol.influxdb import InfluxdbCollectionPlugin

    # 1) 契约层：stargazer raw 必须命中 schema
    stargazer_raw = load_fixture("influxdb/01_stargazer_raw.json")
    stargazer_schema = load_schema("influxdb/01_stargazer_raw.schema.json")
    jsonschema.validate(stargazer_raw, stargazer_schema)

    # 从 fixture 抽出 raw_items（plugin 入参形态）
    raw_items = stargazer_raw["raw_stdout"]["result"]["influxdb"][0]
    ip_addr = raw_items["ip_addr"]

    # 2) 流水线层：跑 4 段
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=ProtocolCollectMetrics,
        plugin_cls=InfluxdbCollectionPlugin,
        model_id="influxdb",
        task_id=18001,
        instances=[{"inst_name": "influxdb-fixture-01", "ip_addr": ip_addr}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )
    instances = run["cmdb_result"]["influxdb"]
    assert len(instances) >= 1, "fixture 驱动流水线应至少产出 1 个实例"

    # 3) 字段对齐层
    expected_doc = load_fixture("influxdb/04_expected_cmdb_result.json")
    expected_subset = expected_doc["expected_instance_subset"]
    cmdb_schema = load_schema("influxdb/04_cmdb_instance.schema.json")

    inst = instances[0]
    jsonschema.validate(inst, cmdb_schema)
    for field, want in expected_subset.items():
        got = inst.get(field)
        assert got == want, f"字段 {field}：期望 {want!r}，实际 {got!r}"

    # inst_name 规则 {ip}-{model_id}-{port} 兜底校验
    assert inst["inst_name"] == f"{ip_addr}-influxdb-{raw_items['port']}", \
        f"inst_name 规则违反：{inst['inst_name']}"