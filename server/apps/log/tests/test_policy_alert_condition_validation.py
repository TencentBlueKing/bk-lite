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
