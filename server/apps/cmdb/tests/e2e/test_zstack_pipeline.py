"""zstack 私有云采集端到端测试 — stub plugin placeholder 模式。

【v5 Task 3.4】2026-07-14
- zstack 无真实 SDK 实现,只占位注册 stub plugin(plugins/community/cloud/zstack.py)
- fixture 标 _placeholder_reason=plugin_stub
- e2e 测试:验证 fixture 满足 placeholder 模式 + common contract 命中
- A/B 端对齐:placeholder 模式允许为空(B 端必填字段检查跳过)
"""
import json

import jsonschema
import pytest

from apps.cmdb.tests.e2e.conftest import E2E_ROOT


def _load(rel_path: str):
    with open(E2E_ROOT / rel_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_zstack_placeholder_fixture_satisfies_common_contract():
    """zstack fixture 满足公共契约(placeholder 模式)。"""
    fixture = _load("fixtures/zstack/01_stargazer_raw.json")
    contract = _load("schemas/00_common_contract.schema.json")
    jsonschema.validate(fixture, contract)

    # 验证 placeholder 状态标记
    assert fixture.get("_placeholder_reason") == "plugin_stub"


def test_zstack_stub_plugin_exists():
    """zstack stub plugin 必须存在(plugins/community/cloud/zstack.py)。"""
    from apps.cmdb.collection.plugins.community.cloud import zstack as zstack_plugin
    from apps.cmdb.constants.constants import CollectPluginTypes
    assert hasattr(zstack_plugin, "ZStackCollectionPlugin")
    cls = zstack_plugin.ZStackCollectionPlugin
    assert cls.supported_model_id == "zstack"
    assert cls.supported_task_type == CollectPluginTypes.CLOUD
    assert cls.metric_names == []  # stub:无 metric
    assert cls.field_mappings == {}  # stub:无 field_mappings


def test_zstack_fixture_matches_01_schema(load_fixture, load_schema):
    """zstack 01 fixture 必符合 01 schema。"""
    raw = load_fixture("zstack/01_stargazer_raw.json")
    schema = load_schema("zstack/01_stargazer_raw.schema.json")
    jsonschema.validate(raw, schema)


def test_zstack_drift_detection(load_schema):
    """zstack schema 拒绝缺 _placeholder_reason 的坏数据。"""
    bad = {"model_id": "zstack", "captured_at": "2026-07-14T10:30:00+08:00", "raw_stdout": {}}
    schema = load_schema("zstack/01_stargazer_raw.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_zstack_alignment_a_placeholder_skip(load_fixture):
    """A 端 placeholder 对象无真实 metric 03,直接跳过(对齐测试由 placeholder 模式绕过)。

    不实际跑 pipeline,因为 stub plugin 无 metric_names,runner._metrics 抛 KeyError。
    """
    fixture = load_fixture("zstack/01_stargazer_raw.json")
    # placeholder 模式:raw_stdout 是空对象
    assert fixture["raw_stdout"] == {}
    assert fixture["_placeholder_reason"] == "plugin_stub"
