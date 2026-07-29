"""CMDB 自动关联规则 BDD（中文 Gherkin）。

对照 specs/capabilities/legacy-prd-cmdb-模型管理.md·自动关联规则：
- 校验 match_pairs 非空、字段存在、字段类型一致、匹配规则合法。
"""

import json
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from apps.cmdb.services.auto_relation_rule import validate_auto_relation_rule_payload
from apps.core.exceptions.base_app_exception import BaseAppException

FEATURE = str(Path(__file__).parent / "auto_relation_rule.feature")
scenarios(FEATURE)


@pytest.fixture
def ctx():
    return {"src_attrs": [], "dst_attrs": [], "rule": None, "error": None}


@given(parsers.parse("源模型属性 {raw}"))
def _seed_src(ctx, raw):
    ctx["src_attrs"] = json.loads(raw)


@given(parsers.parse("目标模型属性 {raw}"))
def _seed_dst(ctx, raw):
    ctx["dst_attrs"] = json.loads(raw)


@when(parsers.parse("我校验自动关联规则 payload={raw}"))
def _validate(ctx, raw):
    payload = None if raw == "null" else json.loads(raw)
    try:
        ctx["rule"] = validate_auto_relation_rule_payload(
            model_association={}, src_attrs=ctx["src_attrs"], dst_attrs=ctx["dst_attrs"], payload=payload
        )
    except BaseAppException as exc:
        ctx["error"] = exc


@then("校验应当通过")
def _ok(ctx):
    assert ctx["error"] is None, ctx["error"]
    assert ctx["rule"] is not None


@then(parsers.parse("返回的规则启用状态应当为 {flag}"))
def _enabled(ctx, flag):
    assert ctx["rule"].enabled is (flag.lower() == "true")


@then(parsers.parse('应当抛出业务异常，消息包含 "{snippet}"'))
def _expect_error(ctx, snippet):
    assert ctx["error"] is not None, "expected BaseAppException, got none"
    assert snippet in str(ctx["error"]), ctx["error"]
