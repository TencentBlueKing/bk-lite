"""
apps/core/views/index_view.py 真实单元测试。

覆盖纯辅助函数（_check_first_login / _get_client_ip / _parse_request_data /
_safe_get_user_id_by_username / _get_portal_branding_settings /
_set_auth_cookie_on_response）以及各登录/用户/客户端视图函数。

外部边界（SystemMgmt RPC、SystemSettings/UserLoginLog DB 行、log_user_login_from_request）
通过 mock 或真实 DB 行注入，断言真实返回 JSON、cookie 副作用与入参契约。
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from apps.core.views import index_view


def _json(response):
    return json.loads(response.content)


def _post(data=None, cookies=None, user=None):
    factory = RequestFactory()
    req = factory.post(
        "/api/v1/core/login/",
        data=json.dumps(data or {}),
        content_type="application/json",
    )
    if cookies:
        req.COOKIES.update(cookies)
    req.user = user if user is not None else MagicMock(locale="en")
    return req


# ---------------------------------------------------------------------------
# 纯辅助函数
# ---------------------------------------------------------------------------


class TestCheckFirstLogin:
    def test_empty_group_list_is_first_login(self):
        user = MagicMock(group_list=[])
        assert index_view._check_first_login(user, "Default") is True

    def test_single_group_matching_default_is_first_login(self):
        user = MagicMock(group_list=[{"name": "Default"}])
        assert index_view._check_first_login(user, "Default") is True

    def test_single_group_not_matching_default_is_not_first(self):
        user = MagicMock(group_list=[{"name": "OtherTeam"}])
        assert index_view._check_first_login(user, "Default") is False

    def test_single_group_string_form(self):
        user = MagicMock(group_list=["Default"])
        assert index_view._check_first_login(user, "Default") is True

    def test_multiple_groups_not_first_login(self):
        user = MagicMock(group_list=[{"name": "A"}, {"name": "B"}])
        assert index_view._check_first_login(user, "A") is False


class TestGetClientIp:
    def test_uses_first_ip_from_x_forwarded_for(self):
        req = MagicMock()
        req.META = {"HTTP_X_FORWARDED_FOR": "1.1.1.1, 2.2.2.2", "REMOTE_ADDR": "9.9.9.9"}
        assert index_view._get_client_ip(req) == "1.1.1.1"

    def test_falls_back_to_remote_addr(self):
        req = MagicMock()
        req.META = {"REMOTE_ADDR": "9.9.9.9"}
        assert index_view._get_client_ip(req) == "9.9.9.9"

    def test_empty_when_no_headers(self):
        req = MagicMock()
        req.META = {}
        assert index_view._get_client_ip(req) == ""


class TestParseRequestData:
    def test_parses_json_body(self):
        req = _post({"a": 1, "b": "x"})
        assert index_view._parse_request_data(req) == {"a": 1, "b": "x"}

    def test_invalid_json_falls_back_to_post_dict(self):
        factory = RequestFactory()
        req = factory.post("/x", data="not-json", content_type="application/json")
        # request.body is non-JSON -> fall back to POST.dict() (empty)
        assert index_view._parse_request_data(req) == {}

    def test_empty_body_returns_post_dict(self):
        factory = RequestFactory()
        req = factory.post("/x", data={"k": "v"})
        # form-encoded body is not valid JSON -> POST.dict()
        assert index_view._parse_request_data(req) == {"k": "v"}


class TestSafeGetUserIdByUsername:
    def test_returns_matching_user_id(self):
        client = MagicMock()
        client.search_users.return_value = {
            "data": {"users": [{"username": "alice", "id": 7}, {"username": "bob", "id": 8}]}
        }
        assert index_view._safe_get_user_id_by_username(client, "bob") == 8

    def test_returns_none_when_no_users(self):
        client = MagicMock()
        client.search_users.return_value = {"data": {"users": []}}
        assert index_view._safe_get_user_id_by_username(client, "bob") is None

    def test_returns_none_when_no_username_match(self):
        client = MagicMock()
        client.search_users.return_value = {"data": {"users": [{"username": "alice", "id": 7}]}}
        assert index_view._safe_get_user_id_by_username(client, "bob") is None

    def test_returns_none_on_exception(self):
        client = MagicMock()
        client.search_users.side_effect = RuntimeError("boom")
        assert index_view._safe_get_user_id_by_username(client, "bob") is None


@pytest.mark.django_db
class TestPortalBrandingAndCookie:
    def test_portal_branding_reads_known_keys(self):
        from apps.system_mgmt.models.system_settings import SystemSettings

        # key 唯一且可能已有 seed 行，使用 update_or_create 避免冲突
        SystemSettings.objects.update_or_create(key="portal_name", defaults={"value": "MyPortal"})
        SystemSettings.objects.update_or_create(key="watermark_text", defaults={"value": "secret"})
        SystemSettings.objects.update_or_create(key="unrelated_key", defaults={"value": "ignored"})

        result = index_view._get_portal_branding_settings()
        assert result["portal_name"] == "MyPortal"
        assert result["watermark_text"] == "secret"
        assert "unrelated_key" not in result

    def test_set_auth_cookie_uses_login_expired_time_setting(self):
        from django.http import JsonResponse
        from apps.system_mgmt.models.system_settings import SystemSettings

        SystemSettings.objects.update_or_create(key="login_expired_time", defaults={"value": "2"})  # 2 hours
        response = JsonResponse({"ok": True})
        index_view._set_auth_cookie_on_response(response, "tok123")

        cookie = response.cookies["bklite_token"]
        assert cookie.value == "tok123"
        assert int(cookie["max-age"]) == 2 * 3600
        assert cookie["httponly"] is True
        assert cookie["samesite"] == "Lax"

    def test_set_auth_cookie_defaults_when_no_setting(self):
        from django.http import JsonResponse

        response = JsonResponse({"ok": True})
        index_view._set_auth_cookie_on_response(response, "tok")
        # 默认 24h
        assert int(response.cookies["bklite_token"]["max-age"]) == 24 * 3600


# ---------------------------------------------------------------------------
# login 视图
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLoginView:
    def test_empty_credentials_rejected_and_logged(self):
        with patch.object(index_view, "log_user_login_from_request") as mock_log:
            resp = index_view.login(_post({"username": "", "password": ""}))
        data = _json(resp)
        assert data["result"] is False
        mock_log.assert_called_once()

    def test_domain_com_uses_system_mgmt_login_and_sets_cookie(self):
        with (
            patch.object(index_view, "SystemMgmt") as MockSM,
            patch.object(index_view, "log_user_login_from_request"),
        ):
            MockSM.return_value.login.return_value = {
                "result": True,
                "data": {"token": "JWT", "username": "alice"},
            }
            resp = index_view.login(_post({"username": "alice", "password": "pw", "domain": "domain.com"}))

        data = _json(resp)
        assert data["result"] is True
        # 调用了 SystemMgmt.login，参数为用户名/密码
        MockSM.return_value.login.assert_called_once_with("alice", "pw")
        assert resp.cookies["bklite_token"].value == "JWT"

    def test_non_domain_com_uses_bk_lite_login(self):
        with (
            patch.object(index_view, "bk_lite_login") as mock_bk,
            patch.object(index_view, "log_user_login_from_request"),
        ):
            mock_bk.return_value = {"result": True, "data": {"token": "T2"}}
            resp = index_view.login(_post({"username": "u", "password": "p", "domain": "corp.io"}))

        assert _json(resp)["result"] is True
        mock_bk.assert_called_once_with("u", "p", "corp.io")

    def test_failed_login_logged_no_cookie(self):
        with (
            patch.object(index_view, "SystemMgmt") as MockSM,
            patch.object(index_view, "log_user_login_from_request") as mock_log,
        ):
            MockSM.return_value.login.return_value = {"result": False, "message": "bad pw"}
            resp = index_view.login(_post({"username": "a", "password": "x", "domain": "domain.com"}))

        assert _json(resp)["result"] is False
        assert "bklite_token" not in resp.cookies
        mock_log.assert_called_once()

    def test_redirect_url_added_on_success(self):
        with (
            patch.object(index_view, "SystemMgmt") as MockSM,
            patch.object(index_view, "log_user_login_from_request"),
        ):
            MockSM.return_value.login.return_value = {"result": True, "data": {"token": "T"}}
            resp = index_view.login(
                _post({"username": "a", "password": "p", "domain": "domain.com", "redirect_url": "/home"})
            )
        assert _json(resp)["data"]["redirect_url"] == "/home"


# ---------------------------------------------------------------------------
# logout 视图
# ---------------------------------------------------------------------------


class TestLogoutView:
    def test_rejects_non_post(self):
        factory = RequestFactory()
        resp = index_view.logout(factory.get("/api/logout/"))
        assert resp.status_code == 405

    def test_revokes_token_from_cookie_and_deletes_cookie(self):
        req = _post({}, cookies={"bklite_token": "tok"})
        with patch.object(index_view, "SystemMgmt") as MockSM:
            resp = index_view.logout(req)
        MockSM.return_value.revoke_token.assert_called_once_with("tok")
        assert _json(resp)["result"] is True
        # delete_cookie 把 max-age 设为 0
        assert resp.cookies["bklite_token"]["max-age"] == 0

    def test_revokes_token_from_body_when_no_cookie(self):
        req = _post({"token": "body-tok"})
        with patch.object(index_view, "SystemMgmt") as MockSM:
            index_view.logout(req)
        MockSM.return_value.revoke_token.assert_called_once_with("body-tok")

    def test_no_token_skips_revoke(self):
        req = _post({})
        with patch.object(index_view, "SystemMgmt") as MockSM:
            resp = index_view.logout(req)
        MockSM.return_value.revoke_token.assert_not_called()
        assert _json(resp)["result"] is True

    def test_exception_still_returns_success_and_clears_cookie(self):
        req = _post({}, cookies={"bklite_token": "tok"})
        with patch.object(index_view, "SystemMgmt") as MockSM:
            MockSM.return_value.revoke_token.side_effect = RuntimeError("nats down")
            resp = index_view.logout(req)
        assert _json(resp)["result"] is True
        assert resp.cookies["bklite_token"]["max-age"] == 0


# ---------------------------------------------------------------------------
# login_info / reset_pwd / OTP / client 视图
# ---------------------------------------------------------------------------


class TestLoginInfoView:
    """login_info 用 @api_view(['GET']) 装饰，需经 DRF APIRequestFactory 调用并强制认证。"""

    def _get(self, user):
        from rest_framework.test import APIRequestFactory, force_authenticate

        factory = APIRequestFactory()
        req = factory.get("/api/v1/core/login_info/")
        force_authenticate(req, user=user)
        return req

    def test_returns_user_payload(self):
        user = MagicMock(
            username="alice",
            display_name="Alice",
            is_superuser=True,
            group_list=[{"name": "T"}],
            roles=["r1"],
            group_tree=[],
            locale="en",
            timezone="UTC",
        )
        req = self._get(user)
        with (
            patch.object(index_view, "_create_system_mgmt_client"),
            patch.object(index_view, "_safe_get_user_id_by_username", return_value=42),
        ):
            resp = index_view.login_info(req)
        data = json.loads(resp.content)
        assert data["result"] is True
        assert data["data"]["user_id"] == 42
        assert data["data"]["username"] == "alice"
        assert data["data"]["is_superuser"] is True

    def test_user_not_found_returns_error(self):
        user = MagicMock(username="ghost", group_list=[])
        req = self._get(user)
        with (
            patch.object(index_view, "_create_system_mgmt_client"),
            patch.object(index_view, "_safe_get_user_id_by_username", return_value=None),
        ):
            resp = index_view.login_info(req)
        assert json.loads(resp.content)["result"] is False


class TestResetPwdView:
    def test_empty_password_rejected(self):
        user = MagicMock(username="u", domain="domain.com")
        req = _post({"password": ""}, user=user)
        resp = index_view.reset_pwd(req)
        assert _json(resp)["result"] is False

    def test_missing_caller_token_rejected(self):
        user = MagicMock(username="u", domain="domain.com")
        req = _post({"password": "new"}, user=user)
        resp = index_view.reset_pwd(req)
        assert _json(resp)["result"] is False

    def test_success_forwards_caller_token(self):
        user = MagicMock(username="u", domain="domain.com")
        req = _post({"password": "new"}, cookies={"bklite_token": "ct"}, user=user)
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.reset_pwd.return_value = {"result": True}
            resp = index_view.reset_pwd(req)
        assert _json(resp)["result"] is True
        mock_client.return_value.reset_pwd.assert_called_once_with(
            "u", "domain.com", "new", caller_token="ct"
        )


class TestOtpViews:
    def test_generate_qr_code_requires_auth(self):
        user = MagicMock(id=None)
        req = _post({}, user=user)
        resp = index_view.generate_qr_code(req)
        assert resp.status_code == 401

    def test_generate_qr_code_success(self):
        user = MagicMock(id=5)
        req = _post({}, user=user)
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.generate_qr_code_by_user_id.return_value = {"result": True}
            resp = index_view.generate_qr_code(req)
        assert _json(resp)["result"] is True
        mock_client.return_value.generate_qr_code_by_user_id.assert_called_once_with(5)

    def test_verify_otp_code_empty_rejected(self):
        user = MagicMock(id=5)
        req = _post({"otp_code": ""}, user=user)
        resp = index_view.verify_otp_code(req)
        assert _json(resp)["result"] is False

    def test_verify_otp_code_success(self):
        user = MagicMock(id=5)
        req = _post({"otp_code": "123456"}, user=user)
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.verify_otp_code_by_user_id.return_value = {"result": True}
            resp = index_view.verify_otp_code(req)
        assert _json(resp)["result"] is True
        mock_client.return_value.verify_otp_code_by_user_id.assert_called_once_with(5, "123456")

    @pytest.mark.django_db
    def test_verify_otp_login_missing_params(self):
        req = _post({"challenge_id": "", "otp_code": ""})
        resp = index_view.verify_otp_login(req)
        assert _json(resp)["result"] is False

    @pytest.mark.django_db
    def test_verify_otp_login_success_sets_cookie(self):
        req = _post({"challenge_id": "ch", "otp_code": "999999"})
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.verify_otp_login.return_value = {
                "result": True,
                "data": {"token": "OTPJWT", "username": "alice"},
            }
            resp = index_view.verify_otp_login(req)
        assert _json(resp)["result"] is True
        assert resp.cookies["bklite_token"].value == "OTPJWT"


class TestClientViews:
    def test_get_my_client_uses_query_or_env(self):
        factory = RequestFactory()
        req = factory.get("/api/my_client/?client_id=abc")
        req.user = MagicMock()
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.get_client.return_value = {"result": True, "data": {}}
            resp = index_view.get_my_client(req)
        assert _json(resp)["result"] is True
        mock_client.return_value.get_client.assert_called_once_with("abc", "")

    def test_get_client_detail_requires_name(self):
        factory = RequestFactory()
        req = factory.get("/api/client_detail/")
        req.user = MagicMock()
        resp = index_view.get_client_detail(req)
        assert _json(resp)["result"] is False

    def test_get_user_menus_requires_name(self):
        factory = RequestFactory()
        req = factory.get("/api/user_menus/")
        req.user = MagicMock()
        resp = index_view.get_user_menus(req)
        assert _json(resp)["result"] is False

    def test_get_user_menus_superuser_via_role(self):
        factory = RequestFactory()
        req = factory.get("/api/user_menus/?name=monitor")
        req.user = MagicMock(is_superuser=False, roles=["monitor--admin"], role_ids=[1], username="u")
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.get_user_menus.return_value = {"result": True, "data": []}
            index_view.get_user_menus(req)
        # is_superuser 应被推断为 True（monitor--admin 在 roles 中）
        _, kwargs = mock_client.return_value.get_user_menus.call_args
        assert kwargs["is_superuser"] is True

    def test_get_all_groups_non_superuser_denied(self):
        req = _post({}, user=MagicMock(is_superuser=False))
        resp = index_view.get_all_groups(req)
        assert _json(resp)["result"] is False

    def test_get_all_groups_superuser_ok(self):
        req = _post({}, user=MagicMock(is_superuser=True))
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.get_all_groups.return_value = {"result": True, "data": []}
            resp = index_view.get_all_groups(req)
        assert _json(resp)["result"] is True


class TestGetDomainListAndBkLiteLogin:
    def test_get_domain_list(self):
        req = _post({})
        with patch.object(index_view, "SystemMgmt") as MockSM:
            MockSM.return_value.get_login_module_domain_list.return_value = {"result": True, "data": ["a"]}
            resp = index_view.get_domain_list(req)
        assert _json(resp)["data"] == ["a"]

    def test_bk_lite_login_namespace_lookup_failure(self):
        with patch.object(index_view, "SystemMgmt") as MockSM:
            MockSM.return_value.get_namespace_by_domain.return_value = {"result": False, "message": "no ns"}
            res = index_view.bk_lite_login("u", "p", "corp.io")
        assert res["result"] is False

    def test_bk_lite_login_remote_login_failure(self):
        with (
            patch.object(index_view, "SystemMgmt") as MockSM,
            patch.object(index_view, "RpcClient") as MockRpc,
        ):
            MockSM.return_value.get_namespace_by_domain.return_value = {"result": True, "data": "ns1"}
            MockRpc.return_value.request.return_value = {"result": False, "message": "bad creds"}
            res = index_view.bk_lite_login("u", "p", "corp.io")
        assert res["result"] is False

    def test_bk_lite_login_success_chain(self):
        with (
            patch.object(index_view, "SystemMgmt") as MockSM,
            patch.object(index_view, "RpcClient") as MockRpc,
        ):
            sm = MockSM.return_value
            sm.get_namespace_by_domain.return_value = {"result": True, "data": "ns1"}
            sm.bk_lite_user_login.return_value = {"result": True, "data": {"token": "FINAL"}}
            MockRpc.return_value.request.return_value = {"result": True, "data": {"username": "real_user"}}
            res = index_view.bk_lite_login("u", "p", "corp.io")
        assert res["result"] is True
        sm.bk_lite_user_login.assert_called_once_with("real_user", "corp.io")


class TestGetClientView:
    """get_client：翻译内置应用描述/标签，并在 license_filter 不存在时静默兜底。"""

    def test_translates_buildin_and_handles_missing_license_filter(self):
        req = _post({}, user=MagicMock(username="alice", domain="domain.com", locale="en"))
        return_data = {
            "result": True,
            "data": [
                {"is_build_in": True, "description": "app.monitor", "tags": ["tag.ops"]},
                {"is_build_in": False, "description": "app.custom"},
            ],
        }
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.get_client.return_value = return_data
            # 不 patch license_filter 模块 -> ImportError 分支被静默兜底
            resp = index_view.get_client(req)
        data = _json(resp)
        assert data["result"] is True
        # 非内置应用 description 不被翻译改写
        assert data["data"][1]["description"] == "app.custom"

    def test_get_client_exception_returns_error(self):
        req = _post({}, user=MagicMock(username="alice", domain="domain.com", locale="en"))
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.get_client.side_effect = RuntimeError("nats down")
            resp = index_view.get_client(req)
        assert _json(resp)["result"] is False

    def test_get_client_detail_success_translates_description(self):
        factory = RequestFactory()
        req = factory.get("/api/client_detail/?name=monitor")
        req.user = MagicMock(locale="en")
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.get_client_detail.return_value = {
                "result": True,
                "data": {"description": "app.monitor"},
            }
            resp = index_view.get_client_detail(req)
        data = _json(resp)
        assert data["result"] is True
        # description 经 loader.get 处理后非空（找不到翻译则回退原 key）
        assert data["data"]["description"]


class TestViewExceptionPaths:
    """各视图在外部边界抛错时返回 result=False，不向上冒泡。"""

    def test_get_wechat_settings_exception(self):
        req = _post({})
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.get_wechat_settings.side_effect = RuntimeError("boom")
            resp = index_view.get_wechat_settings(req)
        assert _json(resp)["result"] is False

    def test_get_my_client_exception(self):
        factory = RequestFactory()
        req = factory.get("/api/my_client/")
        req.user = MagicMock(locale="en")
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.get_client.side_effect = RuntimeError("boom")
            resp = index_view.get_my_client(req)
        assert _json(resp)["result"] is False

    def test_get_user_menus_exception(self):
        factory = RequestFactory()
        req = factory.get("/api/user_menus/?name=monitor")
        req.user = MagicMock(is_superuser=True, roles=[], role_ids=[], username="u", locale="en")
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.get_user_menus.side_effect = RuntimeError("boom")
            resp = index_view.get_user_menus(req)
        assert _json(resp)["result"] is False

    def test_reset_pwd_exception(self):
        user = MagicMock(username="u", domain="domain.com")
        req = _post({"password": "new"}, cookies={"bklite_token": "ct"}, user=user)
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.reset_pwd.side_effect = RuntimeError("boom")
            resp = index_view.reset_pwd(req)
        assert _json(resp)["result"] is False

    def test_verify_otp_login_failure_no_cookie(self):
        req = _post({"challenge_id": "ch", "otp_code": "000000"})
        with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
            mock_client.return_value.verify_otp_login.return_value = {"result": False, "message": "bad otp"}
            resp = index_view.verify_otp_login(req)
        assert _json(resp)["result"] is False
        assert "bklite_token" not in resp.cookies
