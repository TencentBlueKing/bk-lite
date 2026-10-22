"""多指标扫描：单位换算、缺数据保持、锚点无数据、快照与告警中心。"""

import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorAlert
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.alert_lifecycle_notify import AlertLifecycleNotifier
from apps.monitor.services.policy import PolicyService
from apps.monitor.tasks.services.policy_scan.alert_detector import AlertDetector
from apps.monitor.tasks.services.policy_scan.metric_query import MetricQueryService
from apps.monitor.tasks.services.policy_scan.snapshot_recorder import SnapshotRecorder

SENTINEL = "SENTINEL_DO_NOT_LOG_VM_BODY"


def _objects():
    obj = MonitorObject.objects.create(name="MultiScanObj", level="base", instance_id_keys=["instance_id"])
    plugin = MonitorPlugin.objects.create(name="MultiScanPlugin")
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
        display_name="内存使用量",
        query="mem_used{__$labels__}",
        instance_id_keys=["instance_id"],
        data_type="Number",
        unit="bytes",
    )
    return obj, cpu, memory


def _policy(obj, cpu, memory, **overrides):
    base = dict(
        id=41,
        name="双高",
        collect_type="",
        last_run_time=datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc),
        period={"type": "min", "value": 5},
        algorithm="avg_over_time",
        group_algorithm="avg",
        group_by=["instance_id"],
        metric_unit="percent",
        calculation_unit="percent",
        threshold_unit="percent",
        threshold=[],
        compare_mode="absolute",
        compare_value_kind="",
        recovery_threshold={},
        count_predicate={},
        trigger_count=1,
        recovery_condition=1,
        source={"type": "instance", "values": ["('h1',)"]},
        monitor_object=obj,
        alert_name="${metric_name} ${value} ${a_value} ${b_value} ${b_metric_name}",
        no_data_period={"type": "min", "value": 10},
        no_data_alert_name="${metric_name} 无数据",
        no_data_level="warning",
        query_condition={
            "type": "multi",
            "result_name": "CPU 与内存双高",
            "combinator": "all",
            "queries": [
                {
                    "ref": "a",
                    "metric_id": cpu.id,
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
                },
                {
                    "ref": "b",
                    "metric_id": memory.id,
                    "filter": [],
                    "group_algorithm": "max",
                    "group_by": ["instance_id"],
                    "algorithm": "avg_over_time",
                    "metric_unit": "bytes",
                    "calculation_unit": "gibibytes",
                    "threshold_unit": "gibibytes",
                    "role": "level",
                    "threshold": [
                        {"level": "critical", "method": ">", "value": 0.5},
                        {"level": "warning", "method": ">", "value": 0.25},
                    ],
                },
            ],
        },
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _vm(cpu_value, memory_value):
    def query_range(query, start, end, step):
        if "cpu_usage" in query:
            values = [[100, str(cpu_value)]] if cpu_value is not None else []
            metric = {"instance_id": "h1", "vm_trace": SENTINEL}
        elif "mem_used" in query:
            values = [[100, str(memory_value)]] if memory_value is not None else []
            metric = {"instance_id": "h1", "vm_trace": SENTINEL}
        else:
            values = []
            metric = {}
        result = [{"metric": metric, "values": values}] if values else []
        return {"status": "success", "data": {"result": result}, "body": SENTINEL}

    return query_range


def _service(policy):
    service = MetricQueryService(policy, {"('h1',)": "主机1"})
    service.set_monitor_obj_instance_key()
    return service


def _detector(policy, service, active_alerts=None, baselines=None):
    return AlertDetector(
        policy,
        {"('h1',)": "主机1"},
        baselines or {},
        active_alerts or [],
        service,
    )


@pytest.mark.django_db
def test_condition_units_convert_without_rewriting_policy(mocker):
    obj, cpu, memory = _objects()
    policy = _policy(obj, cpu, memory)
    original_threshold = policy.query_condition["queries"][1]["threshold"][0]["value"]
    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
    ).return_value.query_range.side_effect = _vm(93, 1024**3)
    service = _service(policy)
    payloads = service.query_multi_comparison_metrics(policy.period, 1)
    converted = service.convert_condition_values(payloads["b"], policy.query_condition["queries"][1])
    thresholds = service.convert_condition_thresholds(policy.query_condition["queries"][1])

    assert float(converted["data"]["result"][0]["values"][0][1]) == pytest.approx(1)
    assert thresholds[0]["value"] == pytest.approx(0.5)
    assert policy.query_condition["queries"][1]["threshold"][0]["value"] == original_threshold
    assert policy.threshold == []


@pytest.mark.django_db
def test_scan_takes_lower_level_and_renders_condition_variables(mocker, caplog):
    obj, cpu, memory = _objects()
    policy = _policy(obj, cpu, memory)
    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
    ).return_value.query_range.side_effect = _vm(85, 1024**3)
    service = _service(policy)
    detector = _detector(policy, service)
    with caplog.at_level(logging.DEBUG):
        alerts, infos, holds = detector.detect_threshold_alerts()

    assert infos == []
    assert holds == []
    assert alerts[0]["level"] == "warning"
    assert alerts[0]["value"] == pytest.approx(85)
    assert alerts[0]["raw_data"]["condition_values"]["b"] == pytest.approx(1)
    assert "CPU 与内存双高" in alerts[0]["content"]
    assert "85.00" in alerts[0]["content"]
    assert "内存使用量" in alerts[0]["content"]
    assert SENTINEL not in caplog.text

    recorder = SnapshotRecorder(policy, {"('h1',)": "主机1"}, [], service)
    fields = recorder._compare_fields_for_raw(alerts[0]["metric_instance_id"], alerts[0]["raw_data"], alerts[0]["value"])
    assert fields["current_value"] == pytest.approx(85)
    assert fields["result_unit"] == "percent"
    assert fields["condition_values"]["b"] == pytest.approx(1)


@pytest.mark.django_db
def test_missing_non_anchor_data_does_not_change_recovery_count(mocker):
    obj, cpu, memory = _objects()
    policy = _policy(obj, cpu, memory)
    alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id="('h1',)",
        metric_instance_id="('h1',)",
        alert_type="alert",
        status="new",
        info_event_count=2,
    )
    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
    ).return_value.query_range.side_effect = _vm(86, None)
    service = _service(policy)
    detector = _detector(policy, service, active_alerts=[alert])
    alerts, infos, holds = detector.detect_threshold_alerts()
    detector.count_events(alerts, infos)

    alert.refresh_from_db()
    assert alerts == []
    assert infos == []
    assert holds == []
    assert alert.info_event_count == 2
    assert alert.status == "new"


@pytest.mark.django_db
def test_unmet_combination_recovers_after_recovery_condition(mocker, django_capture_on_commit_callbacks):
    obj, cpu, memory = _objects()
    policy = _policy(obj, cpu, memory, recovery_condition=1)
    alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id="('h1',)",
        metric_instance_id="('h1',)",
        alert_type="alert",
        status="new",
        info_event_count=0,
    )
    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.alert_detector.AlertLifecycleNotifier"
    )
    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
    ).return_value.query_range.side_effect = _vm(10, 1)
    service = _service(policy)
    detector = _detector(policy, service, active_alerts=[alert])
    alerts, infos, _ = detector.detect_threshold_alerts()
    detector.count_events(alerts, infos)
    with django_capture_on_commit_callbacks(execute=True):
        detector.recover_threshold_alerts()

    alert.refresh_from_db()
    assert alerts == []
    assert len(infos) == 1
    assert alert.status == "recovered"


@pytest.mark.django_db
def test_no_data_uses_only_the_anchor_existence_query(mocker):
    obj, cpu, memory = _objects()
    policy = _policy(obj, cpu, memory)
    captured = []

    def query_range(query, start, end, step):
        captured.append(query)
        return {"status": "success", "data": {"result": []}}

    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
    ).return_value.query_range.side_effect = query_range
    service = _service(policy)
    detector = _detector(policy, service, baselines={"('h1',)": "('h1',)"})
    events = detector.detect_no_data_alerts()

    assert len(events) == 1
    assert events[0]["metric_instance_id"] == "('h1',)"
    assert "CPU 与内存双高" in events[0]["content"]
    assert captured
    assert all("mem_used" not in query for query in captured)
    assert "cpu_usage" in captured[0]


def _formula_scan_policy(obj, error, request):
    return _policy(
        obj,
        error,
        request,
        alert_name="${a_metric_name} ${a_value}",
        metric_unit="",
        calculation_unit="percent",
        threshold_unit="percent",
        query_condition={
            "type": "multi",
            "result_name": "错误率与请求数",
            "combinator": "all",
            "queries": [
                {
                    "ref": "a",
                    "source": "formula",
                    "metric_name": "错误率",
                    "expression": "a1 / a2 * 100",
                    "operands": [
                        {
                            "ref": "a1",
                            "metric_id": error.id,
                            "filter": [],
                            "group_algorithm": "sum",
                            "group_by": ["instance_id"],
                        },
                        {
                            "ref": "a2",
                            "metric_id": request.id,
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
                        {"level": "critical", "method": ">", "value": 20},
                        {"level": "error", "method": ">", "value": 10},
                        {"level": "warning", "method": ">", "value": 5},
                    ],
                },
                {
                    "ref": "b",
                    "metric_id": request.id,
                    "filter": [],
                    "group_algorithm": "sum",
                    "group_by": ["instance_id"],
                    "algorithm": "avg_over_time",
                    "metric_unit": "counts",
                    "calculation_unit": "counts",
                    "threshold_unit": "counts",
                    "role": "gate",
                    "threshold": [{"method": ">", "value": 100}],
                },
            ],
        },
    )


def _formula_vm(rate, requests):
    def query_range(query, start, end, step):
        if "error_total" in query:
            value = rate
        elif "request_total" in query:
            value = requests
        else:
            value = None
        values = [[100, str(value)]] if value is not None else []
        result = [{"metric": {"instance_id": "h1", "vm_trace": SENTINEL}, "values": values}] if values else []
        return {"status": "success", "data": {"result": result}, "body": SENTINEL}

    return query_range


@pytest.mark.django_db
def test_formula_condition_scan_takes_error_level_and_names_the_result(mocker, caplog):
    obj, error, request = _objects()
    error.name = "error_total"
    error.query = "error_total{__$labels__}"
    error.save(update_fields=["name", "query"])
    request.name = "request_total"
    request.query = "request_total{__$labels__}"
    request.save(update_fields=["name", "query"])
    policy = _formula_scan_policy(obj, error, request)
    captured = []

    def query_range(query, start, end, step):
        captured.append(query)
        return _formula_vm(12, 300)(query, start, end, step)

    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
    ).return_value.query_range.side_effect = query_range
    service = _service(policy)
    detector = _detector(policy, service)
    with caplog.at_level(logging.DEBUG):
        alerts, infos, holds = detector.detect_threshold_alerts()

    assert len(captured) == 2
    assert infos == []
    assert holds == []
    assert alerts[0]["level"] == "error"
    assert alerts[0]["value"] == pytest.approx(12)
    assert alerts[0]["raw_data"]["series"]["a"]
    assert alerts[0]["raw_data"]["condition_values"]["a"] == pytest.approx(12)
    assert alerts[0]["raw_data"]["condition_values"]["b"] == pytest.approx(300)
    assert alerts[0]["content"] == "错误率 12.00%"
    assert SENTINEL not in caplog.text


@pytest.mark.django_db
def test_missing_formula_data_does_not_trigger_or_recover(mocker):
    obj, error, request = _objects()
    error.query = "error_total{__$labels__}"
    error.save(update_fields=["query"])
    request.query = "request_total{__$labels__}"
    request.save(update_fields=["query"])
    policy = _formula_scan_policy(obj, error, request)
    alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id="('h1',)",
        metric_instance_id="('h1',)",
        alert_type="alert",
        status="new",
        info_event_count=0,
    )
    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
    ).return_value.query_range.side_effect = _formula_vm(None, 300)
    service = _service(policy)
    detector = _detector(policy, service, active_alerts=[alert])
    alerts, infos, holds = detector.detect_threshold_alerts()
    detector.count_events(alerts, infos)
    detector.recover_threshold_alerts()

    alert.refresh_from_db()
    assert alerts == []
    assert infos == []
    assert holds == []
    assert alert.info_event_count == 0
    assert alert.status == "new"


@pytest.mark.django_db
def test_missing_formula_operand_metric_fails_the_policy(mocker):
    obj, error, _request = _objects()
    error.query = "error_total{__$labels__}"
    error.save(update_fields=["query"])
    missing = SimpleNamespace(id=999999, query="request_total{__$labels__}")
    policy = _formula_scan_policy(obj, error, missing)
    mocker.patch("apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI")
    service = MetricQueryService(policy, {"('h1',)": "主机1"})
    with pytest.raises(BaseAppException, match="metric does not exist"):
        service.set_monitor_obj_instance_key()


def test_alert_center_item_and_display_name_use_result_name():
    policy = SimpleNamespace(
        id=1,
        name="双高",
        organizations=[],
        monitor_object=None,
        query_condition={"type": "multi", "result_name": "CPU 与内存双高", "queries": []},
    )
    notifier = AlertLifecycleNotifier(policy)
    assert notifier._resolve_alert_center_item(policy) == "CPU 与内存双高"
    assert PolicyService.display_metric_name({"query_condition": policy.query_condition}) == "CPU 与内存双高"
