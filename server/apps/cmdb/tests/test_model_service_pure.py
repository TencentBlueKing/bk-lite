"""CMDB ModelManage 纯逻辑方法覆盖测试（不触图数据库）。

对照 specs/capabilities/legacy-prd-cmdb-模型管理.md：属性默认值归一、tag/enum 字段约束校验、运行时枚举选项解析。
"""

import pytest

from apps.cmdb.services.model import ModelManage
from apps.core.exceptions.base_app_exception import BaseAppException


# --------------------------------------------------------------------------
# _normalize_default_value
# --------------------------------------------------------------------------


def test_normalize_default_value_empty():
    assert ModelManage._normalize_default_value(None) == []
    assert ModelManage._normalize_default_value("") == []


def test_normalize_default_value_scalar():
    assert ModelManage._normalize_default_value("a") == ["a"]


def test_normalize_default_value_dedup():
    assert ModelManage._normalize_default_value(["a", " a ", "b", ""]) == ["a", "b"]


# --------------------------------------------------------------------------
# _normalize_attr_constraints
# --------------------------------------------------------------------------


def test_normalize_attr_constraints_defaults():
    out = ModelManage._normalize_attr_constraints([{"attr_id": "name", "attr_type": "str"}])
    item = out[0]
    assert item["is_only"] is False
    assert item["is_required"] is False
    assert item["editable"] is True
    assert item["option"] == {}
    assert item["default_value"] == []


# --------------------------------------------------------------------------
# _is_tag_attr / validate_tag_attr_definition
# --------------------------------------------------------------------------


def test_is_tag_attr():
    assert ModelManage._is_tag_attr({"attr_type": "tag"}) is True
    assert ModelManage._is_tag_attr({"attr_id": "tag"}) is True
    assert ModelManage._is_tag_attr({"attr_type": "str", "attr_id": "name"}) is False


def test_validate_tag_attr_definition_wrong_id():
    with pytest.raises(BaseAppException):
        ModelManage.validate_tag_attr_definition([], {"attr_type": "tag", "attr_id": "mytag"})


def test_validate_tag_attr_definition_wrong_type():
    with pytest.raises(BaseAppException):
        ModelManage.validate_tag_attr_definition([], {"attr_type": "str", "attr_id": "tag"})


def test_validate_tag_attr_definition_duplicate():
    existing = [{"attr_type": "tag", "attr_id": "tag"}]
    with pytest.raises(BaseAppException):
        ModelManage.validate_tag_attr_definition(existing, {"attr_type": "tag", "attr_id": "tag"})


def test_validate_tag_attr_definition_non_tag_ok():
    ModelManage.validate_tag_attr_definition([], {"attr_type": "str", "attr_id": "name"})


# --------------------------------------------------------------------------
# normalize_tag_field_option
# --------------------------------------------------------------------------


def test_normalize_tag_field_option_list():
    out = ModelManage.normalize_tag_field_option([{"key": "env", "value": "prod"}])
    assert out["mode"] == "free"
    assert out["options"][0]["key"] == "env"


# --------------------------------------------------------------------------
# _validate_attr_id / _validate_model_id
# --------------------------------------------------------------------------


def test_validate_attr_id_ok():
    ModelManage._validate_attr_id("server_ip")


def test_validate_attr_id_bad():
    with pytest.raises(BaseAppException):
        ModelManage._validate_attr_id("1bad!")


def test_validate_model_id_bad():
    with pytest.raises(BaseAppException):
        ModelManage._validate_model_id("")


# --------------------------------------------------------------------------
# normalize_enum_public_binding
# --------------------------------------------------------------------------


def test_normalize_enum_public_binding_non_enum():
    attr = {"attr_type": "str"}
    assert ModelManage.normalize_enum_public_binding(attr) is attr


def test_normalize_enum_public_binding_custom():
    attr = {"attr_type": "enum", "option": {"enum_rule_type": "custom", "option": [{"id": "a"}]}}
    out = ModelManage.normalize_enum_public_binding(attr)
    assert out["enum_rule_type"] == "custom"
    assert out["public_library_id"] is None


# --------------------------------------------------------------------------
# validate_enum_rule_immutable / select_mode
# --------------------------------------------------------------------------


def test_validate_enum_rule_immutable_change_raises():
    with pytest.raises(BaseAppException):
        ModelManage.validate_enum_rule_immutable(
            {"attr_type": "enum", "enum_rule_type": "custom"},
            {"attr_type": "enum", "enum_rule_type": "public_library"},
        )


def test_validate_enum_rule_immutable_same_ok():
    ModelManage.validate_enum_rule_immutable(
        {"attr_type": "enum", "enum_rule_type": "custom"},
        {"attr_type": "enum", "enum_rule_type": "custom"},
    )


def test_validate_enum_rule_immutable_non_enum():
    ModelManage.validate_enum_rule_immutable({"attr_type": "str"}, {"attr_type": "str"})


def test_ensure_enum_select_mode_default():
    out = ModelManage.ensure_enum_select_mode({"attr_type": "enum"})
    assert out["enum_select_mode"] == "single"


def test_ensure_enum_select_mode_non_enum():
    attr = {"attr_type": "str"}
    assert ModelManage.ensure_enum_select_mode(attr) is attr


def test_validate_enum_select_mode_immutable_change_raises():
    with pytest.raises(BaseAppException):
        ModelManage.validate_enum_select_mode_immutable(
            {"attr_type": "enum", "enum_select_mode": "single"},
            {"attr_type": "enum", "enum_select_mode": "multiple"},
        )


# --------------------------------------------------------------------------
# resolve_runtime_enum_options
# --------------------------------------------------------------------------


def test_resolve_runtime_enum_options_non_enum():
    assert ModelManage.resolve_runtime_enum_options({"attr_type": "str"}) == []


def test_resolve_runtime_enum_options_custom():
    attr = {"attr_type": "enum", "enum_rule_type": "custom", "option": [{"id": "a"}]}
    assert ModelManage.resolve_runtime_enum_options(attr) == [{"id": "a"}]


def test_resolve_runtime_enum_options_public_no_id_fallback():
    attr = {"attr_type": "enum", "enum_rule_type": "public_library", "public_library_id": "", "option": [{"id": "x"}]}
    assert ModelManage.resolve_runtime_enum_options(attr) == [{"id": "x"}]


# --------------------------------------------------------------------------
# sanitize_attr_default_value
# --------------------------------------------------------------------------


def test_sanitize_attr_default_value_non_enum():
    out = ModelManage.sanitize_attr_default_value({"attr_type": "str", "default_value": ["a", "a", "b"]})
    assert out["default_value"] == ["a", "b"]


def test_sanitize_attr_default_value_enum_prunes_invalid():
    attr = {
        "attr_type": "enum", "enum_rule_type": "custom",
        "option": [{"id": "a"}, {"id": "b"}], "enum_select_mode": "multiple",
        "default_value": ["a", "z"],
    }
    out = ModelManage.sanitize_attr_default_value(attr)
    assert out["default_value"] == ["a"]


def test_sanitize_attr_default_value_enum_single_truncates():
    attr = {
        "attr_type": "enum", "enum_rule_type": "custom",
        "option": [{"id": "a"}, {"id": "b"}], "enum_select_mode": "single",
        "default_value": ["a", "b"],
    }
    out = ModelManage.sanitize_attr_default_value(attr)
    assert out["default_value"] == ["a"]


# --------------------------------------------------------------------------
# parse_attrs / get_organization_option
# --------------------------------------------------------------------------


def test_parse_attrs():
    assert ModelManage.parse_attrs('[{"attr_id": "name"}]') == [{"attr_id": "name"}]


def test_get_organization_option():
    items = [{"id": 1, "name": "总部", "subGroups": [{"id": 2, "name": "研发", "subGroups": []}]}]
    result = []
    ModelManage.get_organization_option(items, result)
    ids = {r["id"] for r in result}
    assert 1 in ids and 2 in ids
