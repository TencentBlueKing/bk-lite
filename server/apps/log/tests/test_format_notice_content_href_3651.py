"""Issue #3651：_format_notice_content 中 href 误含字面 f" 前缀导致链接失效。

验证修复后生成的链接不再包含字面 f" 前缀，且 URL 被正确插值。

沿用本目录 Django-free 注入式 harness，不依赖 Django settings / ORM。
"""
import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

SERVER_DIR = Path(__file__).resolve().parents[3]

_TEST_BASE_URL = "http://test"
_EXPECTED_HREF = f'{_TEST_BASE_URL}/log/event/alert'


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
        NOTICE_SEND_RETRY_BACKOFF_SECONDS=0,
        NOTICE_COMPENSATE_MAX_RETRY=5,
        NOTICE_COMPENSATE_WINDOW_SECONDS=24 * 3600,
        NOTICE_COMPENSATE_BATCH_SIZE=200,
        NOTICE_COMPENSATE_MIN_AGE_SECONDS=60,
    )


def _fake_logger():
    return types.SimpleNamespace(
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
        info=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )


def _load_policy_scan(monkeypatch):
    _install_module(monkeypatch, "django", db=types.SimpleNamespace(transaction=types.SimpleNamespace()))
    _install_module(monkeypatch, "django.db", transaction=types.SimpleNamespace())
    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=Exception)
    _install_module(monkeypatch, "apps.log.constants.alert_policy", AlertConstants=_fake_alert_constants())
    _install_module(monkeypatch, "apps.log.constants.database", DatabaseConstants=types.SimpleNamespace(DEFAULT_BATCH_SIZE=100))
    _install_module(monkeypatch, "apps.log.constants.web", WebConstants=types.SimpleNamespace(URL=_TEST_BASE_URL))
    _install_module(monkeypatch, "apps.log.models.policy", Alert=object, Event=object, EventRawData=object, AlertSnapshot=object)
    _install_module(monkeypatch, "apps.log.tasks.utils.policy", period_to_seconds=lambda period: 300)
    _install_module(monkeypatch, "apps.log.utils.query_log", VictoriaMetricsAPI=lambda: None)
    _install_module(
        monkeypatch,
        "apps.log.utils.log_group",
        LogGroupQueryBuilder=types.SimpleNamespace(build_query_with_groups=lambda query, groups: (query, [])),
    )
    _install_module(monkeypatch, "apps.monitor.utils.system_mgmt_api", SystemMgmtUtils=object)
    _install_module(monkeypatch, "apps.core.logger", celery_logger=_fake_logger())

    module_path = SERVER_DIR / "apps" / "log" / "tasks" / "services" / "policy_scan.py"
    spec = importlib.util.spec_from_file_location("policy_scan_under_test_3651", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_policy(**overrides):
    base = dict(
        id=1,
        name="测试策略",
        notice=True,
        enable=True,
        notice_type_id=1,
        notice_users=["u1"],
        last_run_time=datetime(2026, 6, 23, 0, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_event(policy, **overrides):
    base = dict(
        id="evt-3651",
        alert_id="alert-3651",
        policy=policy,
        level="error",
        content="日志告警内容",
        event_time=datetime(2026, 6, 23, 0, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 6, 23, 0, 0, tzinfo=timezone.utc),
        notice_result=[],
        notified=False,
        notice_retry_count=0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_format_notice_content_href_no_literal_f_prefix(monkeypatch):
    """_format_notice_content 生成的 href 不应包含字面 f" 前缀。

    修复前输出: href=f"/log/event/alert"
    修复后输出: href="http://test/log/event/alert"

    若 revert 修复，href 会含字面 f" → assert 失败。
    """
    mod = _load_policy_scan(monkeypatch)
    policy = _make_policy()
    scan = mod.LogPolicyScan(policy)
    event = _make_event(policy)

    _, content = scan._format_notice_content(event)

    # 不应含字面 f" 前缀
    assert 'href=f"' not in content, (
        f'链接含字面 f" 前缀，用户点击将得到 404。实际 content: {content!r}'
    )


def test_format_notice_content_href_interpolates_url(monkeypatch):
    """_format_notice_content 生成的 href 应包含正确插值后的 URL。

    若 revert 修复，URL 不会被插值进 href，此断言失败。
    """
    mod = _load_policy_scan(monkeypatch)
    policy = _make_policy()
    scan = mod.LogPolicyScan(policy)
    event = _make_event(policy)

    _, content = scan._format_notice_content(event)

    assert f'href="{_EXPECTED_HREF}"' in content, (
        f'href 未正确插值 URL。期望包含 href="{_EXPECTED_HREF}"，实际 content: {content!r}'
    )
