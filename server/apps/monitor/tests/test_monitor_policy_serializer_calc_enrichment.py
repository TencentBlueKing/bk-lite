"""D4 组合禁则与存量 payload 缺省。"""
import pytest
from rest_framework import serializers

from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer


@pytest.fixture
def metric_ctx():
    obj = MonitorObject.objects.create(name="CalcEnrichObj", level="base")
    plugin = MonitorPlugin.objects.create(name="CalcEnrichPlugin")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    metric = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="cpu",
        query="cpu{__$labels__}",
        instance_id_keys=["instance_id"],
        data_type="Number",
        unit="percent",
    )
    rate_metric = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="if_octets",
        query="rate(if_octets{__$labels__}[5m])",
        instance_id_keys=["instance_id"],
        data_type="Number",
        unit="bytes",
    )
    enum_metric = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="status",
        query="status{__$labels__}",
        instance_id_keys=["instance_id"],
        data_type="Enum",
        unit='[{"id": 1, "name": "up"}]',
    )
    return {
        "obj": obj,
        "metric": metric,
        "rate_metric": rate_metric,
        "enum_metric": enum_metric,
    }


def _payload(metric_ctx, **overrides):
    metric = metric_ctx["metric"]
    data = {
        "name": "calc-enrich",
        "alert_name": "alert ${value}",
        "monitor_object": metric.monitor_object_id,
        "query_condition": {"type": "metric", "metric_id": metric.id, "filter": []},
        "source": {"type": "instance", "values": ["('h1',)"]},
        "schedule": {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "group_algorithm": "avg",
        "algorithm": "avg_over_time",
        "group_by": ["instance_id"],
        "enable_alerts": ["threshold"],
        "threshold": [{"level": "critical", "method": ">", "value": 80}],
        "metric_unit": "percent",
        "calculation_unit": "percent",
        "threshold_unit": "percent",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_stock_payload_without_new_fields_defaults_absolute(metric_ctx):
    serializer = MonitorPolicySerializer(data=_payload(metric_ctx))
    assert serializer.is_valid(), serializer.errors
    instance = serializer.save()
    assert instance.compare_mode == "absolute"
    assert instance.compare_value_kind == ""
    assert instance.recovery_threshold == {}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "compare_mode,kind",
    [
        ("previous_window", "delta"),
        ("previous_window", "percent"),
        ("offset_1h", "percent"),
        ("offset_1h", "ratio"),
        ("offset_24h", "percent"),
        ("offset_24h", "ratio"),
        ("offset_7d", "percent"),
        ("offset_30d", "ratio"),
        ("baseline_4w", "delta"),
    ],
)
def test_legal_compare_combinations_accepted(metric_ctx, compare_mode, kind):
    payload = _payload(
        metric_ctx,
        algorithm="p95_over_time",
        compare_mode=compare_mode,
        compare_value_kind=kind,
    )
    if kind in {"percent", "ratio"}:
        payload["threshold_unit"] = "percent" if kind == "percent" else ""
        payload["calculation_unit"] = "percent"
    serializer = MonitorPolicySerializer(data=payload)
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_accepts_stddev_count_if_and_per_series(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(metric_ctx, algorithm="stddev_over_time")
    )
    assert serializer.is_valid(), serializer.errors

    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            algorithm="count_if_over_time",
            count_predicate={"method": ">", "value": 80},
        )
    )
    assert serializer.is_valid(), serializer.errors

    serializer = MonitorPolicySerializer(
        data=_payload(metric_ctx, algorithm="rate")
    )
    assert serializer.is_valid(), serializer.errors

    serializer = MonitorPolicySerializer(
        data=_payload(metric_ctx, algorithm="changes")
    )
    assert serializer.is_valid(), serializer.errors

    serializer = MonitorPolicySerializer(
        data=_payload(metric_ctx, algorithm="deriv")
    )
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_rejects_kind_mismatch(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            compare_mode="offset_1h",
            compare_value_kind="delta",
        )
    )
    assert not serializer.is_valid()
    assert "compare_value_kind" in serializer.errors


@pytest.mark.django_db
def test_rejects_timeleft_with_quantile(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            algorithm="p95_over_time",
            compare_mode="timeleft",
            compare_value_kind="hours",
            forecast_target=90,
        )
    )
    assert not serializer.is_valid()
    assert "algorithm" in serializer.errors


@pytest.mark.django_db
def test_accepts_timeleft_with_last_over_time(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            algorithm="last_over_time",
            compare_mode="timeleft",
            compare_value_kind="hours",
            forecast_target=90,
            forecast_lookback={"type": "hour", "value": 1},
            threshold=[{"level": "warning", "method": "<", "value": 2}],
        )
    )
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_accepts_timeleft_target_unit_in_same_system(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            algorithm="last_over_time",
            compare_mode="timeleft",
            compare_value_kind="hours",
            metric_unit="bytes",
            calculation_unit="bytes",
            forecast_target=1,
            forecast_target_unit="gibibytes",
            threshold=[{"level": "warning", "method": "<", "value": 24}],
        )
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["forecast_target_unit"] == "gibibytes"


@pytest.mark.django_db
def test_rejects_timeleft_target_unit_outside_metric_system(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            algorithm="last_over_time",
            compare_mode="timeleft",
            compare_value_kind="hours",
            metric_unit="bytes",
            calculation_unit="bytes",
            forecast_target=90,
            forecast_target_unit="percent",
            threshold=[{"level": "warning", "method": "<", "value": 24}],
        )
    )
    assert not serializer.is_valid()
    assert "forecast_target_unit" in serializer.errors


@pytest.mark.django_db
def test_clears_forecast_target_unit_when_not_timeleft(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(metric_ctx, forecast_target_unit="gibibytes")
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["forecast_target_unit"] == ""


@pytest.mark.django_db
def test_rejects_timeleft_with_high_side_threshold(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            algorithm="last_over_time",
            compare_mode="timeleft",
            compare_value_kind="hours",
            forecast_target=90,
            threshold=[{"level": "warning", "method": ">", "value": 2}],
        )
    )
    assert not serializer.is_valid()
    assert "threshold" in serializer.errors


@pytest.mark.django_db
@pytest.mark.parametrize("lookback", ["1h", [1], 4])
def test_rejects_timeleft_with_non_dict_lookback(metric_ctx, lookback):
    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            algorithm="last_over_time",
            compare_mode="timeleft",
            compare_value_kind="hours",
            forecast_target=90,
            forecast_lookback=lookback,
        )
    )
    assert not serializer.is_valid()
    assert "forecast_lookback" in serializer.errors


@pytest.mark.django_db
def test_rejects_count_if_with_compare_window(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            algorithm="count_if_over_time",
            compare_mode="previous_window",
            compare_value_kind="delta",
            count_predicate={"method": ">", "value": 80},
        )
    )
    assert not serializer.is_valid()


@pytest.mark.django_db
def test_rejects_rate_when_base_query_already_has_rate(metric_ctx):
    payload = _payload(
        metric_ctx,
        algorithm="rate",
        query_condition={
            "type": "metric",
            "metric_id": metric_ctx["rate_metric"].id,
            "filter": [],
        },
    )
    serializer = MonitorPolicySerializer(data=payload)
    assert not serializer.is_valid()


@pytest.mark.django_db
def test_rejects_per_series_with_formula(formula_metrics=None):
    obj = MonitorObject.objects.create(name="FormulaRateObj", level="base")
    plugin = MonitorPlugin.objects.create(name="FormulaRatePlugin")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    metric_a = Metric.objects.create(
        monitor_object=obj, monitor_plugin=plugin, metric_group=group,
        name="a", query="a{__$labels__}", instance_id_keys=["instance_id"],
    )
    metric_b = Metric.objects.create(
        monitor_object=obj, monitor_plugin=plugin, metric_group=group,
        name="b", query="b{__$labels__}", instance_id_keys=["instance_id"],
    )
    serializer = MonitorPolicySerializer(
        data={
            "name": "formula-rate",
            "alert_name": "x",
            "monitor_object": obj.id,
            "query_condition": {
                "type": "formula",
                "result_name": "比值",
                "expression": "a / b",
                "queries": [
                    {"ref": "a", "metric_id": metric_a.id, "filter": [], "group_algorithm": "avg", "group_by": ["instance_id"]},
                    {"ref": "b", "metric_id": metric_b.id, "filter": [], "group_algorithm": "avg", "group_by": ["instance_id"]},
                ],
            },
            "source": {"type": "instance", "values": ["('h1',)"]},
            "schedule": {"type": "min", "value": 5},
            "period": {"type": "min", "value": 5},
            "group_algorithm": "avg",
            "algorithm": "rate",
            "group_by": ["instance_id"],
            "enable_alerts": ["threshold"],
            "threshold": [{"level": "critical", "method": ">", "value": 1}],
            "calculation_unit": "percent",
            "threshold_unit": "percent",
        }
    )
    assert not serializer.is_valid()


@pytest.mark.django_db
def test_rejects_enum_with_new_algorithm_or_compare(metric_ctx):
    payload = _payload(
        metric_ctx,
        algorithm="p95_over_time",
        query_condition={
            "type": "metric",
            "metric_id": metric_ctx["enum_metric"].id,
            "filter": [],
        },
        metric_unit="",
        calculation_unit="",
        threshold_unit="",
    )
    serializer = MonitorPolicySerializer(data=payload)
    assert not serializer.is_valid()
    assert "algorithm" in serializer.errors

    payload = _payload(
        metric_ctx,
        algorithm="avg_over_time",
        compare_mode="offset_1h",
        compare_value_kind="percent",
        query_condition={
            "type": "metric",
            "metric_id": metric_ctx["enum_metric"].id,
            "filter": [],
        },
        metric_unit="",
        calculation_unit="",
        threshold_unit="",
    )
    serializer = MonitorPolicySerializer(data=payload)
    assert not serializer.is_valid()
    assert "compare_mode" in serializer.errors


@pytest.mark.django_db
def test_rejects_period_equal_to_offset(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            period={"type": "hour", "value": 1},
            compare_mode="offset_1h",
            compare_value_kind="percent",
        )
    )
    assert not serializer.is_valid()
    assert "compare_mode" in serializer.errors


@pytest.mark.django_db
def test_rejects_recovery_threshold_same_side(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            recovery_threshold={"method": ">", "value": 70},
        )
    )
    assert not serializer.is_valid()
    assert "recovery_threshold" in serializer.errors


@pytest.mark.django_db
def test_accepts_recovery_threshold_opposite_side(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            recovery_threshold={"method": "<", "value": 70},
        )
    )
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_rejects_no_data_detection_shorter_than_recovery(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            no_data_period={"type": "min", "value": 2},
            no_data_recovery_period={"type": "min", "value": 10},
            no_data_level="warning",
        )
    )
    assert not serializer.is_valid()
    assert "no_data_period" in serializer.errors


@pytest.mark.django_db
def test_trap_clears_new_fields(metric_ctx):
    serializer = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            collect_type="trap",
            query_condition={"type": "pmq", "query": "trap"},
            compare_mode="offset_1h",
            compare_value_kind="percent",
            recovery_threshold={"method": "<", "value": 1},
            forecast_target=90,
            metric_unit="",
            calculation_unit="",
            threshold_unit="",
            threshold=[],
        )
    )
    assert serializer.is_valid(), serializer.errors
    instance = serializer.save()
    assert instance.compare_mode == "absolute"
    assert instance.compare_value_kind == ""
    assert instance.recovery_threshold == {}
    assert instance.forecast_target is None
