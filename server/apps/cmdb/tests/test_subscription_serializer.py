"""CMDB 订阅规则序列化器校验覆盖测试。

对照 spec/prd/CMDB：订阅规则按筛选类型/触发类型/接收对象/渠道做参数校验。
"""

from types import SimpleNamespace

import pytest
from rest_framework import serializers

from apps.cmdb.serializers.subscription import SubscriptionRuleSerializer


def _ser(initial_data=None, instance=None):
    s = SubscriptionRuleSerializer.__new__(SubscriptionRuleSerializer)
    s.initial_data = initial_data or {}
    s.instance = instance
    s._context = {}
    s.parent = None
    return s


# --------------------------------------------------------------------------
# validate_name
# --------------------------------------------------------------------------


def test_validate_name_ok():
    assert _ser().validate_name("  规则  ") == "规则"


def test_validate_name_empty():
    with pytest.raises(serializers.ValidationError):
        _ser().validate_name("  ")


# --------------------------------------------------------------------------
# validate_instance_filter
# --------------------------------------------------------------------------


def test_validate_instance_filter_condition_ok():
    ser = _ser(initial_data={"filter_type": "condition"})
    value = {"query_list": [{"field": "name"}]}
    assert ser.validate_instance_filter(value) == value


def test_validate_instance_filter_condition_empty():
    ser = _ser(initial_data={"filter_type": "condition"})
    with pytest.raises(serializers.ValidationError):
        ser.validate_instance_filter({"query_list": []})


def test_validate_instance_filter_condition_too_many():
    ser = _ser(initial_data={"filter_type": "condition"})
    with pytest.raises(serializers.ValidationError):
        ser.validate_instance_filter({"query_list": [{"f": i} for i in range(9)]})


def test_validate_instance_filter_instances_ok():
    ser = _ser(initial_data={"filter_type": "instances"})
    value = {"instance_ids": [1, 2]}
    assert ser.validate_instance_filter(value) == value


def test_validate_instance_filter_instances_empty():
    ser = _ser(initial_data={"filter_type": "instances"})
    with pytest.raises(serializers.ValidationError):
        ser.validate_instance_filter({"instance_ids": []})


def test_validate_instance_filter_bad_type():
    with pytest.raises(serializers.ValidationError):
        _ser().validate_instance_filter("notadict")


def test_validate_instance_filter_unknown_filter_type():
    ser = _ser(initial_data={"filter_type": "weird"})
    with pytest.raises(serializers.ValidationError):
        ser.validate_instance_filter({"query_list": [{"f": 1}]})


# --------------------------------------------------------------------------
# validate_trigger_types
# --------------------------------------------------------------------------


def test_validate_trigger_types_ok():
    assert _ser().validate_trigger_types(["attribute_change"]) == ["attribute_change"]


def test_validate_trigger_types_empty():
    with pytest.raises(serializers.ValidationError):
        _ser().validate_trigger_types([])


def test_validate_trigger_types_invalid():
    with pytest.raises(serializers.ValidationError):
        _ser().validate_trigger_types(["bogus"])


# --------------------------------------------------------------------------
# validate_trigger_config
# --------------------------------------------------------------------------


def test_validate_trigger_config_attribute_change_ok():
    ser = _ser(initial_data={"trigger_types": ["attribute_change"]})
    value = {"attribute_change": {"fields": ["name"]}}
    assert ser.validate_trigger_config(value) == value


def test_validate_trigger_config_attribute_change_missing_fields():
    ser = _ser(initial_data={"trigger_types": ["attribute_change"]})
    with pytest.raises(serializers.ValidationError):
        ser.validate_trigger_config({"attribute_change": {"fields": []}})


def test_validate_trigger_config_expiration_ok():
    ser = _ser(initial_data={"trigger_types": ["expiration"]})
    value = {"expiration": {"time_field": "expire_at", "days_before": 7}}
    assert ser.validate_trigger_config(value) == value


def test_validate_trigger_config_expiration_bad_days():
    ser = _ser(initial_data={"trigger_types": ["expiration"]})
    with pytest.raises(serializers.ValidationError):
        ser.validate_trigger_config({"expiration": {"time_field": "x", "days_before": 0}})


def test_validate_trigger_config_relation_change_normalizes():
    ser = _ser(initial_data={"trigger_types": ["relation_change"]})
    value = {"relation_change": {"related_models": [{"related_model": "host", "fields": ["name"]}]}}
    out = ser.validate_trigger_config(value)
    assert out["relation_change"]["related_model"] == "host"


def test_validate_trigger_config_bad_type():
    with pytest.raises(serializers.ValidationError):
        _ser().validate_trigger_config("notadict")


# --------------------------------------------------------------------------
# _normalize_relation_change_config
# --------------------------------------------------------------------------


def test_normalize_relation_change_legacy():
    ser = _ser()
    out = ser._normalize_relation_change_config({"related_model": "host", "fields": ["name"]})
    assert out["related_models"][0]["related_model"] == "host"


def test_normalize_relation_change_empty_raises():
    ser = _ser()
    with pytest.raises(serializers.ValidationError):
        ser._normalize_relation_change_config({})


def test_normalize_relation_change_duplicate_models():
    ser = _ser()
    with pytest.raises(serializers.ValidationError):
        ser._normalize_relation_change_config({
            "related_models": [
                {"related_model": "host", "fields": ["a"]},
                {"related_model": "host", "fields": ["b"]},
            ]
        })


# --------------------------------------------------------------------------
# validate_recipients / validate_channel_ids
# --------------------------------------------------------------------------


def test_validate_recipients_ok():
    value = {"users": ["u1"], "groups": []}
    assert _ser().validate_recipients(value) == value


def test_validate_recipients_empty():
    with pytest.raises(serializers.ValidationError):
        _ser().validate_recipients({"users": [], "groups": []})


def test_validate_recipients_bad_type():
    with pytest.raises(serializers.ValidationError):
        _ser().validate_recipients({"users": "x", "groups": []})


def test_validate_channel_ids_ok():
    assert _ser().validate_channel_ids([1, 2]) == [1, 2]


def test_validate_channel_ids_empty():
    with pytest.raises(serializers.ValidationError):
        _ser().validate_channel_ids([])


def test_validate_channel_ids_non_int():
    with pytest.raises(serializers.ValidationError):
        _ser().validate_channel_ids([1, "x"])


# --------------------------------------------------------------------------
# get_can_manage
# --------------------------------------------------------------------------


def test_get_can_manage_no_request():
    ser = _ser()
    ser._context = {}
    assert ser.get_can_manage(SimpleNamespace(organization=1)) is False
