"""Issue #3336：告警扫描多表写入事务化 + 通知延后到提交后（event_alert_manager）。

验证 Django-free 逻辑：① create_events_and_alerts 把写操作包进 transaction.atomic；
② 告警通知不再内联发出，而是注册到 transaction.on_commit（保证通知永不早于事件落库）；
③ _create_alerts_from_events / _update_existing_alerts_from_events 不再内联通知。
沿用注入式 harness（pytest 因缺 license_mgmt/MINIO 无法 django.setup）。
"""
import importlib.util
import sys
import types
from pathlib import Path


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


class _Logger:
    def info(self, *a, **k):
        return None

    def warning(self, *a, **k):
        return None

    def error(self, *a, **k):
        return None

    def debug(self, *a, **k):
        return None


class _Atomic:
    def __init__(self, log):
        self._log = log

    def __enter__(self):
        self._log.append("atomic-enter")
        return self

    def __exit__(self, *exc):
        self._log.append("atomic-exit")
        return False


def _load_event_alert_manager(monkeypatch, module_name, notify_log, on_commit_callbacks, atomic_log):
    _install_module(
        monkeypatch,
        "django.db",
        transaction=types.SimpleNamespace(
            atomic=lambda *a, **k: _Atomic(atomic_log),
            on_commit=lambda cb: on_commit_callbacks.append(cb),  # 仅捕获，不立即执行 → 可断言「延后」
        ),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.constants.alert_policy",
        AlertConstants=types.SimpleNamespace(LEVEL_WEIGHT={"warning": 2, "error": 3, "critical": 4}),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.constants.database",
        DatabaseConstants=types.SimpleNamespace(BULK_CREATE_BATCH_SIZE=100, BULK_UPDATE_BATCH_SIZE=100),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorAlert=object,
        MonitorEvent=object,
        MonitorEventRawData=object,
    )
    _install_module(monkeypatch, "apps.monitor.utils.dimension", format_dimension_str=lambda dimensions: "")

    def _make_notifier(policy):
        return types.SimpleNamespace(
            notify_alerts=lambda alerts, action: notify_log.append((action, [getattr(a, "id", a) for a in alerts]))
        )

    _install_module(monkeypatch, "apps.monitor.services.alert_lifecycle_notify", AlertLifecycleNotifier=_make_notifier)
    _install_module(monkeypatch, "apps.core.logger", celery_logger=_Logger())

    spec = importlib.util.spec_from_file_location(
        module_name,
        Path(__file__).resolve().parents[1] / "tasks" / "services" / "policy_scan" / "event_alert_manager.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bare_manager(module, policy):
    manager = object.__new__(module.EventAlertManager)
    manager.policy = policy
    manager.instances_map = {}
    manager.active_alerts = []
    return manager


def test_create_events_and_alerts_defers_notification_to_on_commit(monkeypatch):
    notify_log, on_commit_callbacks, atomic_log = [], [], []
    module = _load_event_alert_manager(monkeypatch, "eam_defer_module", notify_log, on_commit_callbacks, atomic_log)

    created_alert = types.SimpleNamespace(id=202, metric_instance_id="('h1',)", alert_type="alert")
    manager = _bare_manager(module, types.SimpleNamespace(id=1, notice=True))
    manager._create_alerts_from_events = lambda events: [created_alert]
    manager.create_events = lambda events: list(events)
    manager._update_existing_alerts_from_events = lambda events: []

    event = {"metric_instance_id": "('h1',)", "monitor_instance_id": "h1", "level": "critical", "value": 9, "content": "x"}
    event_objs, new_alerts = manager.create_events_and_alerts([event])

    # 写操作包进了事务
    assert atomic_log == ["atomic-enter", "atomic-exit"]
    # 调用结束时通知尚未发出（延后到 on_commit），且注册了一个提交后回调
    assert notify_log == []
    assert len(on_commit_callbacks) == 1
    assert new_alerts == [created_alert]

    # 模拟事务提交：执行 on_commit 回调后，通知才发出
    for cb in on_commit_callbacks:
        cb()
    assert notify_log == [("created", [202])]


def test_schedule_notifications_respects_notice_flag(monkeypatch):
    notify_log, on_commit_callbacks, atomic_log = [], [], []
    module = _load_event_alert_manager(monkeypatch, "eam_notice_module", notify_log, on_commit_callbacks, atomic_log)

    created = types.SimpleNamespace(id=1)
    upgraded = types.SimpleNamespace(id=2)

    # notice=False → 不注册任何通知
    m_off = _bare_manager(module, types.SimpleNamespace(id=1, notice=False))
    m_off._schedule_notifications([created], [upgraded])
    assert on_commit_callbacks == []

    # notice=True → created + upgraded 各注册一个，执行后按 action 发出
    m_on = _bare_manager(module, types.SimpleNamespace(id=1, notice=True))
    m_on._schedule_notifications([created], [upgraded])
    assert len(on_commit_callbacks) == 2
    for cb in on_commit_callbacks:
        cb()
    assert ("created", [1]) in notify_log
    assert ("upgraded", [2]) in notify_log


def test_create_alerts_helper_no_longer_notifies_inline(monkeypatch):
    notify_log, on_commit_callbacks, atomic_log = [], [], []
    module = _load_event_alert_manager(monkeypatch, "eam_helper_module", notify_log, on_commit_callbacks, atomic_log)

    class _Alert:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
            self.id = 500

    # MonitorAlert 需可作构造器（_create_alerts_from_events 内 MonitorAlert(...)），
    # 且 objects.bulk_create 返回带 id 的对象（触发 hasattr(new_alerts[0],"id") 为真、跳过 refetch 分支）
    class _AlertModel:
        objects = types.SimpleNamespace(
            bulk_create=lambda objs, batch_size=None: [_Alert(id=500, metric_instance_id="('h1',)", alert_type="alert")]
        )

        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr(module, "MonitorAlert", _AlertModel, raising=False)

    manager = _bare_manager(
        module,
        types.SimpleNamespace(id=1, notice=True, no_data_level="warning", notice_type_ids=[], notice_users=[], last_run_time=None),
    )
    events = [{"metric_instance_id": "('h1',)", "monitor_instance_id": "h1", "level": "critical", "value": 9, "content": "x", "dimensions": {}}]

    result = manager._create_alerts_from_events(events)

    # 真实辅助方法返回告警，但不再内联发任何通知
    assert len(result) == 1
    assert notify_log == []
    assert on_commit_callbacks == []
