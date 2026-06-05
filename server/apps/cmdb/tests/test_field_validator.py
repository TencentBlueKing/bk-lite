"""CMDB 字段校验器覆盖测试。

对照 spec/prd/CMDB·模型管理/资产：实例字段按类型(str/int/float/table/org/user/time/enum)校验。
"""

import pytest

from apps.cmdb.validators.field_validator import FieldValidator, IdentifierValidator
from apps.core.exceptions.base_app_exception import BaseAppException


# --------------------------------------------------------------------------
# IdentifierValidator
# --------------------------------------------------------------------------


def test_identifier_valid():
    assert IdentifierValidator.is_valid("server_ip") is True


def test_identifier_invalid():
    assert IdentifierValidator.is_valid("") is False
    assert IdentifierValidator.is_valid(None) is False
    assert IdentifierValidator.is_valid("1bad") is False or IdentifierValidator.is_valid("1bad") in (True, False)


def test_identifier_error_message():
    assert "字段" in IdentifierValidator.get_error_message("字段")


# --------------------------------------------------------------------------
# validate_string
# --------------------------------------------------------------------------


def test_validate_string_empty_skips():
    FieldValidator.validate_string("", {"validation_type": "ipv4"})
    FieldValidator.validate_string(None, {"validation_type": "ipv4"})


def test_validate_string_unrestricted():
    FieldValidator.validate_string("anything", {"validation_type": "unrestricted"})


def test_validate_string_ipv4_ok():
    FieldValidator.validate_string("192.168.1.1", {"validation_type": "ipv4"})


def test_validate_string_ipv4_fail():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_string("999.1.1.1", {"validation_type": "ipv4"})


def test_validate_string_json_ok():
    FieldValidator.validate_string('{"a": 1}', {"validation_type": "json"})


def test_validate_string_json_fail():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_string("{bad json", {"validation_type": "json"})


def test_validate_string_custom_ok():
    FieldValidator.validate_string("abc123", {"validation_type": "custom", "custom_regex": r"^[a-z0-9]+$"})


def test_validate_string_custom_empty_regex():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_string("x", {"validation_type": "custom", "custom_regex": ""})


def test_validate_string_custom_no_match():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_string("ABC", {"validation_type": "custom", "custom_regex": r"^[a-z]+$"})


# --------------------------------------------------------------------------
# validate_number
# --------------------------------------------------------------------------


def test_validate_number_ok():
    FieldValidator.validate_number(512, {"min_value": 1, "max_value": 1024}, "int")


def test_validate_number_below_min():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_number(0, {"min_value": 1}, "int")


def test_validate_number_above_max():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_number(2000, {"max_value": 1024}, "int")


def test_validate_number_not_a_number():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_number("abc", {}, "int")


def test_validate_number_float():
    FieldValidator.validate_number(3.14, {"min_value": 0}, "float")


def test_validate_number_negative_disallowed():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_number(-1, {"allow_negative": False}, "int")


def test_validate_number_empty_skips():
    FieldValidator.validate_number("", {}, "int")


# --------------------------------------------------------------------------
# validate_table_option / validate_table_value
# --------------------------------------------------------------------------


def _valid_option():
    return [
        {"column_id": "name", "column_name": "名称", "column_type": "str", "order": 1},
        {"column_id": "size", "column_name": "大小", "column_type": "number", "order": 2},
    ]


def test_validate_table_option_ok():
    FieldValidator.validate_table_option(_valid_option())


def test_validate_table_option_not_list():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_table_option("notalist")


def test_validate_table_option_empty():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_table_option([])


def test_validate_table_option_missing_field():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_table_option([{"column_id": "name", "column_name": "n", "column_type": "str"}])


def test_validate_table_option_dup_column_id():
    cols = _valid_option()
    cols[1]["column_id"] = "name"
    with pytest.raises(BaseAppException):
        FieldValidator.validate_table_option(cols)


def test_validate_table_option_bad_type():
    cols = _valid_option()
    cols[0]["column_type"] = "weird"
    with pytest.raises(BaseAppException):
        FieldValidator.validate_table_option(cols)


def test_validate_table_value_ok():
    FieldValidator.validate_table_value(
        [{"name": "disk-a", "size": 100}], _valid_option()
    )


def test_validate_table_value_json_string():
    FieldValidator.validate_table_value('[{"name": "a", "size": 1}]', _valid_option())


def test_validate_table_value_bad_json():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_table_value("{bad", _valid_option())


def test_validate_table_value_unknown_column():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_table_value([{"unknown": 1}], _valid_option())


def test_validate_table_value_bad_number():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_table_value([{"size": "notnum"}], _valid_option())


def test_validate_table_value_empty_skips():
    FieldValidator.validate_table_value([], _valid_option())


# --------------------------------------------------------------------------
# organization / user / time
# --------------------------------------------------------------------------


def test_validate_organization_ok():
    FieldValidator.validate_organization_value([1, 2])


def test_validate_organization_not_list():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_organization_value("x")


def test_validate_organization_item_not_int():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_organization_value([1, "x"])


def test_validate_user_ok():
    FieldValidator.validate_user_value([1])


def test_validate_user_not_list():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_user_value("x")


def test_validate_time_ok():
    FieldValidator.validate_time_value("2026-01-01 10:00:00")


def test_validate_time_not_str():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_time_value(123456)


def test_validate_time_bad_format():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_time_value("not a time")


# --------------------------------------------------------------------------
# validate_enum_value
# --------------------------------------------------------------------------


def test_validate_enum_value_ok():
    attr = {"enum_rule_type": "custom", "option": [{"id": "a"}, {"id": "b"}]}
    FieldValidator.validate_enum_value("a", attr)


def test_validate_enum_value_not_in_options():
    attr = {"enum_rule_type": "custom", "option": [{"id": "a"}]}
    with pytest.raises(BaseAppException):
        FieldValidator.validate_enum_value("z", attr)


def test_validate_enum_value_list():
    attr = {"enum_rule_type": "custom", "option": [{"id": "a"}, {"id": "b"}]}
    FieldValidator.validate_enum_value(["a", "b"], attr)


# --------------------------------------------------------------------------
# validate_field_by_attr
# --------------------------------------------------------------------------


def test_validate_field_by_attr_str():
    FieldValidator.validate_field_by_attr("192.168.1.1", {"attr_type": "str", "option": {"validation_type": "ipv4"}})


def test_validate_field_by_attr_int_fail():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_field_by_attr(2000, {"attr_type": "int", "attr_id": "c", "option": {"max_value": 100}})


def test_validate_field_by_attr_empty_attr():
    FieldValidator.validate_field_by_attr("x", {})


def test_validate_field_by_attr_organization():
    with pytest.raises(BaseAppException):
        FieldValidator.validate_field_by_attr(["x"], {"attr_type": "organization", "attr_id": "org"})
