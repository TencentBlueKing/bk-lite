"""CMDB 自动关联规则 validate/build_response 覆盖测试。

对照 spec/prd/CMDB·模型关联：自动关联规则字段类型一致性、不支持类型校验、
匹配规则字符串约束、rule_id 重复校验、规则响应构建。
"""

import pytest

from apps.cmdb.services.auto_relation_rule import (
    build_auto_relation_rule_response,
    parse_auto_relation_rule,
    validate_auto_relation_rule_payload,
    validate_auto_relation_rule_set_payload,
)
from apps.core.exceptions.base_app_exception import BaseAppException


_STR_ATTRS = [
    {"attr_id": "ip", "attr_type": "str"},
    {"attr_id": "name", "attr_type": "str"},
]


# --------------------------------------------------------------------------
# validate_auto_relation_rule_payload
# --------------------------------------------------------------------------


def test_validate_payload_not_dict():
    with pytest.raises(BaseAppException):
        validate_auto_relation_rule_payload({}, _STR_ATTRS, _STR_ATTRS, "bad")


def test_validate_payload_empty_match_pairs():
    with pytest.raises(BaseAppException):
        validate_auto_relation_rule_payload({}, _STR_ATTRS, _STR_ATTRS, {"match_pairs": []})


def test_validate_payload_src_field_missing():
    payload = {"match_pairs": [{"src_field_id": "ghost", "dst_field_id": "ip"}]}
    with pytest.raises(BaseAppException):
        validate_auto_relation_rule_payload({}, _STR_ATTRS, _STR_ATTRS, payload)


def test_validate_payload_dst_field_missing():
    payload = {"match_pairs": [{"src_field_id": "ip", "dst_field_id": "ghost"}]}
    with pytest.raises(BaseAppException):
        validate_auto_relation_rule_payload({}, _STR_ATTRS, _STR_ATTRS, payload)


def test_validate_payload_type_mismatch():
    dst = [{"attr_id": "ip", "attr_type": "int"}]
    payload = {"match_pairs": [{"src_field_id": "ip", "dst_field_id": "ip"}]}
    with pytest.raises(BaseAppException):
        validate_auto_relation_rule_payload({}, _STR_ATTRS, dst, payload)


def test_validate_payload_unsupported_type():
    src = [{"attr_id": "f", "attr_type": "table"}]
    dst = [{"attr_id": "f", "attr_type": "table"}]
    payload = {"match_pairs": [{"src_field_id": "f", "dst_field_id": "f"}]}
    with pytest.raises(BaseAppException):
        validate_auto_relation_rule_payload({}, src, dst, payload)


def test_validate_payload_ok():
    payload = {
        "match_pairs": [
            {"src_field_id": "ip", "dst_field_id": "ip", "matching_rule": "exact"}
        ]
    }
    rule = validate_auto_relation_rule_payload({}, _STR_ATTRS, _STR_ATTRS, payload)
    assert rule.rule_id  # auto-assigned
    assert len(rule.match_pairs) == 1


def test_validate_payload_skips_display_field():
    src = [
        {"attr_id": "ip", "attr_type": "str"},
        {"attr_id": "ip_display", "attr_type": "str", "is_display_field": True},
    ]
    payload = {"match_pairs": [{"src_field_id": "ip_display", "dst_field_id": "ip"}]}
    with pytest.raises(BaseAppException):  # display field 被剔除 → 找不到
        validate_auto_relation_rule_payload({}, src, _STR_ATTRS, payload)


# --------------------------------------------------------------------------
# validate_auto_relation_rule_set_payload
# --------------------------------------------------------------------------


def test_validate_set_not_dict():
    with pytest.raises(BaseAppException):
        validate_auto_relation_rule_set_payload({}, _STR_ATTRS, _STR_ATTRS, "x")


def test_validate_set_empty_rules():
    with pytest.raises(BaseAppException):
        validate_auto_relation_rule_set_payload({}, _STR_ATTRS, _STR_ATTRS, {"rules": []})


def test_validate_set_dup_rule_id():
    payload = {
        "rules": [
            {"rule_id": "r1", "match_pairs": [{"src_field_id": "ip", "dst_field_id": "ip"}]},
            {"rule_id": "r1", "match_pairs": [{"src_field_id": "name", "dst_field_id": "name"}]},
        ]
    }
    with pytest.raises(BaseAppException):
        validate_auto_relation_rule_set_payload({}, _STR_ATTRS, _STR_ATTRS, payload)


def test_validate_set_ok():
    payload = {
        "rules": [
            {"rule_id": "r1", "match_pairs": [{"src_field_id": "ip", "dst_field_id": "ip"}]},
            {"rule_id": "r2", "match_pairs": [{"src_field_id": "name", "dst_field_id": "name"}]},
        ]
    }
    rule_set = validate_auto_relation_rule_set_payload({}, _STR_ATTRS, _STR_ATTRS, payload)
    assert len(rule_set.rules) == 2


# --------------------------------------------------------------------------
# build_auto_relation_rule_response / parse_auto_relation_rule
# --------------------------------------------------------------------------


def test_build_response_with_rule():
    payload = {
        "match_pairs": [{"src_field_id": "ip", "dst_field_id": "ip", "matching_rule": "exact"}],
        "rule_id": "r1",
    }
    rule = validate_auto_relation_rule_payload({}, _STR_ATTRS, _STR_ATTRS, payload)
    assoc = {"model_asst_id": "a_b_c"}
    out = build_auto_relation_rule_response(assoc, rule)
    assert out["rule_id"] == "r1"
    assert out["model_asst_id"] == "a_b_c"


def test_build_response_none_rule():
    out = build_auto_relation_rule_response({"model_asst_id": "x"}, None)
    assert out["rule_id"] == ""


def test_parse_auto_relation_rule_none():
    assert parse_auto_relation_rule(None) is None
    assert parse_auto_relation_rule("") is None


def test_parse_auto_relation_rule_ok():
    rule = parse_auto_relation_rule({
        "rules": [{
            "rule_id": "r1", "enabled": True,
            "match_pairs": [{"src_field_id": "a", "dst_field_id": "b", "matching_rule": "exact"}],
        }]
    })
    assert rule is not None
    assert rule.rule_id == "r1"
