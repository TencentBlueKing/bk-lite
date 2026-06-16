"""InfluxDB 采集端到端流水线测试（protocol 大类，协议采集）。

protocol 模式：业务字段平铺到 metric labels（extra_payload_keys=None），
inst_name 规则 {ip}-{model_id}-{port}。覆盖 2.x（全字段）与 1.x（仅版本）。
"""
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
