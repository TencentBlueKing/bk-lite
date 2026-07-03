"""中间件单元测试：AppExceptionMiddleware + RequestTimingMiddleware。

仅 mock 真实外部边界（ipware.get_client_ip 走真实纯函数, request 用轻量桩对象）。
断言真实输出：响应状态码、JSON body 内容、日志级别选择、排除路径逻辑、响应头注入。
"""

import json

import pytest

from apps.core.exceptions.base_app_exception import (
    BaseAppException,
    UnauthorizedException,
    ValidationAppException,
)
from apps.core.middlewares.app_exception_middleware import AppExceptionMiddleware
from apps.core.middlewares.request_timing_middleware import RequestTimingMiddleware

pytestmark = pytest.mark.unit


class _Req:
    def __init__(self, method="GET", path="/api/x/", user=None, meta=None):
        self.method = method
        self.path = path
        self.META = meta or {"REMOTE_ADDR": "10.0.0.5"}
        if user is not None:
            self.user = user


class _User:
    def __init__(self, username="alice"):
        self.username = username


def _body(response):
    return json.loads(response.content.decode("utf-8"))


class TestAppExceptionMiddlewareDispatch:
    def setup_method(self):
        self.mw = AppExceptionMiddleware(get_response=lambda r: None)

    def test_base_app_exception_uses_status_and_message(self):
        exc = BaseAppException(message="自定义业务错误")
        resp = self.mw.process_exception(_Req(), exc)
        assert resp.status_code == 500
        body = _body(resp)
        assert body["result"] is False
        assert body["message"] == "自定义业务错误"

    def test_validation_exception_400(self):
        resp = self.mw.process_exception(_Req(), ValidationAppException())
        assert resp.status_code == 400
        assert _body(resp)["message"] == "请求参数非法"

    def test_unauthorized_exception_401(self):
        resp = self.mw.process_exception(_Req(), UnauthorizedException())
        assert resp.status_code == 401

    def test_drf_api_exception_dict_detail(self):
        from rest_framework.exceptions import ValidationError

        resp = self.mw.process_exception(_Req(user=_User()), ValidationError({"field": ["必填"]}))
        assert resp.status_code == 400
        # dict detail 被 str() 化
        assert "field" in _body(resp)["message"]

    def test_drf_api_exception_list_detail(self):
        from rest_framework.exceptions import APIException

        exc = APIException(detail=["e1", "e2"])
        resp = self.mw.process_exception(_Req(user=_User()), exc)
        assert "e1" in _body(resp)["message"]
        assert "e2" in _body(resp)["message"]

    def test_drf_permission_denied_403(self):
        from rest_framework.exceptions import PermissionDenied

        resp = self.mw.process_exception(_Req(user=_User()), PermissionDenied())
        assert resp.status_code == 403

    def test_system_exception_returns_generic_500(self):
        resp = self.mw.process_exception(_Req(user=_User()), RuntimeError("内部细节不应泄露"))
        assert resp.status_code == 500
        body = _body(resp)
        assert body["message"] == "系统异常,请联系管理员处理"
        assert "内部细节" not in body["message"]

    def test_middleware_self_error_falls_back(self, mocker):
        # 让内部处理函数抛错，验证外层兜底分支
        mocker.patch.object(self.mw, "_handle_system_exception", side_effect=Exception("handler crash"))
        resp = self.mw.process_exception(_Req(), RuntimeError("orig"))
        assert resp.status_code == 500
        assert _body(resp)["message"] == "系统异常,请联系管理员处理"


class TestGetUsername:
    def setup_method(self):
        self.mw = AppExceptionMiddleware(get_response=lambda r: None)

    def test_returns_username_when_present(self):
        assert self.mw._get_username(_Req(user=_User("bob"))) == "bob"

    def test_anonymous_when_no_user(self):
        assert self.mw._get_username(_Req()) == "anonymous"

    def test_anonymous_when_user_access_raises(self):
        class Bad:
            @property
            def user(self):
                raise RuntimeError("no user")

        assert self.mw._get_username(Bad()) == "anonymous"


class _Resp(dict):
    def __init__(self, status_code=200):
        super().__init__()
        self.status_code = status_code

    def __setitem__(self, k, v):
        super().__setitem__(k, v)


class TestRequestTimingMiddleware:
    def setup_method(self):
        self.mw = RequestTimingMiddleware(get_response=lambda r: None)

    def test_process_request_sets_start_time(self):
        req = _Req()
        assert self.mw.process_request(req) is None
        assert hasattr(req, "_start_time")
        assert isinstance(req._start_time, float)

    def test_process_response_without_start_time_passthrough(self):
        resp = _Resp(200)
        out = self.mw.process_response(_Req(), resp)
        assert out is resp

    def test_excluded_path_skips_header(self):
        req = _Req(path="/health/")
        self.mw.process_request(req)
        resp = _Resp(200)
        out = self.mw.process_response(req, resp)
        assert "X-Request-Time" not in resp
        assert out is resp

    def test_exact_root_path_excluded(self):
        assert self.mw._should_exclude("/") is True

    def test_prefix_excluded(self):
        assert self.mw._should_exclude("/static/app.js") is True

    def test_normal_path_not_excluded(self):
        assert self.mw._should_exclude("/api/v1/core/x") is False

    def test_sidecar_path_detection(self):
        assert self.mw._is_sidecar_open_api_path("/node_mgmt/open_api/node/list") is True
        assert self.mw._is_sidecar_open_api_path("/api/v1/other") is False

    def test_timing_header_added_when_enabled(self, mocker):
        mocker.patch.object(RequestTimingMiddleware, "ADD_TIMING_HEADER", True)
        req = _Req(path="/api/v1/core/x")
        self.mw.process_request(req)
        resp = _Resp(200)
        self.mw.process_response(req, resp)
        assert "X-Request-Time" in resp
        assert resp["X-Request-Time"].endswith("ms")

    def test_log_request_slow_warning(self, mocker):
        from apps.core.middlewares import request_timing_middleware as mod

        warn = mocker.patch.object(mod.logger, "warning")
        self.mw._log_request(_Req(path="/api/slow"), _Resp(200), elapsed_time_ms=99999)
        warn.assert_called_once()

    def test_log_request_500_error(self, mocker):
        from apps.core.middlewares import request_timing_middleware as mod

        err = mocker.patch.object(mod.logger, "error")
        self.mw._log_request(_Req(path="/api/err"), _Resp(500), elapsed_time_ms=10)
        err.assert_called_once()

    def test_log_request_400_warning(self, mocker):
        from apps.core.middlewares import request_timing_middleware as mod

        warn = mocker.patch.object(mod.logger, "warning")
        self.mw._log_request(_Req(path="/api/bad"), _Resp(404), elapsed_time_ms=10)
        warn.assert_called_once()

    def test_log_request_sidecar_debug(self, mocker):
        from apps.core.middlewares import request_timing_middleware as mod

        debug = mocker.patch.object(mod.logger, "debug")
        self.mw._log_request(_Req(path="/node_mgmt/open_api/node/x"), _Resp(200), elapsed_time_ms=10)
        debug.assert_called_once()

    def test_log_request_normal_info(self, mocker):
        from apps.core.middlewares import request_timing_middleware as mod

        info = mocker.patch.object(mod.logger, "info")
        self.mw._log_request(_Req(path="/api/v1/core/ok"), _Resp(200), elapsed_time_ms=10)
        info.assert_called_once()
