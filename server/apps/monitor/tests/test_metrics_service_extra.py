"""Metrics 服务补充测试。

聚焦 step 解析、缺失点填充、按实例查询、补充指标单位转换、有效 instance_id_keys。
VictoriaMetricsAPI mock。
"""

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.metrics import Metrics


class TestParseStepToSeconds:
    def test_int_seconds(self):
        assert Metrics.parse_step_to_seconds(30) == 30

    def test_float_seconds(self):
        assert Metrics.parse_step_to_seconds(30.7) == 30

    def test_digit_string(self):
        assert Metrics.parse_step_to_seconds("45") == 45

    @pytest.mark.parametrize("step,expected", [
        ("5m", 300), ("2h", 7200), ("1d", 86400), ("1w", 604800), ("10s", 10),
    ])
    def test_duration_units(self, step, expected):
        assert Metrics.parse_step_to_seconds(step) == expected

    def test_none_raises(self):
        with pytest.raises(ValueError):
            Metrics.parse_step_to_seconds(None)

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            Metrics.parse_step_to_seconds(0)
        with pytest.raises(ValueError):
            Metrics.parse_step_to_seconds("0m")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            Metrics.parse_step_to_seconds("abc")
        with pytest.raises(ValueError):
            Metrics.parse_step_to_seconds("")


class TestFillMissingPoints:
    def test_fills_gaps_with_none(self):
        data = [{"metric": {}, "values": [[0, "1"], [120, "3"]]}]
        Metrics.fill_missing_points(0, 120, 60, data)
        vals = data[0]["values"]
        # 0, 60, 120 三个点；60 处原本缺失，填 None
        ts = [v[0] for v in vals]
        assert 60.0 in ts
        midpoint = [v for v in vals if v[0] == 60.0][0]
        assert midpoint[1] is None

    def test_empty_values_unchanged(self):
        data = [{"metric": {}, "values": []}]
        Metrics.fill_missing_points(0, 60, 60, data)
        assert data[0]["values"] == []


class TestGetMetrics:
    def test_delegates_to_vm_query(self, mocker):
        vm = mocker.patch("apps.monitor.services.metrics.VictoriaMetricsAPI")
        vm.return_value.query.return_value = {"data": {"result": [1]}}
        assert Metrics.get_metrics("up") == {"data": {"result": [1]}}
        vm.return_value.query.assert_called_once_with("up")


class TestQueryMetricByInstance:
    def test_builds_grouped_query(self, mocker):
        vm = mocker.patch("apps.monitor.services.metrics.VictoriaMetricsAPI")
        vm.return_value.query.return_value = {"data": {"result": []}}
        Metrics.query_metric_by_instance(
            "cpu{__$labels__}", "('h1', 'eth0')", ["name", "iface"],
            [{"name": "iface"}],
        )
        called = vm.return_value.query.call_args.args[0]
        assert 'name="h1"' in called and 'iface="eth0"' in called
        assert called.startswith("any(") and "by (iface)" in called

    def test_no_dimensions_no_group_by(self, mocker):
        vm = mocker.patch("apps.monitor.services.metrics.VictoriaMetricsAPI")
        vm.return_value.query.return_value = {"data": {"result": []}}
        Metrics.query_metric_by_instance("cpu{__$labels__}", "('h1',)", ["name"], [])
        called = vm.return_value.query.call_args.args[0]
        assert "by (" not in called
        assert called == 'any(cpu{name="h1"})'

    def test_missing_instance_id_keys_raises(self):
        with pytest.raises(BaseAppException):
            Metrics.query_metric_by_instance("cpu", "('h1',)", [], [])


@pytest.mark.django_db
class TestConvertInstanceListMetrics:
    def _obj_with_metric(self, unit="bytes", data_type="Number", supplementary=None):
        obj = MonitorObject.objects.create(
            name="CILObj", level="base",
            supplementary_indicators=supplementary or ["disk"],
            display_fields=[],
        )
        plugin = MonitorPlugin.objects.create(name="CILPlugin")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        Metric.objects.create(
            monitor_object=obj, monitor_plugin=plugin, metric_group=group,
            name="disk", unit=unit, data_type=data_type,
        )
        return obj

    def test_empty_instances_returned(self):
        assert Metrics.convert_instance_list_metrics(1, []) == []

    def test_missing_object_returns_input(self):
        instances = [{"disk": "1024"}]
        assert Metrics.convert_instance_list_metrics(999999, instances) == instances

    def test_converts_supplementary_value(self):
        obj = self._obj_with_metric(unit="bytes", data_type="Number")
        instances = [{"disk": "2048"}]
        out = Metrics.convert_instance_list_metrics(obj.id, instances)
        assert isinstance(out[0]["disk"], dict)
        assert "unit" in out[0]["disk"]

    def test_enum_wraps_value_with_empty_unit(self):
        obj = self._obj_with_metric(unit='[{"id":1,"name":"on"}]', data_type="Enum")
        instances = [{"disk": "1"}]
        out = Metrics.convert_instance_list_metrics(obj.id, instances)
        assert out[0]["disk"] == {"value": "1", "unit": ""}


@pytest.mark.django_db
class TestGetEffectiveMetricInstanceIdKeys:
    def test_uses_metric_keys(self):
        obj = MonitorObject.objects.create(name="EffObj", level="base", instance_id_keys=["instance_id"])
        plugin = MonitorPlugin.objects.create(name="EffPlugin")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        metric = Metric.objects.create(
            monitor_object=obj, monitor_plugin=plugin, metric_group=group,
            name="m", instance_id_keys=["instance_id", "device"],
        )
        assert Metrics.get_effective_metric_instance_id_keys(metric) == ["instance_id", "device"]

    def test_falls_back_to_monitor_object_keys(self):
        obj = MonitorObject.objects.create(name="EffObj2", level="base", instance_id_keys=["instance_id"])
        plugin = MonitorPlugin.objects.create(name="EffPlugin2")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        metric = Metric.objects.create(
            monitor_object=obj, monitor_plugin=plugin, metric_group=group,
            name="m", instance_id_keys=[],
        )
        assert Metrics.get_effective_metric_instance_id_keys(metric) == ["instance_id"]

    def test_strict_raises_when_all_empty(self):
        obj = MonitorObject.objects.create(name="EffObj3", level="base", instance_id_keys=[])
        plugin = MonitorPlugin.objects.create(name="EffPlugin3")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        metric = Metric.objects.create(
            monitor_object=obj, monitor_plugin=plugin, metric_group=group,
            name="m", instance_id_keys=[],
        )
        with pytest.raises(BaseAppException):
            Metrics.get_effective_metric_instance_id_keys(metric)
