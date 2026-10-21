"""多指标策略组改阈值、接入页指标名和模板往返。"""

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.monitor.models import (
    Metric,
    MetricGroup,
    MonitorAlert,
    MonitorObject,
    MonitorPlugin,
    MonitorPolicy,
    PolicyGroup,
    PolicyGroupRule,
)
from apps.monitor.services.policy import PolicyService
from apps.monitor.services.policy_group import PolicyGroupService
from apps.monitor.views.policy_group import _serialize_rule

pytestmark = pytest.mark.django_db


def _condition(metric, ref, **overrides):
    data = {
        "ref": ref,
        "metric_id": metric.id,
        "filter": [],
        "group_algorithm": "avg",
        "group_by": ["instance_id"],
        "algorithm": "avg_over_time",
        "metric_unit": "percent",
        "calculation_unit": "percent",
        "threshold_unit": "percent",
        "role": "level",
        "threshold": [
            {"level": "critical", "method": ">", "value": 90},
            {"level": "warning", "method": ">", "value": 80},
        ],
    }
    data.update(overrides)
    return data


@pytest.fixture
def metric_ctx():
    obj = MonitorObject.objects.create(name="MultiGroupObj", level="base", instance_id_keys=["instance_id"])
    plugin = MonitorPlugin.objects.create(name="MultiGroupPlugin")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    cpu = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="cpu_usage",
        query="cpu_usage{__$labels__}",
        instance_id_keys=["instance_id"],
        data_type="Number",
        unit="percent",
    )
    memory = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="mem_used",
        query="mem_used{__$labels__}",
        instance_id_keys=["instance_id"],
        data_type="Number",
        unit="percent",
    )
    return {"obj": obj, "plugin": plugin, "cpu": cpu, "memory": memory}


def _rule(metric_ctx):
    policy = MonitorPolicy.objects.create(
        monitor_object=metric_ctx["obj"],
        name="双高",
        algorithm="avg_over_time",
        collect_type="",
        source={"type": "instance", "values": []},
        group_by=["instance_id"],
        threshold=[],
        query_condition={
            "type": "multi",
            "result_name": "CPU 与内存双高",
            "combinator": "all",
            "queries": [
                _condition(metric_ctx["cpu"], "a"),
                _condition(metric_ctx["memory"], "b", role="gate", threshold=[{"method": ">", "value": 1}]),
            ],
        },
    )
    group = PolicyGroup.objects.create(
        organization=1,
        monitor_object=metric_ctx["obj"],
        name="默认",
    )
    return PolicyGroupRule.objects.create(
        group=group,
        plugin=metric_ctx["plugin"],
        policy=policy,
        name="CPU 与内存双高",
    )


def test_condition_thresholds_replace_queries_and_close_open_alerts(metric_ctx):
    rule = _rule(metric_ctx)
    alert = MonitorAlert.objects.create(
        policy_id=rule.policy_id,
        monitor_instance_id="('h1',)",
        metric_instance_id="('h1',)",
        alert_type="alert",
        status="new",
    )
    next_thresholds = {
        "a": [
            {"level": "critical", "method": ">", "value": 95},
            {"level": "warning", "method": ">", "value": 70},
        ],
        "b": [{"method": ">", "value": 2}],
    }
    PolicyGroupService.update_rule(rule, condition_thresholds=next_thresholds, operator="tester")
    rule.policy.refresh_from_db()
    alert.refresh_from_db()
    queries = {item["ref"]: item["threshold"] for item in rule.policy.query_condition["queries"]}
    assert queries["a"][0]["value"] == 95
    assert queries["b"] == [{"method": ">", "value": 2}]
    assert rule.policy.threshold == []
    assert alert.status != "new"


def test_condition_thresholds_reject_non_multi(metric_ctx):
    rule = _rule(metric_ctx)
    rule.policy.query_condition = {"type": "metric", "metric_id": metric_ctx["cpu"].id}
    rule.policy.save(update_fields=["query_condition"])
    with pytest.raises(ValidationAppException, match="只有多指标"):
        PolicyGroupService.update_rule(rule, condition_thresholds={"a": []})


def test_condition_thresholds_reject_unknown_ref(metric_ctx):
    rule = _rule(metric_ctx)
    with pytest.raises(ValidationAppException, match="不对应"):
        PolicyGroupService.update_rule(rule, condition_thresholds={"a": [{"level": "warning", "method": ">", "value": 1}]})


def test_serialized_rule_lists_every_condition_metric(metric_ctx):
    rule = _rule(metric_ctx)
    names = PolicyGroupService.metric_names_for_policies([rule.policy])
    payload = _serialize_rule(rule, names)
    assert payload["metric_names"] == ["cpu_usage", "mem_used"]
    assert payload["query_type"] == "multi"
    assert set(payload["condition_thresholds"]) == {"a", "b"}


def test_portable_multi_round_trip_uses_metric_names(metric_ctx):
    query = {
        "type": "multi",
        "result_name": "CPU 与内存双高",
        "combinator": "all",
        "queries": [
            _condition(metric_ctx["cpu"], "a"),
            _condition(metric_ctx["memory"], "b"),
        ],
    }
    portable = PolicyService._portable_query_condition(query)
    assert "metric_id" not in portable["queries"][0]
    assert portable["queries"][0]["metric_name"] == "cpu_usage"
    assert portable["queries"][1]["metric_name"] == "mem_used"
    assert portable["result_name"] == "CPU 与内存双高"
    runtime = PolicyService._runtime_query_condition(portable, metric_ctx["obj"], metric_ctx["plugin"])
    assert runtime["queries"][0]["metric_id"] == metric_ctx["cpu"].id
    assert runtime["queries"][1]["metric_id"] == metric_ctx["memory"].id
    assert "metric_name" not in runtime["queries"][0]


def test_portable_multi_unknown_metric_rejects_the_whole_template(metric_ctx):
    portable = {
        "type": "multi",
        "result_name": "CPU 与内存双高",
        "combinator": "all",
        "queries": [
            {"ref": "a", "metric_name": "cpu_usage", "role": "level", "threshold": []},
            {"ref": "b", "metric_name": "missing_metric", "role": "level", "threshold": []},
        ],
    }
    with pytest.raises(BaseAppException, match="指标不存在"):
        PolicyService._runtime_query_condition(portable, metric_ctx["obj"], metric_ctx["plugin"])


def _formula_query(metric_ctx):
    return {
        "type": "multi",
        "result_name": "错误率与请求数",
        "combinator": "all",
        "queries": [
            {
                "ref": "a",
                "source": "formula",
                "metric_name": "错误率",
                "expression": "a1 / a2 * 100",
                "operands": [
                    {
                        "ref": "a1",
                        "metric_id": metric_ctx["cpu"].id,
                        "filter": [],
                        "group_algorithm": "sum",
                        "group_by": ["instance_id"],
                    },
                    {
                        "ref": "a2",
                        "metric_id": metric_ctx["memory"].id,
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
                "role": "level",
                "threshold": [
                    {"level": "warning", "method": ">", "value": 5},
                    {"level": "error", "method": ">", "value": 10},
                    {"level": "critical", "method": ">", "value": 20},
                ],
            },
            _condition(metric_ctx["memory"], "b", role="gate", threshold=[{"method": ">", "value": 100}]),
        ],
    }


def test_portable_formula_condition_round_trips_operands_and_keeps_result_name(metric_ctx):
    portable = PolicyService._portable_query_condition(_formula_query(metric_ctx))
    condition = portable["queries"][0]
    assert condition["metric_name"] == "错误率"
    assert "metric_id" not in condition
    assert "metric_plugin" not in condition
    assert condition["operands"][0]["metric_name"] == "cpu_usage"
    assert condition["operands"][0]["metric_plugin"] == "MultiGroupPlugin"
    assert "metric_id" not in condition["operands"][0]
    assert condition["operands"][1]["metric_name"] == "mem_used"

    runtime = PolicyService._runtime_query_condition(portable, metric_ctx["obj"], metric_ctx["plugin"])
    assert runtime["queries"][0]["metric_name"] == "错误率"
    assert runtime["queries"][0]["operands"][0]["metric_id"] == metric_ctx["cpu"].id
    assert runtime["queries"][0]["operands"][1]["metric_id"] == metric_ctx["memory"].id
    assert "metric_name" not in runtime["queries"][0]["operands"][0]
    assert runtime["queries"][1]["metric_id"] == metric_ctx["memory"].id


def test_portable_formula_unknown_operand_rejects_the_whole_template(metric_ctx):
    portable = PolicyService._portable_query_condition(_formula_query(metric_ctx))
    portable["queries"][0]["operands"][1]["metric_name"] = "missing_operand"
    with pytest.raises(BaseAppException, match="指标不存在"):
        PolicyService._runtime_query_condition(portable, metric_ctx["obj"], metric_ctx["plugin"])
    assert portable["queries"][0]["metric_name"] == "错误率"


def test_formula_condition_thresholds_persist_and_metric_names_include_operands(metric_ctx):
    rule = _rule(metric_ctx)
    rule.policy.query_condition = _formula_query(metric_ctx)
    rule.policy.save(update_fields=["query_condition"])
    names = PolicyGroupService.metric_names_for_policies([rule.policy])
    payload = _serialize_rule(rule, names)
    assert "cpu_usage" in payload["metric_names"]
    assert "mem_used" in payload["metric_names"]
    assert "错误率" not in payload["metric_names"]

    PolicyGroupService.update_rule(
        rule,
        condition_thresholds={
            "a": [
                {"level": "warning", "method": ">", "value": 8},
                {"level": "error", "method": ">", "value": 12},
                {"level": "critical", "method": ">", "value": 20},
            ],
            "b": [{"method": ">", "value": 200}],
        },
        operator="tester",
    )
    rule.policy.refresh_from_db()
    saved = rule.policy.query_condition["queries"][0]
    assert saved["threshold"][0]["value"] == 8
    assert saved["expression"] == "a1 / a2 * 100"
    assert saved["operands"][0]["metric_id"] == metric_ctx["cpu"].id
    assert rule.policy.query_condition["queries"][1]["threshold"] == [{"method": ">", "value": 200}]
