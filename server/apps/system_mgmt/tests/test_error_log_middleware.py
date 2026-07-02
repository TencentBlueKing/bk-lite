"""ErrorLogMiddleware 单元测试。

直接调用 process_exception / 辅助方法，断言真实分支与异步任务下发契约。
只 mock 真实外部边界（celery write_error_log_async.delay）。
"""
import types
from unittest.mock import patch

import pytest
from rest_framework.exceptions import PermissionDenied

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.system_mgmt.middleware.error_log_middleware import ErrorLogMiddleware

pytestmark = pytest.mark.django_db


def _mw():
    return ErrorLogMiddleware(get_response=lambda r: None)


def _request(path="/api/v1/system_mgmt/user/", method="GET", authenticated=True):
    user = types.SimpleNamespace(
        is_authenticated=authenticated, username="alice", domain="domain.com", locale="zh-Hans"
    )
    req = types.SimpleNamespace(path=path, method=method, user=user)
    req.get_full_path = lambda: path
    return req


def test_non_api_path_ignored():
    mw = _mw()
    resp = mw.process_exception(_request(path="/static/x.js"), Exception("boom"))
    assert resp is None


def test_api_exception_logs_and_returns_500():
    mw = _mw()
    with patch(
        "apps.system_mgmt.middleware.error_log_middleware.write_error_log_async"
    ) as m_task:
        resp = mw.process_exception(_request(), RuntimeError("kaboom"))
    assert resp.status_code == 500
    # 异步任务被下发，且 app/module 正确解析
    m_task.delay.assert_called_once()
    kwargs = m_task.delay.call_args.kwargs
    assert kwargs["app"] == "system_mgmt"
    assert kwargs["module"] == "user"
    assert kwargs["username"] == "alice"
    assert "kaboom" in kwargs["error_message"]


def test_base_app_exception_uses_custom_message_and_status():
    class MyExc(BaseAppException):
        message = "自定义错误"
        STATUS_CODE = 422

    mw = _mw()
    with patch("apps.system_mgmt.middleware.error_log_middleware.write_error_log_async"):
        resp = mw.process_exception(_request(), MyExc("自定义错误"))
    import json

    body = json.loads(resp.content)
    assert resp.status_code == 422
    assert body["message"] == "自定义错误"
    assert body["result"] is False


def test_drf_api_exception_message():
    mw = _mw()
    with patch("apps.system_mgmt.middleware.error_log_middleware.write_error_log_async"):
        resp = mw.process_exception(_request(), PermissionDenied("无权限"))
    assert resp.status_code == 403


def test_non_whitelisted_app_skips_logging_but_still_responds():
    mw = _mw()
    with patch(
        "apps.system_mgmt.middleware.error_log_middleware.write_error_log_async"
    ) as m_task:
        resp = mw.process_exception(_request(path="/api/v1/unknownapp/foo/"), RuntimeError("x"))
    # 不在白名单 -> 不下发任务
    m_task.delay.assert_not_called()
    assert resp.status_code == 500


def test_anonymous_user_logged_as_anonymous():
    mw = _mw()
    req = _request(authenticated=False)
    with patch(
        "apps.system_mgmt.middleware.error_log_middleware.write_error_log_async"
    ) as m_task:
        mw.process_exception(req, RuntimeError("x"))
    assert m_task.delay.call_args.kwargs["username"] == "anonymous"


def test_parse_path():
    mw = _mw()
    assert mw._parse_path("/api/v1/monitor/alert_rule/") == ("monitor", "alert_rule")
    assert mw._parse_path("/api/v1/operation_analysis/x/") == ("ops-analysis", "x")
    assert mw._parse_path("/notapi") == (None, None)


def test_get_username_helper():
    mw = _mw()
    assert mw._get_username(_request()) == "alice"
    assert mw._get_username(_request(authenticated=False)) == "anonymous"


def test_build_error_message_format():
    mw = _mw()
    msg, stack = mw._build_error_message(_request(), ValueError("bad value"))
    assert "[GET]" in msg
    assert "ValueError" in msg
    assert "bad value" in msg
