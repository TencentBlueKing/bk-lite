"""CMDB 唯一性规则 BDD（中文 Gherkin）。

对照 spec/prd/CMDB·模型管理·唯一规则：
- collect_unique_rule_conflicts：批量数据与既有实例的联合字段唯一性检查；
- 编辑场景排除自身；
- 批次内重复检测；
- validate_unique_rule_payload：字段必填 / 不可重复 / inst_name 禁用 / 规则数上限。

2 happy + 6 corner。
"""

import json
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from apps.cmdb.services.unique_rule import (
    ModelUniqueRule,
    UniqueRuleCheckContext,
    UniqueRulePayload,
    collect_unique_rule_conflicts,
    parse_unique_rules,
    validate_unique_rule_payload,
)
from apps.core.exceptions.base_app_exception import BaseAppException

FEATURE = str(Path(__file__).parent / "unique_rule.feature")
scenarios(FEATURE)


@pytest.fixture
def ctx():
    return {
        "rules": [],
        "attrs_by_id": {},
        "exist_items": [],
        "conflicts": None,
        "error": None,
        "rule_ctx": None,
    }


# ---------------------------------------------------------------------------
# 假设
# ---------------------------------------------------------------------------

@given(parsers.parse("模型唯一规则定义为 {raw}"))
def _seed_rules(ctx, raw):
    ctx["rules"] = parse_unique_rules(json.loads(raw))


@given(parsers.parse("模型属性映射为 {raw}"))
def _seed_attrs(ctx, raw):
    ctx["attrs_by_id"] = json.loads(raw)


@given(parsers.parse("既有实例集合为 {raw}"))
def _seed_exist(ctx, raw):
    ctx["exist_items"] = json.loads(raw)


@given(parsers.re(
    r"唯一规则上下文 attrs=(?P<attrs>\{.*\}) 现有规则数=(?P<n>\d+)"
))
def _seed_rule_ctx(ctx, attrs, n):
    attrs_by_id = json.loads(attrs)
    existing_rules = [
        ModelUniqueRule(rule_id=f"r{i}", order=i + 1, field_ids=["__placeholder__"])
        for i in range(int(n))
    ]
    ctx["rule_ctx"] = UniqueRuleCheckContext(
        model_id="host", attrs_by_id=attrs_by_id, unique_rules=existing_rules
    )


# ---------------------------------------------------------------------------
# 当
# ---------------------------------------------------------------------------

@when(parsers.parse("我检查批次 {raw} 是否冲突"))
def _check_batch(ctx, raw):
    items = json.loads(raw)
    ctx["conflicts"] = collect_unique_rule_conflicts(
        rules=ctx["rules"],
        items=items,
        exist_items=ctx["exist_items"],
        attrs_by_id=ctx["attrs_by_id"],
    )


@when(parsers.re(r"我以排除 ids=(?P<ids>\[[^\]]*\]) 检查批次 (?P<items>\[.*\]) 是否冲突"))
def _check_batch_exclude(ctx, ids, items):
    exclude = set(json.loads(ids))
    ctx["conflicts"] = collect_unique_rule_conflicts(
        rules=ctx["rules"],
        items=json.loads(items),
        exist_items=ctx["exist_items"],
        attrs_by_id=ctx["attrs_by_id"],
        exclude_instance_ids=exclude,
    )


@when(parsers.re(r"我以 payload field_ids=(?P<fids>\[[^\]]*\]) 校验规则"))
def _validate_payload(ctx, fids):
    payload = UniqueRulePayload(field_ids=json.loads(fids))
    try:
        validate_unique_rule_payload(ctx["rule_ctx"], payload)
        ctx["error"] = None
    except BaseAppException as exc:
        ctx["error"] = exc


# ---------------------------------------------------------------------------
# 那么
# ---------------------------------------------------------------------------

@then(parsers.parse("冲突数量应当为 {n:d}"))
def _conflicts_count(ctx, n):
    assert len(ctx["conflicts"]) == n, ctx["conflicts"]


@then(parsers.parse('冲突消息应当包含 "{snippet}"'))
def _conflict_msg(ctx, snippet):
    assert any(snippet in c.message for c in ctx["conflicts"]), [c.message for c in ctx["conflicts"]]


@then(parsers.parse('应当抛出业务异常，消息包含 "{snippet}"'))
def _expect_error(ctx, snippet):
    assert ctx["error"] is not None, "expected BaseAppException, got none"
    assert snippet in str(ctx["error"]), ctx["error"]
