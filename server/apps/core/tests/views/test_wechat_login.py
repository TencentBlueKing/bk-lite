"""
Unit tests for WeChat login functionality.

Tests cover:
- verify_wechat_code() function
- wechat_login() view
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory


@pytest.mark.unit
class TestVerifyWechatCode:
    """Tests for verify_wechat_code() function."""

    @patch("apps.core.views.index_view._create_system_mgmt_client")
    def test_returns_error_when_wechat_not_enabled(self, mock_client):
        """Should return error when WeChat login is not enabled."""
        from apps.core.views.index_view import verify_wechat_code

        mock_client.return_value.get_wechat_settings.return_value = {"result": True, "data": {"enabled": False}}

        result = verify_wechat_code("test_code")

        assert result["success"] is False
        assert "not enabled" in result["error"].lower()

    @patch("apps.core.views.index_view._create_system_mgmt_client")
    def test_returns_error_when_settings_fetch_fails(self, mock_client):
        """Should return error when WeChat settings cannot be fetched."""
        from apps.core.views.index_view import verify_wechat_code

        mock_client.return_value.get_wechat_settings.return_value = {"result": False, "message": "Settings not found"}

        result = verify_wechat_code("test_code")

        assert result["success"] is False

    @patch("apps.core.views.index_view.requests")
    @patch("apps.core.views.index_view._create_system_mgmt_client")
    def test_returns_error_on_token_exchange_failure(self, mock_client, mock_requests):
        """Should return error when WeChat token exchange fails."""
        from apps.core.views.index_view import verify_wechat_code

        mock_client.return_value.get_wechat_settings.return_value = {
            "result": True,
            "data": {"enabled": True, "app_id": "test_app", "app_secret": "test_secret"},
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {"errcode": 40029, "errmsg": "invalid code"}
        mock_requests.get.return_value = mock_response

        result = verify_wechat_code("test_code")

        assert result["success"] is False
        assert result["errcode"] == 40029

    @patch("apps.core.views.index_view.requests")
    @patch("apps.core.views.index_view._create_system_mgmt_client")
    def test_returns_success_on_valid_flow(self, mock_client, mock_requests):
        """Should return success with user info on valid flow."""
        from apps.core.views.index_view import verify_wechat_code

        mock_client.return_value.get_wechat_settings.return_value = {
            "result": True,
            "data": {"enabled": True, "app_id": "test_app", "app_secret": "test_secret"},
        }

        # First call: token exchange
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "test_token", "openid": "test_openid"}

        # Second call: userinfo
        userinfo_response = MagicMock()
        userinfo_response.json.return_value = {"openid": "test_openid", "nickname": "Test User", "unionid": "test_unionid"}

        mock_requests.get.side_effect = [token_response, userinfo_response]

        result = verify_wechat_code("test_code")

        assert result["success"] is True
        assert result["openid"] == "test_openid"
        assert result["nickname"] == "Test User"
        assert result["unionid"] == "test_unionid"

    @patch("apps.core.views.index_view.requests")
    @patch("apps.core.views.index_view._create_system_mgmt_client")
    def test_handles_timeout(self, mock_client, mock_requests):
        """Should handle timeout gracefully."""
        import requests as real_requests

        from apps.core.views.index_view import verify_wechat_code

        mock_client.return_value.get_wechat_settings.return_value = {
            "result": True,
            "data": {"enabled": True, "app_id": "test_app", "app_secret": "test_secret"},
        }

        mock_requests.get.side_effect = real_requests.Timeout("Connection timed out")
        mock_requests.Timeout = real_requests.Timeout

        result = verify_wechat_code("test_code")

        assert result["success"] is False
        assert "timeout" in result["error"].lower()

    @patch("apps.core.views.index_view.requests")
    @patch("apps.core.views.index_view._create_system_mgmt_client")
    def test_returns_error_on_userinfo_failure(self, mock_client, mock_requests):
        """Should return error when userinfo fetch fails."""
        from apps.core.views.index_view import verify_wechat_code

        mock_client.return_value.get_wechat_settings.return_value = {
            "result": True,
            "data": {"enabled": True, "app_id": "test_app", "app_secret": "test_secret"},
        }

        # First call: token exchange success
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "test_token", "openid": "test_openid"}

        # Second call: userinfo failure
        userinfo_response = MagicMock()
        userinfo_response.json.return_value = {"errcode": 40003, "errmsg": "invalid openid"}

        mock_requests.get.side_effect = [token_response, userinfo_response]

        result = verify_wechat_code("test_code")

        assert result["success"] is False
        assert result["errcode"] == 40003


@pytest.mark.unit
class TestWechatLoginView:
    """Tests for wechat_login() view."""

    def _make_request(self, method="POST", data=None):
        factory = RequestFactory()
        if method == "POST":
            request = factory.post("/api/wechat_login/", data=json.dumps(data or {}), content_type="application/json")
        else:
            request = factory.get("/api/wechat_login/")
        request.user = MagicMock()
        request.user.locale = "en"
        return request

    def test_rejects_get_request(self):
        """Should reject GET requests with 405."""
        from apps.core.views.index_view import wechat_login

        request = self._make_request(method="GET")
        response = wechat_login(request)

        assert response.status_code == 405

    def test_rejects_empty_code(self):
        """Should reject request without code."""
        from apps.core.views.index_view import wechat_login

        request = self._make_request(data={})
        response = wechat_login(request)
        data = json.loads(response.content)

        assert data["result"] is False
        assert "code" in data["message"].lower()

    @patch("apps.core.views.index_view.verify_wechat_code")
    def test_returns_error_on_verification_failure(self, mock_verify):
        """Should return error when WeChat verification fails."""
        from apps.core.views.index_view import wechat_login

        mock_verify.return_value = {"success": False, "error": "Invalid code"}

        request = self._make_request(data={"code": "test_code"})
        response = wechat_login(request)
        data = json.loads(response.content)

        assert data["result"] is False
        assert "Invalid code" in data["message"]

    @patch("apps.core.views.index_view._create_system_mgmt_client")
    @patch("apps.core.views.index_view.verify_wechat_code")
    def test_returns_success_on_valid_login(self, mock_verify, mock_client):
        """Should return success with token on valid login."""
        from apps.core.views.index_view import wechat_login

        mock_verify.return_value = {"success": True, "openid": "test_openid", "nickname": "Test User", "unionid": "test_unionid"}

        mock_client.return_value.wechat_user_register.return_value = {
            "result": True,
            "data": {"id": 1, "username": "test_openid", "token": "test_jwt_token"},
        }

        request = self._make_request(data={"code": "test_code"})
        response = wechat_login(request)
        data = json.loads(response.content)

        assert data["result"] is True
        assert data["data"]["token"] == "test_jwt_token"
        assert data["data"]["openid"] == "test_openid"
        assert data["data"]["unionid"] == "test_unionid"

    @patch("apps.core.views.index_view._create_system_mgmt_client")
    @patch("apps.core.views.index_view.verify_wechat_code")
    def test_sets_cookie_on_success(self, mock_verify, mock_client):
        """Should set bklite_token cookie on successful login."""
        from apps.core.views.index_view import wechat_login

        mock_verify.return_value = {"success": True, "openid": "test_openid", "nickname": "Test User"}

        mock_client.return_value.wechat_user_register.return_value = {
            "result": True,
            "data": {"id": 1, "username": "test_openid", "token": "test_jwt_token"},
        }

        request = self._make_request(data={"code": "test_code"})
        response = wechat_login(request)

        # Check that cookie is set
        assert "bklite_token" in response.cookies
        assert response.cookies["bklite_token"].value == "test_jwt_token"

    @patch("apps.core.views.index_view._create_system_mgmt_client")
    @patch("apps.core.views.index_view.verify_wechat_code")
    def test_returns_error_on_user_registration_failure(self, mock_verify, mock_client):
        """Should return error when user registration fails."""
        from apps.core.views.index_view import wechat_login

        mock_verify.return_value = {"success": True, "openid": "test_openid", "nickname": "Test User"}

        mock_client.return_value.wechat_user_register.return_value = {"result": False, "message": "User registration failed"}

        request = self._make_request(data={"code": "test_code"})
        response = wechat_login(request)
        data = json.loads(response.content)

        assert data["result"] is False
