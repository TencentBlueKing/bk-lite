from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.monitor.models import MonitorInstance, MonitorObject, MonitorPolicy
from apps.monitor.services.policy_baseline import PolicyBaselineService
from apps.monitor.tasks.services.policy_scan.alert_detector import AlertDetector
from apps.monitor.tasks.services.policy_scan.metric_query import MetricQueryService


def _policy(**overrides):
    base = {
        "id": 1,
        "last_run_time": datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
        "query_condition": {"type": "formula", "result_name": "错误率"},
        "period": {"type": "min", "value": 5},
        "algorithm": "avg_over_time",
        "group_algorithm": "avg",
        "group_by": ["instance_id"],
        "metric_unit": "",
        "calculation_unit": "",
        "threshold": [{"method": ">", "value": 80, "level": "critical"}],
        "alert_name": "$metric_name $instance_name $metric__status $value",
        "source": {"type": "instance", "values": ["h1"]},
        "monitor_object": SimpleNamespace(name="Host"),
        "no_data_period": {"type": "min", "value": 10},
        "no_data_alert_name": "$metric_name $instance_name $metric__status 无数据",
        "no_data_level": "warning",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _metric_query_service(**overrides):
    base = {
        "metric": None,
        "instance_id_keys": ["instance_id", "status"],
        "query_aggregation_metrics": lambda period, points=1: overrides.get(
            "agg", {"data": {"result": []}}
        ),
        "convert_metric_values": lambda data: data,
        "format_aggregation_metrics": lambda data: overrides.get("formatted", {}),
        "get_display_unit": lambda: "",
        "get_enum_value_map": lambda: {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_formula_query_aggregation_uses_formula_query_and_anchor_group_by(mocker):
    policy = _policy(group_by=["instance_id"])
    compiled = SimpleNamespace(
        query=(
            "sum(a{}) by (instance_id,status) / "
            "on(instance_id) group_left sum(b{}) by (instance_id)"
        ),
        group_by=["instance_id", "status"],
        result_name="错误率",
        warnings=[],
    )
    captured = {}

    build = mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.build_formula_query",
        return_value=compiled,
    )

    def fake_method(query, start, end, step, group_by, group_algorithm=None):
        captured["query"] = query
        captured["group_by"] = group_by
        captured["group_algorithm"] = group_algorithm
        return {"status": "success", "data": {"result": []}}

    mocker.patch.dict(
        "apps.monitor.tasks.services.policy_scan.metric_query.METHOD",
        {"avg_over_time": fake_method},
        clear=False,
    )

    service = MetricQueryService(policy, {})
    service.set_monitor_obj_instance_key()
    service.query_aggregation_metrics(policy.period)

    build.assert_called_once_with(policy.query_condition)
    assert service.instance_id_keys == ["instance_id", "status"]
    assert captured["query"].startswith("sum(a{})")
    assert captured["group_by"] == "instance_id,status"
    assert captured["group_algorithm"] == "avg"


def test_formula_metric_name_template_uses_result_name():
    agg = {
        "data": {
            "result": [
                {
                    "metric": {"instance_id": "h1", "status": "500"},
                    "values": [[100, "95"]],
                }
            ]
        }
    }
    detector = AlertDetector(
        _policy(),
        {"('h1',)": "主机1"},
        {},
        [],
        _metric_query_service(agg=agg),
    )

    alerts, infos = detector.detect_threshold_alerts()

    assert infos == []
    assert alerts[0]["content"].startswith("错误率 主机1 - status:500 500")
    assert alerts[0]["dimensions"] == {"instance_id": "h1", "status": "500"}


def test_formula_no_data_detection_uses_final_result_group_by():
    missing_metric_instance = str(("h1", "500"))
    detector = AlertDetector(
        _policy(),
        {"('h1',)": "主机1"},
        {missing_metric_instance: "('h1',)"},
        [],
        _metric_query_service(formatted={}),
    )

    events = detector.detect_no_data_alerts()

    assert len(events) == 1
    assert events[0]["metric_instance_id"] == missing_metric_instance
    assert events[0]["dimensions"] == {"instance_id": "h1", "status": "500"}
    assert "错误率 主机1 - status:500 500 无数据" == events[0]["content"]


@pytest.mark.django_db
def test_formula_baseline_refresh_uses_final_result_group_by():
    obj = MonitorObject.objects.create(name="FormulaBaseObj", level="base")
    policy = MonitorPolicy.objects.create(
        monitor_object=obj,
        name="formula-policy",
        algorithm="max",
        query_condition={"type": "formula", "result_name": "错误率"},
        source={"type": "instance", "values": ["('h1',)"]},
        group_by=["instance_id"],
        period={"type": "min", "value": 5},
        last_run_time=datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
    )
    MonitorInstance.objects.create(id="('h1',)", name="host1", monitor_object=obj)
    fake_query_svc = MagicMock()
    fake_query_svc.instance_id_keys = ["instance_id", "status"]
    fake_query_svc.query_aggregation_metrics.return_value = {
        "data": {
            "result": [
                {
                    "metric": {"instance_id": "h1", "status": "500"},
                    "values": [[100, "1"]],
                },
            ]
        }
    }

    with patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.MetricQueryService",
        return_value=fake_query_svc,
    ):
        PolicyBaselineService(policy).refresh()

    assert set(
        policy.policyinstancebaseline_set.values_list("metric_instance_id", flat=True)
    ) == {str(("h1", "500"))}


def test_metric_query_path_still_uses_policy_group_by(mocker):
    policy = _policy(
        query_condition={"type": "metric", "metric_id": 9, "filter": []},
        group_by=["instance_id"],
        algorithm="avg_over_time",
    )
    captured = {}

    def fake_method(query, start, end, step, group_by, group_algorithm=None):
        captured["query"] = query
        captured["group_by"] = group_by
        return {"status": "success", "data": {"result": []}}

    mocker.patch.dict(
        "apps.monitor.tasks.services.policy_scan.metric_query.METHOD",
        {"avg_over_time": fake_method},
        clear=False,
    )

    service = MetricQueryService(policy, {})
    service.metric = SimpleNamespace(
        query="cpu{__$labels__}", data_type="Number", unit=""
    )
    service.query_aggregation_metrics(policy.period)

    assert captured == {"query": "cpu{}", "group_by": "instance_id"}


def test_metric_detector_uses_policy_group_by_not_metric_instance_id_keys():
    policy = _policy(
        query_condition={"type": "metric", "metric_id": 9},
        group_by=["instance_id", "mount"],
        alert_name="$instance_name $metric__mount $value",
    )
    agg = {
        "data": {
            "result": [
                {
                    "metric": {"instance_id": "h1", "mount": "/data"},
                    "values": [[100, "95"]],
                }
            ]
        }
    }
    detector = AlertDetector(
        policy,
        {"('h1',)": "主机1"},
        {},
        [],
        _metric_query_service(
            metric=SimpleNamespace(display_name="CPU", name="cpu", dimensions=[]),
            instance_id_keys=["instance_id"],
            agg=agg,
        ),
    )

    alerts, infos = detector.detect_threshold_alerts()

    assert infos == []
    assert alerts[0]["metric_instance_id"] == str(("h1", "/data"))
    assert alerts[0]["monitor_instance_id"] == "('h1',)"
    assert alerts[0]["content"].startswith("主机1 - mount:/data /data")


def test_formula_reversed_group_by_threshold_uses_instance_id_for_scope():
    policy = _policy(group_by=["instance_id"])
    agg = {
        "data": {
            "result": [
                {
                    "metric": {"status": "500", "instance_id": "h1"},
                    "values": [[100, "95"]],
                }
            ]
        }
    }
    detector = AlertDetector(
        policy,
        {"('h1',)": "主机1"},
        {},
        [],
        _metric_query_service(instance_id_keys=["status", "instance_id"], agg=agg),
    )

    alerts, infos = detector.detect_threshold_alerts()

    assert infos == []
    assert alerts[0]["metric_instance_id"] == str(("500", "h1"))
    assert alerts[0]["monitor_instance_id"] == "('h1',)"
    assert alerts[0]["dimensions"] == {"status": "500", "instance_id": "h1"}
    assert alerts[0]["content"].startswith("错误率 主机1")
    assert " 500 " in alerts[0]["content"]


@pytest.mark.django_db
def test_formula_reversed_group_by_baseline_uses_instance_id_for_scope():
    obj = MonitorObject.objects.create(name="FormulaReverseBaseObj", level="base")
    policy = MonitorPolicy.objects.create(
        monitor_object=obj,
        name="formula-policy-reverse",
        algorithm="max",
        query_condition={"type": "formula", "result_name": "错误率"},
        source={"type": "instance", "values": ["('h1',)"]},
        group_by=["instance_id"],
        period={"type": "min", "value": 5},
        last_run_time=datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
    )
    MonitorInstance.objects.create(id="('h1',)", name="host1", monitor_object=obj)
    fake_query_svc = MagicMock()
    fake_query_svc.instance_id_keys = ["status", "instance_id"]
    fake_query_svc.query_aggregation_metrics.return_value = {
        "data": {
            "result": [
                {
                    "metric": {"status": "500", "instance_id": "h1"},
                    "values": [[100, "1"]],
                },
            ]
        }
    }

    with patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.MetricQueryService",
        return_value=fake_query_svc,
    ):
        PolicyBaselineService(policy).refresh()

    baseline = policy.policyinstancebaseline_set.get()
    assert baseline.metric_instance_id == str(("500", "h1"))
    assert baseline.monitor_instance_id == "('h1',)"


def test_formula_lazy_compile_sets_result_group_by_for_formatting(mocker):
    policy = _policy(group_by=["instance_id"])
    compiled = SimpleNamespace(
        query="formula_query",
        group_by=["status", "instance_id"],
        result_name="错误率",
        warnings=[],
    )
    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.build_formula_query",
        return_value=compiled,
    )
    service = MetricQueryService(policy, {"('h1',)": "主机1"})
    metrics = {
        "data": {
            "result": [
                {
                    "metric": {"status": "500", "instance_id": "h1"},
                    "values": [[100, "1"]],
                },
            ]
        }
    }

    assert service.format_pmq() == "formula_query"
    formatted = service.format_aggregation_metrics(metrics)

    assert service.instance_id_keys == ["status", "instance_id"]
    assert list(formatted.keys()) == [str(("500", "h1"))]
