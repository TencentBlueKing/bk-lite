import json
import os
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.test import RequestFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestLoginAuthBindingViews:
    def _make_post_request(self, payload):
        request = RequestFactory().post("/api/v1/core/api/login/", data=json.dumps(payload), content_type="application/json")
        request.user = MagicMock()
        request.user.locale = "en"
        return request

    def _assert_callback_redirect(self, response, expected_status, expected_message):
        assert response.status_code == 302
        location = response["Location"]
        parsed = urlparse(location)
        assert parsed.path == "/auth/signin/login-auth-result"
        query = parse_qs(parsed.query)
        assert query["status"] == [expected_status]
        assert query["message"] == [expected_message]

    @patch("apps.core.views.index_view.SystemMgmt")
    def test_get_login_auth_bindings_returns_public_payload(self, mock_system_mgmt):
        from apps.core.views.index_view import get_login_auth_bindings

        mock_system_mgmt.return_value.get_login_auth_bindings.return_value = {
            "result": True,
            "data": [
                {
                    "id": 3,
                    "name": "Platform Login",
                    "provider_key": "bk_lite_builtin",
                    "integration_instance_id": 1,
                    "integration_instance_name": "BK-Lite Builtin",
                }
            ],
        }

        request = RequestFactory().get("/api/v1/core/api/get_login_auth_bindings/")
        response = get_login_auth_bindings(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert response["Cache-Control"] == "public, max-age=30"
        assert data["result"] is True
        assert data["data"][0]["provider_key"] == "bk_lite_builtin"

    @patch("apps.core.views.index_view.SystemMgmt")
    def test_get_login_auth_bindings_is_rate_limited(self, mock_system_mgmt):
        from apps.core import views
        from apps.core.views.index_view import get_login_auth_bindings

        fake_cache = FakeCache()
        mock_system_mgmt.return_value.get_login_auth_bindings.return_value = {"result": True, "data": []}

        with patch.object(views.index_view, "cache", fake_cache), patch.object(
            views.index_view,
            "LOGIN_AUTH_BINDINGS_RATE_LIMIT",
            1,
        ):
            first_response = get_login_auth_bindings(RequestFactory().get("/api/v1/core/api/get_login_auth_bindings/"))
            second_response = get_login_auth_bindings(RequestFactory().get("/api/v1/core/api/get_login_auth_bindings/"))

        assert first_response.status_code == 200
        assert second_response.status_code == 429
        mock_system_mgmt.return_value.get_login_auth_bindings.assert_called_once()

    @patch("apps.core.views.index_view.SystemMgmt")
    def test_login_with_binding_sets_cookie_and_redirect(self, mock_system_mgmt):
        from apps.core.views.index_view import login

        mock_system_mgmt.return_value.login_with_binding.return_value = {
            "result": True,
            "data": {
                "username": "feishu-user",
                "token": "binding-token",
            },
        }

        request = self._make_post_request({"binding_id": 5, "auth_code": "auth-code", "redirect_url": "/console"})
        response = login(request)
        data = json.loads(response.content)

        mock_system_mgmt.return_value.login_with_binding.assert_called_once_with(
            5,
            "auth-code",
            username="",
            password="",
        )
        assert response.status_code == 200
        assert data["result"] is True
        assert data["data"]["redirect_url"] == "/console"
        assert response.cookies["bklite_token"].value == "binding-token"

    @patch("apps.core.views.index_view.SystemMgmt")
    def test_login_without_binding_keeps_legacy_password_flow(self, mock_system_mgmt):
        from apps.core.views.index_view import login

        mock_system_mgmt.return_value.login.return_value = {
            "result": True,
            "data": {
                "username": "legacy-user",
                "token": "legacy-token",
            },
        }

        request = self._make_post_request({"username": "legacy-user", "password": "secret", "domain": "domain.com"})
        response = login(request)
        data = json.loads(response.content)

        mock_system_mgmt.return_value.login.assert_called_once_with("legacy-user", "secret")
        mock_system_mgmt.return_value.login_with_binding.assert_not_called()
        assert response.status_code == 200
        assert data["result"] is True
        assert response.cookies["bklite_token"].value == "legacy-token"

    @patch("apps.core.views.index_view.SystemMgmt")
    def test_login_with_binding_supports_username_password_credentials(self, mock_system_mgmt):
        from apps.core.views.index_view import login

        mock_system_mgmt.return_value.login_with_binding.return_value = {
            "result": True,
            "data": {
                "username": "ad-user",
                "token": "ad-token",
            },
        }

        request = self._make_post_request(
            {
                "binding_id": 8,
                "username": "alice",
                "password": "secret",
                "redirect_url": "/console",
            }
        )
        response = login(request)
        data = json.loads(response.content)

        mock_system_mgmt.return_value.login_with_binding.assert_called_once_with(8, "", username="alice", password="secret")
        assert response.status_code == 200
        assert data["result"] is True
        assert response.cookies["bklite_token"].value == "ad-token"

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "http://public.example.test:443"}, clear=False)
    @patch("apps.core.views.index_view.build_login_auth_redirect")
    @patch("apps.core.views.index_view.create_auth_request")
    @patch("apps.core.views.index_view._get_login_auth_binding_by_id")
    def test_start_login_auth_calls_runtime_and_returns_public_payload(
        self,
        mock_get_binding,
        mock_create_auth_request,
        mock_build_redirect,
    ):
        from apps.core.views.index_view import start_login_auth

        binding = MagicMock()
        binding.id = 5
        binding.integration_instance.provider_key = "feishu"
        mock_get_binding.return_value = binding
        mock_create_auth_request.return_value = {
            "auth_request_id": "auth-1",
            "poll_token": "poll-1",
            "expires_at": "2026-06-12T10:00:00+00:00",
        }
        mock_build_redirect.return_value = MagicMock(
            success=True,
            payload={"login_url": "https://example.com/sso"},
            summary="",
            to_dict=MagicMock(return_value={"login_url": "https://example.com/sso"}),
        )

        request = RequestFactory().post(
            "/api/v1/core/api/start_login_auth/",
            data=json.dumps({"binding_id": 5, "callback_url": "/console"}),
            content_type="application/json",
        )
        response = start_login_auth(request)
        data = json.loads(response.content)

        mock_build_redirect.assert_called_once_with(
            binding,
            redirect_uri="http://public.example.test:443/api/v1/core/api/login_auth/callback/",
            state=mock_build_redirect.call_args.kwargs["state"],
        )
        assert response.status_code == 200
        assert data["result"] is True
        assert data["data"] == {
            "auth_request_id": "auth-1",
            "poll_token": "poll-1",
            "login_url": "https://example.com/sso",
            "expires_at": "2026-06-12T10:00:00+00:00",
        }

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "https://bklite.canway.net/"}, clear=False)
    @patch("apps.core.views.index_view.build_login_auth_redirect")
    @patch("apps.core.views.index_view.create_auth_request")
    @patch("apps.core.views.index_view._get_login_auth_binding_by_id")
    def test_start_login_auth_uses_env_redirect_uri_over_valid_redirect_origin(
        self,
        mock_get_binding,
        mock_create_auth_request,
        mock_build_redirect,
    ):
        from apps.core.views.index_view import start_login_auth

        binding = MagicMock()
        binding.id = 5
        binding.integration_instance.provider_key = "feishu"
        mock_get_binding.return_value = binding
        mock_create_auth_request.return_value = {
            "auth_request_id": "auth-1",
            "poll_token": "poll-1",
            "expires_at": "2026-06-12T10:00:00+00:00",
        }
        mock_build_redirect.return_value = MagicMock(
            success=True,
            payload={"login_url": "https://example.com/sso"},
            summary="",
            to_dict=MagicMock(return_value={"login_url": "https://example.com/sso"}),
        )

        request = RequestFactory().post(
            "/api/v1/core/api/start_login_auth/",
            data=json.dumps(
                {
                    "binding_id": 5,
                    "callback_url": "/console",
                    "redirect_origin": "https://other.example",
                }
            ),
            content_type="application/json",
            HTTP_ORIGIN="https://other.example",
            HTTP_HOST="internal.example.test",
        )
        response = start_login_auth(request)

        assert response.status_code == 200
        assert mock_build_redirect.call_args.kwargs["redirect_uri"] == (
            "https://bklite.canway.net/api/v1/core/api/login_auth/callback/"
        )

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "https://bklite.canway.net/"}, clear=False)
    @patch("apps.core.views.index_view.build_login_auth_redirect")
    @patch("apps.core.views.index_view.create_auth_request")
    @patch("apps.core.views.index_view._get_login_auth_binding_by_id")
    def test_start_login_auth_drops_invalid_redirect_origin_when_env_exists(
        self,
        mock_get_binding,
        mock_create_auth_request,
        mock_build_redirect,
    ):
        from apps.core.views.index_view import start_login_auth

        binding = MagicMock()
        binding.id = 5
        binding.integration_instance.provider_key = "feishu"
        mock_get_binding.return_value = binding
        mock_create_auth_request.return_value = {
            "auth_request_id": "auth-1",
            "poll_token": "poll-1",
            "expires_at": "2026-06-12T10:00:00+00:00",
        }
        mock_build_redirect.return_value = MagicMock(
            success=True,
            payload={"login_url": "https://example.com/sso"},
            summary="",
            to_dict=MagicMock(return_value={"login_url": "https://example.com/sso"}),
        )

        request = RequestFactory().post(
            "/api/v1/core/api/start_login_auth/",
            data=json.dumps(
                {
                    "binding_id": 5,
                    "callback_url": "/console",
                    "redirect_origin": "https://evil.example",
                }
            ),
            content_type="application/json",
            HTTP_ORIGIN="https://bklite.canway.net",
            HTTP_HOST="internal.example.test",
        )
        response = start_login_auth(request)

        assert response.status_code == 200
        assert mock_build_redirect.call_args.kwargs["redirect_uri"] == (
            "https://bklite.canway.net/api/v1/core/api/login_auth/callback/"
        )
        assert mock_create_auth_request.call_args.kwargs["redirect_origin"] is None

    @patch.dict(os.environ, {}, clear=False)
    @patch("apps.core.views.index_view.build_login_auth_redirect")
    @patch("apps.core.views.index_view.create_auth_request")
    @patch("apps.core.views.index_view._get_login_auth_binding_by_id")
    def test_start_login_auth_uses_validated_redirect_origin_when_env_missing(
        self,
        mock_get_binding,
        mock_create_auth_request,
        mock_build_redirect,
    ):
        from apps.core.views.index_view import start_login_auth

        os.environ.pop("DEFAULT_ZONE_VAR_NODE_SERVER_URL", None)

        binding = MagicMock()
        binding.id = 5
        binding.integration_instance.provider_key = "feishu"
        mock_get_binding.return_value = binding
        mock_create_auth_request.return_value = {
            "auth_request_id": "auth-1",
            "poll_token": "poll-1",
            "expires_at": "2026-06-12T10:00:00+00:00",
        }
        mock_build_redirect.return_value = MagicMock(
            success=True,
            payload={"login_url": "https://example.com/sso"},
            summary="",
            to_dict=MagicMock(return_value={"login_url": "https://example.com/sso"}),
        )

        request = RequestFactory().post(
            "/api/v1/core/api/start_login_auth/",
            data=json.dumps(
                {
                    "binding_id": 5,
                    "callback_url": "/console",
                    "redirect_origin": "https://other.example",
                }
            ),
            content_type="application/json",
            HTTP_ORIGIN="https://other.example",
            HTTP_HOST="internal.example.test",
        )
        response = start_login_auth(request)

        assert response.status_code == 200
        assert mock_build_redirect.call_args.kwargs["redirect_uri"] == (
            "https://other.example/api/v1/core/api/login_auth/callback/"
        )

    @patch.dict(os.environ, {}, clear=False)
    def test_get_login_auth_callback_uri_falls_back_to_request_origin_when_env_missing(self):
        from apps.core.services.login_auth_request_service import get_login_auth_callback_uri

        os.environ.pop("DEFAULT_ZONE_VAR_NODE_SERVER_URL", None)
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test"
        request.META["wsgi.url_scheme"] = "https"

        assert get_login_auth_callback_uri(request=request) == "https://bk.test/api/v1/core/api/login_auth/callback/"

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "http://public.example.test:443"}, clear=False)
    @patch.dict(os.environ, {}, clear=False)
    def test_build_login_auth_result_redirect_keeps_relative_path_when_env_configured(self):
        from apps.core.views.index_view import _build_login_auth_result_redirect

        os.environ.pop("DEFAULT_ZONE_VAR_NODE_SERVER_URL", None)
        request = RequestFactory().get("/api/v1/core/api/login_auth/callback/")
        request.META["HTTP_HOST"] = "bk.test"

        response = _build_login_auth_result_redirect(
            request,
            "success",
            "认证已完成，可返回原页面继续。",
        )

        parsed = urlparse(response["Location"])
        assert parsed.scheme == ""
        assert parsed.netloc == ""
        assert parsed.path == "/auth/signin/login-auth-result"
        query = parse_qs(parsed.query)
        assert query["status"] == ["success"]
        assert query["message"] == ["认证已完成，可返回原页面继续。"]

    @patch("apps.core.views.index_view.build_login_auth_redirect")
    @patch("apps.core.views.index_view.create_auth_request")
    @patch("apps.core.views.index_view._get_login_auth_binding_by_id")
    def test_start_login_auth_accepts_authorize_url_payload(
        self,
        mock_get_binding,
        mock_create_auth_request,
        mock_build_redirect,
    ):
        from apps.core.views.index_view import start_login_auth

        binding = MagicMock()
        binding.id = 5
        binding.integration_instance.provider_key = "feishu"
        mock_get_binding.return_value = binding
        mock_create_auth_request.return_value = {
            "auth_request_id": "auth-1",
            "poll_token": "poll-1",
            "expires_at": "2026-06-12T10:00:00+00:00",
        }
        mock_build_redirect.return_value = MagicMock(
            success=True,
            payload={"authorize_url": "https://example.com/feishu"},
            summary="Feishu login URL generated",
            to_dict=MagicMock(return_value={"authorize_url": "https://example.com/feishu"}),
        )

        request = RequestFactory().post(
            "/api/v1/core/api/start_login_auth/",
            data=json.dumps({"binding_id": 5, "callback_url": "/console"}),
            content_type="application/json",
        )
        response = start_login_auth(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["result"] is True
        assert data["data"]["login_url"] == "https://example.com/feishu"

    @patch("apps.core.views.index_view.validate_poll_token")
    @patch("apps.core.views.index_view.get_auth_request")
    def test_login_auth_status_requires_matching_poll_token(self, mock_get_auth_request, mock_validate_poll_token):
        from apps.core.views.index_view import get_login_auth_request_status

        mock_get_auth_request.return_value = {"poll_token": "expected", "status": "pending"}
        mock_validate_poll_token.return_value = False

        request = RequestFactory().get("/api/v1/core/api/login_auth_requests/auth-1/status?poll_token=wrong")
        response = get_login_auth_request_status(request, "auth-1")
        data = json.loads(response.content)

        assert response.status_code == 403
        assert data["result"] is False

    @patch("apps.core.views.index_view.get_auth_request")
    def test_login_auth_status_returns_expired_when_cache_entry_missing(self, mock_get_auth_request):
        from apps.core.views.index_view import get_login_auth_request_status

        mock_get_auth_request.return_value = None

        request = RequestFactory().get("/api/v1/core/api/login_auth_requests/auth-1/status?poll_token=poll-1")
        response = get_login_auth_request_status(request, "auth-1")
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["result"] is True
        assert data["data"]["status"] == "expired"

    @patch("apps.core.views.index_view.get_auth_request")
    @patch("apps.core.views.index_view.parse_auth_request_state")
    @patch("apps.core.views.index_view.SystemMgmt")
    @patch("apps.core.views.index_view.update_auth_request_status")
    def test_login_auth_callback_marks_request_success_and_sets_cookie(
        self,
        mock_update_status,
        mock_system_mgmt,
        mock_parse_state,
        mock_get_auth_request,
    ):
        from apps.core.views.index_view import login_auth_callback

        mock_parse_state.return_value = {
            "auth_request_id": "auth-1",
            "binding_id": 5,
            "callback_url": "/console",
        }
        mock_get_auth_request.return_value = {"auth_request_id": "auth-1", "status": "pending"}
        mock_system_mgmt.return_value.login_with_binding.return_value = {
            "result": True,
            "data": {
                "id": 9,
                "username": "feishu-user",
                "token": "binding-token",
                "locale": "en",
                "timezone": "Asia/Shanghai",
            },
        }

        request = RequestFactory().get("/api/v1/core/api/login_auth/callback/?state=signed&code=auth-code")
        response = login_auth_callback(request)

        mock_update_status.assert_called_once_with(
            "auth-1",
            status="success",
            login_result={
                "id": 9,
                "username": "feishu-user",
                "token": "binding-token",
                "locale": "en",
                "timezone": "Asia/Shanghai",
                "redirect_url": "/console",
            },
        )
        self._assert_callback_redirect(response, "success", "认证已完成，可返回原页面继续。")
        assert response.cookies["bklite_token"].value == "binding-token"

    @patch("apps.core.views.index_view.get_auth_request")
    @patch("apps.core.views.index_view.parse_auth_request_state")
    @patch("apps.core.views.index_view.update_auth_request_status")
    def test_login_auth_callback_marks_cancelled_on_access_denied(
        self,
        mock_update_status,
        mock_parse_state,
        mock_get_auth_request,
    ):
        from apps.core.views.index_view import login_auth_callback

        mock_parse_state.return_value = {
            "auth_request_id": "auth-1",
            "binding_id": 5,
            "callback_url": "/console",
        }
        mock_get_auth_request.return_value = {"auth_request_id": "auth-1", "status": "pending"}

        request = RequestFactory().get(
            "/api/v1/core/api/login_auth/callback/?state=signed&error=access_denied&error_description=user_cancelled"
        )
        response = login_auth_callback(request)

        mock_update_status.assert_called_once_with("auth-1", status="cancelled", error_message="user_cancelled")
        self._assert_callback_redirect(response, "cancelled", "认证已取消，可返回原页面重试。")

    @patch("apps.core.views.index_view.get_auth_request")
    @patch("apps.core.views.index_view.parse_auth_request_state")
    @patch("apps.core.views.index_view.SystemMgmt")
    @patch("apps.core.views.index_view.update_auth_request_status")
    def test_login_auth_callback_keeps_success_state_for_replayed_callback(
        self,
        mock_update_status,
        mock_system_mgmt,
        mock_parse_state,
        mock_get_auth_request,
    ):
        from apps.core.views.index_view import login_auth_callback

        mock_parse_state.return_value = {
            "auth_request_id": "auth-1",
            "binding_id": 5,
            "callback_url": "/console",
        }
        mock_get_auth_request.return_value = {
            "auth_request_id": "auth-1",
            "status": "success",
            "login_result": {
                "username": "feishu-user",
                "token": "binding-token",
            },
        }

        request = RequestFactory().get("/api/v1/core/api/login_auth/callback/?state=signed&code=replayed-code")
        response = login_auth_callback(request)

        mock_system_mgmt.return_value.login_with_binding.assert_not_called()
        mock_update_status.assert_not_called()
        self._assert_callback_redirect(response, "success", "认证已完成，可返回原页面继续。")

    @patch("apps.core.views.index_view.parse_auth_request_state")
    def test_login_auth_callback_rejects_invalid_state(self, mock_parse_state):
        from apps.core.views.index_view import login_auth_callback

        mock_parse_state.return_value = None

        request = RequestFactory().get("/api/v1/core/api/login_auth/callback/?state=invalid&code=auth-code")
        response = login_auth_callback(request)

        self._assert_callback_redirect(response, "failed", "认证状态无效或已过期，请返回原页面重试。")

    @patch("apps.core.views.index_view.validate_poll_token")
    @patch("apps.core.views.index_view.get_auth_request")
    def test_login_auth_status_returns_failed_payload(self, mock_get_auth_request, mock_validate_poll_token):
        from apps.core.views.index_view import get_login_auth_request_status

        mock_get_auth_request.return_value = {
            "status": "failed",
            "error_message": "provider failed",
            "expires_at": "2026-06-12T10:00:00+00:00",
            "completed_at": "2026-06-12T09:58:00+00:00",
        }
        mock_validate_poll_token.return_value = True

        request = RequestFactory().get("/api/v1/core/api/login_auth_requests/auth-1/status?poll_token=ok")
        response = get_login_auth_request_status(request, "auth-1")
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["data"]["status"] == "failed"
        assert data["data"]["error_message"] == "provider failed"

    @patch("apps.core.views.index_view.validate_poll_token")
    @patch("apps.core.views.index_view.get_auth_request")
    def test_login_auth_status_returns_login_result_on_success(self, mock_get_auth_request, mock_validate_poll_token):
        from apps.core.views.index_view import get_login_auth_request_status

        mock_get_auth_request.return_value = {
            "status": "success",
            "error_message": "",
            "expires_at": "2026-06-12T10:00:00+00:00",
            "completed_at": "2026-06-12T09:58:00+00:00",
            "login_result": {
                "id": 9,
                "username": "feishu-user",
                "token": "binding-token",
                "locale": "en",
            },
        }
        mock_validate_poll_token.return_value = True

        request = RequestFactory().get("/api/v1/core/api/login_auth_requests/auth-1/status?poll_token=ok")
        response = get_login_auth_request_status(request, "auth-1")
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["data"]["status"] == "success"
        assert data["data"]["login_result"]["token"] == "binding-token"

    @patch("apps.core.views.index_view.validate_poll_token")
    @patch("apps.core.views.index_view.get_auth_request")
    def test_login_auth_status_returns_otp_challenge_payload_on_success(self, mock_get_auth_request, mock_validate_poll_token):
        from apps.core.views.index_view import get_login_auth_request_status

        mock_get_auth_request.return_value = {
            "status": "success",
            "error_message": "",
            "expires_at": "2026-06-12T10:00:00+00:00",
            "completed_at": "2026-06-12T09:58:00+00:00",
            "login_result": {
                "require_otp": True,
                "challenge_id": "challenge-1",
                "qr_code": "qr-data",
                "username": "otp-user",
            },
        }
        mock_validate_poll_token.return_value = True

        request = RequestFactory().get("/api/v1/core/api/login_auth_requests/auth-1/status?poll_token=ok")
        response = get_login_auth_request_status(request, "auth-1")
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["data"]["login_result"]["require_otp"] is True
        assert data["data"]["login_result"]["challenge_id"] == "challenge-1"

    @patch.dict(os.environ, {}, clear=False)
    def test_build_login_auth_result_redirect_prefers_validated_origin(self):
        from apps.core.views.index_view import _build_login_auth_result_redirect

        os.environ.pop("DEFAULT_ZONE_VAR_NODE_SERVER_URL", None)
        request = RequestFactory().get("/api/v1/core/api/login_auth/callback/")
        request.META["HTTP_X_FORWARDED_HOST"] = "bk.test"
        request.META["HTTP_X_FORWARDED_PROTO"] = "https"

        response = _build_login_auth_result_redirect(
            request,
            "success",
            "认证已完成，可返回原页面继续。",
            redirect_origin="https://bk.test",
        )

        assert response.status_code == 302
        assert response["Location"] == (
            "https://bk.test/auth/signin/login-auth-result?status=success"
            "&message=%E8%AE%A4%E8%AF%81%E5%B7%B2%E5%AE%8C%E6%88%90%EF%BC%8C"
            "%E5%8F%AF%E8%BF%94%E5%9B%9E%E5%8E%9F%E9%A1%B5%E9%9D%A2%E7%BB%A7%E7%BB%AD%E3%80%82"
        )

    @patch.dict(os.environ, {}, clear=False)
    def test_build_login_auth_result_redirect_falls_back_to_relative_when_origin_rejected(self):
        from apps.core.views.index_view import _build_login_auth_result_redirect

        os.environ.pop("DEFAULT_ZONE_VAR_NODE_SERVER_URL", None)
        request = RequestFactory().get("/api/v1/core/api/login_auth/callback/")
        request.META["HTTP_HOST"] = "a.example"

        response = _build_login_auth_result_redirect(
            request,
            "failed",
            "认证失败，请返回原页面重试。",
            redirect_origin="http://b.example",
        )

        # origin 跨 host 被拒,降级到相对路径
        parsed = urlparse(response["Location"])
        assert parsed.scheme == ""
        assert parsed.netloc == ""
        assert parsed.path == "/auth/signin/login-auth-result"

    @patch.dict(os.environ, {}, clear=False)
    def test_build_login_auth_result_redirect_uses_relative_when_origin_missing(self):
        from apps.core.views.index_view import _build_login_auth_result_redirect

        os.environ.pop("DEFAULT_ZONE_VAR_NODE_SERVER_URL", None)
        request = RequestFactory().get("/api/v1/core/api/login_auth/callback/")
        request.META["HTTP_HOST"] = "bk.test"

        # 不传 redirect_origin,沿用相对路径契约(原有行为)
        response = _build_login_auth_result_redirect(
            request,
            "success",
            "认证已完成，可返回原页面继续。",
        )

        parsed = urlparse(response["Location"])
        assert parsed.scheme == ""
        assert parsed.netloc == ""
        assert parsed.path == "/auth/signin/login-auth-result"

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "http://public.example.test:443"}, clear=False)
    @patch("apps.core.views.index_view.build_login_auth_redirect")
    @patch("apps.core.views.index_view.create_auth_request")
    @patch("apps.core.views.index_view._get_login_auth_binding_by_id")
    def test_start_login_auth_uses_env_redirect_uri_over_stale_frontend_origin(
        self,
        mock_get_binding,
        mock_create_auth_request,
        mock_build_redirect,
    ):
        from apps.core.views.index_view import start_login_auth

        binding = MagicMock()
        binding.id = 5
        binding.integration_instance.provider_key = "feishu"
        mock_get_binding.return_value = binding
        mock_create_auth_request.return_value = {
            "auth_request_id": "auth-1",
            "poll_token": "poll-1",
            "expires_at": "2026-06-12T10:00:00+00:00",
        }
        mock_build_redirect.return_value = MagicMock(
            success=True,
            payload={"login_url": "https://example.com/sso"},
            summary="",
            to_dict=MagicMock(return_value={"login_url": "https://example.com/sso"}),
        )

        request = RequestFactory().post(
            "/api/v1/core/api/start_login_auth/",
            data=json.dumps({
                "binding_id": 5,
                "callback_url": "/console",
                "redirect_origin": "https://bklite.canway.net",
            }),
            content_type="application/json",
        )
        request.META["HTTP_ORIGIN"] = "https://bklite.canway.net"
        request.META["HTTP_HOST"] = "internal.example.test"

        response = start_login_auth(request)

        assert response.status_code == 200
        assert mock_build_redirect.call_args.kwargs["redirect_uri"] == (
            "http://public.example.test:443/api/v1/core/api/login_auth/callback/"
        )

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "http://public.example.test:443"}, clear=False)
    @patch("apps.core.views.index_view.build_login_auth_redirect")
    @patch("apps.core.views.index_view.create_auth_request")
    @patch("apps.core.views.index_view._get_login_auth_binding_by_id")
    def test_start_login_auth_rejects_cross_origin_redirect_origin_and_falls_back_to_env(
        self,
        mock_get_binding,
        mock_create_auth_request,
        mock_build_redirect,
    ):
        from apps.core.views.index_view import start_login_auth

        binding = MagicMock()
        binding.id = 5
        binding.integration_instance.provider_key = "feishu"
        mock_get_binding.return_value = binding
        mock_create_auth_request.return_value = {
            "auth_request_id": "auth-1",
            "poll_token": "poll-1",
            "expires_at": "2026-06-12T10:00:00+00:00",
        }
        mock_build_redirect.return_value = MagicMock(
            success=True,
            payload={"login_url": "https://example.com/sso"},
            summary="",
            to_dict=MagicMock(return_value={"login_url": "https://example.com/sso"}),
        )

        request = RequestFactory().post(
            "/api/v1/core/api/start_login_auth/",
            data=json.dumps({
                "binding_id": 5,
                "callback_url": "/console",
                "redirect_origin": "https://evil.example",
            }),
            content_type="application/json",
        )
        request.META["HTTP_ORIGIN"] = "https://bklite.canway.net"
        request.META["HTTP_HOST"] = "internal.example.test"

        response = start_login_auth(request)

        assert response.status_code == 200
        assert mock_create_auth_request.call_args.kwargs["redirect_origin"] in (None, "")
        assert mock_build_redirect.call_args.kwargs["redirect_uri"] == (
            "http://public.example.test:443/api/v1/core/api/login_auth/callback/"
        )

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "http://public.example.test:443"}, clear=False)
    @patch("apps.core.views.index_view.build_login_auth_redirect")
    @patch("apps.core.views.index_view.create_auth_request")
    @patch("apps.core.views.index_view._get_login_auth_binding_by_id")
    def test_start_login_auth_compatible_without_redirect_origin(
        self,
        mock_get_binding,
        mock_create_auth_request,
        mock_build_redirect,
    ):
        from apps.core.views.index_view import start_login_auth

        binding = MagicMock()
        binding.id = 6
        binding.integration_instance.provider_key = "feishu"
        mock_get_binding.return_value = binding
        mock_create_auth_request.return_value = {
            "auth_request_id": "auth-2",
            "poll_token": "poll-2",
            "expires_at": "2026-06-12T10:00:00+00:00",
        }
        mock_build_redirect.return_value = MagicMock(
            success=True,
            payload={"login_url": "https://example.com/sso"},
            summary="",
            to_dict=MagicMock(return_value={"login_url": "https://example.com/sso"}),
        )

        # 老前端:不传 redirect_origin
        request = RequestFactory().post(
            "/api/v1/core/api/start_login_auth/",
            data=json.dumps({"binding_id": 6, "callback_url": "/console"}),
            content_type="application/json",
        )

        start_login_auth(request)

        # mock_create_auth_request 收到 redirect_origin=None(后端降级到默认空字符串)
        assert mock_create_auth_request.call_args.kwargs["redirect_origin"] in (None, "")
        # redirect_uri 走 env 兑底
        assert mock_build_redirect.call_args.kwargs["redirect_uri"] == (
            "http://public.example.test:443/api/v1/core/api/login_auth/callback/"
        )


class FakeCache:
    def __init__(self):
        self.store = {}
        self.timeouts = {}

    def get(self, key, default=None):
        return self.store.get(key, default)

    def set(self, key, value, timeout=None):
        self.store[key] = value
        self.timeouts[key] = timeout
        return True

    def add(self, key, value, timeout=None):
        if key in self.store:
            return False
        self.store[key] = value
        self.timeouts[key] = timeout
        return True

    def incr(self, key, delta=1):
        if key not in self.store:
            raise ValueError("Key not found")
        self.store[key] += delta
        return self.store[key]


def _load_login_auth_request_service():
    try:
        from apps.core.services import login_auth_request_service
    except ImportError as exc:
        pytest.fail(f"login_auth_request_service import failed: {exc}")
    return login_auth_request_service


@pytest.mark.unit
class TestLoginAuthRequestService:
    def test_create_auth_request_returns_pending_payload(self):
        service = _load_login_auth_request_service()
        fake_cache = FakeCache()

        with patch.object(service, "cache", fake_cache), patch.object(service, "logger") as mock_logger:
            auth_request = service.create_auth_request(
                binding_id=7,
                provider_key="feishu",
                callback_url="/console",
            )

        assert auth_request["binding_id"] == 7
        assert auth_request["provider_key"] == "feishu"
        assert auth_request["callback_url"] == "/console"
        assert auth_request["status"] == "pending"
        assert auth_request["auth_request_id"]
        assert auth_request["poll_token"]
        assert auth_request["expires_at"]
        mock_logger.info.assert_called_once()
        assert "Created login auth request" in mock_logger.info.call_args.args[0]

    def test_validate_poll_token_accepts_only_matching_token(self):
        service = _load_login_auth_request_service()
        fake_cache = FakeCache()

        with patch.object(service, "cache", fake_cache):
            auth_request = service.create_auth_request(
                binding_id=8,
                provider_key="wechat",
                callback_url="/",
            )

        assert service.validate_poll_token(auth_request, auth_request["poll_token"]) is True
        assert service.validate_poll_token(auth_request, "wrong-token") is False

    def test_get_auth_request_returns_none_on_cache_miss(self):
        service = _load_login_auth_request_service()
        fake_cache = FakeCache()

        with patch.object(service, "cache", fake_cache), patch.object(service, "logger") as mock_logger:
            auth_request = service.get_auth_request("missing-auth-request")

        assert auth_request is None
        mock_logger.info.assert_called_once()
        assert "Login auth request cache miss" in mock_logger.info.call_args.args[0]

    def test_build_and_parse_auth_request_state_round_trip(self):
        service = _load_login_auth_request_service()

        state = service.build_auth_request_state(
            auth_request_id="auth-request-1",
            binding_id=11,
            callback_url="/welcome",
        )
        parsed = service.parse_auth_request_state(state)

        assert parsed == {
            "auth_request_id": "auth-request-1",
            "binding_id": 11,
            "callback_url": "/welcome",
        }
        assert service.parse_auth_request_state("invalid-state") is None

    def test_update_auth_request_status_tracks_success_and_clears_stale_login_result(self):
        service = _load_login_auth_request_service()
        fake_cache = FakeCache()

        with patch.object(service, "cache", fake_cache), patch.object(service, "logger") as mock_logger:
            auth_request = service.create_auth_request(
                binding_id=9,
                provider_key="feishu",
                callback_url="/console",
            )
            updated = service.update_auth_request_status(
                auth_request["auth_request_id"],
                status="success",
                login_result={
                    "id": 9,
                    "token": "secret-token",
                    "username": "demo",
                    "locale": "en",
                    "timezone": "Asia/Shanghai",
                    "temporary_pwd": False,
                    "require_otp": True,
                    "challenge_id": "challenge-1",
                    "qr_code": "qr-data",
                    "need_bindng": True,
                    "external_user": {"id": "provider-user"},
                },
            )
            failed = service.update_auth_request_status(
                auth_request["auth_request_id"],
                status="failed",
                error_message="provider failed",
            )

        assert updated["status"] == "success"
        assert updated["completed_at"]
        assert updated["login_result"] == {
            "id": 9,
            "token": "secret-token",
            "username": "demo",
            "locale": "en",
            "timezone": "Asia/Shanghai",
            "temporary_pwd": False,
            "require_otp": True,
            "challenge_id": "challenge-1",
            "qr_code": "qr-data",
            "need_binding": True,
        }
        assert "need_bindng" not in updated["login_result"]
        assert failed["status"] == "failed"
        assert failed["error_message"] == "provider failed"
        assert "login_result" not in failed
        logged_messages = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("Updated login auth request status" in message for message in logged_messages)

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "http://public.example.test:443/"}, clear=False)
    def test_get_login_auth_callback_uri_prefers_env_and_strips_trailing_slash(self):
        service = _load_login_auth_request_service()

        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test"
        request.META["wsgi.url_scheme"] = "https"

        # 即使 request 提供了其他来源,env 仍优先,保证 OAuth 与详情页结果一致
        assert service.get_login_auth_callback_uri(request=request) == (
            "http://public.example.test:443/api/v1/core/api/login_auth/callback/"
        )

    @pytest.mark.parametrize(
        ("env_url", "expected_callback_uri"),
        [
            (
                "https://bklite.canway.net:443/",
                "https://bklite.canway.net/api/v1/core/api/login_auth/callback/",
            ),
            (
                "http://bklite.canway.net:80/",
                "http://bklite.canway.net/api/v1/core/api/login_auth/callback/",
            ),
        ],
    )
    def test_get_login_auth_callback_uri_strips_default_port_from_env_origin(
        self,
        env_url,
        expected_callback_uri,
    ):
        service = _load_login_auth_request_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test"
        request.META["wsgi.url_scheme"] = "https"

        with patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": env_url}, clear=False):
            assert service.get_login_auth_callback_uri(request=request) == expected_callback_uri

    @patch.dict(os.environ, {}, clear=False)
    def test_get_login_auth_callback_uri_falls_back_to_validated_redirect_origin_when_env_missing(self):
        service = _load_login_auth_request_service()

        os.environ.pop("DEFAULT_ZONE_VAR_NODE_SERVER_URL", None)
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "internal.example.test"
        request.META["HTTP_ORIGIN"] = "https://other.example"

        assert service.get_login_auth_callback_uri(
            request=request,
            redirect_origin="https://other.example",
        ) == "https://other.example/api/v1/core/api/login_auth/callback/"

    def test_get_login_auth_callback_uri_returns_empty_when_env_and_request_missing(self):
        service = _load_login_auth_request_service()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEFAULT_ZONE_VAR_NODE_SERVER_URL", None)
            assert service.get_login_auth_callback_uri() == ""

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "https://bklite.canway.net/"}, clear=False)
    def test_get_login_auth_callback_uri_prefers_env_over_validated_redirect_origin(self):
        service = _load_login_auth_request_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "internal.example.test"
        request.META["HTTP_ORIGIN"] = "https://other.example"

        assert service.get_login_auth_callback_uri(
            request=request,
            redirect_origin="https://other.example",
        ) == "https://bklite.canway.net/api/v1/core/api/login_auth/callback/"

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "http://bk.test:443"}, clear=False)
    def test_get_login_auth_callback_uri_falls_back_to_env_when_origin_rejected(self):
        service = _load_login_auth_request_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test:8011"

        # origin 跨端口(8011 vs 3000)被同源校验拒绝,降级到 env
        assert service.get_login_auth_callback_uri(
            request=request,
            redirect_origin="http://bk.test:3000",
        ) == "http://bk.test:443/api/v1/core/api/login_auth/callback/"

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "http://bk.test:443"}, clear=False)
    def test_get_login_auth_callback_uri_legacy_behavior_when_no_origin(self):
        service = _load_login_auth_request_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test:8011"

        # 不传 redirect_origin 时,完全沿用上一轮既有的 env 兑底行为
        assert service.get_login_auth_callback_uri(request=request) == (
            "http://bk.test:443/api/v1/core/api/login_auth/callback/"
        )

    def test_create_auth_request_stores_redirect_origin_in_cache(self):
        service = _load_login_auth_request_service()
        fake_cache = FakeCache()

        with patch.object(service, "cache", fake_cache):
            auth_request = service.create_auth_request(
                binding_id=12,
                provider_key="feishu",
                callback_url="/console",
                redirect_origin="http://bk.test:3000",
            )

            # 返回的 dict 含新字段
            assert auth_request["redirect_origin"] == "http://bk.test:3000"
            # cache 中能读出(后续 login_auth_callback 依赖此字段做回跳拼接)
            cached = service.get_auth_request(auth_request["auth_request_id"])
            assert cached["redirect_origin"] == "http://bk.test:3000"


class TestValidateRedirectOrigin:
    """validate_redirect_origin 纯函数同源校验测试。

    覆盖 host 与 origin 的各种关系以及 origin 字段合法性。
    """

    def _load_service(self):
        return _load_login_auth_request_service()

    def test_accepts_same_origin_host_and_port(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test:3000"

        assert service.validate_redirect_origin(request, "http://bk.test:3000") is True

    def test_accepts_redirect_origin_matching_browser_origin_when_proxy_host_differs(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_ORIGIN"] = "https://bklite.canway.net"
        request.META["HTTP_HOST"] = "internal.example.test"

        assert service.validate_redirect_origin(request, "https://bklite.canway.net") is True

    @pytest.mark.parametrize(
        ("browser_origin", "redirect_origin"),
        [
            ("https://bklite.canway.net:443", "https://bklite.canway.net"),
            ("https://bklite.canway.net", "https://bklite.canway.net:443"),
        ],
    )
    def test_accepts_origin_and_redirect_origin_when_only_default_https_port_differs(
        self,
        browser_origin,
        redirect_origin,
    ):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_ORIGIN"] = browser_origin
        request.META["HTTP_HOST"] = "internal.example.test"

        assert service.validate_redirect_origin(request, redirect_origin) is True

    def test_accepts_https_origin_via_x_forwarded_host(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_X_FORWARDED_HOST"] = "bk.test"
        request.META["HTTP_X_FORWARDED_PROTO"] = "https"

        assert service.validate_redirect_origin(request, "https://bk.test") is True

    def test_rejects_cross_port_between_origin_and_request_host(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test:8011"

        assert service.validate_redirect_origin(request, "http://bk.test:3000") is False

    def test_rejects_cross_host(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "a.example"

        assert service.validate_redirect_origin(request, "http://b.example") is False

    def test_rejects_origin_with_path(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test"

        assert service.validate_redirect_origin(request, "http://bk.test/console") is False

    def test_rejects_origin_with_query(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test"

        assert service.validate_redirect_origin(request, "http://bk.test?x=1") is False

    def test_rejects_origin_with_fragment(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test"

        assert service.validate_redirect_origin(request, "http://bk.test#anchor") is False

    def test_rejects_non_http_scheme(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test"

        assert service.validate_redirect_origin(request, "javascript:alert(1)") is False
        assert service.validate_redirect_origin(request, "file:///etc/passwd") is False

    def test_rejects_empty_or_non_string_or_missing_netloc(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test"

        assert service.validate_redirect_origin(request, "") is False
        assert service.validate_redirect_origin(request, None) is False
        assert service.validate_redirect_origin(request, 123) is False
        assert service.validate_redirect_origin(request, "http://") is False
