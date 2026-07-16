"""PolicyPreviewService 规格测试。

聚焦查询构建、单位换算、参数校验、VM 错误抛出。METHOD/VM 边界 mock。
"""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.policy_preview import PolicyPreviewService


class TestRequireHelpers:
    def test_require_dict_missing(self):
        with pytest.raises(BaseAppException):
            PolicyPreviewService({})._require_dict("query_condition")

    def test_require_value_missing(self):
        with pytest.raises(BaseAppException):
            PolicyPreviewService({})._require_value("algorithm")

    def test_require_string_list_dedups_and_trims(self):
        svc = PolicyPreviewService({"group_by": [" a ", "a", "b", ""]})
        assert svc._require_string_list("group_by") == ["a", "b"]

    def test_require_string_list_all_empty_raises(self):
        with pytest.raises(BaseAppException):
            PolicyPreviewService({"group_by": ["", "  "]})._require_string_list("group_by")


class TestFormatPeriod:
    def test_units(self):
        svc = PolicyPreviewService({})
        assert svc._format_period({"type": "min", "value": 5}) == "5m"
        assert svc._format_period({"type": "hour", "value": 1}) == "1h"
        assert svc._format_period({"type": "day", "value": 2}) == "2d"

    def test_missing_value(self):
        with pytest.raises(BaseAppException):
            PolicyPreviewService({})._format_period({"type": "min"})

    def test_invalid_type(self):
        with pytest.raises(BaseAppException):
            PolicyPreviewService({})._format_period({"type": "week", "value": 1})


class TestPreviewPoints:
    def test_default(self):
        assert PolicyPreviewService({})._preview_points() == 30

    def test_custom(self):
        assert PolicyPreviewService({"preview": {"duration_points": 5}})._preview_points() == 5

    def test_invalid_falls_back(self):
        assert PolicyPreviewService({"preview": {"duration_points": "x"}})._preview_points() == 30

    def test_minimum_one(self):
        # 负值被 max(1, ...) 钳制到 1
        assert PolicyPreviewService({"preview": {"duration_points": -5}})._preview_points() == 1

    def test_zero_is_falsy_uses_default(self):
        # 0 经 `or 30` 退化为默认 30
        assert PolicyPreviewService({"preview": {"duration_points": 0}})._preview_points() == 30


class TestEscapeRegexValue:
    def test_escapes_special_chars(self):
        out = PolicyPreviewService._escape_regex_value("a.b*c")
        assert out == r"a\.b\*c"

    def test_none_becomes_empty(self):
        assert PolicyPreviewService._escape_regex_value(None) == ""


class TestRaiseForVmError:
    def test_success_no_raise(self):
        PolicyPreviewService._raise_for_vm_error({"status": "success"})
        PolicyPreviewService._raise_for_vm_error({})

    def test_error_raises(self):
        with pytest.raises(BaseAppException):
            PolicyPreviewService._raise_for_vm_error({"status": "error", "error": "boom"})


class TestBuildMetricQuery:
    def test_pmq_returns_query(self):
        svc = PolicyPreviewService({})
        q = svc._build_metric_query({"type": "pmq", "query": "up"})
        assert q == "up"

    def test_pmq_missing_query_raises(self):
        svc = PolicyPreviewService({})
        with pytest.raises(BaseAppException):
            svc._build_metric_query({"type": "pmq"})

    def test_metric_missing_id_raises(self):
        svc = PolicyPreviewService({})
        with pytest.raises(BaseAppException):
            svc._build_metric_query({"type": "metric"})

    @pytest.mark.django_db
    def test_metric_substitutes_filters(self):
        obj = MonitorObject.objects.create(name="PPObj", level="base")
        plugin = MonitorPlugin.objects.create(name="PPPlugin")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        metric = Metric.objects.create(
            monitor_object=obj, monitor_plugin=plugin, metric_group=group,
            name="cpu", query="cpu{__$labels__}", instance_id_keys=["instance_id"],
        )
        svc = PolicyPreviewService({"preview": {"instance_id_values": ["h1"]}})
        q = svc._build_metric_query({"type": "metric", "metric_id": metric.id, "filter": []})
        assert 'instance_id=~"h1"' in q

    @pytest.mark.django_db
    def test_metric_not_found_raises(self):
        svc = PolicyPreviewService({})
        with pytest.raises(BaseAppException):
            svc._build_metric_query({"type": "metric", "metric_id": 999999})


class TestPreviewThreshold:
    def test_keeps_threshold_copy_in_threshold_unit(self):
        thresholds = [{"level": "critical", "method": ">", "value": -2}]
        svc = PolicyPreviewService(
            {
                "threshold": thresholds,
                "threshold_unit": "kibibytes",
                "calculation_unit": "bytes",
            }
        )

        converted = svc._preview_thresholds()

        assert converted[0]["value"] == -2
        assert converted is not thresholds
        assert thresholds[0]["value"] == -2

    def test_empty_thresholds_are_supported(self):
        assert PolicyPreviewService({})._preview_thresholds() == []


class TestPreviewEndToEnd:
    def test_preview_pmq(self, mocker):
        svc = PolicyPreviewService({
            "query_condition": {"type": "pmq", "query": "up"},
            "period": {"type": "min", "value": 5},
            "algorithm": "max",
            "group_by": ["instance_id"],
        })
        mocker.patch.dict(
            "apps.monitor.services.policy_preview.METHOD",
            {"max": mocker.Mock(return_value={"status": "success", "data": {"result": []}})},
            clear=False,
        )
        out = svc.preview()
        assert "by (instance_id)" in out["query"]
        assert out["data"]["data"]["result"] == []
        assert out["warnings"] == []

    def test_preview_pmq_converts_metric_values_to_threshold_unit(self, mocker):
        threshold = [{"level": "critical", "method": ">", "value": 2}]
        vm_response = {
            "status": "success",
            "data": {"result": [{"values": [[1, "2048"]]}]},
        }
        original_response = deepcopy(vm_response)
        svc = PolicyPreviewService(
            {
                "query_condition": {"type": "pmq", "query": "disk_used"},
                "period": {"type": "min", "value": 5},
                "algorithm": "max",
                "group_by": ["instance_id"],
                "metric_unit": "bytes",
                "calculation_unit": "bytes",
                "threshold_unit": "kibibytes",
                "threshold": threshold,
            }
        )
        mocker.patch.dict(
            "apps.monitor.services.policy_preview.METHOD",
            {"max": mocker.Mock(return_value=vm_response)},
            clear=False,
        )

        out = svc.preview()

        assert out["chart_unit"] == "kibibytes"
        assert out["data"]["unit"] == "KiB"
        assert out["data"]["data"]["result"][0]["values"] == [[1, "2.0"]]
        assert out["threshold"] == threshold
        assert out["threshold"] is not threshold
        assert vm_response == original_response

    def test_preview_formula_converts_calculation_values_to_threshold_unit(
        self, mocker
    ):
        vm_response = {
            "status": "success",
            "data": {"result": [{"values": [[1, "2048"]]}]},
        }
        svc = PolicyPreviewService(
            {
                "query_condition": {"type": "formula"},
                "period": {"type": "min", "value": 5},
                "algorithm": "max",
                "calculation_unit": "bytes",
                "threshold_unit": "kibibytes",
                "preview": {"instance_id_values": ["host-1"]},
            }
        )
        mocker.patch.object(
            svc, "_build_formula_instance_filters", return_value={}
        )
        mocker.patch(
            "apps.monitor.services.policy_preview.build_formula_query",
            return_value=SimpleNamespace(
                query="formula_query", group_by=["instance_id"], warnings=[]
            ),
        )
        mocker.patch(
            "apps.monitor.services.policy_preview.query_formula_policy_metrics",
            return_value=vm_response,
        )

        out = svc.preview()

        assert out["chart_unit"] == "kibibytes"
        assert out["data"]["data"]["result"][0]["values"] == [[1, "2.0"]]

    def test_preview_invalid_algorithm(self):
        svc = PolicyPreviewService({
            "query_condition": {"type": "pmq", "query": "up"},
            "period": {"type": "min", "value": 5},
            "algorithm": "bogus",
            "group_by": ["instance_id"],
        })
        with pytest.raises(BaseAppException):
            svc.preview()
