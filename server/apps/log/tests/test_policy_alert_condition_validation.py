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


def test_keyword_min_hits_replaces_trigger_count_and_recover_after():
    condition = {
        "query": "OutOfMemoryError",
        "rule": {"trigger_count": 3, "recover_after": 2, "min_hits": 4},
    }
    serializer = _serializer(condition, alert_type="keyword")
    assert serializer.is_valid(), serializer.errors
    rule = serializer.validated_data["alert_condition"]["rule"]
    assert rule["min_hits"] == 4
    assert "trigger_count" not in rule
    assert "recover_after" not in rule


def test_keyword_min_hits_defaults_to_one_and_rejects_out_of_range():
    missing = _serializer({"query": "oom", "rule": {}}, alert_type="keyword")
    assert missing.is_valid(), missing.errors
    assert missing.validated_data["alert_condition"]["rule"]["min_hits"] == 1

    rejected = _serializer({"query": "oom", "rule": {"min_hits": 100001}}, alert_type="keyword")
    assert not rejected.is_valid()
    assert "命中条数" in str(rejected.errors)


def test_aggregate_recover_after_is_bounded_and_drops_min_hits():
    rejected = _condition("count")
    rejected["rule"]["recover_after"] = 11
    rejected_serializer = _serializer(rejected)
    assert not rejected_serializer.is_valid()
    assert "自动恢复" in str(rejected_serializer.errors)

    accepted = _condition("count")
    accepted["rule"]["recover_after"] = 3
    accepted["rule"]["min_hits"] = 9
    serializer = _serializer(accepted)
    assert serializer.is_valid(), serializer.errors
    rule = serializer.validated_data["alert_condition"]["rule"]
    assert rule["recover_after"] == 3
    assert "min_hits" not in rule

    cleared = _condition("count")
    cleared["rule"]["recover_after"] = None
    cleared_serializer = _serializer(cleared)
    assert cleared_serializer.is_valid(), cleared_serializer.errors
    assert cleared_serializer.validated_data["alert_condition"]["rule"]["recover_after"] is None


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
    assert "这一档还没填完" in str(rejected.errors)

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


def _guard(func="count_uniq", field="user", op=">=", value="20"):
    condition = _condition(func, op=op, value=value, field=field)
    condition["rule"]["conditions"][0]["role"] = "guard"
    return condition


def test_missing_role_is_stored_as_regular():
    serializer = _serializer(_condition("count"))
    assert serializer.is_valid(), serializer.errors
    stored = serializer.validated_data["alert_condition"]["rule"]["conditions"][0]
    assert stored["role"] == "regular"


def _with_regular(condition):
    condition["rule"]["conditions"].insert(
        0,
        {"role": "regular", "func": "count", "field": "_msg", "op": ">", "value": "1"},
    )
    return condition


def test_guard_stores_one_threshold_and_drops_a_ladder():
    serializer = _serializer(_with_regular(_guard()))
    assert serializer.is_valid(), serializer.errors
    stored = serializer.validated_data["alert_condition"]["rule"]["conditions"][1]
    assert stored["role"] == "guard"
    assert stored["compare"] == {"kind": "absolute"}
    assert "thresholds" not in stored
    assert stored["value"] == "20"

    ladder = _with_regular(_guard())
    ladder["rule"]["conditions"][1]["thresholds"] = [{"level": "warning", "value": "20"}]
    rejected = _serializer(ladder)
    assert not rejected.is_valid()
    assert "只有一个门槛" in str(rejected.errors)


def test_guard_rejects_delta_and_or_and_a_policy_with_only_guards():
    delta = _with_regular(_guard())
    delta["rule"]["conditions"][1]["compare"] = {"kind": "delta", "to": "previous_window"}
    rejected_delta = _serializer(delta)
    assert not rejected_delta.is_valid()
    assert "只能比当前值" in str(rejected_delta.errors)

    either = _with_regular(_guard())
    either["rule"]["mode"] = "or"
    rejected_or = _serializer(either)
    assert not rejected_or.is_valid()
    assert "不能带前置条件" in str(rejected_or.errors)

    only_guard = _serializer(_guard())
    assert not only_guard.is_valid()
    assert "至少要有一条常规条件" in str(only_guard.errors)


def test_and_level_sets_ignore_guards():
    condition = _with_thresholds(
        _condition("count"),
        [{"level": "warning", "value": "10"}, {"level": "error", "value": "50"}],
    )
    condition["rule"]["conditions"][0]["role"] = "regular"
    condition["rule"]["conditions"].append({"role": "guard", "func": "count_uniq", "field": "user", "op": ">=", "value": "20"})
    serializer = _serializer(condition)
    assert serializer.is_valid(), serializer.errors
    roles = [item["role"] for item in serializer.validated_data["alert_condition"]["rule"]["conditions"]]
    assert roles == ["regular", "guard"]
