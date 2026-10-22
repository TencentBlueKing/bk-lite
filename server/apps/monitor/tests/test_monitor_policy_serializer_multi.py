import pytest

from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer


@pytest.fixture
def metric_ctx():
    obj = MonitorObject.objects.create(
        name="MultiSerializerObj",
        level="base",
        instance_id_keys=["instance_id", "container_id"],
    )
    plugin = MonitorPlugin.objects.create(name="MultiSerializerPlugin")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    cpu = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="cpu_usage",
        display_name="CPU 使用率",
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
        unit="bytes",
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
        name="fan_state",
        query="fan_state{__$labels__}",
        instance_id_keys=["instance_id"],
        data_type="Enum",
        unit='[{"id": 1, "name": "up"}]',
    )
    return {
        "obj": obj,
        "cpu": cpu,
        "memory": memory,
        "rate_metric": rate_metric,
        "enum_metric": enum_metric,
    }


def _condition(metric, ref="a", **overrides):
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


def _payload(metric_ctx, queries=None, **overrides):
    cpu = metric_ctx["cpu"]
    memory = metric_ctx["memory"]
    data = {
        "name": "cpu-and-memory",
        "alert_name": "${metric_name} ${a_value}",
        "monitor_object": metric_ctx["obj"].id,
        "query_condition": {
            "type": "multi",
            "result_name": "CPU 与内存双高",
            "combinator": "all",
            "queries": queries
            or [
                _condition(cpu, "a", group_by=["device", "instance_id"]),
                _condition(memory, "b", metric_unit="bytes", calculation_unit="bytes", threshold_unit="bytes"),
            ],
        },
        "source": {"type": "instance", "values": ["('h1',)"]},
        "schedule": {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "enable_alerts": ["threshold"],
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_serializer_mirrors_anchor_and_drops_policy_threshold(metric_ctx):
    serializer = MonitorPolicySerializer(data=_payload(metric_ctx, threshold=[{"level": "warning", "method": ">", "value": 1}]))
    assert serializer.is_valid(), serializer.errors
    policy = serializer.save()

    assert policy.threshold == []
    assert policy.algorithm == "avg_over_time"
    assert policy.group_algorithm == "avg"
    assert policy.group_by == ["instance_id", "device", "container_id"]
    assert policy.compare_mode == "absolute"
    assert policy.compare_value_kind == ""
    assert policy.recovery_threshold == {}
    assert policy.count_predicate == {}
    assert policy.metric_unit == "percent"
    assert policy.query_condition["queries"][0]["group_by"] == ["instance_id", "device", "container_id"]
    assert policy.query_condition["queries"][0]["threshold"][0]["level"] == "critical"
    assert "algorithm" not in _payload(metric_ctx)


@pytest.mark.django_db
def test_serializer_rejects_multi_mode_locks(metric_ctx):
    compare = MonitorPolicySerializer(data=_payload(metric_ctx, compare_mode="previous_window", compare_value_kind="delta"))
    assert not compare.is_valid()
    assert "当前值" in str(compare.errors["compare_mode"])

    timeleft = MonitorPolicySerializer(
        data=_payload(metric_ctx, compare_mode="timeleft", compare_value_kind="hours", forecast_target=100)
    )
    assert not timeleft.is_valid()
    assert "compare_mode" in timeleft.errors

    recovery = MonitorPolicySerializer(
        data=_payload(metric_ctx, recovery_threshold={"method": "<", "value": 70})
    )
    assert not recovery.is_valid()
    assert "恢复阈值" in str(recovery.errors["recovery_threshold"])

    trap = MonitorPolicySerializer(data=_payload(metric_ctx, collect_type="trap"))
    assert not trap.is_valid()
    assert "Trap" in str(trap.errors["collect_type"])


@pytest.mark.django_db
def test_serializer_rejects_rate_on_rate_query_enum_algorithm_and_bad_unit(metric_ctx):
    rate = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            queries=[
                _condition(metric_ctx["rate_metric"], "a", algorithm="rate", metric_unit="bytes", calculation_unit="bytes", threshold_unit="byteps"),
                _condition(metric_ctx["cpu"], "b"),
            ],
        )
    )
    assert not rate.is_valid()
    assert "rate/irate/increase" in str(rate.errors["query_condition"])

    enum_algorithm = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            queries=[
                _condition(metric_ctx["enum_metric"], "a", algorithm="rate", threshold=[{"level": "warning", "method": "=", "value": 1}]),
                _condition(metric_ctx["cpu"], "b"),
            ],
        )
    )
    assert not enum_algorithm.is_valid()
    assert "枚举" in str(enum_algorithm.errors["query_condition"])

    enum_method = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            queries=[
                _condition(metric_ctx["enum_metric"], "a", threshold=[{"level": "warning", "method": ">", "value": 1}]),
                _condition(metric_ctx["cpu"], "b"),
            ],
        )
    )
    assert not enum_method.is_valid()
    assert "=" in str(enum_method.errors["query_condition"])

    unit = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            queries=[
                _condition(metric_ctx["cpu"], "a", threshold_unit="bytes"),
                _condition(metric_ctx["memory"], "b", metric_unit="bytes", calculation_unit="bytes", threshold_unit="bytes"),
            ],
        )
    )
    assert not unit.is_valid()
    assert "不能转换" in str(unit.errors["query_condition"])


def _formula_condition(metric_ctx, **overrides):
    data = {
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
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_serializer_accepts_formula_condition_and_aligns_operand_dimensions(metric_ctx):
    gate = _condition(
        metric_ctx["cpu"],
        "b",
        role="gate",
        threshold=[{"method": ">", "value": 100}],
    )
    serializer = MonitorPolicySerializer(data=_payload(metric_ctx, queries=[_formula_condition(metric_ctx), gate]))
    assert serializer.is_valid(), serializer.errors
    policy = serializer.save()
    saved = policy.query_condition["queries"][0]
    assert policy.metric_unit == ""
    assert policy.calculation_unit == "percent"
    assert policy.threshold == []
    assert saved["metric_name"] == "错误率"
    assert "container_id" in saved["group_by"]
    assert saved["operands"][0]["group_by"] == saved["group_by"]
    assert saved["operands"][1]["group_by"] == saved["group_by"]


@pytest.mark.django_db
def test_serializer_rejects_enum_operand_missing_metric_and_unknown_result_unit(metric_ctx):
    enum_operands = _formula_condition(metric_ctx)
    enum_operands["operands"][1]["metric_id"] = metric_ctx["enum_metric"].id
    enum_policy = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            queries=[enum_operands, _condition(metric_ctx["cpu"], "b", role="gate", threshold=[{"method": ">", "value": 1}])],
        )
    )
    assert not enum_policy.is_valid()
    assert "枚举" in str(enum_policy.errors["query_condition"])

    missing = _formula_condition(metric_ctx)
    missing["operands"][1]["metric_id"] = 999999
    missing_policy = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            queries=[missing, _condition(metric_ctx["cpu"], "b", role="gate", threshold=[{"method": ">", "value": 1}])],
        )
    )
    assert not missing_policy.is_valid()
    assert "操作数指标不存在" in str(missing_policy.errors["query_condition"])

    unknown = _formula_condition(metric_ctx, calculation_unit="not_a_unit", threshold_unit="not_a_unit")
    unknown_policy = MonitorPolicySerializer(
        data=_payload(
            metric_ctx,
            queries=[unknown, _condition(metric_ctx["cpu"], "b", role="gate", threshold=[{"method": ">", "value": 1}])],
        )
    )
    assert not unknown_policy.is_valid()
    assert "结果单位无效" in str(unknown_policy.errors["query_condition"])
