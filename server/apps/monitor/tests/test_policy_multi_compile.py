"""多指标条件编译必须与同参数单指标策略逐字相同，存在性只查锚点。"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.tasks.services.policy_scan.metric_query import MetricQueryService
from apps.monitor.tasks.utils.policy_methods import compile_existence_query, compile_policy_query
from apps.monitor.tasks.utils.policy_multi import compile_condition_query, condition_policy_like

pytestmark = pytest.mark.unit


def _single(condition):
    return SimpleNamespace(**condition_policy_like({"collect_type": "", "period": {"type": "min", "value": 5}}, condition))


def test_each_condition_compiles_to_the_same_string_as_a_single_metric_policy():
    anchor = {
        "ref": "a",
        "metric_id": 1,
        "filter": [{"name": "mode", "method": "=", "value": "user"}],
        "group_algorithm": "avg",
        "group_by": ["instance_id"],
        "algorithm": "avg_over_time",
        "count_predicate": {},
    }
    rate_condition = {
        "ref": "b",
        "metric_id": 2,
        "filter": [],
        "group_algorithm": "max",
        "group_by": ["instance_id", "device"],
        "algorithm": "rate",
        "count_predicate": {},
    }
    policy = {"collect_type": "", "period": {"type": "min", "value": 5}}

    for condition, base in ((anchor, 'cpu{mode="user"}'), (rate_condition, "mem{}")):
        single = _single(condition)
        group_by = ",".join(condition["group_by"])
        assert compile_condition_query(policy, condition, base, "5m") == compile_policy_query(
            single, base, "5m", group_by
        )
        assert compile_condition_query(policy, condition, base, "5m", existence=True) == compile_existence_query(
            single, base, "5m", group_by
        )


@pytest.mark.django_db
def test_existence_query_runs_only_for_the_anchor(mocker):
    obj = MonitorObject.objects.create(name="MultiCompileObj", level="base", instance_id_keys=["instance_id"])
    plugin = MonitorPlugin.objects.create(name="MultiCompilePlugin")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    cpu = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="cpu_usage",
        query="cpu_usage{__$labels__}",
        instance_id_keys=["instance_id"],
    )
    memory = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="mem_used",
        query="mem_used{__$labels__}",
        instance_id_keys=["instance_id"],
    )
    policy = SimpleNamespace(
        id=7,
        collect_type="",
        metric_unit="percent",
        calculation_unit="percent",
        threshold_unit="percent",
        compare_mode="absolute",
        compare_value_kind="",
        algorithm="avg_over_time",
        last_run_time=datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc),
        period={"type": "min", "value": 5},
        monitor_object=obj,
        query_condition={
            "type": "multi",
            "result_name": "CPU 与内存双高",
            "combinator": "all",
            "queries": [
                {
                    "ref": "a",
                    "metric_id": cpu.id,
                    "filter": [],
                    "group_algorithm": "avg",
                    "group_by": ["instance_id"],
                    "algorithm": "avg_over_time",
                },
                {
                    "ref": "b",
                    "metric_id": memory.id,
                    "filter": [],
                    "group_algorithm": "avg",
                    "group_by": ["instance_id"],
                    "algorithm": "max_over_time",
                },
            ],
        },
    )
    captured = []
    vm = mocker.patch("apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI")
    vm.return_value.query_range.side_effect = lambda query, start, end, step: captured.append(query) or {
        "status": "success",
        "data": {"result": []},
    }

    service = MetricQueryService(policy, {"('h1',)": "主机1"})
    service.set_monitor_obj_instance_key()
    service.query_existence_metrics(policy.period)
    service.query_multi_comparison_metrics(policy.period, 1)

    assert len(captured) == 3
    assert captured[0].startswith("avg_over_time((avg(cpu_usage")
    assert "mem_used" not in captured[0]
    assert any("mem_used" in query for query in captured[1:])
    assert service.get_result_group_by() == ["instance_id"]


def _formula_metrics():
    obj = MonitorObject.objects.create(name="FormulaCompileObj", level="base", instance_id_keys=["instance_id"])
    plugin = MonitorPlugin.objects.create(name="FormulaCompilePlugin")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    error = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="error_total",
        query="error_total{__$labels__}",
        instance_id_keys=["instance_id"],
        data_type="Number",
        unit="counts",
    )
    request = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="request_total",
        query="request_total{__$labels__}",
        instance_id_keys=["instance_id"],
        data_type="Number",
        unit="counts",
    )
    return obj, error, request


def _formula_item(error, request, **overrides):
    data = {
        "ref": "a",
        "source": "formula",
        "metric_name": "错误率",
        "expression": "a1 / a2 * 100",
        "operands": [
            {
                "ref": "a1",
                "metric_id": error.id,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
            {
                "ref": "a2",
                "metric_id": request.id,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
        ],
        "group_by": ["instance_id"],
        "algorithm": "avg_over_time",
        "metric_unit": "",
        "calculation_unit": "percent",
        "threshold_unit": "percent",
        "count_predicate": {},
        "role": "level",
        "threshold": [{"level": "warning", "method": ">", "value": 5}],
    }
    data.update(overrides)
    return data


def _policy_shell(obj, query_condition, **overrides):
    data = dict(
        id=8,
        collect_type="",
        metric_unit="",
        calculation_unit="percent",
        threshold_unit="percent",
        compare_mode="absolute",
        compare_value_kind="",
        algorithm="avg_over_time",
        group_algorithm="sum",
        group_by=["instance_id"],
        count_predicate={},
        last_run_time=datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc),
        period={"type": "min", "value": 5},
        monitor_object=obj,
        query_condition=query_condition,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def _capture_queries(mocker):
    captured = []
    vm = mocker.patch("apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI")
    vm.return_value.query_range.side_effect = lambda query, start, end, step: captured.append(query) or {
        "status": "success",
        "data": {"result": []},
    }
    return captured


@pytest.mark.django_db
def test_formula_condition_query_matches_formula_policy_and_injects_selector(mocker):
    obj, error, request = _formula_metrics()
    condition = _formula_item(error, request)
    gate = {
        "ref": "b",
        "metric_id": request.id,
        "filter": [],
        "group_algorithm": "sum",
        "group_by": ["instance_id"],
        "algorithm": "avg_over_time",
        "role": "gate",
        "threshold": [{"method": ">", "value": 100}],
    }
    formula_policy = _policy_shell(
        obj,
        {
            "type": "formula",
            "result_name": "错误率",
            "expression": condition["expression"],
            "queries": condition["operands"],
        },
    )
    multi_policy = _policy_shell(
        obj,
        {
            "type": "multi",
            "result_name": "错误率与请求数",
            "combinator": "all",
            "queries": [condition, gate],
        },
    )
    instances = {"('h1',)": "主机1"}
    captured = _capture_queries(mocker)

    formula_service = MetricQueryService(formula_policy, instances)
    formula_service.set_monitor_obj_instance_key()
    formula_service.query_comparison_metrics(formula_policy.period, 1)
    formula_query = captured[0]
    captured.clear()

    multi_service = MetricQueryService(multi_policy, instances)
    multi_service.set_monitor_obj_instance_key()
    multi_service.query_multi_comparison_metrics(multi_policy.period, 1)

    assert len(captured) == 2
    assert captured[0] == formula_query
    assert "error_total" in captured[0]
    assert "request_total" in captured[0]
    assert 'instance_id=~"h1"' in captured[0]
    assert captured[0].count('instance_id=~"h1"') >= 2
    assert "request_total" in captured[1]
    assert "error_total" not in captured[1]


@pytest.mark.django_db
def test_formula_condition_count_if_uses_bool_and_existence_uses_last_over_time(mocker):
    obj, error, request = _formula_metrics()
    predicate = {"method": ">", "value": 1}
    condition = _formula_item(
        error,
        request,
        algorithm="count_if_over_time",
        count_predicate=predicate,
        calculation_unit="count",
        threshold_unit="count",
    )
    gate = {
        "ref": "b",
        "metric_id": request.id,
        "filter": [],
        "group_algorithm": "sum",
        "group_by": ["instance_id"],
        "algorithm": "avg_over_time",
        "role": "gate",
        "threshold": [{"method": ">", "value": 100}],
    }
    formula_policy = _policy_shell(
        obj,
        {
            "type": "formula",
            "result_name": "错误率",
            "expression": condition["expression"],
            "queries": condition["operands"],
        },
        algorithm="count_if_over_time",
        count_predicate=predicate,
        calculation_unit="count",
        threshold_unit="count",
    )
    multi_policy = _policy_shell(
        obj,
        {
            "type": "multi",
            "result_name": "错误率与请求数",
            "combinator": "all",
            "queries": [condition, gate],
        },
        algorithm="count_if_over_time",
        count_predicate=predicate,
    )
    instances = {"('h1',)": "主机1"}
    captured = _capture_queries(mocker)

    formula_service = MetricQueryService(formula_policy, instances)
    formula_service.set_monitor_obj_instance_key()
    formula_service.query_comparison_metrics(formula_policy.period, 1)
    formula_query = captured[0]
    captured.clear()
    formula_service.query_existence_metrics(formula_policy.period)
    formula_existence = captured[0]
    captured.clear()

    multi_service = MetricQueryService(multi_policy, instances)
    multi_service.set_monitor_obj_instance_key()
    multi_service.query_multi_comparison_metrics(multi_policy.period, 1)
    assert captured[0] == formula_query
    assert "bool" in captured[0]
    assert "sum_over_time" in captured[0]
    captured.clear()
    multi_service.query_existence_metrics(multi_policy.period)
    assert captured[0] == formula_existence
    assert captured[0].startswith("last_over_time((")
    assert "error_total" in captured[0]
    assert len(captured) == 1
