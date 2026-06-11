"""Issue #2827: 活跃告警持续命中时不应每个扫描周期重复通知。

验证点（revert 修复后以下用例必须失败）：
1. 已成功通知且级别未变的活跃告警，后续周期不再发送通知；
2. 首次触发正常发送并回写 Alert.notice=True；
3. 级别变化重置 Alert.notice，重新放开通知；
4. 发送失败时 Alert.notice 保持 False，下个周期重试。
"""

import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


class FakeAlert:
    objects = None  # 由测试注入 FakeManager

    def __init__(self, **kwargs):
        kwargs.setdefault("notice", False)
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeEvent:
    objects = None  # 由测试注入 FakeManager

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        alert = kwargs.get("alert")
        self.alert_id = getattr(alert, "id", None)


class FakeManager:
    def __init__(self, filter_result=None):
        self.filter_result = list(filter_result or [])
        self.bulk_create_calls = []
        self.bulk_update_calls = []

    def filter(self, **kwargs):
        return list(self.filter_result)

    def bulk_create(self, objs, batch_size=None):
        self.bulk_create_calls.append(list(objs))
        return list(objs)

    def bulk_update(self, objs, fields, batch_size=None):
        self.bulk_update_calls.append((list(objs), list(fields)))


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_policy_scan_module(monkeypatch):
    _install_module(monkeypatch, "django", db=types.SimpleNamespace(transaction=types.SimpleNamespace()))
    _install_module(monkeypatch, "django.db", transaction=types.SimpleNamespace())

    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=Exception)
    _install_module(
        monkeypatch,
        "apps.log.constants.alert_policy",
        AlertConstants=types.SimpleNamespace(STATUS_NEW="new", STATUS_CLOSED="closed"),
    )
    _install_module(monkeypatch, "apps.log.constants.database", DatabaseConstants=types.SimpleNamespace(DEFAULT_BATCH_SIZE=100))
    _install_module(monkeypatch, "apps.log.constants.web", WebConstants=types.SimpleNamespace())
    _install_module(
        monkeypatch,
        "apps.log.models.policy",
        Alert=FakeAlert,
        Event=FakeEvent,
        EventRawData=object,
        AlertSnapshot=object,
    )
    _install_module(monkeypatch, "apps.log.tasks.utils.policy", period_to_seconds=lambda period: 300)
    _install_module(monkeypatch, "apps.log.utils.query_log", VictoriaMetricsAPI=lambda: None)
    _install_module(
        monkeypatch,
        "apps.log.utils.log_group",
        LogGroupQueryBuilder=types.SimpleNamespace(build_query_with_groups=lambda query, groups: (query, [])),
    )
    _install_module(monkeypatch, "apps.monitor.utils.system_mgmt_api", SystemMgmtUtils=object)
    _install_module(
        monkeypatch,
        "apps.core.logger",
        celery_logger=types.SimpleNamespace(
            warning=lambda *args, **kwargs: None,
            error=lambda *args, **kwargs: None,
            info=lambda *args, **kwargs: None,
            debug=lambda *args, **kwargs: None,
        ),
    )

    module_path = Path(__file__).resolve().parents[1] / "tasks" / "services" / "policy_scan.py"
    spec = importlib.util.spec_from_file_location("policy_scan_notice_dedup_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _build_policy():
    return SimpleNamespace(
        id=1,
        notice=True,
        notice_users=["user1"],
        notice_type_id=1,
        collect_type="collect-type",
        last_run_time=datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc),
        period={"type": "min", "value": 1},
    )


def _build_scan(module, monkeypatch, existing_alerts=None):
    alert_manager = FakeManager(filter_result=existing_alerts)
    event_manager = FakeManager()
    monkeypatch.setattr(module.Alert, "objects", alert_manager, raising=False)
    monkeypatch.setattr(module.Event, "objects", event_manager, raising=False)

    scan = module.LogPolicyScan(_build_policy(), scan_time=datetime(2026, 6, 11, 10, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(scan, "_create_snapshots_for_alerts", lambda *args, **kwargs: None)
    return scan, alert_manager, event_manager


def _event_payload(level="warning"):
    return {
        "source_id": "policy_1_host-a",
        "level": level,
        "content": "error count exceeded",
        "value": 10,
    }


def _patch_send(scan, monkeypatch, success=True):
    calls = []

    def fake_send(event_obj):
        calls.append(event_obj)
        return success, [{"result": success}]

    monkeypatch.setattr(scan, "send_notice", fake_send)
    return calls


def test_first_trigger_sends_and_marks_alert_notified(monkeypatch):
    module = _load_policy_scan_module(monkeypatch)
    scan, alert_manager, _ = _build_scan(module, monkeypatch, existing_alerts=[])
    calls = _patch_send(scan, monkeypatch, success=True)

    event_objs = scan.create_events([_event_payload()])
    scan.notice(event_objs)

    assert len(calls) == 1
    assert event_objs[0].alert.notice is True
    # Alert.notice=True 已批量回写
    notice_updates = [c for c in alert_manager.bulk_update_calls if "notice" in c[1]]
    assert notice_updates


def test_continued_hit_same_level_skips_renotice(monkeypatch):
    module = _load_policy_scan_module(monkeypatch)
    notified_alert = FakeAlert(
        id="alert-1",
        source_id="policy_1_host-a",
        created_at=datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc),
        level="warning",
        value=5,
        content="old",
        notice=True,
    )
    scan, _, _ = _build_scan(module, monkeypatch, existing_alerts=[notified_alert])
    calls = _patch_send(scan, monkeypatch, success=True)

    event_objs = scan.create_events([_event_payload(level="warning")])
    scan.notice(event_objs)

    # 同一活跃告警持续命中且级别未变：不得重复发送
    assert calls == []


def test_level_change_resets_notice_and_renotifies(monkeypatch):
    module = _load_policy_scan_module(monkeypatch)
    notified_alert = FakeAlert(
        id="alert-1",
        source_id="policy_1_host-a",
        created_at=datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc),
        level="warning",
        value=5,
        content="old",
        notice=True,
    )
    scan, alert_manager, _ = _build_scan(module, monkeypatch, existing_alerts=[notified_alert])
    calls = _patch_send(scan, monkeypatch, success=True)

    event_objs = scan.create_events([_event_payload(level="critical")])

    # 级别变化重置通知标记，且 notice 字段进入批量更新
    update_calls = [c for c in alert_manager.bulk_update_calls if notified_alert in c[0]]
    assert update_calls and "notice" in update_calls[0][1]

    scan.notice(event_objs)
    assert len(calls) == 1
    assert notified_alert.notice is True


def test_failed_send_keeps_alert_unnotified_for_retry(monkeypatch):
    module = _load_policy_scan_module(monkeypatch)
    scan, _, _ = _build_scan(module, monkeypatch, existing_alerts=[])
    calls = _patch_send(scan, monkeypatch, success=False)

    event_objs = scan.create_events([_event_payload()])
    scan.notice(event_objs)

    assert len(calls) == 1
    assert event_objs[0].alert.notice is False

    # 下个周期允许重试发送
    scan.notice(event_objs)
    assert len(calls) == 2
