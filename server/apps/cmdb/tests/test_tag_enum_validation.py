"""CMDB 标签/枚举字段归一与校验覆盖测试。

对照 spec/prd/CMDB·模型管理：tag 字段 free/strict 模式校验，enum 单选/多选校验。
"""

import pytest

from apps.cmdb.validators.field_validator import (
    normalize_enum_values,
    normalize_tag_field_option,
    normalize_tag_input_values,
    validate_enum_values,
    validate_tag_values,
)
from apps.core.exceptions.base_app_exception import BaseAppException


# --------------------------------------------------------------------------
# normalize_tag_field_option
# --------------------------------------------------------------------------


def test_normalize_tag_option_none():
    cfg = normalize_tag_field_option(None)
    assert cfg.mode == "free"
    assert cfg.options == []


def test_normalize_tag_option_not_dict():
    with pytest.raises(BaseAppException):
        normalize_tag_field_option("x")


def test_normalize_tag_option_bad_mode():
    with pytest.raises(BaseAppException):
        normalize_tag_field_option({"mode": "weird"})


def test_normalize_tag_option_with_options():
    cfg = normalize_tag_field_option({"mode": "strict", "options": [{"key": "env", "value": "prod"}]})
    assert cfg.mode == "strict"
    assert cfg.options[0].key == "env"


def test_normalize_tag_option_dedup():
    cfg = normalize_tag_field_option({"options": [{"key": "a", "value": "1"}, {"key": "a", "value": "1"}]})
    assert len(cfg.options) == 1


def test_normalize_tag_option_invalid_value():
    with pytest.raises(BaseAppException):
        normalize_tag_field_option({"options": [{"key": "a", "value": "has space"}]})


# --------------------------------------------------------------------------
# normalize_tag_input_values
# --------------------------------------------------------------------------


def test_normalize_tag_input_empty():
    assert normalize_tag_input_values(None) == []
    assert normalize_tag_input_values("") == []


def test_normalize_tag_input_list():
    assert normalize_tag_input_values(["a:1", " b:2 "]) == ["a:1", "b:2"]


def test_normalize_tag_input_string():
    assert normalize_tag_input_values("a:1,b:2") == ["a:1", "b:2"]


def test_normalize_tag_input_bad_type():
    with pytest.raises(BaseAppException):
        normalize_tag_input_values(123)


# --------------------------------------------------------------------------
# validate_tag_values
# --------------------------------------------------------------------------


def test_validate_tag_values_free_ok():
    cfg = normalize_tag_field_option({"mode": "free"})
    result = validate_tag_values(["env:prod"], cfg)
    assert not result.errors
    assert result.normalized_values[0].raw == "env:prod"


def test_validate_tag_values_bad_format():
    cfg = normalize_tag_field_option({"mode": "free"})
    result = validate_tag_values(["noseparator"], cfg)
    assert result.errors


def test_validate_tag_values_strict_not_in_candidates():
    cfg = normalize_tag_field_option({"mode": "strict", "options": [{"key": "env", "value": "prod"}]})
    result = validate_tag_values(["env:dev"], cfg)
    assert result.errors


def test_validate_tag_values_strict_ok():
    cfg = normalize_tag_field_option({"mode": "strict", "options": [{"key": "env", "value": "prod"}]})
    result = validate_tag_values(["env:prod"], cfg)
    assert not result.errors


def test_validate_tag_values_not_list():
    cfg = normalize_tag_field_option(None)
    result = validate_tag_values("notalist", cfg)
    assert result.errors


def test_validate_tag_values_dedup():
    cfg = normalize_tag_field_option({"mode": "free"})
    result = validate_tag_values(["env:prod", "env:prod"], cfg)
    assert len(result.normalized_values) == 1


# --------------------------------------------------------------------------
# normalize_enum_values / validate_enum_values
# --------------------------------------------------------------------------


def test_normalize_enum_values_variants():
    assert normalize_enum_values(None) == []
    assert normalize_enum_values(["a", " b "]) == ["a", "b"]
    assert normalize_enum_values("a,b") == ["a", "b"]


def test_validate_enum_values_required_empty():
    with pytest.raises(BaseAppException):
        validate_enum_values([], "multiple", {"a"}, required=True)


def test_validate_enum_values_single_too_many():
    with pytest.raises(BaseAppException):
        validate_enum_values(["a", "b"], "single", {"a", "b"}, required=False)


def test_validate_enum_values_invalid_option():
    with pytest.raises(BaseAppException):
        validate_enum_values(["z"], "multiple", {"a", "b"}, required=False)


def test_validate_enum_values_ok():
    validate_enum_values(["a"], "multiple", {"a", "b"}, required=True)
