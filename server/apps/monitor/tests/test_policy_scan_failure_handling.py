import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest


class _Logger:
    def info(self, *args, **kwargs):
        return None

    def debug(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


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


def _load_snapshot_recorder_module(monkeypatch, module_name):
    class _MonitorEventRawDataQuerySet:
        def select_related(self, *args):
            return []

    class _MonitorEventRawDataManager:
        def filter(self, **kwargs):
            return _MonitorEventRawDataQuerySet()

    class MonitorEventRawData:
        objects = _MonitorEventRawDataManager()

    class MonitorAlertMetricSnapshot:
        pass

    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorEventRawData=MonitorEventRawData,
        MonitorAlertMetricSnapshot=MonitorAlertMetricSnapshot,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.tasks.utils.policy_methods",
        METHOD={},
        period_to_seconds=lambda period: 60,
    )
    _install_module(monkeypatch, "apps.core.logger", celery_logger=_Logger())

    return _load_module(
        module_name,
        Path(__file__).resolve().parents[1] / "tasks" / "services" / "policy_scan" / "snapshot_recorder.py",
    )


class _PolicyQuerySet:
    def __init__(self, manager):
        self.manager = manager

    def select_related(self, *args):
        return self

    def first(self):
        return self.manager.policy

    def update(self, **kwargs):
        self.manager.updates.append(kwargs)
        for key, value in kwargs.items():
            setattr(self.manager.policy, key, value)
        return 1


class _PolicyManager:
    def __init__(self, policy):
        self.policy = policy
        self.updates = []

    def filter(self, **kwargs):
        return _PolicyQuerySet(self)


class _PolicyModel:
    objects = None


class _FrozenDateTime(datetime):
    fixed_now = datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.fixed_now.replace(tzinfo=None)
        return cls.fixed_now.astimezone(tz)


def _install_monitor_policy_dependencies(monkeypatch, policy, scan_cls):
    def shared_task(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    _PolicyModel.objects = _PolicyManager(policy)

    _install_module(monkeypatch, "celery", shared_task=shared_task)
    _install_module(monkeypatch, "celery_singleton", Singleton=object)
    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=Exception)
    _install_module(monkeypatch, "apps.monitor.models", MonitorPolicy=_PolicyModel)
    _install_module(monkeypatch, "apps.core.logger", celery_logger=_Logger())
    _install_module(monkeypatch, "apps.monitor.tasks.services.policy_scan", MonitorPolicyScan=scan_cls)
    _install_module(monkeypatch, "apps.monitor.tasks.utils.policy_methods", period_to_seconds=lambda period: 60)
    _install_module(
        monkeypatch,
        "apps.monitor.constants.alert_policy",
        AlertConstants=types.SimpleNamespace(MAX_BACKFILL_SECONDS=3600, MAX_BACKFILL_COUNT=10),
    )


def test_scan_policy_task_does_not_persist_watermark_when_scan_fails(monkeypatch):
    policy = types.SimpleNamespace(
        id=1001,
        enable=True,
        last_run_time=datetime(2026, 4, 21, 7, 59, tzinfo=timezone.utc),
        period={"type": "min", "value": 1},
    )

    class FailingScan:
        def __init__(self, policy_obj):
            self.policy_obj = policy_obj

        def run(self):
            raise RuntimeError("victoriametrics unavailable")

    _install_monitor_policy_dependencies(monkeypatch, policy, FailingScan)
    module = _load_module(
        "monitor_policy_failure_test_module",
        Path(__file__).resolve().parents[1] / "tasks" / "monitor_policy.py",
    )
    module.datetime = _FrozenDateTime

    with pytest.raises(RuntimeError, match="victoriametrics unavailable"):
        module.scan_policy_task(policy.id)

    assert _PolicyModel.objects.updates == []


def test_scan_policy_task_persists_watermark_after_successful_scan(monkeypatch):
    policy = types.SimpleNamespace(
        id=1002,
        enable=True,
        last_run_time=datetime(2026, 4, 21, 7, 59, tzinfo=timezone.utc),
        period={"type": "min", "value": 1},
    )
    scanned_at = []

    class SuccessfulScan:
        def __init__(self, policy_obj):
            self.policy_obj = policy_obj

        def run(self):
            scanned_at.append(self.policy_obj.last_run_time)

    _install_monitor_policy_dependencies(monkeypatch, policy, SuccessfulScan)
    module = _load_module(
        "monitor_policy_success_test_module",
        Path(__file__).resolve().parents[1] / "tasks" / "monitor_policy.py",
    )
    module.datetime = _FrozenDateTime

    result = module.scan_policy_task(policy.id)

    assert scanned_at == [_FrozenDateTime.fixed_now]
    assert _PolicyModel.objects.updates == [{"last_run_time": _FrozenDateTime.fixed_now}]
    assert result["success"] is True


def _install_monitor_policy_view_dependencies(monkeypatch):
    class ModelViewSet:
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    beat_models = _install_module(
        monkeypatch,
        "django_celery_beat.models",
        PeriodicTask=object,
        CrontabSchedule=object,
    )
    _install_module(monkeypatch, "django_celery_beat", models=beat_models)
    rest_viewsets = _install_module(monkeypatch, "rest_framework.viewsets", ModelViewSet=ModelViewSet)
    rest_decorators = _install_module(monkeypatch, "rest_framework.decorators", action=action)
    _install_module(monkeypatch, "rest_framework", viewsets=rest_viewsets, decorators=rest_decorators)
    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=Exception)
    _install_module(
        monkeypatch,
        "apps.core.utils.permission_utils",
        get_permission_rules=lambda *args, **kwargs: {},
        permission_filter=lambda *args, **kwargs: [],
    )
    _install_module(monkeypatch, "apps.core.utils.web_utils", WebUtils=object)
    _install_module(
        monkeypatch,
        "apps.monitor.constants.alert_policy",
        AlertConstants=types.SimpleNamespace(NO_DATA="no_data"),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.constants.database",
        DatabaseConstants=types.SimpleNamespace(BULK_CREATE_BATCH_SIZE=100, BULK_UPDATE_BATCH_SIZE=100),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.constants.permission",
        PermissionConstants=types.SimpleNamespace(POLICY_MODULE="policy", DEFAULT_PERMISSION=[]),
    )
    _install_module(monkeypatch, "apps.monitor.filters.monitor_policy", MonitorPolicyFilter=object)

    class _ImportQuerySet:
        def all(self):
            return []

    class _ImportMonitorPolicy:
        objects = _ImportQuerySet()

    _install_module(monkeypatch, "apps.monitor.models", PolicyOrganization=object, MonitorAlert=object)
    _install_module(monkeypatch, "apps.monitor.models.monitor_policy", MonitorPolicy=_ImportMonitorPolicy)
    _install_module(monkeypatch, "apps.monitor.serializers.monitor_policy", MonitorPolicySerializer=object)
    _install_module(monkeypatch, "apps.monitor.services.alert_lifecycle_notify", AlertLifecycleNotifier=object)
    _install_module(monkeypatch, "apps.monitor.services.policy", PolicyService=object)
    _install_module(monkeypatch, "apps.monitor.services.policy_baseline", PolicyBaselineService=object)
    _install_module(monkeypatch, "apps.monitor.utils.pagination", parse_page_params=lambda *args, **kwargs: (1, 10))
    _install_module(monkeypatch, "config.drf.pagination", CustomPageNumberPagination=object)


def test_monitor_policy_baseline_refreshes_when_grouping_contract_changes(monkeypatch):
    _install_monitor_policy_view_dependencies(monkeypatch)
    module = _load_module(
        "monitor_policy_view_baseline_test_module",
        Path(__file__).resolve().parents[1] / "views" / "monitor_policy.py",
    )

    view = module.MonitorPolicyViewSet()
    old_policy = types.SimpleNamespace(
        source={"type": "instance", "values": ["('host-1',)"]},
        group_by=["instance_id", "mountpoint"],
        query_condition={"metric_id": 10},
        monitor_object_id=3,
        collect_type="host",
        enable_alerts=["threshold", "no_data"],
    )
    updated_policy = types.SimpleNamespace(
        source={"type": "instance", "values": ["('host-1',)"]},
        group_by=["instance_id"],
        query_condition={"metric_id": 10},
        monitor_object_id=3,
        collect_type="host",
        enable_alerts=["threshold", "no_data"],
    )

    old_state = view.get_baseline_state(old_policy)

    assert view.should_update_policy_baselines(old_policy, old_state, updated_policy) is True
    assert view.baseline_state_changed(old_state, updated_policy) is True


def test_monitor_policy_baseline_ignores_source_value_reordering(monkeypatch):
    _install_monitor_policy_view_dependencies(monkeypatch)
    module = _load_module(
        "monitor_policy_view_source_reorder_test_module",
        Path(__file__).resolve().parents[1] / "views" / "monitor_policy.py",
    )

    view = module.MonitorPolicyViewSet()
    old_policy = types.SimpleNamespace(
        source={"type": "organization", "values": [3, 1, 2]},
        group_by=["instance_id"],
        query_condition={"metric_id": 10, "filter": [{"key": "mountpoint", "value": "/data"}]},
        monitor_object_id=3,
        collect_type="host",
        enable_alerts=["no_data"],
    )
    updated_policy = types.SimpleNamespace(
        source={"type": "organization", "values": [2, 3, 1]},
        group_by=["instance_id"],
        query_condition={"metric_id": 10, "filter": [{"key": "mountpoint", "value": "/data"}]},
        monitor_object_id=3,
        collect_type="host",
        enable_alerts=["no_data"],
    )

    old_state = view.get_baseline_state(old_policy)

    assert view.baseline_state_changed(old_state, updated_policy) is False
    assert view.should_update_policy_baselines(old_policy, old_state, updated_policy) is False


def test_monitor_policy_enable_alert_toggle_updates_baselines_without_request_key_dependency(monkeypatch):
    _install_monitor_policy_view_dependencies(monkeypatch)
    module = _load_module(
        "monitor_policy_view_enable_toggle_test_module",
        Path(__file__).resolve().parents[1] / "views" / "monitor_policy.py",
    )

    view = module.MonitorPolicyViewSet()
    old_policy = types.SimpleNamespace(
        source={"type": "instance", "values": ["('host-1',)"]},
        group_by=["instance_id"],
        query_condition={"metric_id": 10},
        monitor_object_id=3,
        collect_type="host",
        enable_alerts=["threshold", "no_data"],
    )
    updated_policy = types.SimpleNamespace(
        source={"type": "instance", "values": ["('host-1',)"]},
        group_by=["instance_id"],
        query_condition={"metric_id": 10},
        monitor_object_id=3,
        collect_type="host",
        enable_alerts=["threshold"],
    )

    old_state = view.get_baseline_state(old_policy)

    assert view.should_update_policy_baselines(old_policy, old_state, updated_policy) is True
    assert view.baseline_state_changed(old_state, updated_policy) is False


def test_monitor_policy_disabling_no_data_closes_only_active_no_data_alerts(monkeypatch):
    _install_monitor_policy_view_dependencies(monkeypatch)
    module = _load_module(
        "monitor_policy_view_disable_no_data_test_module",
        Path(__file__).resolve().parents[1] / "views" / "monitor_policy.py",
    )

    policy = types.SimpleNamespace(id=42)
    active_no_data_alert = types.SimpleNamespace(
        status="new",
        alert_type="no_data",
        end_event_time=None,
        operator="",
        operation_logs=[],
        alert_center_notified=True,
    )
    recovered_no_data_alert = types.SimpleNamespace(
        status="recovered",
        alert_type="no_data",
        end_event_time=None,
        operator="",
        operation_logs=[],
    )
    active_threshold_alert = types.SimpleNamespace(
        status="new",
        alert_type="alert",
        end_event_time=None,
        operator="",
        operation_logs=[],
    )
    bulk_updates = []
    lifecycle_calls = []
    baseline_calls = []
    filter_calls = []

    class PolicyQuerySet:
        def first(self):
            return policy

    class MonitorPolicy:
        class objects:
            @staticmethod
            def filter(**kwargs):
                return PolicyQuerySet()

    class AlertQuerySet(list):
        pass

    class MonitorAlert:
        class objects:
            @staticmethod
            def filter(**kwargs):
                filter_calls.append(kwargs)
                return AlertQuerySet([active_no_data_alert])

            @staticmethod
            def bulk_update(alerts, fields):
                bulk_updates.append((alerts, fields))

    class PolicyBaselineService:
        def __init__(self, policy_obj):
            self.policy_obj = policy_obj

        def clear(self):
            baseline_calls.append(("clear", self.policy_obj.id))

    class AlertLifecycleNotifier:
        def __init__(self, policy_obj):
            self.policy_obj = policy_obj

        def notify_alerts(self, alerts, action, operator="", reason=""):
            lifecycle_calls.append((alerts, action, operator, reason))

    module.MonitorPolicy = MonitorPolicy
    module.MonitorAlert = MonitorAlert
    module.PolicyBaselineService = PolicyBaselineService
    module.AlertLifecycleNotifier = AlertLifecycleNotifier
    module.datetime = _FrozenDateTime

    module.MonitorPolicyViewSet().update_policy_baselines(
        policy_id=policy.id,
        enable_alerts=["threshold"],
        operator="alice",
    )

    assert filter_calls == [{"policy_id": policy.id, "alert_type": "no_data", "status": "new"}]
    assert active_no_data_alert.status == "closed"
    assert active_no_data_alert.end_event_time == _FrozenDateTime.fixed_now
    assert active_no_data_alert.operator == "alice"
    assert active_no_data_alert.operation_logs[-1]["reason"] == "no_data_disabled"
    assert recovered_no_data_alert.status == "recovered"
    assert active_threshold_alert.status == "new"
    assert bulk_updates == [([active_no_data_alert], ["status", "end_event_time", "operator", "operation_logs", "alert_center_notified"])]
    assert lifecycle_calls == [([active_no_data_alert], "closed", "alice", "no_data_disabled")]
    assert baseline_calls == [("clear", policy.id)]


def _install_scanner_dependencies(monkeypatch):
    alert_constants = types.SimpleNamespace(THRESHOLD="threshold", NO_DATA="no_data")

    _install_module(monkeypatch, "apps.monitor.constants.alert_policy", AlertConstants=alert_constants)
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorInstanceOrganization=object,
        MonitorAlert=object,
        MonitorInstance=object,
        PolicyInstanceBaseline=object,
    )
    _install_module(monkeypatch, "apps.monitor.services.policy_baseline", PolicyBaselineService=object)
    _install_module(monkeypatch, "apps.monitor.tasks.services.policy_scan.metric_query", MetricQueryService=object)
    _install_module(monkeypatch, "apps.monitor.tasks.services.policy_scan.alert_detector", AlertDetector=object)
    _install_module(monkeypatch, "apps.monitor.tasks.services.policy_scan.event_alert_manager", EventAlertManager=object)
    _install_module(monkeypatch, "apps.monitor.tasks.services.policy_scan.snapshot_recorder", SnapshotRecorder=object)
    _install_module(monkeypatch, "apps.core.logger", celery_logger=_Logger())
    return alert_constants


def test_policy_scan_collect_events_propagates_threshold_failures(monkeypatch):
    alert_constants = _install_scanner_dependencies(monkeypatch)
    module = _load_module(
        "monitor_policy_scanner_failure_test_module",
        Path(__file__).resolve().parents[1] / "tasks" / "services" / "policy_scan" / "scanner.py",
    )

    scanner = object.__new__(module.MonitorPolicyScan)
    scanner.policy = types.SimpleNamespace(id=1003, enable_alerts=[alert_constants.THRESHOLD])

    def fail_threshold():
        raise RuntimeError("metric query failed")

    scanner._process_threshold_alerts = fail_threshold

    with pytest.raises(RuntimeError, match="metric query failed"):
        scanner._collect_events()


def test_policy_scan_pre_check_propagates_metric_setup_failures(monkeypatch):
    _install_scanner_dependencies(monkeypatch)
    module = _load_module(
        "monitor_policy_scanner_precheck_test_module",
        Path(__file__).resolve().parents[1] / "tasks" / "services" / "policy_scan" / "scanner.py",
    )

    scanner = object.__new__(module.MonitorPolicyScan)
    scanner.policy = types.SimpleNamespace(id=1004, source={})
    scanner.metric_query_service = types.SimpleNamespace(set_monitor_obj_instance_key=lambda: (_ for _ in ()).throw(RuntimeError("metric missing")))

    with pytest.raises(RuntimeError, match="metric missing"):
        scanner._pre_check()


def test_snapshot_recorder_reuses_fallback_raw_metric_query_for_multiple_alerts(monkeypatch):
    module = _load_snapshot_recorder_module(monkeypatch, "monitor_policy_snapshot_recorder_cache_test_module")

    policy = types.SimpleNamespace(
        id=1005,
        period={"type": "min", "value": 1},
        group_by=["instance_id"],
        last_run_time=datetime(2026, 5, 14, 8, 0, tzinfo=timezone.utc),
    )
    query_calls = []

    def query_raw_metrics(period):
        query_calls.append(period)
        return {
            "data": {
                "result": [
                    {"metric": {"instance_id": "host-1"}, "values": [[1, "1"]]},
                    {"metric": {"instance_id": "host-2"}, "values": [[1, "2"]]},
                ]
            }
        }

    recorder = module.SnapshotRecorder(
        policy,
        {},
        [
            types.SimpleNamespace(id=1, metric_instance_id="('host-1',)", monitor_instance_id="host-1", alert_type="alert"),
            types.SimpleNamespace(id=2, metric_instance_id="('host-2',)", monitor_instance_id="host-2", alert_type="alert"),
        ],
        types.SimpleNamespace(query_raw_metrics=query_raw_metrics),
    )
    snapshot_calls = []
    recorder._update_alert_snapshot = (
        lambda alert, event_objs, raw_data, snapshot_time, is_new_alert=False, is_no_data_alert=False: snapshot_calls.append((alert.id, raw_data))
    )

    recorder.record_snapshots_for_active_alerts()

    assert len(query_calls) == 1
    assert snapshot_calls == [
        (1, {"metric": {"instance_id": "host-1"}, "values": [[1, "1"]]}),
        (2, {"metric": {"instance_id": "host-2"}, "values": [[1, "2"]]}),
    ]


def test_snapshot_recorder_skips_fallback_raw_metric_query_for_no_data_alerts(monkeypatch):
    module = _load_snapshot_recorder_module(monkeypatch, "monitor_policy_snapshot_recorder_no_data_test_module")

    policy = types.SimpleNamespace(
        id=1006,
        period={"type": "min", "value": 1},
        group_by=["instance_id"],
        last_run_time=datetime(2026, 5, 14, 8, 0, tzinfo=timezone.utc),
    )

    def unexpected_query(period):
        raise AssertionError("no_data snapshots should not query fallback raw metrics")

    recorder = module.SnapshotRecorder(
        policy,
        {},
        [
            types.SimpleNamespace(id=3, metric_instance_id="('host-3',)", monitor_instance_id="host-3", alert_type="no_data"),
        ],
        types.SimpleNamespace(query_raw_metrics=unexpected_query),
    )
    snapshot_calls = []
    recorder._update_alert_snapshot = (
        lambda alert, event_objs, raw_data, snapshot_time, is_new_alert=False, is_no_data_alert=False: snapshot_calls.append(
            (alert.id, raw_data, is_no_data_alert)
        )
    )

    recorder.record_snapshots_for_active_alerts()

    assert snapshot_calls == [(3, {}, True)]


def test_threshold_event_does_not_reuse_active_no_data_alert(monkeypatch):
    _install_module(
        monkeypatch,
        "apps.monitor.constants.alert_policy",
        AlertConstants=types.SimpleNamespace(),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.constants.database",
        DatabaseConstants=types.SimpleNamespace(
            BULK_CREATE_BATCH_SIZE=100,
            BULK_UPDATE_BATCH_SIZE=100,
        ),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorAlert=object,
        MonitorEvent=object,
        MonitorEventRawData=object,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.dimension",
        format_dimension_str=lambda dimensions: "",
    )
    _install_module(
        monkeypatch,
        "apps.monitor.services.alert_lifecycle_notify",
        AlertLifecycleNotifier=lambda *args, **kwargs: types.SimpleNamespace(notify_alerts=lambda *a, **kw: None),
    )
    _install_module(monkeypatch, "apps.core.logger", celery_logger=_Logger())

    module = _load_module(
        "monitor_policy_event_alert_manager_key_test_module",
        Path(__file__).resolve().parents[1] / "tasks" / "services" / "policy_scan" / "event_alert_manager.py",
    )

    metric_instance_id = "('host-1',)"
    active_no_data_alert = types.SimpleNamespace(
        id=101,
        metric_instance_id=metric_instance_id,
        monitor_instance_id="host-1",
        alert_type="no_data",
    )
    created_alert = types.SimpleNamespace(
        id=202,
        metric_instance_id=metric_instance_id,
        alert_type="alert",
    )
    created_from_events = []
    persisted_events = []
    existing_updates = []

    manager = object.__new__(module.EventAlertManager)
    manager.policy = types.SimpleNamespace(id=1006, name="mixed-policy")
    manager.active_alerts = [active_no_data_alert]
    manager._create_alerts_from_events = lambda events: created_from_events.extend(events) or [created_alert]
    manager.create_events = lambda events: persisted_events.extend(events) or events
    manager._update_existing_alerts_from_events = lambda events: existing_updates.extend(events)

    threshold_event = {
        "metric_instance_id": metric_instance_id,
        "monitor_instance_id": "host-1",
        "dimensions": {"instance_id": "host-1"},
        "value": 95.0,
        "level": "critical",
        "content": "cpu critical",
    }

    event_objs, new_alerts = manager.create_events_and_alerts([threshold_event])

    assert created_from_events == [threshold_event]
    assert persisted_events == [threshold_event]
    assert existing_updates == []
    assert threshold_event["alert_id"] == created_alert.id
    assert threshold_event["_alert_obj"] is created_alert
    assert event_objs == [threshold_event]
    assert new_alerts == [created_alert]


def test_alert_center_created_and_recovery_events_share_same_external_id(monkeypatch):
    _install_module(
        monkeypatch,
        "apps.monitor.constants.alert_policy",
        AlertConstants=types.SimpleNamespace(),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.constants.database",
        DatabaseConstants=types.SimpleNamespace(BULK_UPDATE_BATCH_SIZE=100),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorAlert=object,
        MonitorEvent=types.SimpleNamespace(objects=types.SimpleNamespace(bulk_update=lambda *args, **kwargs: None)),
        MonitorEventRawData=object,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.dimension",
        format_dimension_str=lambda dimensions: "",
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.system_mgmt_api",
        SystemMgmtUtils=types.SimpleNamespace(send_msg_with_channel=lambda *args, **kwargs: {"result": True}),
    )
    _install_module(monkeypatch, "apps.system_mgmt.models", Channel=object)
    _install_module(monkeypatch, "apps.core.logger", celery_logger=_Logger(), monitor_logger=_Logger())

    lifecycle_module = _load_module(
        "monitor_alert_lifecycle_notify_consistency_test_module",
        Path(__file__).resolve().parents[1] / "services" / "alert_lifecycle_notify.py",
    )

    alert = types.SimpleNamespace(
        id=99,
        policy_id=1011,
        content="cpu critical",
        level="critical",
        value=95.0,
        start_event_time=datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc),
        end_event_time=datetime(2026, 4, 21, 8, 5, tzinfo=timezone.utc),
        monitor_instance_id="host-1",
        monitor_instance_name="Host 1",
        dimensions={"instance_id": "host-1"},
        metric_instance_id="('host-1',)",
        status="recovered",
        notice_type_ids=[9],
        notice_users=[],
    )

    lifecycle_notifier = object.__new__(lifecycle_module.AlertLifecycleNotifier)
    lifecycle_notifier.policy = types.SimpleNamespace(id=1011, name="alert-center-policy", notice_type_ids=[9])

    created_payload = lifecycle_notifier._build_alert_center_payload(alert, "created", operator="", reason="")
    recovery_payload = lifecycle_notifier._build_alert_center_payload(alert, "recovered", operator="tester", reason="auto")

    assert created_payload["external_id"] == str(alert.id)
    assert recovery_payload["external_id"] == str(alert.id)
    assert created_payload["external_id"] == recovery_payload["external_id"]


def test_last_over_time_uses_policy_window_in_range_selector(monkeypatch):
    query_calls = []

    class VictoriaMetricsAPI:
        def query(self, query, step="5m", time=None):
            query_calls.append((query, step, time))
            return {"data": {"result": [{"value": [200, "7"]}]}}

    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=Exception,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.victoriametrics_api",
        VictoriaMetricsAPI=VictoriaMetricsAPI,
    )

    module = _load_module(
        "monitor_policy_methods_last_over_time_test_module",
        Path(__file__).resolve().parents[1] / "tasks" / "utils" / "policy_methods.py",
    )

    result = module.last_over_time(
        "ping_percent_packet_loss{instance_type='ping'}",
        start=100,
        end=200,
        step="5m",
        group_by="instance_id",
    )

    assert query_calls == [
        (
            "any(last_over_time(ping_percent_packet_loss{instance_type='ping'}[5m])) by (instance_id)",
            None,
            200,
        )
    ]
    assert result["data"]["result"][0]["values"] == [[200, "7"]]


@pytest.mark.parametrize(
    "method_name",
    ["sum_over_time", "max_over_time", "min_over_time", "avg_over_time"],
)
def test_over_time_methods_use_policy_window_in_range_selector(monkeypatch, method_name):
    query_calls = []

    class VictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            query_calls.append((query, start, end, step))
            return {"data": {"result": [{"values": [[200, "7"]]}]}}

    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=Exception,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.victoriametrics_api",
        VictoriaMetricsAPI=VictoriaMetricsAPI,
    )

    module = _load_module(
        f"monitor_policy_methods_{method_name}_test_module",
        Path(__file__).resolve().parents[1] / "tasks" / "utils" / "policy_methods.py",
    )

    result = getattr(module, method_name)(
        "node_cpu_seconds_total",
        start=100,
        end=200,
        step="5m",
        group_by="instance_id",
    )

    assert query_calls == [
        (
            f"any({method_name}(node_cpu_seconds_total[5m])) by (instance_id)",
            100,
            200,
            "5m",
        )
    ]
    assert result["data"]["result"][0]["values"] == [[200, "7"]]


def test_last_over_time_uses_policy_window_for_bare_metric_selector(monkeypatch):
    query_calls = []

    class VictoriaMetricsAPI:
        def query(self, query, step="5m", time=None):
            query_calls.append((query, step, time))
            return {"data": {"result": [{"value": [200, "11"]}]}}

    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=Exception,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.victoriametrics_api",
        VictoriaMetricsAPI=VictoriaMetricsAPI,
    )

    module = _load_module(
        "monitor_policy_methods_last_over_time_bare_metric_test_module",
        Path(__file__).resolve().parents[1] / "tasks" / "utils" / "policy_methods.py",
    )

    result = module.last_over_time("node_cpu_seconds_total", start=100, end=200, step="1m", group_by="instance_id")

    assert query_calls == [
        (
            "any(last_over_time(node_cpu_seconds_total[1m])) by (instance_id)",
            None,
            200,
        )
    ]
    assert result["data"]["result"][0]["values"] == [[200, "11"]]


def test_last_over_time_uses_policy_window_for_label_only_selector(monkeypatch):
    query_calls = []

    class VictoriaMetricsAPI:
        def query(self, query, step="5m", time=None):
            query_calls.append((query, step, time))
            return {"data": {"result": [{"value": [200, "13"]}]}}

    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=Exception,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.victoriametrics_api",
        VictoriaMetricsAPI=VictoriaMetricsAPI,
    )

    module = _load_module(
        "monitor_policy_methods_last_over_time_label_selector_test_module",
        Path(__file__).resolve().parents[1] / "tasks" / "utils" / "policy_methods.py",
    )

    result = module.last_over_time("{instance_type='ping'}", start=100, end=200, step="1m", group_by="instance_id")

    assert query_calls == [
        (
            "any(last_over_time({instance_type='ping'}[1m])) by (instance_id)",
            None,
            200,
        )
    ]
    assert result["data"]["result"][0]["values"] == [[200, "13"]]


def test_last_over_time_keeps_step_query_for_complex_pmq(monkeypatch):
    query_calls = []

    class VictoriaMetricsAPI:
        def query(self, query, step="5m", time=None):
            query_calls.append((query, step, time))
            return {"data": {"result": [{"value": [200, "9"]}]}}

    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=Exception,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.victoriametrics_api",
        VictoriaMetricsAPI=VictoriaMetricsAPI,
    )

    module = _load_module(
        "monitor_policy_methods_last_over_time_complex_query_test_module",
        Path(__file__).resolve().parents[1] / "tasks" / "utils" / "policy_methods.py",
    )

    result = module.last_over_time(
        "sum(rate(ping_percent_packet_loss{instance_type='ping'}[1m])) by (instance_id)",
        start=100,
        end=200,
        step="5m",
        group_by="instance_id",
    )

    assert query_calls == [
        (
            "any(last_over_time(sum(rate(ping_percent_packet_loss{instance_type='ping'}[1m])) by (instance_id))) by (instance_id)",
            "5m",
            200,
        )
    ]
    assert result["data"]["result"][0]["values"] == [[200, "9"]]


def test_last_over_time_keeps_step_query_for_offset_selector(monkeypatch):
    query_calls = []

    class VictoriaMetricsAPI:
        def query(self, query, step="5m", time=None):
            query_calls.append((query, step, time))
            return {"data": {"result": [{"value": [200, "17"]}]}}

    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=Exception,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.victoriametrics_api",
        VictoriaMetricsAPI=VictoriaMetricsAPI,
    )

    module = _load_module(
        "monitor_policy_methods_last_over_time_offset_selector_test_module",
        Path(__file__).resolve().parents[1] / "tasks" / "utils" / "policy_methods.py",
    )

    result = module.last_over_time("node_cpu_seconds_total offset 5m", start=100, end=200, step="1m", group_by="instance_id")

    assert query_calls == [
        (
            "any(last_over_time(node_cpu_seconds_total offset 5m)) by (instance_id)",
            "1m",
            200,
        )
    ]
    assert result["data"]["result"][0]["values"] == [[200, "17"]]


def _install_policy_baseline_dependencies(monkeypatch):
    _install_module(monkeypatch, "apps.core.logger", monitor_logger=_Logger())
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorInstance=object,
        MonitorInstanceOrganization=object,
        PolicyInstanceBaseline=object,
    )


def test_policy_baseline_query_metric_instances_returns_none_when_query_fails(monkeypatch):
    _install_policy_baseline_dependencies(monkeypatch)

    class MetricQueryService:
        def __init__(self, policy, instances_map):
            self.policy = policy
            self.instances_map = instances_map

        def set_monitor_obj_instance_key(self):
            return None

        def query_aggregation_metrics(self, period):
            raise RuntimeError("victoriametrics unavailable")

    _install_module(
        monkeypatch,
        "apps.monitor.tasks.services.policy_scan.metric_query",
        MetricQueryService=MetricQueryService,
    )

    module = _load_module(
        "monitor_policy_baseline_query_failure_test_module",
        Path(__file__).resolve().parents[1] / "services" / "policy_baseline.py",
    )

    policy = types.SimpleNamespace(
        id=1010,
        source={"type": "instance", "values": ["host-1"]},
        last_run_time=datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc),
        period={"type": "min", "value": 1},
        group_by=["instance_id"],
    )

    service = module.PolicyBaselineService(policy)

    assert service._query_metric_instances({"host-1": "Host 1"}) is None


def test_policy_baseline_refresh_keeps_existing_baselines_when_query_fails(monkeypatch):
    _install_policy_baseline_dependencies(monkeypatch)
    module = _load_module(
        "monitor_policy_baseline_refresh_failure_test_module",
        Path(__file__).resolve().parents[1] / "services" / "policy_baseline.py",
    )

    policy = types.SimpleNamespace(
        id=1011,
        source={"type": "instance", "values": ["host-1"]},
    )
    service = module.PolicyBaselineService(policy)
    clear_calls = []
    replace_calls = []

    monkeypatch.setattr(service, "_build_instances_map", lambda: {"host-1": "Host 1"})
    monkeypatch.setattr(service, "_query_metric_instances", lambda instances_map: None)
    monkeypatch.setattr(service, "clear", lambda: clear_calls.append(True))
    monkeypatch.setattr(
        service,
        "_replace_baselines",
        lambda metric_instances: replace_calls.append(metric_instances),
    )

    service.refresh()

    assert clear_calls == []
    assert replace_calls == []


def test_policy_baseline_refresh_clears_baselines_when_query_succeeds_but_is_empty(monkeypatch):
    _install_policy_baseline_dependencies(monkeypatch)
    module = _load_module(
        "monitor_policy_baseline_refresh_empty_result_test_module",
        Path(__file__).resolve().parents[1] / "services" / "policy_baseline.py",
    )

    policy = types.SimpleNamespace(
        id=1012,
        source={"type": "instance", "values": ["host-1"]},
    )
    service = module.PolicyBaselineService(policy)
    clear_calls = []
    replace_calls = []

    monkeypatch.setattr(service, "_build_instances_map", lambda: {"host-1": "Host 1"})
    monkeypatch.setattr(service, "_query_metric_instances", lambda instances_map: {})
    monkeypatch.setattr(service, "clear", lambda: clear_calls.append(True))
    monkeypatch.setattr(
        service,
        "_replace_baselines",
        lambda metric_instances: replace_calls.append(metric_instances),
    )

    service.refresh()

    assert clear_calls == [True]
    assert replace_calls == []


def _install_lifecycle_notify_dependencies(monkeypatch, send_side_effect):
    """Helper: install minimal mocks to load alert_lifecycle_notify.py"""
    _install_module(
        monkeypatch,
        "apps.monitor.utils.system_mgmt_api",
        SystemMgmtUtils=types.SimpleNamespace(send_msg_with_channel=send_side_effect),
    )
    _install_module(monkeypatch, "apps.system_mgmt.models", Channel=object)
    _install_module(monkeypatch, "apps.core.logger", monitor_logger=_Logger())
    return _load_module(
        f"monitor_alert_lifecycle_retry_{id(send_side_effect)}",
        Path(__file__).resolve().parents[1] / "services" / "alert_lifecycle_notify.py",
    )


def test_push_to_alert_center_returns_failure_on_first_failed_attempt(monkeypatch):
    """_push_to_alert_center 单次尝试失败时应返回 success=False，不重试"""
    call_count = []

    def always_fail(*args, **kwargs):
        call_count.append(1)
        return {"result": False, "message": "transient error"}

    sleep_calls = []
    monkeypatch.setattr("time.sleep", lambda s: sleep_calls.append(s))

    module = _install_lifecycle_notify_dependencies(monkeypatch, always_fail)

    notifier = object.__new__(module.AlertLifecycleNotifier)
    notifier.policy = None

    alert = types.SimpleNamespace(
        id=1,
        policy_id=10,
        content="test",
        level="warning",
        value=50.0,
        start_event_time=None,
        end_event_time=None,
        monitor_instance_id="host-1",
        monitor_instance_name="Host 1",
        dimensions={},
        metric_instance_id="",
        status="recovered",
    )

    results = notifier._push_to_alert_center(9, "alert-center", [alert], "recovered", "", "")

    assert len(call_count) == 1
    assert sleep_calls == []
    assert len(results) == 1
    log_alert, log_entry = results[0]
    assert log_entry["success"] is False
    assert log_entry.get("is_alert_center") is True


def test_push_to_alert_center_returns_success_on_first_successful_attempt(monkeypatch):
    """_push_to_alert_center 单次尝试成功时应返回 success=True"""
    call_count = []

    def always_succeed(*args, **kwargs):
        call_count.append(1)
        return {"result": True}

    sleep_calls = []
    monkeypatch.setattr("time.sleep", lambda s: sleep_calls.append(s))

    module = _install_lifecycle_notify_dependencies(monkeypatch, always_succeed)

    notifier = object.__new__(module.AlertLifecycleNotifier)
    notifier.policy = None

    alert = types.SimpleNamespace(
        id=2,
        policy_id=10,
        content="test",
        level="critical",
        value=99.0,
        start_event_time=None,
        end_event_time=None,
        monitor_instance_id="host-2",
        monitor_instance_name="Host 2",
        dimensions={},
        metric_instance_id="",
        status="closed",
    )

    results = notifier._push_to_alert_center(9, "alert-center", [alert], "closed", "", "")

    assert len(call_count) == 1
    assert sleep_calls == []
    log_alert, log_entry = results[0]
    assert log_entry["success"] is True
    # 成功路径不应携带 error 字段（仅失败时记录）
    assert "error" not in log_entry


def test_retry_alert_center_lifecycle_notify_task_marks_success_and_increments_failures(monkeypatch):
    """补偿任务：成功的告警标记 notified=True，失败的递增 retry_count"""
    recovered_alert = types.SimpleNamespace(
        id=10,
        status="recovered",
        alert_center_notified=False,
        alert_center_retry_count=0,
    )
    closed_alert = types.SimpleNamespace(
        id=20,
        status="closed",
        alert_center_notified=False,
        alert_center_retry_count=2,
    )
    update_calls = []  # 记录 (filter_kwargs, update_kwargs)，验证失败路径的 F() 原子递增

    class _UpdateQS:
        def __init__(self, filter_kwargs):
            self.filter_kwargs = filter_kwargs

        def update(self, **kwargs):
            update_calls.append((self.filter_kwargs, kwargs))
            return len(self.filter_kwargs.get("id__in", []))

    class _AlertQS:
        def filter(self, **kwargs):
            # 失败递增走 filter(id__in=...).update()；补偿查询走 order_by/__getitem__
            if "id__in" in kwargs and "status__in" not in kwargs:
                return _UpdateQS(kwargs)
            return self

        def order_by(self, *args):
            return self

        def __getitem__(self, sl):
            return [recovered_alert, closed_alert]

    class _MonitorAlert:
        objects = _AlertQS()

    def shared_task(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    # recovered → push succeeds, closed → push fails
    push_results = {
        "recovered": [(recovered_alert, True)],
        "closed": [(closed_alert, False)],
    }

    marked_success = []

    class _FakeNotifier:
        def __init__(self, policy=None):
            pass

        def push_to_alert_center_only(self, alerts, action, **kwargs):
            return push_results[action]

        def _mark_alert_center_notified(self, alert_ids):
            marked_success.extend(list(alert_ids))

    _install_module(monkeypatch, "celery", shared_task=shared_task)
    _install_module(monkeypatch, "celery_singleton", Singleton=object)
    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=Exception)
    _install_module(monkeypatch, "apps.monitor.models", MonitorPolicy=object, MonitorAlert=_MonitorAlert)
    _install_module(monkeypatch, "apps.core.logger", celery_logger=_Logger())
    _install_module(monkeypatch, "apps.monitor.tasks.services.policy_scan", MonitorPolicyScan=object)
    _install_module(monkeypatch, "apps.monitor.tasks.utils.policy_methods", period_to_seconds=lambda p: 60)
    _install_module(
        monkeypatch,
        "apps.monitor.constants.alert_policy",
        AlertConstants=types.SimpleNamespace(MAX_BACKFILL_SECONDS=3600, MAX_BACKFILL_COUNT=10),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.services.alert_lifecycle_notify",
        AlertLifecycleNotifier=_FakeNotifier,
    )

    module = _load_module(
        "monitor_policy_retry_task_test_module",
        Path(__file__).resolve().parents[1] / "tasks" / "monitor_policy.py",
    )

    result = module.retry_alert_center_lifecycle_notify_task()

    assert result["succeeded"] == 1
    assert result["failed"] == 1
    assert result["total"] == 2

    # 成功路径：复用 _mark_alert_center_notified，传入成功告警 id
    assert marked_success == [10]

    # 失败路径：filter(id__in=[20]).update() 做 F() 原子递增
    fail_update = next((c for c in update_calls if c[0].get("id__in") == [20]), None)
    assert fail_update is not None
    assert "alert_center_retry_count" in fail_update[1]
