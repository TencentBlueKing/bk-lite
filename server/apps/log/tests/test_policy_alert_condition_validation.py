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


def test_stored_no_data_is_dropped_on_write():
    condition = _condition("count")
    condition["no_data"] = {"enabled": "yes", "level": "fatal"}
    serializer = _serializer(condition, alert_type="keyword")
    assert serializer.is_valid(), serializer.errors
    assert "no_data" not in serializer.validated_data["alert_condition"]


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


def test_custom_offset_is_stored_and_legacy_target_is_normalized():
    custom = _condition("count", value="20")
    custom["rule"]["conditions"][0]["compare"] = {"kind": "percent", "to": "offset_days", "offset": 3}
    serializer = _serializer(custom)
    assert serializer.is_valid(), serializer.errors
    stored = serializer.validated_data["alert_condition"]["rule"]["conditions"][0]["compare"]
    assert stored == {"kind": "percent", "to": "offset_days", "offset": 3}

    legacy = _condition("count", value="20")
    legacy["rule"]["conditions"][0]["compare"] = {"kind": "delta", "to": "offset_7d"}
    legacy_serializer = _serializer(legacy)
    assert legacy_serializer.is_valid(), legacy_serializer.errors
    assert legacy_serializer.validated_data["alert_condition"]["rule"]["conditions"][0]["compare"] == {
        "kind": "delta",
        "to": "offset_days",
        "offset": 7,
    }


def test_custom_offset_out_of_range_is_rejected():
    condition = _condition("count", value="20")
    condition["rule"]["conditions"][0]["compare"] = {"kind": "percent", "to": "offset_hours", "offset": 0}
    serializer = _serializer(condition)
    assert not serializer.is_valid()
    assert "比较方式或对照无效" in str(serializer.errors)


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


def _with_thresholds(condition, thresholds, op=">", index=0):
    stored = dict(condition)
    stored["rule"] = dict(condition["rule"])
    conditions = [dict(item) for item in condition["rule"]["conditions"]]
    conditions[index] = {**conditions[index], "op": op, "thresholds": thresholds}
    stored["rule"]["conditions"] = conditions
    return stored


def test_ladder_stores_sorted_thresholds_and_mirrors_lightest_value():
    condition = _with_thresholds(
        _condition("count", value="999"),
        [
            {"level": "critical", "value": "200"},
            {"level": "warning", "value": "10"},
            {"level": "error", "value": "50"},
        ],
    )
    serializer = PolicySerializer(
        data={"alert_type": "aggregate", "alert_level": "warning", "alert_condition": condition},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    stored = serializer.validated_data["alert_condition"]["rule"]["conditions"][0]
    assert stored["thresholds"] == [
        {"level": "warning", "value": "10"},
        {"level": "error", "value": "50"},
        {"level": "critical", "value": "200"},
    ]
    assert stored["value"] == "10"
    assert serializer.validated_data["alert_level"] == "critical"


def test_legacy_condition_save_does_not_invent_thresholds():
    serializer = _serializer(_condition("count", op=">", value="5"))
    assert serializer.is_valid(), serializer.errors
    stored = serializer.validated_data["alert_condition"]["rule"]["conditions"][0]
    assert "thresholds" not in stored
    assert stored["value"] == "5"
    assert "alert_level" not in serializer.validated_data


def test_descending_greater_than_ladder_is_rejected():
    condition = _with_thresholds(
        _condition("count"),
        [
            {"level": "warning", "value": "200"},
            {"level": "error", "value": "50"},
        ],
    )
    serializer = _serializer(condition)
    assert not serializer.is_valid()
    assert "严格单调" in str(serializer.errors)


def test_less_than_ladder_must_descend():
    accepted = _with_thresholds(
        _condition("count"),
        [
            {"level": "warning", "value": "200"},
            {"level": "critical", "value": "10"},
        ],
        op="<",
    )
    serializer = _serializer(accepted)
    assert serializer.is_valid(), serializer.errors
    rejected = _with_thresholds(
        _condition("count"),
        [
            {"level": "warning", "value": "10"},
            {"level": "error", "value": "50"},
        ],
        op="<",
    )
    assert not _serializer(rejected).is_valid()


def test_equality_allows_one_non_numeric_rung_only():
    one = _with_thresholds(
        _condition("count", op="in", value="error", field="level"),
        [{"level": "warning", "value": "error"}],
        op="in",
    )
    serializer = _serializer(one)
    assert serializer.is_valid(), serializer.errors
    stored = serializer.validated_data["alert_condition"]["rule"]["conditions"][0]
    assert stored["value"] == "error"
    assert stored["op"] == "in"
    two = _with_thresholds(
        _condition("count", op="=", value="1"),
        [
            {"level": "warning", "value": "1"},
            {"level": "error", "value": "2"},
        ],
        op="=",
    )
    rejected = _serializer(two)
    assert not rejected.is_valid()
    assert "一档" in str(rejected.errors)


def test_and_level_sets_must_match_and_or_may_differ():
    shared = _condition("count")
    shared["rule"]["conditions"] = [
        {
            "func": "count",
            "field": "_msg",
            "op": ">",
            "value": "10",
            "thresholds": [
                {"level": "warning", "value": "10"},
                {"level": "error", "value": "50"},
            ],
        },
        {
            "func": "sum",
            "field": "bytes",
            "op": ">",
            "value": "1",
            "thresholds": [{"level": "warning", "value": "1"}],
        },
    ]
    shared["rule"]["mode"] = "and"
    rejected = _serializer(shared)
    assert not rejected.is_valid()
    assert "级别必须一致" in str(rejected.errors)

    shared["rule"]["mode"] = "or"
    accepted = PolicySerializer(
        data={"alert_type": "aggregate", "alert_level": "warning", "alert_condition": shared},
        partial=True,
    )
    assert accepted.is_valid(), accepted.errors
    assert accepted.validated_data["alert_level"] == "error"


def test_unknown_or_duplicate_level_is_rejected():
    unknown = _with_thresholds(_condition("count"), [{"level": "info", "value": "1"}])
    assert not _serializer(unknown).is_valid()
    duplicate = _with_thresholds(
        _condition("count"),
        [
            {"level": "warning", "value": "1"},
            {"level": "warning", "value": "2"},
        ],
    )
    assert not _serializer(duplicate).is_valid()
    empty = _with_thresholds(_condition("count"), [])
    assert not _serializer(empty).is_valid()
