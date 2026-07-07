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
