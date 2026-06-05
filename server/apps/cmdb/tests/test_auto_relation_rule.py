"""CMDB 自动关联规则纯逻辑覆盖测试（不触图数据库）。

对照 spec/prd/CMDB·自动发现：自动关联规则解析/序列化/校验，匹配对去重与类型约束。
"""

import json

import pytest

from apps.cmdb.services import auto_relation_rule as ar
from apps.cmdb.services.auto_relation_rule import (
    AutoRelationMatchPair,
    AutoRelationRule,
    AutoRelationRuleSet,
)
from apps.core.exceptions.base_app_exception import BaseAppException


# --------------------------------------------------------------------------
# normalize helpers
# --------------------------------------------------------------------------


def test_normalize_field_id():
    assert ar._normalize_field_id("  ip  ") == "ip"
    assert ar._normalize_field_id(None) == ""


def test_normalize_matching_rule_default():
    assert ar._normalize_matching_rule("") == "exact"
    assert ar._normalize_matching_rule("contains") == "contains"


def test_normalize_matching_rule_invalid_raise():
    with pytest.raises(BaseAppException):
        ar._normalize_matching_rule("weird", raise_on_invalid=True)


# --------------------------------------------------------------------------
# _build_match_pairs
# --------------------------------------------------------------------------


def test_build_match_pairs_ok():
    pairs = ar._build_match_pairs([{"src_field_id": "a", "dst_field_id": "b"}])
    assert pairs[0].src_field_id == "a"
    assert pairs[0].matching_rule == "exact"


def test_build_match_pairs_dedup():
    raw = [{"src_field_id": "a", "dst_field_id": "b"}, {"src_field_id": "a", "dst_field_id": "b"}]
    assert len(ar._build_match_pairs(raw)) == 1


def test_build_match_pairs_skips_empty():
    assert ar._build_match_pairs([{"src_field_id": "", "dst_field_id": "b"}]) == []


def test_build_match_pairs_raise_on_invalid():
    with pytest.raises(BaseAppException):
        ar._build_match_pairs([{"src_field_id": "", "dst_field_id": "b"}], raise_on_invalid=True)


def test_build_match_pairs_non_dict_raise():
    with pytest.raises(BaseAppException):
        ar._build_match_pairs(["notadict"], raise_on_invalid=True)


# --------------------------------------------------------------------------
# canonicalize
# --------------------------------------------------------------------------


def test_canonicalize_compact_rule_group_list():
    out = ar._canonicalize_compact_rule_group([{"src_field_id": "a", "dst_field_id": "b"}])
    assert out["enabled"] is True
    assert "rule_id" in out


def test_canonicalize_compact_rule_group_dict():
    out = ar._canonicalize_compact_rule_group({"rule_id": "r1", "match_pairs": []})
    assert out["rule_id"] == "r1"


def test_canonicalize_payload_list():
    out = ar.canonicalize_auto_relation_rule_set_payload([{"src_field_id": "a", "dst_field_id": "b"}])
    assert "rules" in out


def test_canonicalize_rule_item_shorthand_matching_rule():
    item = {"matching_rule": "contains", "match_pairs": [{"src_field_id": "a", "dst_field_id": "b"}]}
    out = ar._canonicalize_rule_item_payload(item)
    assert out["match_pairs"][0]["matching_rule"] == "contains"
    assert "matching_rule" not in out


# --------------------------------------------------------------------------
# parse / dump round-trip
# --------------------------------------------------------------------------


def test_parse_rule_set_empty():
    assert ar.parse_auto_relation_rule_set(None) is None
    assert ar.parse_auto_relation_rule_set("") is None


def test_parse_rule_set_bad_json():
    assert ar.parse_auto_relation_rule_set("{bad") is None


def test_parse_rule_set_ok():
    raw = json.dumps({"version": 2, "rules": [
        {"rule_id": "r1", "enabled": True, "match_pairs": [{"src_field_id": "a", "dst_field_id": "b"}]}
    ]})
    rs = ar.parse_auto_relation_rule_set(raw)
    assert rs.version == 2
    assert rs.rules[0].rule_id == "r1"


def test_parse_rule_set_autogenerates_rule_id():
    # 紧凑 canonicalize 会为缺失 rule_id 的规则自动生成 ID
    raw = {"rules": [{"match_pairs": [{"src_field_id": "a", "dst_field_id": "b"}]}]}
    rs = ar.parse_auto_relation_rule_set(raw)
    assert rs is not None
    assert rs.rules[0].rule_id  # 自动生成


def test_parse_rule_set_empty_match_pairs_none():
    raw = {"rules": [{"rule_id": "r1", "match_pairs": []}]}
    assert ar.parse_auto_relation_rule_set(raw) is None


def test_parse_single_rule():
    raw = {"rules": [{"rule_id": "r1", "match_pairs": [{"src_field_id": "a", "dst_field_id": "b"}]}]}
    rule = ar.parse_auto_relation_rule(raw)
    assert rule.rule_id == "r1"


def test_dump_rule_set_roundtrip():
    rule = AutoRelationRule(rule_id="r1", enabled=True, match_pairs=[
        AutoRelationMatchPair(src_field_id="a", dst_field_id="b", matching_rule="exact")
    ])
    rs = AutoRelationRuleSet(version=2, rules=[rule])
    dumped = ar.dump_auto_relation_rule_set(rs)
    parsed = json.loads(dumped)
    assert parsed["rules"][0]["rule_id"] == "r1"


def test_dump_rule_set_empty():
    assert ar.dump_auto_relation_rule_set(None) == ""
    assert ar.dump_auto_relation_rule(None) == ""


def test_dump_compact_single_rule():
    rule = AutoRelationRule(rule_id="r1", enabled=True, match_pairs=[
        AutoRelationMatchPair(src_field_id="a", dst_field_id="b", matching_rule="exact")
    ])
    rs = AutoRelationRuleSet(version=2, rules=[rule])
    out = json.loads(ar.dump_auto_relation_rule_set_compact(rs))
    # 单规则 + exact → 紧凑列表，省略 matching_rule
    assert out == [{"src_field_id": "a", "dst_field_id": "b"}]


def test_dump_compact_disabled_rule():
    rule = AutoRelationRule(rule_id="r1", enabled=False, match_pairs=[
        AutoRelationMatchPair(src_field_id="a", dst_field_id="b", matching_rule="contains")
    ])
    rs = AutoRelationRuleSet(version=2, rules=[rule])
    out = json.loads(ar.dump_auto_relation_rule_set_compact(rs))
    assert out["enabled"] is False
    assert out["match_pairs"][0]["matching_rule"] == "contains"
