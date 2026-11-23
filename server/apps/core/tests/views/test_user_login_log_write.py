import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from apps.core.views import index_view
from apps.system_mgmt.models import (
    IntegrationInstance,
    IntegrationInstanceStatusChoices,
    LoginAuthBinding,
    LoginAuthBindingPlatformFieldChoices,
    LoginAuthBindingUnmatchedActionChoices,
    UserLoginLog,
)
from apps.system_mgmt.otp_challenge import create_challenge, verify_challenge
from apps.system_mgmt.utils.login_log_utils import format_login_method_display

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-user-login-log-write",
        }
    }
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _json(response):
    return json.loads(response.content)


def _post(path, data, **extra):
    request = RequestFactory().post(
        path,
        data=json.dumps(data),
        content_type="application/json",
        REMOTE_ADDR="10.9.8.7",
        **extra,
    )
    request.user = MagicMock(locale="zh-Hans")
    return request


def _create_binding(provider_key="feishu", name="Feishu"):
    instance = IntegrationInstance.objects.create(
        name=name,
        provider_key=provider_key,
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    return LoginAuthBinding.objects.create(
        name=f"{name} Binding",
        integration_instance=instance,
        enabled=True,
        external_field="username",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        order=1,
    )


def _logs():
    return list(UserLoginLog.objects.order_by("id"))


def test_local_password_token_writes_one_success():
    with patch.object(index_view, "SystemMgmt") as mock_client:
        mock_client.return_value.login.return_value = {
            "result": True,
            "data": {"token": "JWT", "username": "alice"},
        }
        resp = index_view.login(_post("/login/", {"username": "alice", "password": "pw", "domain": "domain.com"}))

    assert _json(resp)["result"] is True
    logs = _logs()
    assert len(logs) == 1
    assert logs[0].status == UserLoginLog.STATUS_SUCCESS
    assert logs[0].username == "alice"
    assert logs[0].login_method == "bk_lite_builtin"
    assert logs[0].used_otp is False


def test_binding_password_token_writes_one_success_with_provider_key():
    binding = _create_binding("ad", "AD")
    with patch.object(index_view, "SystemMgmt") as mock_client:
        mock_client.return_value.login_with_binding.return_value = {
            "result": True,
            "data": {"token": "ADJWT", "username": "bob"},
        }
        resp = index_view.login(_post("/login/", {"username": "bob", "password": "pw", "binding_id": binding.id}))

    assert _json(resp)["result"] is True
    logs = _logs()
    assert len(logs) == 1
    assert logs[0].login_method == "ad"
    assert logs[0].status == UserLoginLog.STATUS_SUCCESS
    assert logs[0].used_otp is False


def test_otp_challenge_does_not_write_login_log():
    with patch.object(index_view, "SystemMgmt") as mock_client:
        mock_client.return_value.login.return_value = {
            "result": True,
            "data": {"require_otp": True, "challenge_id": "chal-1", "username": "alice"},
        }
        with patch.object(index_view, "remember_otp_challenge_login_method") as remember:
            resp = index_view.login(_post("/login/", {"username": "alice", "password": "pw", "domain": "domain.com"}))

    assert _json(resp)["data"]["challenge_id"] == "chal-1"
    remember.assert_called_once_with("chal-1", "bk_lite_builtin")
    assert UserLoginLog.objects.count() == 0


def test_binding_otp_challenge_does_not_write_login_log():
    binding = _create_binding("feishu")
    challenge_id = create_challenge(user_id=9, username="lark")
    with patch.object(index_view, "SystemMgmt") as mock_client:
        mock_client.return_value.login_with_binding.return_value = {
            "result": True,
            "data": {"require_otp": True, "challenge_id": challenge_id, "username": "lark"},
        }
        resp = index_view.login(_post("/login/", {"binding_id": binding.id, "auth_code": "code"}))

    assert _json(resp)["data"]["require_otp"] is True
    assert UserLoginLog.objects.count() == 0
    assert verify_challenge(challenge_id)["login_method"] == "feishu"


def test_verify_otp_success_writes_used_otp_display():
    challenge_id = create_challenge(user_id=9, username="alice", login_method="bk_lite_builtin")
    with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
        mock_client.return_value.verify_otp_login.return_value = {
            "result": True,
            "data": {"token": "OTPJWT", "username": "alice"},
        }
        resp = index_view.verify_otp_login(_post("/otp/", {"challenge_id": challenge_id, "otp_code": "123456"}))

    assert _json(resp)["result"] is True
    logs = _logs()
    assert len(logs) == 1
    assert logs[0].used_otp is True
    assert logs[0].login_method == "bk_lite_builtin"
    assert format_login_method_display(logs[0].login_method, logs[0].used_otp).endswith("(OTP)")
    assert "123456" not in (logs[0].failure_reason or "")
    assert "OTPJWT" not in json.dumps(logs[0].__dict__, default=str)


def test_verify_otp_failure_writes_user_message_without_code():
    challenge_id = create_challenge(user_id=9, username="alice", login_method="feishu")
    with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
        mock_client.return_value.verify_otp_login.return_value = {
            "result": False,
            "message": "Invalid OTP code",
        }
        resp = index_view.verify_otp_login(_post("/otp/", {"challenge_id": challenge_id, "otp_code": "654321"}))

    assert _json(resp)["result"] is False
    logs = _logs()
    assert len(logs) == 1
    assert logs[0].status == UserLoginLog.STATUS_FAILED
    assert logs[0].failure_reason == "Invalid OTP code"
    dumped = json.dumps(
        {
            "reason": logs[0].failure_reason,
            "username": logs[0].username,
            "method": logs[0].login_method,
        }
    )
    assert "654321" not in dumped


def test_login_auth_callback_success_writes_once_and_polling_does_not():
    binding = _create_binding("feishu")
    auth_request, origin_browser_token, _other = TestLoginAuthBindingsSupport.make_bound_auth_request(binding.id)
    with (
        patch.object(
            index_view, "parse_auth_request_state", return_value={"auth_request_id": "auth-1", "binding_id": binding.id, "callback_url": "/console"}
        ),
        patch.object(index_view, "get_auth_request", return_value=auth_request),
        patch.object(index_view, "SystemMgmt") as mock_client,
        patch.object(index_view, "update_auth_request_status"),
        patch.object(index_view, "validate_poll_token", return_value=True),
        patch.object(index_view, "validate_browser_binding", return_value=True),
    ):
        mock_client.return_value.login_with_binding.return_value = {
            "result": True,
            "data": {"token": "binding-token", "username": "lark"},
        }
        request = RequestFactory().get("/callback/?state=signed&code=auth-code")
        request.COOKIES["bklite_login_auth_browser_auth-1"] = origin_browser_token
        index_view.login_auth_callback(request)
        assert UserLoginLog.objects.count() == 1

        poll = RequestFactory().get("/status/?poll_token=poll-1")
        poll.COOKIES["bklite_login_auth_browser_auth-1"] = origin_browser_token
        index_view.get_login_auth_request_status(poll, "auth-1")

    logs = _logs()
    assert len(logs) == 1
    assert logs[0].status == UserLoginLog.STATUS_SUCCESS
    assert logs[0].login_method == "feishu"
    assert logs[0].username == "lark"


def test_login_auth_callback_otp_challenge_does_not_write():
    binding = _create_binding("wecom")
    challenge_id = create_challenge(user_id=4, username="wecom-user")
    auth_request, origin_browser_token, _other = TestLoginAuthBindingsSupport.make_bound_auth_request(binding.id)
    with (
        patch.object(
            index_view, "parse_auth_request_state", return_value={"auth_request_id": "auth-1", "binding_id": binding.id, "callback_url": "/console"}
        ),
        patch.object(index_view, "get_auth_request", return_value=auth_request),
        patch.object(index_view, "SystemMgmt") as mock_client,
        patch.object(index_view, "update_auth_request_status"),
        patch.object(index_view, "validate_browser_binding", return_value=True),
    ):
        mock_client.return_value.login_with_binding.return_value = {
            "result": True,
            "data": {"require_otp": True, "challenge_id": challenge_id, "username": "wecom-user"},
        }
        request = RequestFactory().get("/callback/?state=signed&code=auth-code")
        request.COOKIES["bklite_login_auth_browser_auth-1"] = origin_browser_token
        index_view.login_auth_callback(request)

    assert UserLoginLog.objects.count() == 0
    assert verify_challenge(challenge_id)["login_method"] == "wecom"


def test_login_auth_callback_cancel_does_not_write():
    binding = _create_binding("wechat")
    with (
        patch.object(
            index_view, "parse_auth_request_state", return_value={"auth_request_id": "auth-1", "binding_id": binding.id, "callback_url": "/console"}
        ),
        patch.object(index_view, "get_auth_request", return_value={"auth_request_id": "auth-1", "status": "pending"}),
        patch.object(index_view, "validate_browser_binding", return_value=True),
        patch.object(index_view, "update_auth_request_status"),
    ):
        request = RequestFactory().get("/callback/?state=signed&error=access_denied")
        index_view.login_auth_callback(request)
    assert UserLoginLog.objects.count() == 0


def test_login_auth_callback_provider_failure_logs_provider_message():
    binding = _create_binding("feishu")
    auth_request, origin_browser_token, _other = TestLoginAuthBindingsSupport.make_bound_auth_request(binding.id)
    provider_message = "invalid app access_token"
    with (
        patch.object(
            index_view, "parse_auth_request_state", return_value={"auth_request_id": "auth-1", "binding_id": binding.id, "callback_url": "/console"}
        ),
        patch.object(index_view, "get_auth_request", return_value=auth_request),
        patch.object(index_view, "SystemMgmt") as mock_client,
        patch.object(index_view, "update_auth_request_status") as mock_update,
        patch.object(index_view, "validate_browser_binding", return_value=True),
    ):
        mock_client.return_value.login_with_binding.return_value = {
            "result": False,
            "message": provider_message,
        }
        request = RequestFactory().get("/callback/?state=signed&code=auth-code")
        request.COOKIES["bklite_login_auth_browser_auth-1"] = origin_browser_token
        index_view.login_auth_callback(request)

    logs = _logs()
    assert len(logs) == 1
    assert logs[0].status == UserLoginLog.STATUS_FAILED
    assert logs[0].login_method == "feishu"
    assert logs[0].failure_reason == provider_message
    assert mock_update.call_args.kwargs["error_message"] == provider_message


def test_login_auth_callback_exception_logs_system_error_not_exception():
    binding = _create_binding("wecom")
    auth_request, origin_browser_token, _other = TestLoginAuthBindingsSupport.make_bound_auth_request(binding.id)
    with (
        patch.object(
            index_view, "parse_auth_request_state", return_value={"auth_request_id": "auth-1", "binding_id": binding.id, "callback_url": "/console"}
        ),
        patch.object(index_view, "get_auth_request", return_value=auth_request),
        patch.object(index_view, "SystemMgmt") as mock_client,
        patch.object(index_view, "update_auth_request_status") as mock_update,
        patch.object(index_view, "validate_browser_binding", return_value=True),
    ):
        mock_client.return_value.login_with_binding.side_effect = RuntimeError("nats secret boom")
        request = RequestFactory().get("/callback/?state=signed&code=auth-code")
        request.COOKIES["bklite_login_auth_browser_auth-1"] = origin_browser_token
        request.user = MagicMock(locale="en")
        index_view.login_auth_callback(request)

    logs = _logs()
    assert len(logs) == 1
    assert logs[0].status == UserLoginLog.STATUS_FAILED
    assert "nats secret boom" not in (logs[0].failure_reason or "")
    assert logs[0].failure_reason == mock_update.call_args.kwargs["error_message"]


def test_get_bk_settings_token_exchange_does_not_write_login_log():
    from apps.core.tests.views.test_blueking_get_bk_settings import _create_ready_binding, _request
    from apps.system_mgmt.models import User

    _create_ready_binding()
    User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        domain="domain.com",
        password="hashed",
    )
    with patch("apps.core.views.index_view.execute_login_with_binding") as login:
        login.return_value = {"result": True, "data": {"token": "login-token", "username": "alice"}}
        index_view.get_bk_settings(_request(cookies={"bk_token": "bk-token"}))
    assert UserLoginLog.objects.count() == 0


def test_start_login_auth_does_not_write_login_log():
    binding = _create_binding("feishu")
    with (
        patch.object(index_view, "_get_login_auth_binding_by_id", return_value=binding),
        patch.object(index_view, "create_auth_request") as create_req,
        patch.object(index_view, "build_login_auth_redirect") as build_redirect,
        patch.object(index_view, "create_browser_binding_token", return_value="browser-token"),
    ):
        create_req.return_value = {
            "auth_request_id": "auth-1",
            "poll_token": "poll-1",
            "expires_at": "2026-06-12T10:00:00+00:00",
        }
        build_redirect.return_value = MagicMock(
            success=True,
            payload={"authorize_url": "https://example.com/feishu"},
            summary="",
            to_dict=MagicMock(return_value={}),
        )
        request = RequestFactory().post(
            "/start/",
            data=json.dumps({"binding_id": binding.id, "callback_url": "/console"}),
            content_type="application/json",
        )
        index_view.start_login_auth(request)
    assert UserLoginLog.objects.count() == 0


def test_old_domain_login_does_not_set_login_method():
    with patch.object(index_view, "bk_lite_login") as mock_bk:
        mock_bk.return_value = {"result": True, "data": {"token": "T2"}}
        index_view.login(_post("/login/", {"username": "u", "password": "p", "domain": "corp.io"}))
    logs = _logs()
    assert len(logs) == 1
    assert logs[0].login_method == ""
    assert logs[0].used_otp is False


def test_wechat_login_write_behavior_unchanged():
    with (
        patch.object(index_view, "verify_wechat_code", return_value={"success": True, "openid": "oid", "nickname": "n"}),
        patch.object(index_view, "_create_system_mgmt_client") as mock_client,
    ):
        mock_client.return_value.wechat_user_register.return_value = {
            "result": True,
            "data": {"token": "WX", "username": "oid"},
        }
        index_view.wechat_login(_post("/wechat/", {"code": "wx-code"}))
    logs = _logs()
    assert len(logs) == 1
    assert logs[0].domain == "wechat"
    assert logs[0].login_method == ""
    assert logs[0].status == UserLoginLog.STATUS_SUCCESS


def test_unhandled_login_error_uses_user_facing_reason():
    with patch.object(index_view, "SystemMgmt") as mock_client:
        mock_client.return_value.login.side_effect = RuntimeError("nats secret boom")
        resp = index_view.login(_post("/login/", {"username": "a", "password": "p", "domain": "domain.com"}))
    body = _json(resp)
    logs = _logs()
    assert body["message"] == logs[0].failure_reason
    assert "nats secret boom" not in logs[0].failure_reason
    assert logs[0].login_method == "bk_lite_builtin"


class TestLoginAuthBindingsSupport:
    @staticmethod
    def make_bound_auth_request(binding_id):
        from apps.core.services import login_auth_request_service as service

        origin_browser_token = service.create_browser_binding_token()
        other_browser_token = service.create_browser_binding_token()
        with patch.object(service, "cache", FakeCache()):
            auth_request = service.create_auth_request(
                binding_id=binding_id,
                provider_key="feishu",
                callback_url="/console",
                browser_binding_token=origin_browser_token,
            )
        auth_request["status"] = "pending"
        auth_request["auth_request_id"] = "auth-1"
        return auth_request, origin_browser_token, other_browser_token


class FakeCache(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def set(self, key, value, timeout=None):
        self[key] = value
        return True
