"""Issue #3341：首次告警通知失败必须进入告警中心补偿队列。"""

import ast
import sys
import types
from collections import defaultdict
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

MONITOR_ROOT = Path(__file__).resolve().parents[1]


def _load_methods(path, class_name, method_names, globals_dict):
    tree = ast.parse(path.read_text())
    source_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    methods = [
        node for node in source_class.body
        if isinstance(node, ast.FunctionDef) and node.name in method_names
    ]
    probe_class = ast.ClassDef(
        name="Subject",
        bases=[],
        keywords=[],
        body=methods,
        decorator_list=[],
    )
    ast.fix_missing_locations(probe_class)
    exec(
        compile(ast.Module(body=[probe_class], type_ignores=[]), str(path), "exec"),
        globals_dict,
    )
    return globals_dict["Subject"]


def _load_method(path, class_name, method_name, globals_dict):
    return _load_methods(path, class_name, {method_name}, globals_dict)


def _load_function(path, function_name, globals_dict):
    tree = ast.parse(path.read_text())
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    function.decorator_list = []
    ast.fix_missing_locations(function)
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"),
        globals_dict,
    )
    return globals_dict[function_name]


class _PendingObjects:
    def __init__(self, notified_by_id, events):
        self.notified_by_id = notified_by_id
        self.events = events
        self.ids = []

    def filter(self, **kwargs):
        self.ids = list(kwargs["id__in"])
        return self

    def update(self, **kwargs):
        for alert_id in self.ids:
            self.notified_by_id[alert_id] = kwargs["alert_center_notified"]
        self.events.append(("update", dict(self.notified_by_id)))


def test_schedule_notifications_persists_pending_state_before_on_commit():
    notified_by_id = {101: True, 102: True}
    events = []
    callbacks = []
    notify_calls = []

    def on_commit(callback):
        events.append(("on_commit", dict(notified_by_id)))
        callbacks.append(callback)

    subject = _load_method(
        MONITOR_ROOT / "tasks/services/policy_scan/event_alert_manager.py",
        "EventAlertManager",
        "_schedule_notifications",
        {
            "transaction": types.SimpleNamespace(on_commit=on_commit),
            "MonitorAlert": types.SimpleNamespace(
                objects=_PendingObjects(notified_by_id, events)
            ),
            "AlertLifecycleNotifier": lambda policy: types.SimpleNamespace(
                notify_alerts=lambda alerts, action: notify_calls.append(
                    (action, [alert.id for alert in alerts])
                )
            ),
        },
    )()
    subject.policy = types.SimpleNamespace(notice=True)

    subject._schedule_notifications(
        [types.SimpleNamespace(id=101)],
        [types.SimpleNamespace(id=102)],
    )

    assert notified_by_id == {101: False, 102: False}
    assert events == [
        ("update", {101: False, 102: False}),
        ("on_commit", {101: False, 102: False}),
        ("on_commit", {101: False, 102: False}),
    ]
    for callback in callbacks:
        callback()
    assert notify_calls == [("created", [101]), ("upgraded", [102])]


def test_schedule_notifications_disabled_keeps_notified_state():
    notified_by_id = {101: True}
    events = []
    subject = _load_method(
        MONITOR_ROOT / "tasks/services/policy_scan/event_alert_manager.py",
        "EventAlertManager",
        "_schedule_notifications",
        {
            "transaction": types.SimpleNamespace(
                on_commit=lambda callback: events.append(("on_commit", callback))
            ),
            "MonitorAlert": types.SimpleNamespace(
                objects=_PendingObjects(notified_by_id, events)
            ),
            "AlertLifecycleNotifier": object,
        },
    )()
    subject.policy = types.SimpleNamespace(notice=False)

    subject._schedule_notifications([types.SimpleNamespace(id=101)], [])

    assert notified_by_id == {101: True}
    assert events == []


class _RetryQuery:
    def __init__(self, alerts):
        self.alerts = alerts

    def order_by(self, *fields):
        return self

    def __getitem__(self, item):
        return _RetryQuery(self.alerts[item])

    def __iter__(self):
        return iter(self.alerts)


class _RetryObjects:
    def __init__(self, alerts):
        self.alerts = alerts
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        selected = list(self.alerts)
        if "status__in" in kwargs:
            selected = [a for a in selected if a.status in kwargs["status__in"]]
        if "alert_center_notified" in kwargs:
            selected = [
                a for a in selected
                if a.alert_center_notified == kwargs["alert_center_notified"]
            ]
        if "alert_center_retry_count__lt" in kwargs:
            selected = [
                a for a in selected
                if a.alert_center_retry_count < kwargs["alert_center_retry_count__lt"]
            ]
        return _RetryQuery(selected)


def test_retry_task_selects_pending_lifecycle_actions(monkeypatch):
    policy_a = types.SimpleNamespace(id=301, name="策略 A", organizations=[7])
    policy_b = types.SimpleNamespace(id=303, name="策略 B", organizations=[8])
    alerts = [
        types.SimpleNamespace(
            id=201, status="new",
            policy_id=policy_a.id,
            alert_center_notified=False, alert_center_retry_count=0,
        ),
        types.SimpleNamespace(
            id=206, status="new",
            policy_id=policy_b.id,
            alert_center_notified=False, alert_center_retry_count=0,
        ),
        types.SimpleNamespace(
            id=202, status="recovered",
            policy_id=302,
            alert_center_notified=False, alert_center_retry_count=0,
        ),
        types.SimpleNamespace(
            id=203, status="closed",
            policy_id=302,
            alert_center_notified=False, alert_center_retry_count=9,
        ),
        types.SimpleNamespace(
            id=204, status="new",
            policy_id=policy_a.id,
            alert_center_notified=True, alert_center_retry_count=0,
        ),
        types.SimpleNamespace(
            id=205, status="new",
            policy_id=policy_a.id,
            alert_center_notified=False, alert_center_retry_count=10,
        ),
    ]
    objects = _RetryObjects(alerts)
    loaded_policy_ids = []
    pushes = []
    marked = []
    notifier_policies = []
    notifier = types.SimpleNamespace(
        push_to_alert_center_only=lambda grouped, action: (
            pushes.append((action, [alert.id for alert in grouped]))
            or [(alert, True) for alert in grouped]
        ),
        _mark_alert_center_notified=lambda alert_ids: marked.append(alert_ids),
    )
    models = types.ModuleType("apps.monitor.models")
    models.MonitorAlert = types.SimpleNamespace(objects=objects)
    models.MonitorPolicy = types.SimpleNamespace(
        objects=types.SimpleNamespace(
            in_bulk=lambda policy_ids: (
                loaded_policy_ids.append(set(policy_ids))
                or {policy_a.id: policy_a, policy_b.id: policy_b}
            )
        )
    )
    notify_module = types.ModuleType(
        "apps.monitor.services.alert_lifecycle_notify"
    )

    def build_notifier(notifier_policy=None, policies_by_id=None):
        notifier_policies.append((notifier_policy, policies_by_id))
        return notifier

    notify_module.AlertLifecycleNotifier = build_notifier
    monkeypatch.setitem(sys.modules, "apps.monitor.models", models)
    monkeypatch.setitem(
        sys.modules,
        "apps.monitor.services.alert_lifecycle_notify",
        notify_module,
    )
    retry_task = _load_function(
        MONITOR_ROOT / "tasks/monitor_policy.py",
        "retry_alert_center_lifecycle_notify_task",
        {
            "defaultdict": defaultdict,
            "F": lambda field: field,
            "logger": types.SimpleNamespace(
                info=lambda *args, **kwargs: None,
                exception=lambda *args, **kwargs: None,
                error=lambda *args, **kwargs: None,
            ),
        },
    )

    result = retry_task()

    assert objects.filters == [{
        "status__in": ["new", "recovered", "closed"],
        "alert_center_notified": False,
        "alert_center_retry_count__lt": 10,
    }]
    assert pushes == [
        ("created", [201, 206]),
        ("recovered", [202]),
        ("closed", [203]),
    ]
    assert loaded_policy_ids == [{policy_a.id, policy_b.id}]
    assert notifier_policies == [
        (None, {policy_a.id: policy_a, policy_b.id: policy_b})
    ]
    assert marked == [[201, 206, 202, 203]]
    assert result == {
        "success": True,
        "total": 4,
        "succeeded": 4,
        "failed": 0,
    }


def test_retry_payload_uses_new_alert_policy_without_changing_terminal_actions():
    policy = types.SimpleNamespace(id=301, name="策略 A", organizations=[7])
    alert = types.SimpleNamespace(
        id=201,
        policy_id=policy.id,
        content="CPU 告警",
        level="critical",
        value=95,
        start_event_time=None,
        end_event_time=None,
        monitor_instance_id="host-1",
        monitor_instance_name="主机 1",
        dimensions={"ip": "127.0.0.1"},
        metric_instance_id="cpu",
        status="new",
    )
    subject = _load_methods(
        MONITOR_ROOT / "services/alert_lifecycle_notify.py",
        "AlertLifecycleNotifier",
        {"_resolve_alert_organizations", "_build_alert_center_payload"},
        {
            "ACTION_TO_ALERT_CENTER": {
                "created": "created",
                "recovered": "recovery",
            },
            "LEVEL_TO_ALERT_CENTER": {"critical": "0"},
        },
    )()
    subject.policy = None
    subject.policies_by_id = {policy.id: policy}

    created_payload = subject._build_alert_center_payload(
        alert, "created", "", "", {}
    )
    recovered_payload = subject._build_alert_center_payload(
        alert, "recovered", "", "", {}
    )

    assert created_payload["organizations"] == [7]
    assert created_payload["labels"]["policy_name"] == "策略 A"
    assert recovered_payload["organizations"] == []
    assert recovered_payload["labels"]["policy_name"] == ""
