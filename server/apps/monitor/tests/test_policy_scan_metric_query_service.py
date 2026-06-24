"""MetricQueryService 规格测试。

聚焦查询语句格式化、周期换算、单位转换、聚合结果格式化、枚举映射等逻辑。
真实外部边界 VictoriaMetricsAPI / METHOD 通过 mock 替换，返回真实形态假数据。
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.tasks.services.policy_scan.metric_query import MetricQueryService


def _policy(**kwargs):
    base = dict(
        id=1,
        query_condition={"type": "pmq", "query": "up"},
        collect_type="",
        group_by=["instance_id"],
        algorithm="max",
        metric_unit="",
        calculation_unit="",
        last_run_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


class TestFormatPeriod:
    def test_min_hour_day(self):
        svc = MetricQueryService(_policy(), {})
        assert svc.format_period({"type": "min", "value": 5}) == "5m"
        assert svc.format_period({"type": "hour", "value": 2}) == "2h"
        assert svc.format_period({"type": "day", "value": 1}) == "1d"

    def test_points_divides_value(self):
        svc = MetricQueryService(_policy(), {})
        assert svc.format_period({"type": "min", "value": 10}, points=2) == "5m"

    def test_empty_period_raises(self):
        svc = MetricQueryService(_policy(), {})
        with pytest.raises(BaseAppException):
            svc.format_period(None)

    def test_invalid_type_raises(self):
        svc = MetricQueryService(_policy(), {})
        with pytest.raises(BaseAppException):
            svc.format_period({"type": "week", "value": 1})


class TestFormatPmq:
    def test_pmq_returns_query_directly(self):
        svc = MetricQueryService(_policy(query_condition={"type": "pmq", "query": "rate(x[5m])"}), {})
        assert svc.format_pmq() == "rate(x[5m])"

    def test_metric_type_substitutes_labels(self):
        svc = MetricQueryService(
            _policy(query_condition={"type": "metric", "metric_id": 9, "filter": [
                {"name": "instance_id", "method": "=", "value": "h1"},
            ]}),
            {},
        )
        svc.metric = SimpleNamespace(query="cpu{__$labels__}", data_type="Number", unit="")
        assert svc.format_pmq() == 'cpu{instance_id="h1"}'

    def test_metric_type_empty_filter(self):
        svc = MetricQueryService(
            _policy(query_condition={"type": "metric", "metric_id": 9, "filter": []}),
            {},
        )
        svc.metric = SimpleNamespace(query="cpu{__$labels__}", data_type="Number", unit="")
        assert svc.format_pmq() == "cpu{}"


@pytest.mark.django_db
class TestSetMonitorObjInstanceKey:
    def test_pmq_trap_uses_source(self):
        svc = MetricQueryService(_policy(query_condition={"type": "pmq"}, collect_type="trap"), {})
        svc.set_monitor_obj_instance_key()
        assert svc.instance_id_keys == ["source"]

    def test_pmq_non_trap_uses_configured_keys(self):
        svc = MetricQueryService(
            _policy(query_condition={"type": "pmq", "instance_id_keys": ["a", "b"]}, collect_type="snmp"),
            {},
        )
        svc.set_monitor_obj_instance_key()
        assert svc.instance_id_keys == ["a", "b"]

    def test_metric_type_loads_from_db(self):
        obj = MonitorObject.objects.create(name="MQObj", level="base")
        plugin = MonitorPlugin.objects.create(name="MQPlugin")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        metric = Metric.objects.create(
            monitor_object=obj, monitor_plugin=plugin, metric_group=group,
            name="m", query="m{__$labels__}", instance_id_keys=["instance_id", "device"],
        )
        svc = MetricQueryService(_policy(query_condition={"type": "metric", "metric_id": metric.id}), {})
        svc.set_monitor_obj_instance_key()
        assert svc.instance_id_keys == ["instance_id", "device"]
        assert svc.metric.id == metric.id

    def test_metric_missing_raises(self):
        svc = MetricQueryService(_policy(query_condition={"type": "metric", "metric_id": 999999}), {})
        with pytest.raises(BaseAppException):
            svc.set_monitor_obj_instance_key()


class TestQueryAggregationMetrics:
    def test_calls_method_with_computed_range(self, mocker):
        svc = MetricQueryService(_policy(algorithm="max", group_by=["instance_id"]), {})
        fake = mocker.patch.dict(
            "apps.monitor.tasks.services.policy_scan.metric_query.METHOD",
            {"max": mocker.Mock(return_value={"data": {"result": []}})},
            clear=False,
        )
        result = svc.query_aggregation_metrics({"type": "min", "value": 5})
        assert result == {"data": {"result": []}}
        method = fake["max"]
        args = method.call_args.args
        # query, start, end, step, group_by
        assert args[0] == "up"
        assert args[3] == "5m"
        assert args[4] == "instance_id"
        # end - start == 300 秒
        assert args[2] - args[1] == 300

    def test_invalid_algorithm_raises(self):
        svc = MetricQueryService(_policy(algorithm="bogus"), {})
        with pytest.raises(BaseAppException):
            svc.query_aggregation_metrics({"type": "min", "value": 5})


class TestQueryRawMetrics:
    def test_uses_vm_query_range(self, mocker):
        svc = MetricQueryService(_policy(), {})
        vm = mocker.patch(
            "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
        )
        vm.return_value.query_range.return_value = {"data": {"result": [1]}}
        out = svc.query_raw_metrics({"type": "min", "value": 5})
        assert out == {"data": {"result": [1]}}
        call = vm.return_value.query_range.call_args.args
        assert call[0] == "up"
        assert call[3] == "5m"


class TestConvertMetricValues:
    def test_disabled_returns_input_unchanged(self):
        svc = MetricQueryService(_policy(metric_unit="", calculation_unit=""), {})
        data = {"data": {"result": [{"values": [[0, "1"]]}]}}
        assert svc.convert_metric_values(data) is data

    def test_not_convertible_returns_unchanged(self):
        svc = MetricQueryService(_policy(metric_unit="bytes", calculation_unit="seconds"), {})
        data = {"data": {"result": [{"values": [[0, "1024"]]}]}}
        out = svc.convert_metric_values(data)
        assert out["data"]["result"][0]["values"] == [[0, "1024"]]

    def test_convertible_scales_values(self):
        # bytes -> kibibytes，1024 bytes = 1 KiB
        svc = MetricQueryService(_policy(metric_unit="bytes", calculation_unit="kibibytes"), {})
        data = {"data": {"result": [{"values": [[100, "2048"], [200, "1024"]]}]}}
        out = svc.convert_metric_values(data)
        vals = out["data"]["result"][0]["values"]
        assert vals[0][0] == 100
        assert float(vals[0][1]) == pytest.approx(2.0)
        assert float(vals[1][1]) == pytest.approx(1.0)


class TestGetDisplayUnit:
    def test_conversion_enabled_uses_calculation_unit(self):
        svc = MetricQueryService(_policy(metric_unit="bytes", calculation_unit="kibibytes"), {})
        assert svc.get_display_unit() == "KiB"

    def test_only_metric_unit(self):
        svc = MetricQueryService(_policy(metric_unit="bytes", calculation_unit=""), {})
        assert svc.get_display_unit() == "B"

    def test_no_unit_returns_empty(self):
        svc = MetricQueryService(_policy(metric_unit="", calculation_unit=""), {})
        assert svc.get_display_unit() == ""


class TestEnumHelpers:
    def test_no_metric_returns_empty(self):
        svc = MetricQueryService(_policy(), {})
        assert svc.get_enum_value_map() == {}
        assert svc.is_enum_metric() is False

    def test_non_enum_returns_empty(self):
        svc = MetricQueryService(_policy(), {})
        svc.metric = SimpleNamespace(data_type="Number", unit="")
        assert svc.get_enum_value_map() == {}
        assert svc.is_enum_metric() is False

    def test_enum_parses_unit_json(self):
        svc = MetricQueryService(_policy(), {})
        svc.metric = SimpleNamespace(
            data_type="Enum",
            unit='[{"id": 1, "name": "up"}, {"id": 0, "name": "down"}]',
        )
        assert svc.get_enum_value_map() == {1: "up", 0: "down"}
        assert svc.is_enum_metric() is True

    def test_enum_bad_json_returns_empty(self):
        svc = MetricQueryService(_policy(), {})
        svc.metric = SimpleNamespace(data_type="Enum", unit="not-json")
        assert svc.get_enum_value_map() == {}


class TestFormatAggregationMetrics:
    def test_groups_by_keys_and_takes_last_value(self):
        svc = MetricQueryService(_policy(group_by=["instance_id"]), {})
        metrics = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[0, "1"], [10, "5"]]},
        ]}}
        out = svc.format_aggregation_metrics(metrics)
        assert out["('h1',)"]["value"] == 5.0
        assert out["('h1',)"]["raw_data"]["metric"]["instance_id"] == "h1"

    def test_instances_map_filters_out_unknown(self):
        svc = MetricQueryService(_policy(group_by=["instance_id"]), {"('h1',)": "name"})
        metrics = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[0, "1"]]},
            {"metric": {"instance_id": "h2"}, "values": [[0, "2"]]},
        ]}}
        out = svc.format_aggregation_metrics(metrics)
        assert set(out.keys()) == {"('h1',)"}
