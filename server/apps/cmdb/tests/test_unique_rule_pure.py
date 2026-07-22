"""CMDB 模型唯一规则纯逻辑覆盖测试（不触图数据库）。

对照 spec/prd/CMDB·模型管理：唯一规则解析/序列化/重排、批次与现存实例冲突检测。
"""

import json

import pytest

from apps.cmdb.graph.falkordb import FalkorDBClient
from apps.cmdb.services import unique_rule as ur
from apps.cmdb.services.unique_rule import ModelUniqueRule
from apps.core.exceptions.base_app_exception import BaseAppException


# --------------------------------------------------------------------------
# value helpers
# --------------------------------------------------------------------------


def test_deduplicate_field_ids():
    assert ur._deduplicate_field_ids(["a", " a ", "b", "", "b"]) == ["a", "b"]


def test_normalize_compare_value():
    assert ur._normalize_compare_value({"b": 1, "a": 2}) == json.dumps({"b": 1, "a": 2}, ensure_ascii=False, sort_keys=True)
    assert ur._normalize_compare_value("x") == '"x"'


def test_format_value_for_message():
    assert ur._format_value_for_message([1, 2]) == "[1, 2]"
    assert ur._format_value_for_message("x") == "x"


def test_is_empty_unique_rule_value():
    assert ur._is_empty_unique_rule_value(None) is True
    assert ur._is_empty_unique_rule_value("  ") is True
    assert ur._is_empty_unique_rule_value("x") is False
    assert ur._is_empty_unique_rule_value(0) is False


def test_build_rule_signature_with_empty_returns_none():
    assert ur._build_rule_signature({"a": None, "b": "x"}, ["a", "b"]) is None


def test_build_rule_signature_ok():
    sig = ur._build_rule_signature({"a": "1", "b": "2"}, ["a", "b"])
    assert sig == ('"1"', '"2"')


def test_get_attr_name():
    assert ur._get_attr_name({"a": {"attr_name": "名称"}}, "a") == "名称"
    assert ur._get_attr_name({}, "x") == "x"


def test_collect_occupied_field_ids():
    rules = [
        ModelUniqueRule(rule_id="r1", order=1, field_ids=["a", "b"]),
        ModelUniqueRule(rule_id="r2", order=2, field_ids=["c"]),
    ]
    assert ur._collect_occupied_field_ids(rules) == {"a", "b", "c"}
    assert ur._collect_occupied_field_ids(rules, editing_rule_id="r1") == {"c"}


# --------------------------------------------------------------------------
# parse / dump / reorder
# --------------------------------------------------------------------------


def test_parse_unique_rules_empty():
    assert ur.parse_unique_rules(None) == []
    assert ur.parse_unique_rules("") == []
    assert ur.parse_unique_rules([]) == []


def test_parse_unique_rules_bad_json():
    assert ur.parse_unique_rules("{bad json") == []


def test_parse_unique_rules_non_list():
    assert ur.parse_unique_rules('{"a": 1}') == []


def test_parse_unique_rules_from_dicts():
    raw = json.dumps([{"rule_id": "r1", "order": 1, "field_ids": ["a", "a", "b"]}])
    rules = ur.parse_unique_rules(raw)
    assert len(rules) == 1
    assert rules[0].field_ids == ["a", "b"]  # 去重


def test_parse_unique_rules_skips_empty_field_ids():
    raw = [{"rule_id": "r1", "field_ids": []}]
    assert ur.parse_unique_rules(raw) == []


def test_parse_unique_rules_from_dataclass():
    rules = ur.parse_unique_rules([ModelUniqueRule(rule_id="r1", order=5, field_ids=["a"])])
    assert rules[0].order == 1  # reorder 后


def test_dump_unique_rules():
    rules = [ModelUniqueRule(rule_id="r1", order=3, field_ids=["a"])]
    dumped = ur.dump_unique_rules(rules)
    parsed = json.loads(dumped)
    assert parsed[0]["order"] == 1


def test_reorder_unique_rules():
    rules = [
        ModelUniqueRule(rule_id="r1", order=5, field_ids=["a"]),
        ModelUniqueRule(rule_id="r2", order=9, field_ids=["b"]),
    ]
    out = ur.reorder_unique_rules(rules)
    assert [r.order for r in out] == [1, 2]


def test_reorder_empty():
    assert ur.reorder_unique_rules([]) == []


# --------------------------------------------------------------------------
# collect_unique_rule_conflicts
# --------------------------------------------------------------------------


def test_collect_conflicts_with_existing():
    rules = [ModelUniqueRule(rule_id="r1", order=1, field_ids=["name"])]
    items = [{"name": "host1", "_id": 10}]
    exist_items = [{"name": "host1", "_id": 1, "inst_name": "existing"}]
    attrs_by_id = {"name": {"attr_name": "名称"}}
    conflicts = ur.collect_unique_rule_conflicts(rules, items, exist_items, attrs_by_id)
    assert len(conflicts) == 1
    assert "现有实例冲突" in conflicts[0].message


def test_collect_conflicts_within_batch():
    rules = [ModelUniqueRule(rule_id="r1", order=1, field_ids=["name"])]
    items = [{"name": "dup"}, {"name": "dup"}]
    conflicts = ur.collect_unique_rule_conflicts(rules, items, [], {"name": {"attr_name": "名称"}})
    assert len(conflicts) == 1
    assert "本批次" in conflicts[0].message


def test_collect_conflicts_none():
    rules = [ModelUniqueRule(rule_id="r1", order=1, field_ids=["name"])]
    items = [{"name": "a"}, {"name": "b"}]
    assert ur.collect_unique_rule_conflicts(rules, items, [], {"name": {}}) == []


def test_collect_conflicts_excludes_instance():
    rules = [ModelUniqueRule(rule_id="r1", order=1, field_ids=["name"])]
    items = [{"name": "host1", "_id": 1}]
    exist_items = [{"name": "host1", "_id": 1}]
    # 排除自身 → 无冲突
    conflicts = ur.collect_unique_rule_conflicts(rules, items, exist_items, {"name": {}}, exclude_instance_ids={1})
    assert conflicts == []


@pytest.mark.parametrize("value", [None, "", 0, False])
def test_instance_single_unique_precheck_matches_legacy_falsy_skip(value):
    item = {"serial": value}
    existing = [{"_id": 1, "serial": value}]
    check_attr_map = {
        "is_only": {"serial": "序列号"},
        "unique_rules": [],
        "attrs_by_id": {"serial": {"attr_id": "serial", "attr_name": "序列号"}},
    }

    FalkorDBClient.check_unique_attr(item, check_attr_map["is_only"], existing)
    assert ur.collect_instance_unique_conflicts(check_attr_map, [item], existing) == []


def test_instance_single_unique_precheck_matches_legacy_whitespace_conflict():
    item = {"serial": "   "}
    existing = [{"_id": 1, "serial": "   "}]
    check_attr_map = {
        "is_only": {"serial": "序列号"},
        "unique_rules": [],
        "attrs_by_id": {"serial": {"attr_id": "serial", "attr_name": "序列号"}},
    }

    with pytest.raises(BaseAppException):
        FalkorDBClient.check_unique_attr(item, check_attr_map["is_only"], existing)
    assert len(ur.collect_instance_unique_conflicts(check_attr_map, [item], existing)) == 1


def test_raise_unique_rule_conflict_raises():
    rules = [{"rule_id": "r1", "order": 1, "field_ids": ["name"]}]
    items = [{"name": "host1"}]
    exist_items = [{"name": "host1", "_id": 1}]
    with pytest.raises(BaseAppException):
        ur.raise_unique_rule_conflict_if_needed(rules, items, exist_items, {"name": {}})


def test_raise_unique_rule_conflict_noop():
    ur.raise_unique_rule_conflict_if_needed([], [{"name": "a"}], [], {})


# --------------------------------------------------------------------------
# _evaluate_field_selectability
# --------------------------------------------------------------------------


def test_evaluate_field_selectability_inst_name():
    ok, reason = ur._evaluate_field_selectability("inst_name", {}, "str", set())
    assert ok is False and "内置" in reason


def test_evaluate_field_selectability_organization():
    ok, reason = ur._evaluate_field_selectability("organization", {}, "organization", set())
    assert ok is False


def test_evaluate_field_selectability_display_field():
    ok, reason = ur._evaluate_field_selectability("x", {"is_display_field": True, "is_required": True}, "str", set())
    assert ok is False


def test_evaluate_field_selectability_not_required():
    ok, reason = ur._evaluate_field_selectability("x", {"is_required": False}, "str", set())
    assert ok is False and "必填" in reason


def test_evaluate_field_selectability_unsupported_type():
    ok, reason = ur._evaluate_field_selectability("x", {"is_required": True}, "enum", set())
    assert ok is False


def test_evaluate_field_selectability_occupied():
    ok, reason = ur._evaluate_field_selectability("x", {"is_required": True}, "str", {"x"})
    assert ok is False and "已被" in reason


def test_evaluate_field_selectability_ok():
    ok, reason = ur._evaluate_field_selectability("x", {"is_required": True}, "str", set())
    assert ok is True and reason == ""


# --------------------------------------------------------------------------
# validate_unique_rule_payload
# --------------------------------------------------------------------------


def _ctx(attrs_by_id, unique_rules=None):
    from apps.cmdb.services.unique_rule import UniqueRuleCheckContext

    return UniqueRuleCheckContext(
        model_id="host",
        attrs_by_id=attrs_by_id,
        unique_rules=unique_rules or [],
    )


def test_validate_payload_empty_fields():
    from apps.cmdb.services.unique_rule import UniqueRulePayload

    ctx = _ctx({})
    with pytest.raises(BaseAppException):
        ur.validate_unique_rule_payload(ctx, UniqueRulePayload(field_ids=[]))


def test_validate_payload_duplicate_fields():
    from apps.cmdb.services.unique_rule import UniqueRulePayload

    ctx = _ctx({"a": {"is_required": True, "attr_type": "str"}})
    with pytest.raises(BaseAppException):
        ur.validate_unique_rule_payload(ctx, UniqueRulePayload(field_ids=["a", "a"]))


def test_validate_payload_field_not_exist():
    from apps.cmdb.services.unique_rule import UniqueRulePayload

    ctx = _ctx({"a": {"is_required": True, "attr_type": "str"}})
    with pytest.raises(BaseAppException):
        ur.validate_unique_rule_payload(ctx, UniqueRulePayload(field_ids=["missing"]))


def test_validate_payload_inst_name_rejected():
    from apps.cmdb.services.unique_rule import UniqueRulePayload

    ctx = _ctx({"inst_name": {"is_required": True, "attr_type": "str"}})
    with pytest.raises(BaseAppException):
        ur.validate_unique_rule_payload(ctx, UniqueRulePayload(field_ids=["inst_name"]))


def test_validate_payload_not_required():
    from apps.cmdb.services.unique_rule import UniqueRulePayload

    ctx = _ctx({"a": {"is_required": False, "attr_type": "str", "attr_name": "A"}})
    with pytest.raises(BaseAppException):
        ur.validate_unique_rule_payload(ctx, UniqueRulePayload(field_ids=["a"]))


def test_validate_payload_unsupported_type():
    from apps.cmdb.services.unique_rule import UniqueRulePayload

    ctx = _ctx({"a": {"is_required": True, "attr_type": "enum", "attr_name": "A"}})
    with pytest.raises(BaseAppException):
        ur.validate_unique_rule_payload(ctx, UniqueRulePayload(field_ids=["a"]))


def test_validate_payload_ok():
    from apps.cmdb.services.unique_rule import UniqueRulePayload

    ctx = _ctx({"a": {"is_required": True, "attr_type": "str", "attr_name": "A"}})
    ur.validate_unique_rule_payload(ctx, UniqueRulePayload(field_ids=["a"]))


# --------------------------------------------------------------------------
# build_unique_rule_context / list_unique_rules（patch search_model_info）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_build_unique_rule_context(monkeypatch):
    attrs = [
        {"attr_id": "inst_name", "attr_name": "名称", "attr_type": "str", "is_only": True},
        {"attr_id": "sn", "attr_name": "序列号", "attr_type": "str", "is_only": True, "is_required": True},
    ]
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda model_id: {"model_id": "host", "attrs": json.dumps(attrs), "unique_rules": "[]"},
    )
    ctx = ur.build_unique_rule_context("host")
    assert "sn" in ctx.attrs_by_id
    assert "sn" in ctx.legacy_unique_fields  # is_only 且非 inst_name


@pytest.mark.django_db
def test_build_unique_rule_context_model_missing(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_info", lambda model_id: {})
    with pytest.raises(BaseAppException):
        ur.build_unique_rule_context("nope")


@pytest.mark.django_db
def test_list_unique_rules(monkeypatch):
    attrs = [{"attr_id": "sn", "attr_name": "序列号", "attr_type": "str", "is_required": True}]
    rules = json.dumps([{"rule_id": "r1", "order": 1, "field_ids": ["sn"]}])
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda model_id: {"model_id": "host", "attrs": json.dumps(attrs), "unique_rules": rules},
    )
    out = ur.list_unique_rules("host")
    assert out[0]["field_names"] == ["序列号"]


@pytest.mark.django_db
def test_list_unique_rule_candidate_fields(monkeypatch):
    attrs = [
        {"attr_id": "sn", "attr_name": "序列号", "attr_type": "str", "is_required": True},
        {"attr_id": "inst_name", "attr_name": "名称", "attr_type": "str"},
    ]
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda model_id: {"model_id": "host", "attrs": json.dumps(attrs), "unique_rules": "[]"},
    )
    out = ur.list_unique_rule_candidate_fields("host")
    by_id = {f.attr_id: f for f in out}
    assert by_id["sn"].selectable is True
    assert by_id["inst_name"].selectable is False
