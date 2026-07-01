"""policy_methods 测试 — 周期换算/查询构建的纯逻辑 + 聚合方法对 VM 边界的入参契约。"""
from unittest.mock import patch

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.tasks.utils import policy_methods as pm

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("period,expected", [
    ({"type": "min", "value": 5}, 300),
    ({"type": "hour", "value": 2}, 7200),
    ({"type": "day", "value": 1}, 86400),
])
def test_period_to_seconds(period, expected):
    assert pm.period_to_seconds(period) == expected


def test_period_to_seconds_empty_raises():
    with pytest.raises(BaseAppException, match="period is empty"):
        pm.period_to_seconds(None)


def test_period_to_seconds_invalid_type_raises():
    with pytest.raises(BaseAppException, match="invalid period type"):
        pm.period_to_seconds({"type": "week", "value": 1})


def test_build_policy_query_normal_aggregation():
    assert pm.build_policy_query("sum", "cpu", "5m", "instance_id") == "sum(cpu) by (instance_id)"


def test_build_policy_query_over_time_simple_selector_gets_range():
    # 裸指标属于简单 selector，会被补上 [step]
    q = pm.build_policy_query("max_over_time", "cpu", "5m", "instance_id")
    assert q == "any(max_over_time(cpu[5m])) by (instance_id)"


def test_build_policy_query_over_time_complex_expr_unchanged():
    # 复杂表达式不补 range selector，保持原样
    q = pm.build_policy_query("avg_over_time", "rate(cpu[1m])", "5m", "instance_id")
    assert q == "any(avg_over_time(rate(cpu[1m]))) by (instance_id)"


def test_build_policy_query_invalid_algorithm_raises():
    with pytest.raises(BaseAppException, match="invalid algorithm method"):
        pm.build_policy_query("median", "cpu", "5m", "instance_id")


@pytest.mark.parametrize("query,expected", [
    ("cpu", True),
    ("cpu{host='a'}", True),
    ("{host='a'}", True),
    ("rate(cpu[1m])", False),
    ("", False),
    ("  ", False),
])
def test_supports_explicit_range_selector(query, expected):
    assert pm._supports_explicit_range_selector(query) is expected


def test_sum_calls_vm_query_range_with_built_query():
    with patch.object(pm, "VictoriaMetricsAPI") as MockVM:
        inst = MockVM.return_value
        inst.query_range.return_value = {"data": {"result": []}}
        out = pm._sum("cpu", "s", "e", "5m", "instance_id")
    inst.query_range.assert_called_once_with("sum(cpu) by (instance_id)", "s", "e", "5m")
    assert out == {"data": {"result": []}}


def test_max_over_time_calls_query_range():
    with patch.object(pm, "VictoriaMetricsAPI") as MockVM:
        inst = MockVM.return_value
        inst.query_range.return_value = {"data": {"result": []}}
        pm.max_over_time("cpu", "s", "e", "5m", "instance_id")
    inst.query_range.assert_called_once_with("any(max_over_time(cpu[5m])) by (instance_id)", "s", "e", "5m")


def test_last_over_time_simple_selector_uses_instant_query_and_wraps_values():
    with patch.object(pm, "VictoriaMetricsAPI") as MockVM:
        inst = MockVM.return_value
        inst.query.return_value = {"data": {"result": [{"value": [123, "9"]}]}}
        out = pm.last_over_time("cpu", "s", "e", "5m", "instance_id")
    # 简单 selector → query(query, None, end)
    inst.query.assert_called_once_with("any(last_over_time(cpu[5m])) by (instance_id)", None, "e")
    # values 被包装成 [value]
    assert out["data"]["result"][0]["values"] == [[123, "9"]]


def test_last_over_time_complex_expr_uses_step_path():
    with patch.object(pm, "VictoriaMetricsAPI") as MockVM:
        inst = MockVM.return_value
        inst.query.return_value = {"data": {"result": []}}
        pm.last_over_time("rate(cpu[1m])", "s", "e", "5m", "instance_id")
    inst.query.assert_called_once_with("any(last_over_time(rate(cpu[1m]))) by (instance_id)", "5m", "e")


def test_method_registry_maps_all_algorithms():
    assert set(pm.METHOD) == {
        "sum", "avg", "max", "min", "count",
        "max_over_time", "min_over_time", "avg_over_time", "sum_over_time", "last_over_time",
    }
