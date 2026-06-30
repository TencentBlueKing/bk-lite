import importlib.util
import importlib
import sys
import types
from pathlib import Path

import pytest


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_policy_methods(monkeypatch, module_name="monitor_policy_preview_policy_methods_test_module", vm_cls=None):
    if vm_cls is None:
        class VictoriaMetricsAPI:
            pass
        vm_cls = VictoriaMetricsAPI

    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=Exception,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.victoriametrics_api",
        VictoriaMetricsAPI=vm_cls,
    )

    return _load_module(
        module_name,
        Path(__file__).resolve().parents[1] / "tasks" / "utils" / "policy_methods.py",
    )


def test_build_two_stage_over_time_query_wraps_complex_expression(monkeypatch):
    module = _load_policy_methods(monkeypatch, "monitor_policy_preview_complex_query_builder_test_module")

    query = module.build_policy_query(
        "avg_over_time",
        '100 - cpu_usage_idle{cpu="cpu-total", instance_type="os", instance_id=~"abc"}',
        "5m",
        "instance_id",
    )

    assert query == (
        'avg_over_time((avg(100 - cpu_usage_idle{cpu="cpu-total", '
        'instance_type="os", instance_id=~"abc"}) by (instance_id))[5m:10s])'
    )


def test_build_two_stage_over_time_query_uses_subquery_resolution(monkeypatch):
    module = _load_policy_methods(monkeypatch, "monitor_policy_preview_simple_query_builder_test_module")

    query = module.build_policy_query(
        "avg_over_time",
        'cpu_usage_idle{cpu="cpu-total", instance_id=~"abc"}',
        "5m",
        "instance_id",
    )

    assert query == (
        'avg_over_time((avg(cpu_usage_idle{cpu="cpu-total", '
        'instance_id=~"abc"}) by (instance_id))[5m:10s])'
    )


def test_build_legacy_normal_aggregation_query_maps_to_window_query(monkeypatch):
    module = _load_policy_methods(monkeypatch, "monitor_policy_preview_normal_query_builder_test_module")

    query = module.build_policy_query(
        "avg",
        '100 - cpu_usage_idle{cpu="cpu-total", instance_id=~"abc"}',
        "5m",
        "instance_id",
    )

    assert query == (
        'avg_over_time((avg(100 - cpu_usage_idle{cpu="cpu-total", '
        'instance_id=~"abc"}) by (instance_id))[5m:10s])'
    )


def test_build_two_stage_count_over_time_query_uses_count_grouping(monkeypatch):
    module = _load_policy_methods(monkeypatch, "monitor_policy_preview_count_query_builder_test_module")

    query = module.build_policy_query(
        "count_over_time",
        "interface_info",
        "5m",
        "instance_id",
        "count",
    )

    assert query == "count_over_time((count(interface_info) by (instance_id))[5m:10s])"


def test_build_legacy_count_query_uses_count_grouping_and_last_window(monkeypatch):
    module = _load_policy_methods(monkeypatch, "monitor_policy_preview_legacy_count_query_builder_test_module")

    query = module.build_policy_query(
        "count",
        "interface_info",
        "5m",
        "instance_id",
    )

    assert query == "last_over_time((count(interface_info) by (instance_id))[5m:10s])"


def _load_policy_preview_service(monkeypatch, metric, vm_response=None):
    vm_response = vm_response or {
        "status": "success",
        "data": {"result": [{"metric": {"instance_id": "abc"}, "values": [[100, "7"]]}]},
    }

    class MetricQuerySet:
        def filter(self, **kwargs):
            self.filter_kwargs = kwargs
            return self

        def first(self):
            return metric

    class Metric:
        objects = MetricQuerySet()

    class VictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            self.last_call = (query, start, end, step)
            return vm_response

    class UnitConverter:
        @staticmethod
        def get_display_unit(unit):
            return unit

        @staticmethod
        def is_convertible(source_unit, target_unit):
            return False

    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=Exception,
    )
    _install_module(monkeypatch, "apps.monitor.models.monitor_metrics", Metric=Metric)
    _install_module(
        monkeypatch,
        "apps.monitor.utils.victoriametrics_api",
        VictoriaMetricsAPI=VictoriaMetricsAPI,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.unit_converter",
        UnitConverter=UnitConverter,
    )

    policy_methods = _load_policy_methods(monkeypatch, "apps.monitor.tasks.utils.policy_methods", VictoriaMetricsAPI)
    monkeypatch.setitem(sys.modules, "apps.monitor.tasks.utils.policy_methods", policy_methods)

    metric_query = _load_module(
        "apps.monitor.tasks.utils.metric_query",
        Path(__file__).resolve().parents[1] / "tasks" / "utils" / "metric_query.py",
    )
    monkeypatch.setitem(sys.modules, "apps.monitor.tasks.utils.metric_query", metric_query)

    return _load_module(
        "monitor_policy_preview_service_test_module",
        Path(__file__).resolve().parents[1] / "services" / "policy_preview.py",
    )


def test_policy_preview_scopes_metric_query_to_selected_instance_and_returns_query(monkeypatch):
    metric = types.SimpleNamespace(
        query='100 - cpu_usage_idle{cpu="cpu-total", instance_type="os", __$labels__}',
        unit="percent",
        instance_id_keys=["instance_id"],
    )
    module = _load_policy_preview_service(monkeypatch, metric)
    payload = {
        "monitor_object": 1,
        "query_condition": {"type": "metric", "metric_id": 10, "filter": []},
        "period": {"type": "min", "value": 5},
        "algorithm": "avg_over_time",
        "group_by": ["instance_id"],
        "metric_unit": "percent",
        "calculation_unit": "percent",
        "preview": {"instance_id": "host-1", "instance_id_values": ["abc"]},
    }

    result = module.PolicyPreviewService(payload).preview()

    assert result["query"] == (
        'avg_over_time((avg(100 - cpu_usage_idle{cpu="cpu-total", '
        'instance_type="os", instance_id=~"abc"}) by (instance_id))[5m:10s])'
    )
    assert result["data"]["status"] == "success"
    assert result["data"]["unit"] == "percent"


def test_policy_preview_requires_preview_instance_values(monkeypatch):
    metric = types.SimpleNamespace(
        query='cpu_usage_idle{__$labels__}',
        unit="percent",
        instance_id_keys=["instance_id"],
    )
    module = _load_policy_preview_service(monkeypatch, metric)
    payload = {
        "query_condition": {"type": "metric", "metric_id": 10, "filter": []},
        "period": {"type": "min", "value": 5},
        "algorithm": "avg",
        "group_by": ["instance_id"],
        "preview": {"instance_id": "host-1", "instance_id_values": []},
    }

    with pytest.raises(Exception, match="preview.instance_id_values is required"):
        module.PolicyPreviewService(payload).preview()


def test_policy_preview_surfaces_victoriametrics_error(monkeypatch):
    metric = types.SimpleNamespace(
        query='cpu_usage_idle{__$labels__}',
        unit="percent",
        instance_id_keys=["instance_id"],
    )
    module = _load_policy_preview_service(
        monkeypatch,
        metric,
        vm_response={"status": "error", "error": "parse error: unexpected by"},
    )
    payload = {
        "query_condition": {"type": "metric", "metric_id": 10, "filter": []},
        "period": {"type": "min", "value": 5},
        "algorithm": "avg",
        "group_by": ["instance_id"],
        "preview": {"instance_id": "host-1", "instance_id_values": ["abc"]},
    }

    with pytest.raises(Exception, match="parse error: unexpected by"):
        module.PolicyPreviewService(payload).preview()


def test_policy_preview_filters_empty_group_by_values(monkeypatch):
    metric = types.SimpleNamespace(
        query='cpu_usage_idle{__$labels__}',
        unit="percent",
        instance_id_keys=["instance_id"],
    )
    module = _load_policy_preview_service(monkeypatch, metric)
    payload = {
        "query_condition": {"type": "metric", "metric_id": 10, "filter": []},
        "period": {"type": "min", "value": 5},
        "algorithm": "sum_over_time",
        "group_by": ["instance_id", None, ""],
        "preview": {"instance_id": "host-1", "instance_id_values": ["abc"]},
    }

    result = module.PolicyPreviewService(payload).preview()

    assert result["query"] == 'sum_over_time((sum(cpu_usage_idle{instance_id=~"abc"}) by (instance_id))[5m:10s])'


def test_monitor_policy_preview_action_delegates_to_preview_service(monkeypatch):
    module = importlib.import_module("apps.monitor.views.monitor_policy")
    service_calls = []

    class PolicyPreviewService:
        def __init__(self, payload):
            service_calls.append(payload)

        def preview(self):
            return {"query": "preview-query", "data": {"status": "success"}, "warnings": []}

    monkeypatch.setattr(module, "PolicyPreviewService", PolicyPreviewService, raising=False)
    monkeypatch.setattr(
        module.WebUtils,
        "response_success",
        staticmethod(lambda data: {"wrapped": data}),
    )

    request = types.SimpleNamespace(data={"query_condition": {"metric_id": 10}})
    response = module.MonitorPolicyViewSet().preview(request)

    assert service_calls == [request.data]
    assert response == {
        "wrapped": {
            "query": "preview-query",
            "data": {"status": "success"},
            "warnings": [],
        }
    }
