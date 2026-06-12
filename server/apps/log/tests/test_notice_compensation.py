"""Issue #2923：日志告警通知失败补偿。

覆盖两层防线：
- 范围A 内联重试：send_notice 遇瞬时通道故障按 NOTICE_SEND_MAX_ATTEMPTS 重试。
- 范围B 持久化补偿：compensate_log_notice_task 回扫 notified=False 的近期失败事件重投。

沿用本目录既有的 Django-free 注入式 harness（sys.modules 伪依赖 + importlib 按路径加载），
不依赖 Django settings / ORM，规避 license_mgmt 缺失导致的 settings 加载失败。
"""
import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

SERVER_DIR = Path(__file__).resolve().parents[3]


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _fake_alert_constants():
    return types.SimpleNamespace(
        STATUS_NEW="new",
        STATUS_CLOSED="closed",
        LEVEL_INFO="info",
        NOTICE_SEND_MAX_ATTEMPTS=3,
        NOTICE_SEND_RETRY_BACKOFF_SECONDS=0,  # 测试不真正 sleep
        NOTICE_COMPENSATE_MAX_RETRY=5,
        NOTICE_COMPENSATE_WINDOW_SECONDS=24 * 3600,
        NOTICE_COMPENSATE_BATCH_SIZE=200,
        NOTICE_COMPENSATE_MIN_AGE_SECONDS=60,  # fresh 用例依赖 age 门槛过滤刚落库事件
    )


def _fake_logger():
    return types.SimpleNamespace(
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
        info=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )


def _load_policy_scan(monkeypatch, system_mgmt_utils):
    _install_module(monkeypatch, "django", db=types.SimpleNamespace(transaction=types.SimpleNamespace()))
    _install_module(monkeypatch, "django.db", transaction=types.SimpleNamespace())
    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=Exception)
    _install_module(monkeypatch, "apps.log.constants.alert_policy", AlertConstants=_fake_alert_constants())
    _install_module(monkeypatch, "apps.log.constants.database", DatabaseConstants=types.SimpleNamespace(DEFAULT_BATCH_SIZE=100))
    _install_module(monkeypatch, "apps.log.constants.web", WebConstants=types.SimpleNamespace(URL="http://test"))
    _install_module(monkeypatch, "apps.log.models.policy", Alert=object, Event=object, EventRawData=object, AlertSnapshot=object)
    _install_module(monkeypatch, "apps.log.tasks.utils.policy", period_to_seconds=lambda period: 300)
    _install_module(monkeypatch, "apps.log.utils.query_log", VictoriaMetricsAPI=lambda: None)
    _install_module(
        monkeypatch,
        "apps.log.utils.log_group",
        LogGroupQueryBuilder=types.SimpleNamespace(build_query_with_groups=lambda query, groups: (query, [])),
    )
    _install_module(monkeypatch, "apps.monitor.utils.system_mgmt_api", SystemMgmtUtils=system_mgmt_utils)
    _install_module(monkeypatch, "apps.core.logger", celery_logger=_fake_logger())

    module_path = SERVER_DIR / "apps" / "log" / "tasks" / "services" / "policy_scan.py"
    spec = importlib.util.spec_from_file_location("policy_scan_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_policy(**overrides):
    base = dict(
        id=7,
        name="测试策略",
        notice=True,
        enable=True,
        notice_type_id=3,
        notice_users=["u1"],
        last_run_time=datetime(2026, 6, 9, 8, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_event(policy, **overrides):
    base = dict(
        id="evt-1",
        alert_id="alert-1",
        policy=policy,
        level="error",
        content="some error",
        event_time=datetime(2026, 6, 9, 8, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 6, 9, 8, 0, tzinfo=timezone.utc),
        notice_result=[],
        notified=False,
        notice_retry_count=0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _RecordingSender:
    """模拟 SystemMgmtUtils：前 fail_times 次返回失败，之后成功。"""

    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.calls = 0

    def send_msg_with_channel(self, channel_id, title, content, users):
        self.calls += 1
        if self.calls <= self.fail_times:
            return {"result": False, "message": f"transient {self.calls}"}
        return {"result": True, "message": "ok"}


# ---------- 范围A：send_notice 内联重试 ----------

def test_send_notice_retries_until_success(monkeypatch):
    sender = _RecordingSender(fail_times=2)
    mod = _load_policy_scan(monkeypatch, type("S", (), {"send_msg_with_channel": staticmethod(sender.send_msg_with_channel)}))
    scan = mod.LogPolicyScan(_make_policy())

    ok, result = scan.send_notice(_make_event(scan.policy))

    assert ok is True
    assert result.get("result") is True
    assert sender.calls == 3  # 失败2次后第3次成功（revert 掉重试循环则只调用1次、返回 False）


def test_send_notice_exhausts_attempts_and_returns_last_failure(monkeypatch):
    sender = _RecordingSender(fail_times=99)
    mod = _load_policy_scan(monkeypatch, type("S", (), {"send_msg_with_channel": staticmethod(sender.send_msg_with_channel)}))
    scan = mod.LogPolicyScan(_make_policy())

    ok, result = scan.send_notice(_make_event(scan.policy))

    assert ok is False
    assert result.get("result") is False
    assert sender.calls == 3  # 用尽 NOTICE_SEND_MAX_ATTEMPTS


def test_send_notice_without_users_short_circuits(monkeypatch):
    sender = _RecordingSender(fail_times=0)
    mod = _load_policy_scan(monkeypatch, type("S", (), {"send_msg_with_channel": staticmethod(sender.send_msg_with_channel)}))
    scan = mod.LogPolicyScan(_make_policy(notice_users=[]))

    ok, result = scan.send_notice(_make_event(scan.policy))

    assert ok is False
    assert result == []
    assert sender.calls == 0


# ---------- 范围B：compensate_log_notice_task 选取 + 重投 ----------

class _FakeQS:
    def __init__(self, items):
        self.items = list(items)

    def filter(self, **kw):
        res = self.items
        for k, v in kw.items():
            if k == "notified":
                res = [e for e in res if e.notified == v]
            elif k == "notice_retry_count__lt":
                res = [e for e in res if e.notice_retry_count < v]
            elif k == "event_time__gte":
                res = [e for e in res if e.event_time >= v]
            elif k == "created_at__lte":
                res = [e for e in res if e.created_at <= v]
            elif k == "policy__notice":
                res = [e for e in res if e.policy.notice == v]
            elif k == "policy__enable":
                res = [e for e in res if e.policy.enable == v]
            else:
                raise AssertionError(f"未预期的 filter 条件: {k}")
        return _FakeQS(res)

    def exclude(self, **kw):
        res = self.items
        for k, v in kw.items():
            assert k == "level"
            res = [e for e in res if e.level != v]
        return _FakeQS(res)

    def select_related(self, *a):
        return self

    def order_by(self, *a):
        return _FakeQS(sorted(self.items, key=lambda e: e.event_time))

    def __getitem__(self, sl):
        return self.items[sl]


def _load_compensate_task(monkeypatch, events, sender, bulk_recorder):
    policy_scan_mod = _load_policy_scan(monkeypatch, type("S", (), {"send_msg_with_channel": staticmethod(sender.send_msg_with_channel)}))

    class FakeEvent:
        objects = SimpleNamespace(
            filter=lambda **kw: _FakeQS(events).filter(**kw),
            bulk_update=lambda objs, fields, batch_size=None: bulk_recorder.setdefault("event", []).append((list(objs), list(fields))),
        )

    class FakeAlert:
        def __init__(self, id=None, notice=None):
            self.id = id
            self.notice = notice

        objects = SimpleNamespace(
            bulk_update=lambda objs, fields, batch_size=None: bulk_recorder.setdefault("alert", []).append((list(objs), list(fields))),
        )

    _install_module(monkeypatch, "celery", shared_task=lambda *a, **k: (lambda f: f), Singleton=object)
    _install_module(monkeypatch, "celery_singleton", Singleton=object)
    _install_module(monkeypatch, "apps.log.models.policy", Alert=FakeAlert, Event=FakeEvent, Policy=object)
    _install_module(monkeypatch, "apps.log.tasks.services.policy_scan", LogPolicyScan=policy_scan_mod.LogPolicyScan)
    _install_module(monkeypatch, "apps.log.tasks.utils.policy", period_to_seconds=lambda p: 300)

    module_path = SERVER_DIR / "apps" / "log" / "tasks" / "policy.py"
    spec = importlib.util.spec_from_file_location("log_policy_tasks_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, FakeAlert


def test_compensate_resends_failed_event_and_marks_notified(monkeypatch):
    sender = _RecordingSender(fail_times=0)  # 补偿时通道已恢复
    policy = _make_policy()
    failed = _make_event(policy, id="evt-fail", notified=False, notice_retry_count=1, event_time=datetime.now(timezone.utc))
    bulk = {}
    mod, _ = _load_compensate_task(monkeypatch, [failed], sender, bulk)

    result = mod.compensate_log_notice_task()

    assert result["compensated"] == 1
    assert failed.notified is True
    assert failed.notice_retry_count == 2
    assert sender.calls == 1
    assert "event" in bulk and "alert" in bulk  # 事件 + 告警通知状态都被回写


def test_compensate_skips_settled_info_and_exhausted_events(monkeypatch):
    sender = _RecordingSender(fail_times=0)
    policy = _make_policy()
    now = datetime.now(timezone.utc)
    candidates = [
        _make_event(policy, id="ok", notified=True, event_time=now),  # 已成功
        _make_event(policy, id="info", level="info", notified=False, event_time=now),  # info 不通知
        _make_event(policy, id="exhausted", notified=False, notice_retry_count=5, event_time=now),  # 超重投上限
        _make_event(policy, id="stale", notified=False, event_time=now - timedelta(days=2)),  # 超出补偿时间窗
        _make_event(policy, id="fresh", notified=False, event_time=now, created_at=now),  # 刚落库，未过 MIN_AGE，防与首发并发双投
        _make_event(policy, id="target", notified=False, event_time=now),  # 唯一应被补偿（created_at 默认久远）
    ]
    bulk = {}
    mod, _ = _load_compensate_task(monkeypatch, candidates, sender, bulk)

    result = mod.compensate_log_notice_task()

    assert sender.calls == 1  # 只对 target 发了一次
    assert result["scanned"] == 1


def test_compensate_marks_no_user_event_settled_without_sending(monkeypatch):
    sender = _RecordingSender(fail_times=0)
    policy = _make_policy(notice_users=[])  # 无通知人
    evt = _make_event(policy, id="no-user", notified=False, event_time=datetime.now(timezone.utc))
    bulk = {}
    mod, _ = _load_compensate_task(monkeypatch, [evt], sender, bulk)

    result = mod.compensate_log_notice_task()

    assert sender.calls == 0
    assert evt.notified is True  # 直接收敛，避免无意义重投占配额
    assert result["compensated"] == 0
