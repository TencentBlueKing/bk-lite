"""
Issue #3367: create_events 多步写无外层事务 → Alert/Event/EventRawData 部分失败数据不一致

验证 create_events 的 Alert + Event + EventRawData 写操作被包裹在同一个 transaction.atomic() 中：
- 若 EventRawData.save() 失败，前面已写入的 Alert / Event 应随事务回滚，不留孤儿记录。

使用 Django-free 注入式测试（不依赖 ORM/settings），可通过独立 harness 运行：
    uv run pytest server/apps/log/tests/test_create_events_atomic_3367.py -v
"""
import importlib.util
import sys
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# 覆盖 conftest.py 的 autouse 夹具（Django-free 测试无需 settings 注入）
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def use_dummy_cache_backend():
    """No-op override: 本文件是 Django-free 注入式测试，不需要 settings 夹具。"""


@pytest.fixture(autouse=True)
def disable_auth_middleware():
    """No-op override: 本文件是 Django-free 注入式测试，不需要 settings 夹具。"""


# ---------------------------------------------------------------------------
# 依赖注入工具
# ---------------------------------------------------------------------------

def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_policy_scan_module(monkeypatch, transaction_mock):
    """加载 policy_scan.py，注入伪依赖（无 Django settings / ORM）。"""
    _install_module(monkeypatch, "django", db=types.SimpleNamespace(transaction=transaction_mock))
    _install_module(monkeypatch, "django.db", transaction=transaction_mock)

    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=Exception)
    _install_module(
        monkeypatch,
        "apps.log.constants.alert_policy",
        AlertConstants=types.SimpleNamespace(STATUS_NEW="new", STATUS_CLOSED="closed"),
    )
    _install_module(
        monkeypatch,
        "apps.log.constants.database",
        DatabaseConstants=types.SimpleNamespace(DEFAULT_BATCH_SIZE=100),
    )
    _install_module(monkeypatch, "apps.log.constants.web", WebConstants=types.SimpleNamespace())
    _install_module(
        monkeypatch,
        "apps.log.models.policy",
        Alert=object,
        Event=object,
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
            warning=lambda *a, **kw: None,
            error=lambda *a, **kw: None,
            info=lambda *a, **kw: None,
            debug=lambda *a, **kw: None,
        ),
    )

    module_path = Path(__file__).resolve().parents[1] / "tasks" / "services" / "policy_scan.py"
    spec = importlib.util.spec_from_file_location("policy_scan_atomic_3367_module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 辅助：构造最小 policy / scan 对象
# ---------------------------------------------------------------------------

def _make_scan(module, policy, transaction_mock):
    scan = object.__new__(module.LogPolicyScan)
    scan.policy = policy
    scan.scan_time = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
    # 让 _create_snapshots_for_alerts 空转，不影响本次验证焦点
    scan._create_snapshots_for_alerts = lambda *a, **kw: None
    return scan


# ---------------------------------------------------------------------------
# 测试 1：正常路径——所有写操作在同一个 atomic() 内执行
# ---------------------------------------------------------------------------

def test_create_events_db_writes_inside_atomic(monkeypatch):
    """正常路径：Alert / Event / EventRawData 的 DB 写在 transaction.atomic() 上下文内。"""
    # --- 记录 atomic 上下文进入/退出 ---
    atomic_entered = []
    atomic_exited = []

    class FakeAtomic:
        def __enter__(self):
            atomic_entered.append(True)
            return self

        def __exit__(self, *args):
            atomic_exited.append(True)
            return False  # 不吞异常

    transaction_mock = SimpleNamespace(atomic=lambda: FakeAtomic())

    module = _load_policy_scan_module(monkeypatch, transaction_mock)

    policy = SimpleNamespace(
        id=42,
        collect_type="keyword",
        period={"type": "min", "value": 5},
        last_run_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    scan = _make_scan(module, policy, transaction_mock)

    # --- 伪造 ORM ---
    fake_alert_id = uuid.uuid4().hex
    fake_alert = SimpleNamespace(id=fake_alert_id, source_id="src1", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))

    alert_cls = MagicMock()
    alert_cls.objects.filter.return_value = []  # 无已存在告警
    alert_cls.objects.bulk_create.return_value = [fake_alert]

    # bulk_create 返回传入的实际对象，确保 event_obj.id 与 event_id_to_raw_data 的 key 匹配
    event_cls = MagicMock()
    event_cls.objects.bulk_create.side_effect = lambda objs, **kwargs: list(objs)

    raw_data_obj = MagicMock()

    def fake_raw_data_cls(**kwargs):
        return raw_data_obj

    # 注入到模块命名空间
    module.Alert = alert_cls
    module.Event = MagicMock(side_effect=lambda **kw: SimpleNamespace(**kw))
    module.Event.objects = event_cls.objects
    module.EventRawData = fake_raw_data_cls

    events = [
        {
            "source_id": "src1",
            "level": "error",
            "content": "test error",
            "raw_data": {"log": "line1"},
        }
    ]

    scan.create_events(events)

    # atomic() 应当被进入并退出（正常路径下退出时无异常）
    assert atomic_entered, "transaction.atomic() 未被进入 — create_events 缺少外层事务"
    assert atomic_exited, "transaction.atomic() 未正常退出"
    # EventRawData.save() 应在 atomic 内调用
    raw_data_obj.save.assert_called_once()


# ---------------------------------------------------------------------------
# 测试 2：EventRawData.save() 失败 → atomic 上下文捕获异常并 re-raise
#         （即异常会传播给 atomic.__exit__，事务回滚）
# ---------------------------------------------------------------------------

def test_create_events_raw_data_failure_propagates_through_atomic(monkeypatch):
    """
    EventRawData.save() 抛出异常时，异常应通过 atomic().__exit__ 传播出去
    （Django 的 atomic 会在 __exit__ 收到异常时标记回滚）。
    验证：异常确实从 create_events 向上抛出，且 atomic.__exit__ 收到了异常。
    """
    exit_exc_info = []

    class FakeAtomic:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            exit_exc_info.append((exc_type, exc_val))
            return False  # 不吞异常，确保它继续向上传播

    transaction_mock = SimpleNamespace(atomic=lambda: FakeAtomic())
    module = _load_policy_scan_module(monkeypatch, transaction_mock)

    policy = SimpleNamespace(
        id=99,
        collect_type="keyword",
        period={"type": "min", "value": 5},
        last_run_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    scan = _make_scan(module, policy, transaction_mock)

    alert_cls = MagicMock()
    alert_cls.objects.filter.return_value = []
    alert_cls.objects.bulk_create.return_value = []

    # bulk_create 返回传入的实际对象，确保 event_obj.id 与 event_id_to_raw_data 的 key 匹配
    event_cls = MagicMock()
    event_cls.objects.bulk_create.side_effect = lambda objs, **kwargs: list(objs)

    class FakeRawDataObj:
        def save(self):
            raise IOError("MinIO timeout simulated")

    def fake_raw_data_cls(**kw):
        return FakeRawDataObj()

    module.Alert = alert_cls
    module.Event = MagicMock(side_effect=lambda **kw: SimpleNamespace(**kw))
    module.Event.objects = event_cls.objects
    module.EventRawData = fake_raw_data_cls

    events = [
        {
            "source_id": "src_fail",
            "level": "warning",
            "content": "fail case",
            "raw_data": {"log": "line_fail"},
        }
    ]

    import pytest
    with pytest.raises(IOError, match="MinIO timeout simulated"):
        scan.create_events(events)

    # atomic.__exit__ 必须收到异常——这是 Django 判断是否回滚的入口
    assert exit_exc_info, "atomic().__exit__ 未收到异常 — 说明 DB 写入不在 atomic 上下文内，事务无法回滚"
    exc_type, exc_val = exit_exc_info[0]
    assert exc_type is IOError, f"期望 IOError，实际收到 {exc_type}"
    assert "MinIO timeout" in str(exc_val)


# ---------------------------------------------------------------------------
# 测试 3：空 events → 直接返回 []，不进入 atomic
# ---------------------------------------------------------------------------

def test_create_events_empty_returns_empty_no_atomic(monkeypatch):
    """空 events 列表应立即返回 []，无需进入事务。"""
    atomic_called = []

    class FakeAtomic:
        def __enter__(self):
            atomic_called.append(True)
            return self

        def __exit__(self, *a):
            return False

    transaction_mock = SimpleNamespace(atomic=lambda: FakeAtomic())
    module = _load_policy_scan_module(monkeypatch, transaction_mock)

    policy = SimpleNamespace(id=1, collect_type="kw", period={"type": "min", "value": 1},
                             last_run_time=datetime(2026, 1, 1, tzinfo=timezone.utc))
    scan = _make_scan(module, policy, transaction_mock)

    result = scan.create_events([])
    assert result == []
    assert not atomic_called, "空 events 时不应进入 transaction.atomic()"
