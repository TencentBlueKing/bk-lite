"""MySQL 采集端到端流水线测试 —— protocol 大类代表。

Protocol 与 db 大类格式一致（平铺，不解析 metric.result），inst_name 规则也是 {ip}-{model_id}-{port}。
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


def test_step1_raw_matches_schema(load_fixture, load_schema):
    raw = load_fixture("mysql/01_raw_collector.json")
    schema = load_schema("mysql/01_raw_collector.schema.json")
    jsonschema.validate(raw, schema)


@pytest.mark.django_db
def test_mysql_pipeline_end_to_end(load_fixture, load_schema, monkeypatch):
    from apps.cmdb.collection.collect_plugin.protocol import ProtocolCollectMetrics
    from apps.cmdb.collection.plugins.community.protocol.mysql import MysqlCollectionPlugin

    raw = load_fixture("mysql/01_raw_collector.json")
    expected = load_fixture("mysql/04_expected_cmdb_result.json")

    run = pipeline.run_full_pipeline_generic(
        raw_items=raw,
        runner_cls=ProtocolCollectMetrics,
        plugin_cls=MysqlCollectionPlugin,
        model_id="mysql",
        task_id=4001,
        instances=[{"inst_name": "mysql-prod-01", "ip_addr": "10.0.0.41"}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"]["mysql"]
    assert len(instances) >= expected["instance_count_min"]

    inst_schema = load_schema("mysql/04_cmdb_instance.schema.json")
    for inst in instances:
        jsonschema.validate(inst, inst_schema)

    actual = instances[0]
    for field, expected_value in expected["expected_instance_subset"].items():
        assert actual.get(field) == expected_value, \
            f"字段 {field}：期望 {expected_value!r}，实际 {actual.get(field)!r}"


def test_drift_detection(load_schema):
    bad = {"ip_addr": "1.1.1.1", "port": "3306", "version": "8.0", "enable_binlog": "Yes"}  # enum 漂移
    schema = load_schema("mysql/01_raw_collector.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
