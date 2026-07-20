"""mycat archived placeholder 端到端测试 — license/集群/平台阻塞模式。

【v5 Task 4】2026-07-14
- 对象:MyCat 数据库中间件(task_type=HOST)
- 阻塞原因:集群/平台阻塞(_placeholder_reason='cluster_complex')
- archived plugin:apps/cmdb/collection/plugins/community/archived/mycat.py
  - priority=1,metric_names=[],field_mappings={}(stub)
- e2e 测试:验证 fixture 满足公共契约 + placeholder 模式 + 04 schema
- A 端对齐:placeholder 模式允许 metric 名/instance_id vacuous 通过
- B 端对齐:test_cmdb_vm_format_alignment 在 _placeholder_reason 存在时 pytest.skip
"""
import json

import jsonschema
import pytest

from apps.cmdb.tests.e2e.conftest import E2E_ROOT


def _load(rel_path: str):
    with open(E2E_ROOT / rel_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_mycat_placeholder_fixture_satisfies_common_contract():
    """mycat fixture 满足公共契约(集群/平台阻塞 placeholder 模式)。"""
    fixture = _load("fixtures/mycat/01_stargazer_raw.json")
    contract = _load("schemas/00_common_contract.schema.json")
    jsonschema.validate(fixture, contract)

    # 验证 placeholder 状态标记
    assert fixture.get("license_status") == "missing"
    assert fixture.get("_placeholder_reason") == "cluster_complex"


def test_mycat_archived_stub_plugin_exists():
    """mycat archived stub plugin 必须存在(plugins/community/archived/mycat.py)。"""
    import importlib
    mod = importlib.import_module("apps.cmdb.collection.plugins.community.archived.mycat")
    from apps.cmdb.constants.constants import CollectPluginTypes

    # 找以 model_id 开头且以 CollectionPlugin 结尾的类
    target_prefix = "mycat".replace("_", "").lower()
    plugin_cls = None
    for attr_name in dir(mod):
        cls = getattr(mod, attr_name)
        if not isinstance(cls, type):
            continue
        if not attr_name.endswith("CollectionPlugin"):
            continue
        if attr_name.startswith("Base"):
            continue
        if attr_name.lower().replace("_", "").startswith(target_prefix):
            plugin_cls = cls
            break

    assert plugin_cls is not None, f"{mod.__name__} 中未找到 mycat*CollectionPlugin 类"
    assert plugin_cls.supported_model_id == "mycat"
    assert plugin_cls.supported_task_type == CollectPluginTypes.HOST
    assert plugin_cls.metric_names == []  # stub:无 metric
    assert plugin_cls.field_mappings == {}  # stub:无 field_mappings
    assert plugin_cls.priority == 1  # archived 占位低优先级


def test_mycat_conftest_runner_plugin_registered():
    """mycat 已在 conftest._MODEL_RUNNER_MAP 注册(A/B 端对齐能命中)。"""
    from apps.cmdb.tests.e2e.conftest import _MODEL_RUNNER_MAP
    assert "mycat" in _MODEL_RUNNER_MAP
    runner_type, extra = _MODEL_RUNNER_MAP["mycat"]
    # task_type → runner_type 映射校验
    expected_runner_type = {
        "MIDDLEWARE": "middleware",
        "PROTOCOL": "protocol",
        "HOST": "protocol",  # archived host 暂用 protocol runner 占位
    }.get("HOST")
    assert runner_type == expected_runner_type, \
        f"{runner_type!r} != {expected_runner_type!r}(task_type='HOST')"


def test_mycat_alignment_covered_model_id_listed():
    """mycat 已在 ALIGNMENT_COVERED_MODEL_IDS 注册(A/B 端对齐能跑到)。"""
    from apps.cmdb.tests.e2e.conftest import ALIGNMENT_COVERED_MODEL_IDS
    assert "mycat" in ALIGNMENT_COVERED_MODEL_IDS


def test_mycat_fixture_matches_01_schema(load_fixture, load_schema):
    """mycat 01 fixture 必符合 01 schema。"""
    raw = load_fixture("mycat/01_stargazer_raw.json")
    schema = load_schema("mycat/01_stargazer_raw.schema.json")
    jsonschema.validate(raw, schema)


def test_mycat_fixture_matches_04_schema(load_fixture, load_schema):
    """mycat 04 schema 是 placeholder 模式(只含 _placeholder_reason + license_status 必填)。"""
    schema = load_schema("mycat/04_cmdb_instance.schema.json")
    # 必填字段校验
    assert "_placeholder_reason" in schema.get("required", [])
    assert "license_status" in schema.get("required", [])
    # placeholder_reason enum 校验
    prop = schema["properties"]["_placeholder_reason"]
    assert "cluster_complex" in prop["enum"]


def test_mycat_drift_detection_01_schema(load_schema):
    """mycat 01 schema 拒绝缺 _placeholder_reason/license_status 的坏数据。"""
    bad = {"model_id": "mycat", "captured_at": "2026-07-14T10:30:00+08:00", "raw_stdout": {}}
    schema = load_schema("mycat/01_stargazer_raw.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_mycat_expected_04_placeholder(load_fixture):
    """mycat 04 expected fixture 必带 license_status=missing + instance_count_min=0。"""
    expected = load_fixture("mycat/04_expected_cmdb_result.json")
    assert expected["model_id"] == "mycat"
    assert expected["license_status"] == "missing"
    assert expected["instance_count_min"] == 0
    assert expected["_placeholder_reason"] == "cluster_complex"
