import math

import pytest
from rest_framework import serializers

from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer


@pytest.fixture
def formula_metrics():
    obj = MonitorObject.objects.create(name="FormulaSerializerObj", level="base")
    plugin = MonitorPlugin.objects.create(name="FormulaSerializerPlugin")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    metric_a = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="http_5xx_total",
        query="http_5xx_total{__$labels__}",
        instance_id_keys=["instance_id", "status"],
    )
    metric_b = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="http_requests_total",
        query="http_requests_total{__$labels__}",
        instance_id_keys=["instance_id"],
    )
    return metric_a, metric_b


@pytest.mark.django_db
def test_serializer_accepts_valid_formula_query_condition(formula_metrics):
    metric_a, metric_b = formula_metrics
    serializer = MonitorPolicySerializer()
    value = {
        "type": "formula",
        "result_name": "错误率",
        "expression": "a / b * 100",
        "queries": [
            {
                "ref": "a",
                "metric_id": metric_a.id,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id", "status"],
            },
            {
                "ref": "b",
                "metric_id": metric_b.id,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
        ],
    }

    assert serializer.validate_query_condition(value) == value


@pytest.mark.django_db
def test_serializer_rejects_formula_with_missing_metric_id(formula_metrics):
    metric_a, _ = formula_metrics
    serializer = MonitorPolicySerializer()
    value = {
        "type": "formula",
        "result_name": "错误率",
        "expression": "a / b * 100",
        "queries": [
            {
                "ref": "a",
                "metric_id": metric_a.id,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id", "status"],
            },
            {
                "ref": "b",
                "metric_id": 999999,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
        ],
    }

    with pytest.raises(serializers.ValidationError) as exc:
        serializer.validate_query_condition(value)

    assert "metric does not exist" in str(exc.value)


def _formula_policy_payload(formula_metrics):
    metric_a, metric_b = formula_metrics
    return {
        "name": "容量差值策略",
        "alert_name": "容量差值 ${value}",
        "monitor_object": metric_a.monitor_object_id,
        "query_condition": {
            "type": "formula",
            "result_name": "容量差值",
            "expression": "a - b",
            "queries": [
                {
                    "ref": "a",
                    "metric_id": metric_a.id,
                    "filter": [],
                    "group_algorithm": "sum",
                    "group_by": ["instance_id"],
                },
                {
                    "ref": "b",
                    "metric_id": metric_b.id,
                    "filter": [],
                    "group_algorithm": "sum",
                    "group_by": ["instance_id"],
                },
            ],
        },
        "source": {"type": "instance", "values": ["('host-a',)"]},
        "schedule": {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "group_algorithm": "sum",
        "algorithm": "avg_over_time",
        "group_by": ["instance_id"],
        "enable_alerts": ["threshold"],
    }


def test_threshold_accepts_negative_zero_and_decimal_values():
    serializer = MonitorPolicySerializer()
    value = [
        {"level": "critical", "method": "<", "value": -10},
        {"level": "error", "method": ">=", "value": 0},
        {"level": "warning", "method": ">", "value": 0.5},
    ]

    assert serializer.validate_threshold(value) == value


@pytest.mark.parametrize("invalid", [True, math.nan, math.inf, -math.inf])
def test_threshold_rejects_non_finite_or_boolean_values(invalid):
    serializer = MonitorPolicySerializer()

    with pytest.raises(serializers.ValidationError):
        serializer.validate_threshold(
            [{"level": "critical", "method": ">", "value": invalid}]
        )


@pytest.mark.django_db
def test_serializer_accepts_convertible_threshold_unit(formula_metrics):
    payload = _formula_policy_payload(formula_metrics)
    payload["metric_unit"] = ""
    payload["calculation_unit"] = "bytes"
    payload["threshold_unit"] = "gibibytes"
    payload["threshold"] = [
        {"level": "critical", "method": ">", "value": 10}
    ]

    serializer = MonitorPolicySerializer(data=payload)

    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_serializer_rejects_cross_system_threshold_unit(formula_metrics):
    payload = _formula_policy_payload(formula_metrics)
    payload["calculation_unit"] = "bytes"
    payload["threshold_unit"] = "percent"
    payload["threshold"] = [
        {"level": "critical", "method": ">", "value": 80}
    ]

    serializer = MonitorPolicySerializer(data=payload)

    assert not serializer.is_valid()
    assert "threshold_unit" in serializer.errors


@pytest.mark.django_db
def test_serializer_accepts_legacy_empty_threshold_unit(formula_metrics):
    payload = _formula_policy_payload(formula_metrics)
    payload["calculation_unit"] = "bytes"
    payload["threshold_unit"] = ""
    payload["threshold"] = [
        {"level": "critical", "method": ">", "value": 10}
    ]

    serializer = MonitorPolicySerializer(data=payload)

    assert serializer.is_valid(), serializer.errors
