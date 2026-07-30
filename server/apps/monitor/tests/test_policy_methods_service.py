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


def test_build_policy_query_maps_legacy_aggregation_to_two_stage_query():
    assert (
        pm.build_policy_query("sum", "cpu", "5m", "instance_id")
        == "sum_over_time((sum(cpu) by (instance_id))[5m:10s])"
    )


def test_build_policy_query_maps_legacy_window_algorithm_to_group_algorithm():
    q = pm.build_policy_query("max_over_time", "cpu", "5m", "instance_id")
    assert q == "max_over_time((max(cpu) by (instance_id))[5m:10s])"


def test_build_policy_query_preserves_complex_metric_expression_inside_group_stage():
    q = pm.build_policy_query("avg_over_time", "rate(cpu[1m])", "5m", "instance_id")
    assert q == "avg_over_time((avg(rate(cpu[1m])) by (instance_id))[5m:10s])"


def test_build_policy_query_uses_explicit_two_stage_algorithms():
    q = pm.build_policy_query("last_over_time", "cpu", "1h", "instance_id", "count")
    assert q == "last_over_time((count(cpu) by (instance_id))[1h:2m])"


def test_build_policy_query_invalid_algorithm_raises():
    with pytest.raises(BaseAppException, match="invalid algorithm method"):
        pm.build_policy_query("median", "cpu", "5m", "instance_id")


@pytest.mark.parametrize("period,expected", [
    ("5m", "10s"),
    ("1h", "2m"),
    ("1d", "48m"),
])
def test_period_step_generates_thirty_subquery_samples(period, expected):
    assert pm.period_step(period) == expected


@pytest.mark.parametrize("period", ["", "5s", "week", None])
def test_period_step_rejects_invalid_period(period):
    with pytest.raises(BaseAppException, match="invalid period"):
        pm.period_step(period)


def test_sum_calls_vm_query_range_with_built_query():
    with patch.object(pm, "VictoriaMetricsAPI") as MockVM:
        inst = MockVM.return_value
        inst.query_range.return_value = {"data": {"result": []}}
        out = pm._sum("cpu", "s", "e", "5m", "instance_id")
    inst.query_range.assert_called_once_with(
        "sum_over_time((sum(cpu) by (instance_id))[5m:10s])",
        "s",
        "e",
        "5m",
    )
    assert out == {"data": {"result": []}}


def test_max_over_time_calls_query_range():
    with patch.object(pm, "VictoriaMetricsAPI") as MockVM:
        inst = MockVM.return_value
        inst.query_range.return_value = {"data": {"result": []}}
        pm.max_over_time("cpu", "s", "e", "5m", "instance_id")
    inst.query_range.assert_called_once_with(
        "max_over_time((max(cpu) by (instance_id))[5m:10s])",
        "s",
        "e",
        "5m",
    )


def test_last_over_time_uses_range_query_with_two_stage_aggregation():
    with patch.object(pm, "VictoriaMetricsAPI") as MockVM:
        inst = MockVM.return_value
        inst.query_range.return_value = {"data": {"result": [{"values": [[123, "9"]]}]}}
        out = pm.last_over_time("cpu", "s", "e", "5m", "instance_id")
    inst.query_range.assert_called_once_with(
        "last_over_time((avg(cpu) by (instance_id))[5m:10s])",
        "s",
        "e",
        "5m",
    )
    assert out["data"]["result"][0]["values"] == [[123, "9"]]


def test_method_registry_maps_all_algorithms():
    assert set(pm.METHOD) == {
        "sum", "avg", "max", "min", "count",
        "max_over_time", "min_over_time", "avg_over_time", "sum_over_time",
        "count_over_time", "last_over_time",
    }
