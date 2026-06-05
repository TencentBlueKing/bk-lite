"""CMDB 唯一规则显示增强与导入/导出辅助覆盖测试（无 DB）。

对照 spec/prd/CMDB·模型管理：属性列表的 unique_display_type 标记、
attr 导出补 unique_rule_order 列、validate_unique_rule_payload 边界、
_collect_existing_instance_conflicts 多场景。
"""

import pytest

from apps.cmdb.services.unique_rule import (
    ModelUniqueRule,
    UniqueRuleCheckContext,
    UniqueRulePayload,
    _collect_existing_instance_conflicts,
    apply_unique_rules_to_attr_export_rows,
    collect_unique_rule_conflicts,
    enrich_attrs_with_unique_display,
    raise_unique_rule_conflict_if_needed,
    validate_unique_rule_payload,
)
from apps.core.exceptions.base_app_exception import BaseAppException


# --------------------------------------------------------------------------
# enrich_attrs_with_unique_display
# --------------------------------------------------------------------------


def test_enrich_attrs_marks_joint_and_single():
    attrs = [
        {"attr_id": "a"},
        {"attr_id": "b"},
        {"attr_id": "c"},
        {"attr_id": "d", "is_only": True},
    ]
    rules = [
        ModelUniqueRule(rule_id="r1", order=1, field_ids=["a", "b"]),
        ModelUniqueRule(rule_id="r2", order=2, field_ids=["c"]),
    ]
    out = enrich_attrs_with_unique_display(attrs, rules, model_id="host")
    by_id = {x["attr_id"]: x for x in out}
    assert by_id["a"]["unique_display_type"] == "joint"
    assert by_id["b"]["unique_display_type"] == "joint"
    assert by_id["c"]["unique_display_type"] == "single"
    assert by_id["d"]["unique_display_type"] == "single"  # is_only legacy


def test_enrich_attrs_no_rules_no_only():
    out = enrich_attrs_with_unique_display([{"attr_id": "a"}], [])
    assert out[0]["unique_display_type"] == "none"


# --------------------------------------------------------------------------
# apply_unique_rules_to_attr_export_rows
# --------------------------------------------------------------------------


def test_apply_unique_rules_to_export_rows():
    rows = [{"attr_id": "a"}, {"attr_id": "b"}, {"attr_id": "c"}]
    rules = [
        ModelUniqueRule(rule_id="r1", order=1, field_ids=["a", "b"]),
        ModelUniqueRule(rule_id="r2", order=2, field_ids=["c"]),
    ]
    out = apply_unique_rules_to_attr_export_rows(rows, rules)
    assert {r["attr_id"]: r["unique_rule_order"] for r in out} == {"a": 1, "b": 1, "c": 2}


def test_apply_unique_rules_empty_rules():
    rows = [{"attr_id": "a"}]
    out = apply_unique_rules_to_attr_export_rows(rows, [])
    assert out[0]["unique_rule_order"] == ""


# --------------------------------------------------------------------------
# validate_unique_rule_payload 额外边界
# --------------------------------------------------------------------------


def _ctx(attrs_by_id, unique_rules=None):
    return UniqueRuleCheckContext(
        model_id="host", attrs_by_id=attrs_by_id, unique_rules=unique_rules or [],
        builtin_unique_fields={"inst_name"}, legacy_unique_fields=set(),
    )


def test_validate_payload_organization_rejected():
    ctx = _ctx({"organization": {"attr_id": "organization", "is_required": True, "attr_type": "list"}})
    with pytest.raises(BaseAppException):
        validate_unique_rule_payload(ctx, UniqueRulePayload(field_ids=["organization"]))


def test_validate_payload_max_count_exceeded():
    rules = [ModelUniqueRule(rule_id=f"r{i}", order=i, field_ids=[f"f{i}"]) for i in range(1, 4)]
    ctx = _ctx({"x": {"attr_id": "x", "is_required": True, "attr_type": "str"}}, unique_rules=rules)
    with pytest.raises(BaseAppException):
        validate_unique_rule_payload(ctx, UniqueRulePayload(field_ids=["x"]))


def test_validate_payload_occupied_by_other_rule():
    rules = [ModelUniqueRule(rule_id="r1", order=1, field_ids=["a"])]
    ctx = _ctx({"a": {"attr_id": "a", "is_required": True, "attr_type": "str"}}, unique_rules=rules)
    with pytest.raises(BaseAppException):
        validate_unique_rule_payload(ctx, UniqueRulePayload(field_ids=["a"]))


def test_validate_payload_editing_self_allowed():
    rules = [ModelUniqueRule(rule_id="r1", order=1, field_ids=["a"])]
    ctx = _ctx({"a": {"attr_id": "a", "is_required": True, "attr_type": "str"}}, unique_rules=rules)
    # editing r1 → 跳过自身占用 → 通过
    validate_unique_rule_payload(ctx, UniqueRulePayload(field_ids=["a"]), editing_rule_id="r1")


# --------------------------------------------------------------------------
# _collect_existing_instance_conflicts
# --------------------------------------------------------------------------


def test_collect_existing_conflicts_finds_match():
    rules = [ModelUniqueRule(rule_id="r1", order=1, field_ids=["ip"])]
    attrs_by_id = {"ip": {"attr_id": "ip", "attr_name": "IP", "attr_type": "str"}}
    exist = [{"_id": 1, "inst_name": "h1", "ip": "1.1.1.1"}, {"_id": 2, "inst_name": "h2", "ip": "2.2.2.2"}]

    # 与历史 h1 冲突
    conflicts = _collect_existing_instance_conflicts(
        rules, exist, attrs_by_id
    )
    # 无新数据时无冲突
    assert conflicts == []


def test_collect_conflicts_via_collect_helper():
    rules = [ModelUniqueRule(rule_id="r1", order=1, field_ids=["ip"])]
    attrs_by_id = {"ip": {"attr_id": "ip", "attr_name": "IP", "attr_type": "str"}}
    items = [{"_id": None, "ip": "1.1.1.1"}]  # 新增项
    existing = [{"_id": 100, "inst_name": "old", "ip": "1.1.1.1"}]
    conflicts = collect_unique_rule_conflicts(
        rules=rules, items=items, exist_items=existing, attrs_by_id=attrs_by_id
    )
    assert len(conflicts) == 1
    assert conflicts[0].field_ids == ["ip"]


def test_raise_unique_rule_conflict_helper():
    rules = [{"rule_id": "r1", "order": 1, "field_ids": ["ip"]}]
    attrs_by_id = {"ip": {"attr_id": "ip", "attr_name": "IP", "attr_type": "str"}}
    items = [{"_id": None, "ip": "1.1.1.1"}]
    existing = [{"_id": 100, "inst_name": "old", "ip": "1.1.1.1"}]
    with pytest.raises(BaseAppException):
        raise_unique_rule_conflict_if_needed(
            unique_rules=rules, items=items, exist_items=existing, attrs_by_id=attrs_by_id
        )
