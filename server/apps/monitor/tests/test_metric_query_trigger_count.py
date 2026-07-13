import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_metric_query_module(monkeypatch):
    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=Exception,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        Metric=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: types.SimpleNamespace(first=lambda: None))),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.tasks.utils.metric_query",
        format_to_vm_filter=lambda filters: "",
    )
    _install_module(monkeypatch, "apps.monitor.tasks")
    _install_module(monkeypatch, "apps.monitor.tasks.utils")
    _install_module(
        monkeypatch,
        "apps.monitor.tasks.utils.policy_methods",
        METHOD={},
        period_to_seconds=lambda period: period["value"] * 60,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.victoriametrics_api",
        VictoriaMetricsAPI=object,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.unit_converter",
        UnitConverter=types.SimpleNamespace(
            is_convertible=lambda *_: False,
            get_display_unit=lambda unit: unit,
        ),
    )
    _install_module(
        monkeypatch,
        "apps.core.logger",
        celery_logger=types.SimpleNamespace(
            warning=lambda *args, **kwargs: None,
            error=lambda *args, **kwargs: None,
            info=lambda *args, **kwargs: None,
        ),
    )

    spec = importlib.util.spec_from_file_location(
        "metric_query_trigger_count_module",
        Path(__file__).resolve().parents[1] / "tasks" / "services" / "policy_scan" / "metric_query.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_query_aggregation_metrics_uses_trigger_count_for_range_but_keeps_period_step(monkeypatch):
    module = _load_metric_query_module(monkeypatch)
    captured = {}

    def fake_method(query, start, end, step, group_by, group_algorithm=None):
        captured.update(
            {
                "query": query,
                "start": start,
                "end": end,
                "step": step,
                "group_by": group_by,
                "group_algorithm": group_algorithm,
            }
        )
        return {"data": {"result": []}}

    monkeypatch.setitem(module.METHOD, "avg", fake_method)

    policy = types.SimpleNamespace(
        last_run_time=datetime(2026, 6, 24, 10, 10, tzinfo=timezone.utc),
        query_condition={"type": "pmq", "query": "up{}"},
        group_by=["instance_id"],
        algorithm="avg",
        metric_unit="",
        calculation_unit="",
    )

    service = module.MetricQueryService(policy, {})
    service.query_aggregation_metrics({"type": "min", "value": 5}, points=2)

    assert captured["end"] == int(policy.last_run_time.timestamp())
    assert captured["start"] == captured["end"] - 10 * 60
    assert captured["step"] == "5m"
    assert captured["query"] == "up{}"
    assert captured["group_by"] == "instance_id"
    assert captured["group_algorithm"] is None


def test_query_aggregation_metrics_passes_group_algorithm(monkeypatch):
    module = _load_metric_query_module(monkeypatch)
    captured = {}

    def fake_method(query, start, end, step, group_by, group_algorithm=None):
        captured["group_algorithm"] = group_algorithm
        return {"data": {"result": []}}

    monkeypatch.setitem(module.METHOD, "avg_over_time", fake_method)

    policy = types.SimpleNamespace(
        last_run_time=datetime(2026, 6, 24, 10, 10, tzinfo=timezone.utc),
        query_condition={"type": "pmq", "query": "up{}"},
        group_by=["instance_id"],
        group_algorithm="max",
        algorithm="avg_over_time",
        metric_unit="",
        calculation_unit="",
    )

    service = module.MetricQueryService(policy, {})
    service.query_aggregation_metrics({"type": "min", "value": 5}, points=1)

    assert captured["group_algorithm"] == "max"
