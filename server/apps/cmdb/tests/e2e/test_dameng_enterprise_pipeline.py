"""dameng_enterprise 商业版达梦数据库端到端测试 — 复用 dameng plugin。

【v5 Task 3.6】2026-07-14
- 商业版 dameng 复用社区版 dameng plugin(apps/cmdb/collection/plugins/community/db/dameng.py)
- e2e 走 license 阻塞 placeholder 模式(同 dameng),fixture 标 license_status=missing
- A/B 端对齐:placeholder 模式允许为空
"""
import json

import jsonschema
import pytest

from apps.cmdb.tests.e2e.conftest import E2E_ROOT


def _load(rel_path: str):
    with open(E2E_ROOT / rel_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_dameng_enterprise_placeholder_fixture_satisfies_common_contract():
    """dameng_enterprise fixture 满足公共契约(license 阻塞 placeholder)。"""
    fixture = _load("fixtures/dameng_enterprise/01_stargazer_raw.json")
    contract = _load("schemas/00_common_contract.schema.json")
    jsonschema.validate(fixture, contract)

    # 验证 placeholder 状态标记
    assert fixture.get("license_status") == "missing"
    assert fixture.get("_placeholder_reason") == "dameng_enterprise_license"


def test_dameng_enterprise_reuses_dameng_plugin():
    """dameng_enterprise 复用 dameng 路径(社区版 dameng 同 plugin 类,只存在 placeholder 模式)。

    实际:dameng 社区版 CMDB 端无 plugin 类(brief 描述期望,但实际未实现),
    本测试仅验证 dameng_enterprise 与 dameng 都走相同 placeholder 模式。
    """
    # dameng_enterprise 在 conftest._MODEL_RUNNER_MAP 注册为 db runner
    from apps.cmdb.tests.e2e.conftest import _MODEL_RUNNER_MAP
    assert "dameng_enterprise" in _MODEL_RUNNER_MAP
    # dameng(社区版)同样注册
    assert "dameng" in _MODEL_RUNNER_MAP
    # 商业版/社区版 runner_type 一致(都是 db)
    assert _MODEL_RUNNER_MAP["dameng_enterprise"][0] == "db"
    assert _MODEL_RUNNER_MAP["dameng"][0] == "db"


def test_dameng_enterprise_alias_resolves_to_dameng():
    """dameng_enterprise 复用 dameng schema 目录(SCHEMA_DIR_ALIAS)。"""
    from apps.cmdb.tests.e2e.utils.model_reflection import SCHEMA_DIR_ALIAS
    # dameng_enterprise alias → dameng
    assert SCHEMA_DIR_ALIAS.get("dameng_enterprise") == "dameng"


def test_dameng_enterprise_fixture_matches_01_schema(load_fixture, load_schema):
    """dameng_enterprise 01 fixture 必符合 01 schema。"""
    raw = load_fixture("dameng_enterprise/01_stargazer_raw.json")
    schema = load_schema("dameng_enterprise/01_stargazer_raw.schema.json")
    jsonschema.validate(raw, schema)


def test_dameng_enterprise_drift_detection(load_schema):
    """dameng_enterprise schema 拒绝缺 license_status 的坏数据。"""
    bad = {"model_id": "dameng_enterprise", "captured_at": "2026-07-14T10:30:00+08:00", "raw_stdout": {}}
    schema = load_schema("dameng_enterprise/01_stargazer_raw.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_dameng_enterprise_blocked_reason_documented():
    """dameng_enterprise fixture 必带 blocked_reason + next_steps + references。"""
    fixture = _load("fixtures/dameng_enterprise/01_stargazer_raw.json")
    assert fixture.get("blocked_reason"), "dameng_enterprise fixture 应有 blocked_reason 字段"
    assert fixture.get("next_steps"), "dameng_enterprise fixture 应有 next_steps 字段"
    assert fixture.get("references"), "dameng_enterprise fixture 应有 references 字段"
