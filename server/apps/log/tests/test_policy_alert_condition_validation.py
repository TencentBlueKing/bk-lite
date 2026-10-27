"""聚合策略 alert_condition 校验：新增函数收紧，旧函数保持可保存。"""

import pytest

from apps.log.serializers.policy import PolicySerializer


def _serializer(alert_condition, alert_type="aggregate"):
    return PolicySerializer(
        data={"alert_type": alert_type, "alert_condition": alert_condition},
        partial=True,
    )


def _condition(func, op=">", value="1", field="_msg"):
    return {
        "query": "level:error",
        "group_by": ["service"],
        "rule": {"mode": "and", "conditions": [{"func": func, "field": field, "op": op, "value": value}]},
    }


@pytest.mark.parametrize("func", ["count", "sum", "avg", "max", "min", "count_rate", "count_delta"])
def test_aggregate_funcs_are_accepted(func):
    serializer = _serializer(_condition(func, value="-1" if func == "count_delta" else "1"))
    assert serializer.is_valid(), serializer.errors


def test_unknown_aggregate_func_is_rejected():
    serializer = _serializer(_condition("percentile"))
    assert not serializer.is_valid()
    assert "不支持的聚合函数" in str(serializer.errors)


def test_count_rate_rejects_non_numeric_operator():
    serializer = _serializer(_condition("count_rate", op="in", value="1"))
    assert not serializer.is_valid()
    assert "该函数只支持数值比较" in str(serializer.errors)


def test_count_rate_rejects_non_numeric_threshold():
    serializer = _serializer(_condition("count_rate", value="abc"))
    assert not serializer.is_valid()
    assert "阈值必须是数字" in str(serializer.errors)


def test_sample_limit_above_ten_is_rejected():
    condition = _condition("count")
    condition["limit"] = 11
    serializer = _serializer(condition)
    assert not serializer.is_valid()
    assert "样本条数须在 1 到 10 之间" in str(serializer.errors)


def test_legacy_count_condition_without_limit_is_accepted():
    serializer = _serializer(_condition("count", op="in", value="error", field="level"))
    assert serializer.is_valid(), serializer.errors


def test_keyword_condition_skips_aggregate_func_checks():
    serializer = _serializer(_condition("percentile"), alert_type="keyword")
    assert serializer.is_valid(), serializer.errors


def test_group_by_must_be_string_list():
    condition = _condition("count")
    condition["group_by"] = "service"
    serializer = _serializer(condition)
    assert not serializer.is_valid()
    assert "分组字段格式错误" in str(serializer.errors)


def _valid_condition(func):
    condition = _condition(func, value="1", field="duration" if func in {"sum", "avg", "max", "min", "count_uniq", "quantile"} else "_msg")
    if func == "quantile":
        condition["rule"]["conditions"][0]["params"] = {"quantile": 0.95}
    if func == "ratio":
        condition["rule"]["conditions"][0]["params"] = {"filter": "status:500"}
    if func == "count_delta":
        condition["rule"]["conditions"][0]["value"] = "-1"
    return condition


@pytest.mark.parametrize(
    "func",
    ["count", "sum", "avg", "max", "min", "count_uniq", "quantile", "ratio", "count_rate", "bytes_rate", "count_delta"],
)
def test_catalog_funcs_are_accepted(func):
    serializer = _serializer(_valid_condition(func))
    assert serializer.is_valid(), serializer.errors


def test_percent_without_target_is_rejected():
    condition = _condition("count")
    condition["rule"]["conditions"][0]["compare"] = {"kind": "percent"}
    serializer = _serializer(condition)
    assert not serializer.is_valid()
    assert "比较方式或对照无效" in str(serializer.errors)


def test_ratio_with_compare_is_rejected():
    condition = _valid_condition("ratio")
    condition["rule"]["conditions"][0]["compare"] = {"kind": "delta", "to": "previous_window"}
    serializer = _serializer(condition)
    assert not serializer.is_valid()
    assert "该函数不支持这种比较方式" in str(serializer.errors)


def test_ratio_filter_with_pipe_is_rejected():
    condition = _valid_condition("ratio")
    condition["rule"]["conditions"][0]["params"] = {"filter": "status:500 | delete"}
    serializer = _serializer(condition)
    assert not serializer.is_valid()
    assert "占比筛选无效" in str(serializer.errors)


def test_quantile_outside_choices_is_rejected():
    condition = _valid_condition("quantile")
    condition["rule"]["conditions"][0]["params"] = {"quantile": 0.8}
    serializer = _serializer(condition)
    assert not serializer.is_valid()
    assert "分位数必须是" in str(serializer.errors)


def test_trigger_count_above_five_is_rejected():
    condition = _condition("count")
    condition["rule"]["trigger_count"] = 6
    serializer = _serializer(condition)
    assert not serializer.is_valid()
    assert "连续满足次数" in str(serializer.errors)


def test_no_data_enabled_non_boolean_is_rejected():
    condition = _condition("count")
    condition["no_data"] = {"enabled": "yes", "level": "warning"}
    serializer = _serializer(condition, alert_type="keyword")
    assert not serializer.is_valid()
    assert "布尔" in str(serializer.errors)


def test_no_data_level_fatal_is_rejected():
    condition = _condition("count")
    condition["no_data"] = {"enabled": True, "level": "fatal"}
    serializer = _serializer(condition)
    assert not serializer.is_valid()
    assert "无数据告警级别无效" in str(serializer.errors)


def test_count_delta_is_normalized_on_write():
    serializer = _serializer(_condition("count_delta", value="-1"))
    assert serializer.is_valid(), serializer.errors
    stored = serializer.validated_data["alert_condition"]["rule"]["conditions"][0]
    assert stored["func"] == "count"
    assert stored["field"] == "_msg"
    assert stored["compare"] == {"kind": "delta", "to": "previous_window"}
    assert stored["value"] == "-1"


def test_absolute_legacy_count_keeps_non_numeric_operator():
    serializer = _serializer(_condition("count", op="in", value="error", field="level"))
    assert serializer.is_valid(), serializer.errors
    stored = serializer.validated_data["alert_condition"]["rule"]["conditions"][0]
    assert stored["op"] == "in"
    assert stored["compare"] == {"kind": "absolute"}


def test_count_uniq_and_percent_payload_is_accepted():
    condition = _condition("count", value="50")
    condition["rule"]["conditions"] = [
        {"func": "count_uniq", "field": "client_ip", "op": ">", "value": "50"},
        {
            "func": "count",
            "field": "_msg",
            "op": ">",
            "value": "20",
            "compare": {"kind": "percent", "to": "offset_24h"},
        },
        {"func": "bytes_rate", "field": "_msg", "op": ">", "value": "10"},
    ]
    serializer = _serializer(condition)
    assert serializer.is_valid(), serializer.errors
