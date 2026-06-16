"""Issue #3369: AlertSnapshot.snapshots 无上界累积应被截断至 _MAX_ALERT_SNAPSHOTS。

验证点（revert 修复后以下用例必须失败）：
1. extend 后长度超过上限时，列表被裁剪为最新 N 条；
2. 长度未超出上限时，不做裁剪（全量保留）；
3. 上限由 LOG_MAX_ALERT_SNAPSHOTS 环境变量控制；
4. 裁剪后仍调用 snapshot_obj.save()，确保持久化。
"""

import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# 伪依赖注入
# ---------------------------------------------------------------------------

def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


class FakeSnapshotObj:
    def __init__(self, existing_snapshots=None):
        self.snapshots = list(existing_snapshots or [])
        self.save_calls = []

    def save(self, update_fields=None):
        self.save_calls.append({"update_fields": update_fields, "snapshots_len": len(self.snapshots)})


class FakeAlertSnapshotManager:
    def __init__(self, snapshot_obj):
        self._snapshot_obj = snapshot_obj
        self._created = False

    def get_or_create(self, alert_id, defaults=None):
        if not self._created:
            self._created = True
            return self._snapshot_obj, True
        return self._snapshot_obj, False

    def select_for_update(self):
        return self

    def get(self, pk=None):
        return self._snapshot_obj


class FakeAlertSnapshot:
    objects = None  # 由测试注入


class FakeTransaction:
    class atomic:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass


def _load_module(monkeypatch):
    """加载 policy_scan 模块，注入最小化伪依赖，避免 Django settings 触发。"""
    _install_module(monkeypatch, "django", db=types.SimpleNamespace(transaction=FakeTransaction()))
    _install_module(monkeypatch, "django.db", transaction=FakeTransaction())

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
        Alert=object,
        Event=object,
        EventRawData=object,
        AlertSnapshot=FakeAlertSnapshot,
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
    spec = importlib.util.spec_from_file_location("policy_scan_snapshot_cap_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _build_scan(module):
    policy = SimpleNamespace(
        id=1,
        notice=False,
        notice_users=[],
        notice_type_id=None,
        collect_type="collect-type",
        last_run_time=datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc),
        period={"type": "min", "value": 1},
    )
    return module.LogPolicyScan(policy, scan_time=datetime(2026, 6, 11, 10, 1, tzinfo=timezone.utc))


def _make_event(event_id):
    return SimpleNamespace(
        id=event_id,
        event_time=datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

def test_snapshots_truncated_when_exceeds_cap(monkeypatch):
    """extend 后总数超出上限：列表应被裁剪，只保留最新 N 条（revert 修复后此测试必须失败）。"""
    module = _load_module(monkeypatch)

    cap = module._MAX_ALERT_SNAPSHOTS
    # 预置 cap-1 条历史快照
    existing = [{"type": "event", "event_id": f"old-{i}"} for i in range(cap - 1)]
    snapshot_obj = FakeSnapshotObj(existing_snapshots=existing)
    monkeypatch.setattr(module.AlertSnapshot, "objects", FakeAlertSnapshotManager(snapshot_obj), raising=False)

    # 新增 3 条事件 → 总长 cap+2，超出上限
    new_events = [_make_event(f"new-{i}") for i in range(3)]
    scan = _build_scan(module)
    scan._update_alert_snapshot(
        alert_id=1,
        policy_id=1,
        source_id="src-1",
        event_objs=new_events,
        event_raw_data_map={e.id: {} for e in new_events},
        snapshot_time=datetime(2026, 6, 11, 10, 1, tzinfo=timezone.utc),
    )

    assert len(snapshot_obj.snapshots) == cap, (
        f"期望快照数被裁剪至 {cap}，实际为 {len(snapshot_obj.snapshots)}"
    )
    # 保留的是最新的条目（即 new-* 和最近的 old-*）
    last_event_ids = [s["event_id"] for s in snapshot_obj.snapshots[-3:]]
    assert last_event_ids == ["new-0", "new-1", "new-2"], (
        f"期望最新 3 条为 new-*，实际为 {last_event_ids}"
    )


def test_snapshots_not_truncated_when_within_cap(monkeypatch):
    """extend 后总数未超出上限：列表应完整保留，不做裁剪。"""
    module = _load_module(monkeypatch)

    cap = module._MAX_ALERT_SNAPSHOTS
    # 预置 3 条历史快照（远小于上限）
    existing = [{"type": "event", "event_id": f"old-{i}"} for i in range(3)]
    snapshot_obj = FakeSnapshotObj(existing_snapshots=existing)
    monkeypatch.setattr(module.AlertSnapshot, "objects", FakeAlertSnapshotManager(snapshot_obj), raising=False)

    new_events = [_make_event(f"new-{i}") for i in range(2)]
    scan = _build_scan(module)
    scan._update_alert_snapshot(
        alert_id=1,
        policy_id=1,
        source_id="src-1",
        event_objs=new_events,
        event_raw_data_map={e.id: {} for e in new_events},
        snapshot_time=datetime(2026, 6, 11, 10, 1, tzinfo=timezone.utc),
    )

    assert len(snapshot_obj.snapshots) == 5, (
        f"期望全量保留 5 条，实际为 {len(snapshot_obj.snapshots)}"
    )
    assert len(snapshot_obj.snapshots) <= cap


def test_save_called_after_truncation(monkeypatch):
    """裁剪后必须调用 save()，否则快照不会持久化。"""
    module = _load_module(monkeypatch)

    cap = module._MAX_ALERT_SNAPSHOTS
    existing = [{"type": "event", "event_id": f"old-{i}"} for i in range(cap)]
    snapshot_obj = FakeSnapshotObj(existing_snapshots=existing)
    monkeypatch.setattr(module.AlertSnapshot, "objects", FakeAlertSnapshotManager(snapshot_obj), raising=False)

    new_events = [_make_event("new-0")]
    scan = _build_scan(module)
    scan._update_alert_snapshot(
        alert_id=1,
        policy_id=1,
        source_id="src-1",
        event_objs=new_events,
        event_raw_data_map={"new-0": {}},
        snapshot_time=datetime(2026, 6, 11, 10, 1, tzinfo=timezone.utc),
    )

    assert snapshot_obj.save_calls, "裁剪后必须调用 save() 持久化"
    assert snapshot_obj.save_calls[0]["snapshots_len"] == cap


def test_cap_configurable_via_env(monkeypatch):
    """LOG_MAX_ALERT_SNAPSHOTS 环境变量应控制上限值（revert 修复后此测试必须失败）。"""
    monkeypatch.setenv("LOG_MAX_ALERT_SNAPSHOTS", "10")
    module = _load_module(monkeypatch)

    assert module._MAX_ALERT_SNAPSHOTS == 10, (
        f"期望 _MAX_ALERT_SNAPSHOTS=10，实际为 {module._MAX_ALERT_SNAPSHOTS}"
    )

    existing = [{"type": "event", "event_id": f"old-{i}"} for i in range(10)]
    snapshot_obj = FakeSnapshotObj(existing_snapshots=existing)
    monkeypatch.setattr(module.AlertSnapshot, "objects", FakeAlertSnapshotManager(snapshot_obj), raising=False)

    new_events = [_make_event("extra-0"), _make_event("extra-1")]
    scan = _build_scan(module)
    scan._update_alert_snapshot(
        alert_id=1,
        policy_id=1,
        source_id="src-1",
        event_objs=new_events,
        event_raw_data_map={e.id: {} for e in new_events},
        snapshot_time=datetime(2026, 6, 11, 10, 1, tzinfo=timezone.utc),
    )

    assert len(snapshot_obj.snapshots) == 10, (
        f"期望上限为 10，实际为 {len(snapshot_obj.snapshots)}"
    )
    last_ids = [s["event_id"] for s in snapshot_obj.snapshots[-2:]]
    assert last_ids == ["extra-0", "extra-1"]
