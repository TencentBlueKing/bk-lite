"""Issue #3602：MonitorPolicyViewSet.update()/partial_update() 多步 DB 写缺少事务包裹。

验证修复后 update() 和 partial_update() 中所有附属步骤（update_or_create_task、
update_policy_organizations、close_active_threshold_alerts_for_policy_config_change 等）
与主表写入一同包含在 transaction.atomic() 块内。

测试策略：
- 注入式 harness（Django-free），不依赖 settings 加载
- 直接操作 sys.modules（不用 monkeypatch fixture，避免 conftest autouse 干扰）
- 用 _AtomicCapture 追踪 atomic 进入/退出，同时记录每一步调用顺序
- revert 修复（移除 atomic 包裹）则测试失败，满足「revert 后必须失败」要求
"""
import importlib.util
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

_MONITOR_POLICY_PATH = (
    Path(__file__).resolve().parent.parent / "views" / "monitor_policy.py"
)


# ---------------------------------------------------------------------------
# sys.modules 临时注入 helper
# ---------------------------------------------------------------------------

@contextmanager
def _patched_modules(overrides: dict):
    """临时将 overrides 注入 sys.modules，退出时恢复原值。"""
    saved = {}
    for name in overrides:
        saved[name] = sys.modules.get(name)
    try:
        for name, mod in overrides.items():
            sys.modules[name] = mod
        yield
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        # 清理被测模块以免缓存干扰
        sys.modules.pop("monitor_policy_view_3602", None)


def _make_module(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


# ---------------------------------------------------------------------------
# AtomicCapture
# ---------------------------------------------------------------------------

class _AtomicCapture:
    """记录 transaction.atomic() 上下文管理器进入/退出的顺序标记。"""

    def __init__(self, call_log: list):
        self._log = call_log

    def __enter__(self):
        self._log.append("atomic:enter")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._log.append("atomic:exit")
        return False  # 不吞异常


# ---------------------------------------------------------------------------
# 加载被测模块并构造 ViewSet 实例
# ---------------------------------------------------------------------------

def _build_sys_modules_overrides(call_log: list) -> dict:
    overrides = {}

    def install(name, **attrs):
        overrides[name] = _make_module(name, **attrs)

    # django.db
    install(
        "django.db",
        transaction=types.SimpleNamespace(atomic=lambda: _AtomicCapture(call_log)),
    )
    install("django.db.models", Model=object)
    install("django.db.models.functions", TruncDate=object)

    # django_celery_beat
    class _PT:
        objects = types.SimpleNamespace(
            filter=lambda **_kw: types.SimpleNamespace(delete=lambda: None),
            create=lambda **_kw: None,
        )
    class _CS:
        objects = types.SimpleNamespace(get_or_create=lambda **_kw: (object(), True))
    install("django_celery_beat.models", PeriodicTask=_PT, CrontabSchedule=_CS)

    # rest_framework
    class _ModelViewSet:
        def update(self, request, *args, **kwargs):
            call_log.append("super:update")
            return "response_obj"
        def partial_update(self, request, *args, **kwargs):
            call_log.append("super:partial_update")
            return "response_obj"

    install("rest_framework", status=object)
    install("rest_framework.decorators", action=lambda **_k: (lambda f: f))
    install("rest_framework.viewsets", ModelViewSet=_ModelViewSet)
    install("rest_framework.filters", SearchFilter=object, OrderingFilter=object)
    install("django_filters.rest_framework", DjangoFilterBackend=object)

    # app stubs
    install("apps.core.exceptions.base_app_exception", BaseAppException=Exception)
    install("apps.core.utils.web_utils", WebUtils=types.SimpleNamespace(response_success=lambda d: d))
    install("apps.core.utils.team_utils", get_current_team=lambda *_a, **_kw: None)
    install("apps.monitor.constants.alert_policy", AlertConstants=types.SimpleNamespace(NO_DATA="no_data"))
    install("apps.monitor.constants.database", DatabaseConstants=types.SimpleNamespace(BULK_CREATE_BATCH_SIZE=1000))
    install("apps.monitor.constants.permission", PermissionConstants=types.SimpleNamespace(POLICY="policy"))

    class _FakePolicy:
        enable = False
        enable_alerts = []

    class _FakeQS:
        def first(self):
            return _FakePolicy()
        def all(self):
            return []

    class _FakeMonitorPolicy:
        objects = types.SimpleNamespace(
            filter=lambda **_kw: _FakeQS(),
            all=lambda: [],
        )

    class _FakeMonitorAlert:
        objects = types.SimpleNamespace(filter=lambda **_kw: [])

    install(
        "apps.monitor.models",
        PolicyOrganization=types.SimpleNamespace(
            objects=types.SimpleNamespace(
                filter=lambda **_kw: types.SimpleNamespace(
                    delete=lambda: None,
                    __iter__=lambda s: iter([]),
                ),
                bulk_create=lambda objs, batch_size=1000: None,
            )
        ),
        MonitorAlert=_FakeMonitorAlert,
    )
    install("apps.monitor.models.monitor_policy", MonitorPolicy=_FakeMonitorPolicy)
    install("apps.monitor.filters.monitor_policy", MonitorPolicyFilter=object)
    install("apps.monitor.serializers.monitor_policy", MonitorPolicySerializer=object)
    install("apps.monitor.services.policy_baseline",
            PolicyBaselineService=lambda policy: types.SimpleNamespace(clear=lambda: None))
    install("apps.monitor.services.policy",
            PolicyService=types.SimpleNamespace(
                get_policy_templates=lambda name: [],
                get_policy_templates_monitor_object=lambda: [],
            ))
    install("apps.monitor.services.policy_bulk", build_bulk_policy_payloads=lambda **_kw: [])
    install("apps.monitor.services.policy_preview",
            PolicyPreviewService=types.SimpleNamespace(preview=lambda *_a, **_kw: {}))
    install("apps.monitor.services.alert_lifecycle_notify",
            AlertLifecycleNotifier=object,
            NOTIFY_SCOPE_ALERT_CENTER_ONLY="alert_center_only",
            NOTIFY_SCOPE_ALL_CONFIGURED="all_configured")
    install("apps.core.utils.permission_utils",
            get_permission_rules=lambda *_a, **_kw: [],
            permission_filter=lambda *_a, **_kw: None)
    install("apps.monitor.utils.pagination", parse_page_params=lambda *_a, **_kw: (0, 20))
    install("config.drf.pagination", CustomPageNumberPagination=object)

    # Parent packages (empty stubs to satisfy import machinery)
    for pkg in [
        "apps", "apps.core", "apps.core.exceptions", "apps.core.utils",
        "apps.monitor", "apps.monitor.constants", "apps.monitor.filters",
        "apps.monitor.models", "apps.monitor.serializers", "apps.monitor.services",
        "apps.monitor.utils", "config", "config.drf",
    ]:
        if pkg not in overrides:
            install(pkg)

    return overrides


def _load_view_module(overrides: dict):
    spec = importlib.util.spec_from_file_location("monitor_policy_view_3602", _MONITOR_POLICY_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["monitor_policy_view_3602"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_viewset(mod, call_log: list):
    vs = mod.MonitorPolicyViewSet()

    def traced(name):
        def fn(*_a, **_kw):
            call_log.append(name)
        return fn

    vs.update_or_create_task = traced("update_or_create_task")
    vs.update_policy_organizations = traced("update_policy_organizations")
    vs.update_policy_baselines = traced("update_policy_baselines")
    vs.close_active_threshold_alerts_for_policy_config_change = traced(
        "close_active_threshold_alerts_for_policy_config_change"
    )
    vs.handle_policy_enable_change = traced("handle_policy_enable_change")
    vs.get_baseline_state = lambda policy: None
    vs.should_update_policy_baselines = lambda *_a, **_kw: False
    vs.baseline_state_changed = lambda *_a, **_kw: False
    vs.format_crontab = lambda s: object()
    return vs


class _FakeUser:
    username = "tester"


class _FakeRequest:
    def __init__(self, data):
        self.data = data
        self.user = _FakeUser()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_update_wraps_all_steps_in_atomic():
    """update() 中所有 DB 步骤必须在 transaction.atomic() 块内。

    若修复被 revert（移除 with transaction.atomic()），call_log 中不含 atomic:enter /
    atomic:exit，以下断言失败 → 确认测试能检出缺陷。
    """
    call_log = []
    overrides = _build_sys_modules_overrides(call_log)

    with _patched_modules(overrides):
        mod = _load_view_module(overrides)
        vs = _make_viewset(mod, call_log)

        req = _FakeRequest({
            "name": "policy-A",
            "schedule": "*/5 * * * *",
            "organizations": [1],
            "enable": True,
        })
        result = vs.update(req, pk=1)

    assert result == "response_obj", "update() 应返回 super().update() 的结果"
    assert "atomic:enter" in call_log, "update() 必须使用 transaction.atomic()"
    assert "atomic:exit" in call_log, "transaction.atomic() 必须正常退出"

    ei = call_log.index("atomic:enter")
    xi = call_log.index("atomic:exit")

    assert "super:update" in call_log
    si = call_log.index("super:update")
    assert ei < si < xi, (
        f"super().update() (idx={si}) 必须在 atomic 块内 [enter={ei}, exit={xi}]"
    )

    assert "update_or_create_task" in call_log
    ti = call_log.index("update_or_create_task")
    assert ei < ti < xi, f"update_or_create_task (idx={ti}) 必须在 atomic 块内"

    assert "update_policy_organizations" in call_log
    oi = call_log.index("update_policy_organizations")
    assert ei < oi < xi, f"update_policy_organizations (idx={oi}) 必须在 atomic 块内"

    assert "close_active_threshold_alerts_for_policy_config_change" in call_log
    ci = call_log.index("close_active_threshold_alerts_for_policy_config_change")
    assert ei < ci < xi, f"close_alerts (idx={ci}) 必须在 atomic 块内"


def test_partial_update_wraps_all_steps_in_atomic():
    """partial_update() 同样要求所有步骤在 atomic 块内。"""
    call_log = []
    overrides = _build_sys_modules_overrides(call_log)

    with _patched_modules(overrides):
        mod = _load_view_module(overrides)
        vs = _make_viewset(mod, call_log)

        req = _FakeRequest({
            "schedule": "0 * * * *",
            "organizations": [2],
        })
        result = vs.partial_update(req, pk=1)

    assert result == "response_obj", "partial_update() 应返回 super().partial_update() 的结果"
    assert "atomic:enter" in call_log, "partial_update() 必须使用 transaction.atomic()"
    assert "atomic:exit" in call_log

    ei = call_log.index("atomic:enter")
    xi = call_log.index("atomic:exit")

    assert "super:partial_update" in call_log
    si = call_log.index("super:partial_update")
    assert ei < si < xi, f"super().partial_update() (idx={si}) 必须在 atomic 块内"

    assert "update_or_create_task" in call_log
    ti = call_log.index("update_or_create_task")
    assert ei < ti < xi, f"update_or_create_task (idx={ti}) 必须在 atomic 块内"

    assert "update_policy_organizations" in call_log
    oi = call_log.index("update_policy_organizations")
    assert ei < oi < xi, f"update_policy_organizations (idx={oi}) 必须在 atomic 块内"


def test_update_exception_in_subtask_propagates_through_atomic():
    """若 update_or_create_task 抛出异常，应从 atomic 块内向外传播（不被吞掉）。

    这确保调用方（DRF exception handler）能捕获并让数据库回滚事务，而不是静默返回。
    """
    call_log = []
    overrides = _build_sys_modules_overrides(call_log)

    with _patched_modules(overrides):
        mod = _load_view_module(overrides)
        vs = _make_viewset(mod, call_log)

        def _failing_task(*_a, **_kw):
            call_log.append("update_or_create_task:raise")
            raise RuntimeError("DB 连接超时")

        vs.update_or_create_task = _failing_task

        req = _FakeRequest({
            "schedule": "*/5 * * * *",
            "organizations": [],
        })

        with pytest.raises(RuntimeError, match="DB 连接超时"):
            vs.update(req, pk=1)

    # atomic 块已进入——说明 super().update() 也在 atomic 内
    assert "atomic:enter" in call_log, "异常必须从 atomic 块内抛出，而不是在 atomic 之前"
    # close 和 handle_policy_enable_change 不应被执行（因为异常已中断）
    assert "close_active_threshold_alerts_for_policy_config_change" not in call_log, (
        "事务中断后，后续步骤不应被执行"
    )
