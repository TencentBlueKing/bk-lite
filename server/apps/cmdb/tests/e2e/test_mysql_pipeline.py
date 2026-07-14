"""MySQL 采集端到端流水线测试 —— db 大类代表。

【Phase 2.2】2026-07-10 — 第二闭环
- test_step1_raw_matches_schema / test_mysql_pipeline_end_to_end / test_drift_detection: 原有契约测试
- test_mysql_pipeline_fixture_driven: **用真实 stargazer 落盘的 fixture 驱动全链路**
- test_mysql_canonical_to_step3: **直接喂 raw_stdout["result"]["mysql"] 列表,验证 runner 平铺路径(db 类 extra_payload_keys=None)**

db runner 与 protocol runner 格式一致(平铺,不解析 metric.result),
inst_name 规则 {ip}-{model_id}-{port}。
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
        instances=[{"inst_name": "mysql-prod-01", "ip_addr": raw["ip_addr"]}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"]["mysql"]
    assert len(instances) >= expected["instance_count_min"]

    inst_schema = load_schema("mysql/04_cmdb_instance.schema.json")
    for inst in instances:
        jsonschema.validate(inst, inst_schema)

    actual = instances[0]
    # end_to_end 用 01_raw_collector.json(10.0.0.41:3306 / version 8.0.36)
    end_to_end_expected = {
        "inst_name": "10.0.0.41-mysql-3306",
        "ip_addr":   "10.0.0.41",
        "port":      "3306",
        "version":   "8.0.36",
    }
    for field, expected_value in end_to_end_expected.items():
        assert actual.get(field) == expected_value, \
            f"end_to_end 字段 {field}：期望 {expected_value!r}，实际 {actual.get(field)!r}"


def test_drift_detection(load_schema):
    bad = {"ip_addr": "1.1.1.1", "port": "3306", "version": "8.0", "enable_binlog": "Yes"}  # enum 漂移
    schema = load_schema("mysql/01_raw_collector.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


# =============================================================================
# Phase 2.2:fixture 驱动的真实链路验证
# =============================================================================


@pytest.mark.django_db
def test_mysql_pipeline_fixture_driven(monkeypatch, load_fixture, load_schema):
    """Phase 2.2 第二闭环：用 stargazer 真实落盘的 fixture 驱动 4 段流水线。

    与 test_mysql_pipeline_end_to_end 的区别:
    - 后者用 01_raw_collector.json(人造 raw,字段已对齐 04_expected)
    - 本测试用 01_stargazer_raw.json(由 cli 真实落盘,字段名 / 类型可能更"野生")

    验证三层:
      1) 契约层:fixture 命中 01_stargazer_raw schema(stargazer 真实输出契约稳定)
      2) 流水线层:cmdb_result["mysql"] 至少 1 个实例
      3) 字段对齐层:实例关键字段与 expected_instance_subset 一致
    """
    from apps.cmdb.collection.collect_plugin.protocol import ProtocolCollectMetrics
    from apps.cmdb.collection.plugins.community.protocol.mysql import MysqlCollectionPlugin

    # 1) 契约层
    stargazer_raw = load_fixture("mysql/01_stargazer_raw.json")
    raw_schema = load_schema("mysql/01_stargazer_raw.schema.json")
    jsonschema.validate(stargazer_raw, raw_schema)

    # 从 fixture 抽出 raw_items(plugin 入参形态)
    raw_items = stargazer_raw["raw_stdout"]["result"]["mysql"][0]
    ip_addr = raw_items["ip_addr"]

    # 2) 流水线层(db runner extra_payload_keys=None 平铺)
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=ProtocolCollectMetrics,
        plugin_cls=MysqlCollectionPlugin,
        model_id="mysql",
        task_id=14001,
        instances=[{"inst_name": "mysql-fixture-01", "ip_addr": ip_addr}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )
    instances = run["cmdb_result"]["mysql"]
    assert len(instances) >= 1, "fixture 驱动流水线应至少产出 1 个实例"

    # 3) 字段对齐层
    expected_doc = load_fixture("mysql/04_expected_cmdb_result.json")
    expected_subset = expected_doc["expected_instance_subset"]
    inst_schema = load_schema("mysql/04_cmdb_instance.schema.json")

    inst = instances[0]
    jsonschema.validate(inst, inst_schema)
    for field, want in expected_subset.items():
        got = inst.get(field)
        assert got == want, f"字段 {field}：期望 {want!r}，实际 {got!r}"

    # inst_name 规则 {ip}-{model_id}-{port} 兜底校验
    assert inst["inst_name"] == f"{ip_addr}-mysql-{raw_items['port']}", \
        f"inst_name 规则违反：{inst['inst_name']}"


@pytest.mark.django_db
def test_mysql_canonical_to_step3(monkeypatch, load_fixture, load_schema):
    """Phase 2.2 第二闭环变体：直接喂 raw_stdout["result"]["mysql"] 列表,
    模拟 step1_stargazer_normalize_generic 的真实入参形态(已经是 list)。
    """
    from apps.cmdb.collection.collect_plugin.protocol import ProtocolCollectMetrics
    from apps.cmdb.collection.plugins.community.protocol.mysql import MysqlCollectionPlugin

    stargazer_raw = load_fixture("mysql/01_stargazer_raw.json")
    # 直接喂 raw_items 列表(已经是 cli 落盘的"标准化"形态)
    raw_items = stargazer_raw["raw_stdout"]["result"]["mysql"]

    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=ProtocolCollectMetrics,
        plugin_cls=MysqlCollectionPlugin,
        model_id="mysql",
        task_id=14002,
        instances=[{"inst_name": "mysql-canon-01", "ip_addr": raw_items[0]["ip_addr"]}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )
    instances = run["cmdb_result"]["mysql"]
    assert len(instances) >= 1
    # 字段对齐
    inst = instances[0]
    inst_schema = load_schema("mysql/04_cmdb_instance.schema.json")
    jsonschema.validate(inst, inst_schema)
    assert inst["version"] == "8.0.46"
    # mysql plugin 的 field_mapping 不含 role/master_host(2026-07-10 现状),
    # 所以 inst 不会有 role;但其他字段必须命中 expected_subset
    expected_doc = load_fixture("mysql/04_expected_cmdb_result.json")
    for field, want in expected_doc["expected_instance_subset"].items():
        got = inst.get(field)
        assert got == want, f"字段 {field}：期望 {want!r}，实际 {got!r}"