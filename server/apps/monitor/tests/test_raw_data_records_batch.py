"""Issue #3335：事件原始数据写入去 N+1（_create_raw_data_records 批量化）单测。

原实现对每条事件做一次 .exists() SELECT + 逐行 save() INSERT。本测验证：
① 命中 event_obj_map 的事件不再逐条 SELECT（正常情况零额外查询）；
② 写入改为单次 bulk_create；③ 不在 map 的 id 走一次批量 id__in 存在性兜底（非逐条）。
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


def _load(monkeypatch, name, filter_calls, bulk_calls, saved):
    class _EventQS:
        def __init__(self, ids):
            self.ids = list(ids)

        def values_list(self, field, flat=False):
            return list(self.ids)  # 简化：传入的 id 都视为存在

    class _MonitorEvent:
        class objects:
            @staticmethod
            def filter(**kwargs):
                filter_calls.append(kwargs)
                return _EventQS(kwargs.get("id__in", []))

    class _RawData:
        def __init__(self, event_id=None, data=None):
            self.event_id = event_id
            self.data = data

        def save(self):
            saved.append(self.event_id)  # 若被逐行 save（旧实现），会记录在此 → 新实现应为空

        class objects:
            @staticmethod
            def bulk_create(objs, batch_size=None):
                bulk_calls.append(([o.event_id for o in objs], batch_size))
                return list(objs)

    _install_module(monkeypatch, "apps.monitor.constants.alert_policy", AlertConstants=types.SimpleNamespace())
    _install_module(
        monkeypatch,
        "apps.monitor.constants.database",
        DatabaseConstants=types.SimpleNamespace(BULK_CREATE_BATCH_SIZE=100, BULK_UPDATE_BATCH_SIZE=100),
    )
    _install_module(monkeypatch, "apps.monitor.models", MonitorAlert=object, MonitorEvent=_MonitorEvent, MonitorEventRawData=_RawData)
    _install_module(
        monkeypatch,
        "apps.monitor.services.alert_lifecycle_notify",
        AlertLifecycleNotifier=lambda *a, **k: types.SimpleNamespace(notify_alerts=lambda *a, **k: None),
    )
    _install_module(monkeypatch, "apps.monitor.utils.dimension", format_dimension_str=lambda d: "")
    _install_module(monkeypatch, "apps.core.logger", celery_logger=_Logger())

    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parents[1] / "tasks" / "services" / "policy_scan" / "event_alert_manager.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manager(module):
    mgr = object.__new__(module.EventAlertManager)
    mgr.policy = types.SimpleNamespace(id=1)
    return mgr


def test_all_events_in_map_bulk_create_without_per_event_select(monkeypatch):
    filter_calls, bulk_calls, saved = [], [], []
    module = _load(monkeypatch, "raw_all_in_map_module", filter_calls, bulk_calls, saved)
    mgr = _manager(module)

    event_objs = [types.SimpleNamespace(id="e1"), types.SimpleNamespace(id="e2")]
    events_with_raw_data = [{"event_id": "e1", "raw_data": {"a": 1}}, {"event_id": "e2", "raw_data": {"b": 2}}]

    mgr._create_raw_data_records(events_with_raw_data, event_objs)

    # 命中 map → 不做任何逐条/批量 SELECT
    assert filter_calls == []
    # 单次 bulk_create 写全部，batch_size 透传；不再逐行 save
    assert bulk_calls == [(["e1", "e2"], 100)]
    assert saved == []


def test_missing_event_id_uses_single_batched_existence_check(monkeypatch):
    filter_calls, bulk_calls, saved = [], [], []
    module = _load(monkeypatch, "raw_missing_module", filter_calls, bulk_calls, saved)
    mgr = _manager(module)

    event_objs = [types.SimpleNamespace(id="e1")]  # e2 不在 map
    events_with_raw_data = [{"event_id": "e1", "raw_data": {}}, {"event_id": "e2", "raw_data": {}}]

    mgr._create_raw_data_records(events_with_raw_data, event_objs)

    # 仅一次批量 id__in 兜底（非逐条），且只查不在 map 的 e2
    assert filter_calls == [{"id__in": ["e2"]}]
    # e1（map）+ e2（兜底确认存在）都写入，单次 bulk_create
    assert bulk_calls == [(["e1", "e2"], 100)]
    assert saved == []


def test_empty_raw_data_skips_bulk_create(monkeypatch):
    filter_calls, bulk_calls, saved = [], [], []
    module = _load(monkeypatch, "raw_empty_module", filter_calls, bulk_calls, saved)
    mgr = _manager(module)

    mgr._create_raw_data_records([], [types.SimpleNamespace(id="e1")])

    assert filter_calls == []
    assert bulk_calls == []
    assert saved == []
