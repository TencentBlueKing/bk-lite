"""MetricQueryService 规格测试。

聚焦查询语句格式化、周期换算、单位转换、聚合结果格式化、枚举映射等逻辑。
真实外部边界 VictoriaMetricsAPI / METHOD 通过 mock 替换，返回真实形态假数据。
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.alert_policy import AlertConstants
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
        threshold_unit="",
        compare_mode="absolute",
        compare_value_kind="",
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

    def test_points_keep_period_step(self):
        svc = MetricQueryService(_policy(), {})
        assert svc.format_period({"type": "min", "value": 10}, points=2) == "10m"

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
            _policy(
                query_condition={
                    "type": "metric",
                    "metric_id": 9,
                    "filter": [
                        {"name": "instance_id", "method": "=", "value": "h1"},
                    ],
                }
            ),
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
            monitor_object=obj,
            monitor_plugin=plugin,
            metric_group=group,
            name="m",
            query="m{__$labels__}",
            instance_id_keys=["instance_id", "device"],
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
    def test_calls_query_range_with_compiled_comparison_query(self, mocker):
        svc = MetricQueryService(_policy(algorithm="max", group_by=["instance_id"]), {})
        vm = mocker.patch(
            "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
        )
        vm.return_value.query_range.return_value = {"data": {"result": []}}
        result = svc.query_comparison_metrics({"type": "min", "value": 5})
        assert result == {"data": {"result": []}}
        args = vm.return_value.query_range.call_args.args
        assert args[0] == "max_over_time((max(up) by (instance_id))[5m:10s])"
        assert args[3] == "5m"
        assert args[2] - args[1] == 300

    def test_existence_query_ignores_compare_mode(self, mocker):
        svc = MetricQueryService(
            _policy(
                algorithm="p95_over_time",
                group_algorithm="avg",
                compare_mode="offset_1h",
                compare_value_kind="percent",
                group_by=["instance_id"],
            ),
            {},
        )
        vm = mocker.patch(
            "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
        )
        vm.return_value.query_range.return_value = {"data": {"result": []}}
        svc.query_existence_metrics({"type": "min", "value": 5})
        args = vm.return_value.query_range.call_args.args
        assert args[0] == (
            "quantile_over_time(0.95, ((avg(up) by (instance_id))[5m:10s]))"
        )
        assert "offset" not in args[0]

    def test_existence_rate_uses_last_over_time(self, mocker):
        svc = MetricQueryService(
            _policy(
                algorithm="rate",
                group_algorithm="avg",
                group_by=["instance_id"],
            ),
            {},
        )
        vm = mocker.patch(
            "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
        )
        vm.return_value.query_range.return_value = {"data": {"result": []}}
        svc.query_existence_metrics({"type": "min", "value": 5})
        args = vm.return_value.query_range.call_args.args
        assert args[0] == "last_over_time((avg(up) by (instance_id))[5m:10s])"
        assert "rate(" not in args[0]

    def test_comparison_query_applies_offset_percent(self, mocker):
        svc = MetricQueryService(
            _policy(
                algorithm="avg_over_time",
                group_algorithm="avg",
                compare_mode="offset_1h",
                compare_value_kind="percent",
                group_by=["instance_id"],
            ),
            {},
        )
        vm = mocker.patch(
            "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
        )
        vm.return_value.query_range.return_value = {"data": {"result": []}}
        svc.query_comparison_metrics({"type": "min", "value": 5})
        query = vm.return_value.query_range.call_args.args[0]
        window = "avg_over_time((avg(up) by (instance_id))[5m:10s])"
        assert query == f"({window} - {window} offset 1h) / ({window} offset 1h) * 100"

    def test_invalid_algorithm_raises(self):
        svc = MetricQueryService(_policy(algorithm="bogus"), {})
        with pytest.raises(BaseAppException):
            svc.query_comparison_metrics({"type": "min", "value": 5})


def _host_object():
    return SimpleNamespace(instance_id_keys=["instance_id"])


def _metric_policy(instances_map, **kwargs):
    base = dict(
        query_condition={"type": "metric", "metric_id": 9, "filter": []},
        group_by=["instance_id"],
        algorithm="max",
        monitor_object=_host_object(),
    )
    base.update(kwargs)
    svc = MetricQueryService(_policy(**base), instances_map)
    svc.metric = SimpleNamespace(
        query='cpu{instance_type="os", __$labels__}', data_type="Number", unit=""
    )
    return svc


class TestScopePushdown:
    """策略实例范围必须编进 PromQL selector，而不是回包后在 Python 里丢弃（issue #5777）。"""

    def _patch_vm(self, mocker):
        vm = mocker.patch("apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI")
        vm.return_value.query_range.return_value = {"status": "success", "data": {"result": []}}
        return vm.return_value.query_range

    def test_metric_query_injects_instance_matcher(self, mocker):
        query_range = self._patch_vm(mocker)
        svc = _metric_policy({"('h-1',)": "主机1", "('h2',)": "主机2"})
        svc.query_comparison_metrics({"type": "min", "value": 5})
        query = query_range.call_args.args[0]
        assert 'cpu{instance_type="os", instance_id=~"h\\\\-1|h2"}' in query
        assert query.endswith("by (instance_id))[5m:10s])")

    def test_metric_query_combines_scope_with_policy_filter(self, mocker):
        query_range = self._patch_vm(mocker)
        svc = _metric_policy(
            {"('h1',)": "主机1"},
            query_condition={
                "type": "metric",
                "metric_id": 9,
                "filter": [{"name": "path", "method": "=", "value": "/"}],
            },
        )
        svc.query_existence_metrics({"type": "min", "value": 5})
        query = query_range.call_args.args[0]
        assert 'instance_id=~"h1",path="/"' in query

    def test_no_source_keeps_unscoped_query(self, mocker):
        query_range = self._patch_vm(mocker)
        svc = _metric_policy({})
        svc.query_comparison_metrics({"type": "min", "value": 5})
        assert 'cpu{instance_type="os", }' in query_range.call_args.args[0]

    def test_pmq_query_is_not_rewritten(self, mocker):
        query_range = self._patch_vm(mocker)
        svc = MetricQueryService(
            _policy(query_condition={"type": "pmq", "query": "up"}, monitor_object=_host_object()),
            {"('h1',)": "主机1"},
        )
        svc.query_comparison_metrics({"type": "min", "value": 5})
        assert query_range.call_count == 1
        assert "max_over_time((max(up) by (instance_id))" in query_range.call_args.args[0]

    def test_derivative_object_scopes_every_identity_key(self, mocker):
        query_range = self._patch_vm(mocker)
        svc = _metric_policy(
            {"('cluster-a', 'orders-7f9')": "orders", "('cluster-a', 'pay-1')": "pay"},
            monitor_object=SimpleNamespace(instance_id_keys=["instance_id", "pod"]),
            group_by=["instance_id", "pod"],
        )
        svc.query_comparison_metrics({"type": "min", "value": 5})
        query = query_range.call_args.args[0]
        assert 'instance_id=~"cluster\\\\-a"' in query
        assert 'pod=~"orders\\\\-7f9|pay\\\\-1"' in query

    def test_identity_shorter_than_keys_falls_back_to_unscoped(self, mocker):
        query_range = self._patch_vm(mocker)
        svc = _metric_policy(
            {"('cluster-a',)": "c"},
            monitor_object=SimpleNamespace(instance_id_keys=["instance_id", "pod"]),
        )
        svc.query_comparison_metrics({"type": "min", "value": 5})
        assert "=~" not in query_range.call_args.args[0]

    def test_large_scope_is_batched_and_merged(self, mocker):
        mocker.patch.object(AlertConstants, "SCAN_SCOPE_BATCH_SIZE", 2)
        vm = mocker.patch("apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI")
        seen = []

        def fake_query_range(query, start, end, step):
            seen.append(query)
            return {
                "status": "success",
                "data": {"resultType": "matrix", "result": [{"metric": {"q": len(seen)}, "values": []}]},
            }

        vm.return_value.query_range.side_effect = fake_query_range
        svc = _metric_policy({f"('h{i}',)": f"主机{i}" for i in range(5)})
        out = svc.query_comparison_metrics({"type": "min", "value": 5})

        assert len(seen) == 3
        assert 'instance_id=~"h0|h1"' in seen[0]
        assert 'instance_id=~"h2|h3"' in seen[1]
        assert 'instance_id=~"h4"' in seen[2]
        assert out["status"] == "success"
        assert out["data"]["resultType"] == "matrix"
        assert [item["metric"]["q"] for item in out["data"]["result"]] == [1, 2, 3]

    def test_batch_error_payload_is_returned_as_is(self, mocker):
        mocker.patch.object(AlertConstants, "SCAN_SCOPE_BATCH_SIZE", 1)
        vm = mocker.patch("apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI")
        error = {"status": "error", "errorType": "execution", "error": "boom"}
        vm.return_value.query_range.side_effect = [
            {"status": "success", "data": {"result": [{"metric": {}, "values": []}]}},
            error,
        ]
        svc = _metric_policy({"('h1',)": "a", "('h2',)": "b"})
        assert svc.query_comparison_metrics({"type": "min", "value": 5}) == error


class TestQueryPolicyWindowMetrics:
    def test_scopes_to_given_instances_and_end_time(self, mocker):
        vm = mocker.patch("apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI")
        vm.return_value.query_range.return_value = {"data": {"result": []}}
        svc = _metric_policy({f"('h{i}',)": "x" for i in range(10)})
        end = int(svc.policy.last_run_time.timestamp()) - 300

        svc.query_policy_window_metrics({"type": "min", "value": 5}, ["('h3',)"], end_timestamp=end)

        query, start, end_arg, step = vm.return_value.query_range.call_args.args
        assert 'instance_id=~"h3"' in query
        assert "by (instance_id)" in query
        assert "max_over_time(" in query
        assert end_arg == end
        assert end_arg - start == 300
        assert step == "5m"

    def test_empty_instance_list_does_not_query(self, mocker):
        vm = mocker.patch("apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI")
        svc = _metric_policy({"('h1',)": "x"})
        assert svc.query_policy_window_metrics({"type": "min", "value": 5}, []) == {"data": {"result": []}}
        vm.return_value.query_range.assert_not_called()

    def test_none_instances_uses_policy_scope(self, mocker):
        vm = mocker.patch("apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI")
        vm.return_value.query_range.return_value = {"data": {"result": []}}
        svc = _metric_policy({"('h1',)": "x"})
        svc.query_policy_window_metrics({"type": "min", "value": 5})
        assert 'instance_id=~"h1"' in vm.return_value.query_range.call_args.args[0]

    def test_raw_unaggregated_query_is_gone(self):
        assert not hasattr(MetricQueryService, "query_raw_metrics")


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

    def test_percent_skips_metric_unit_conversion(self):
        svc = MetricQueryService(
            _policy(
                metric_unit="bytes",
                calculation_unit="kibibytes",
                compare_mode="offset_1h",
                compare_value_kind="percent",
            ),
            {},
        )
        data = {"data": {"result": [{"values": [[100, "2048"]]}]}}
        out = svc.convert_metric_values(data)
        assert out["data"]["result"][0]["values"] == [[100, "2048"]]
        assert svc.get_effective_calculation_unit() == "percent"
        assert svc.convert_thresholds(
            [{"level": "critical", "method": ">", "value": 50}]
        )[0]["value"] == 50

    def test_mid_series_conversion_failure_keeps_all_original_values(self, mocker):
        svc = MetricQueryService(_policy(metric_unit="bytes", calculation_unit="kibibytes"), {})
        data = {
            "data": {
                "result": [
                    {"metric": {"instance_id": "a"}, "values": [[100, "2048"]]},
                    {"metric": {"instance_id": "b"}, "values": [[100, "2048"]]},
                    {"metric": {"instance_id": "c"}, "values": [[100, "2048"]]},
                ]
            }
        }
        original_values = [[[100, "2048"]], [[100, "2048"]], [[100, "2048"]]]
        calls = {"n": 0}

        def _convert_values(values, _source_unit, _target_unit):
            calls["n"] += 1
            if calls["n"] == 2:
                raise ValueError("conversion failed on second series")
            return [value / 1024 for value in values]

        mocker.patch(
            "apps.monitor.tasks.services.policy_scan.metric_query.UnitConverter.convert_values",
            side_effect=_convert_values,
        )

        out = svc.convert_metric_values(data)
        result_values = [item["values"][0][1] for item in out["data"]["result"]]
        has_converted = any(float(value) == pytest.approx(2.0) for value in result_values)
        has_raw = any(float(value) == pytest.approx(2048) for value in result_values)

        assert not (has_converted and has_raw), f"mixed units: {result_values}"
        for result, expected in zip(out["data"]["result"], original_values):
            assert result["values"] == expected
        assert data["data"]["result"][0]["values"] == [[100, "2048"]]
        assert data["data"]["result"][1]["values"] == [[100, "2048"]]
        assert data["data"]["result"][2]["values"] == [[100, "2048"]]


class TestConvertThresholds:
    def test_legacy_empty_threshold_unit_uses_calculation_unit(self):
        svc = MetricQueryService(
            _policy(calculation_unit="bytes", threshold_unit=""), {}
        )
        original = [{"level": "critical", "method": ">", "value": 10}]

        converted = svc.convert_thresholds(original)

        assert converted == original
        assert converted is not original

    def test_gibibytes_threshold_converts_to_bytes_without_mutating_policy(self):
        svc = MetricQueryService(
            _policy(calculation_unit="bytes", threshold_unit="gibibytes"), {}
        )
        original = [{"level": "critical", "method": "<", "value": -2}]

        converted = svc.convert_thresholds(original)

        assert converted[0]["value"] == pytest.approx(-2 * 1024**3)
        assert original[0]["value"] == -2

    def test_cross_system_threshold_raises(self):
        svc = MetricQueryService(
            _policy(calculation_unit="bytes", threshold_unit="percent"), {}
        )

        with pytest.raises(BaseAppException, match="不能转换"):
            svc.convert_thresholds(
                [{"level": "critical", "method": ">", "value": 80}]
            )


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
    def test_derivative_dimension_resolves_selected_child_instance(self):
        monitor_object = SimpleNamespace(
            instance_id_keys=["instance_id", "pod"]
        )
        child_id = "('cluster-a', 'orders-7f9')"
        svc = MetricQueryService(
            _policy(group_by=["pod"], monitor_object=monitor_object),
            {child_id: "orders-7f9"},
        )

        assert svc.get_monitor_instance_id_from_tuple(
            ("orders-7f9",), ["pod"]
        ) == child_id

    def test_groups_by_keys_and_takes_last_value(self):
        svc = MetricQueryService(_policy(group_by=["instance_id"]), {})
        metrics = {
            "data": {
                "result": [
                    {"metric": {"instance_id": "h1"}, "values": [[0, "1"], [10, "5"]]},
                ]
            }
        }
        out = svc.format_aggregation_metrics(metrics)
        assert out["('h1',)"]["value"] == 5.0
        assert out["('h1',)"]["raw_data"]["metric"]["instance_id"] == "h1"

    def test_instances_map_filters_out_unknown(self):
        svc = MetricQueryService(_policy(group_by=["instance_id"]), {"('h1',)": "name"})
        metrics = {
            "data": {
                "result": [
                    {"metric": {"instance_id": "h1"}, "values": [[0, "1"]]},
                    {"metric": {"instance_id": "h2"}, "values": [[0, "2"]]},
                ]
            }
        }
        out = svc.format_aggregation_metrics(metrics)
        assert set(out.keys()) == {"('h1',)"}

    @pytest.mark.parametrize("bad_value", ["inf", "-inf", "nan"])
    def test_skips_non_finite_last_value(self, bad_value):
        svc = MetricQueryService(_policy(group_by=["instance_id"]), {})
        metrics = {
            "data": {
                "result": [
                    {"metric": {"instance_id": "h1"}, "values": [[0, bad_value]]},
                ]
            }
        }

        assert svc.format_aggregation_metrics(metrics) == {}
