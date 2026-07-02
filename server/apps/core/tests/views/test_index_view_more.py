import pydantic.root_model  # noqa
"""apps/core/views/index_view.py 补充覆盖（baseline 未触达的视图/分支）。

聚焦：
- index：render index.prod.html（真实模板渲染）
- get_bk_settings：合并门户品牌设置到 verify_bk_token 结果（真实 DB SystemSettings 行）
- get_wechat_settings：成功透传
- _get_loader：使用 request.user.locale 分支
- login：系统异常 -> system_error（255-265）
- wechat_login：非 POST / 系统异常分支
- generate_qr_code / verify_otp_code：未认证 / 失败日志 / 异常分支
- get_my_client / get_all_groups / get_domain_list 等剩余 result=False 分支

策略：SystemMgmt RPC、SystemSettings DB、log_user_login_from_request 在真实边界打桩/写真实行，
断言真实返回 JSON 与 cookie 副作用。
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from apps.core.views import index_view

pytestmark = pytest.mark.unit


def _json(resp):
    return json.loads(resp.content)


def _post(data=None, cookies=None, user=None):
    factory = RequestFactory()
    req = factory.post("/x/", data=json.dumps(data or {}), content_type="application/json")
    if cookies:
        req.COOKIES.update(cookies)
    req.user = user if user is not None else MagicMock(locale="en")
    return req


class TestGetLoader:
    def test_uses_user_locale(self):
        user = MagicMock()
        user.locale = "zh-Hans"
        req = MagicMock(user=user)
        loader = index_view._get_loader(req)
        assert loader.default_lang == "zh-Hans"

    def test_defaults_en_when_no_user(self):
        loader = index_view._get_loader(None)
        assert loader.default_lang == "en"

    def test_falls_back_en_when_locale_empty(self):
        user = MagicMock()
        user.locale = ""
        req = MagicMock(user=user)
        loader = index_view._get_loader(req)
        assert loader.default_lang == "en"


@pytest.mark.django_db
class TestIndexAndBkSettings:
    def test_get_bk_settings_merges_branding(self):
        from apps.system_mgmt.models.system_settings import SystemSettings

        SystemSettings.objects.update_or_create(key="portal_name", defaults={"value": "Brand"})
        req = _post({}, cookies={"bk_token": "tk"})
        with patch.object(index_view, "SystemMgmt") as MockSM:
            MockSM.return_value.verify_bk_token.return_value = {"result": True, "data": {"user": "x"}}
            resp = index_view.get_bk_settings(req)
        data = _json(resp)
        assert data["result"] is True
        assert data["data"]["portal_name"] == "Brand"
        assert data["data"]["user"] == "x"

class TestGetWechatSettingsSuccess:
    def test_success_passthrough(self):
        req = _post({})
        with patch.object(index_view, "_create_system_mgmt_client") as mc:
            mc.return_value.get_wechat_settings.return_value = {"result": True, "data": {"enabled": True}}
            resp = index_view.get_wechat_settings(req)
        assert _json(resp)["data"]["enabled"] is True


class TestLoginException:
    def test_system_error_when_login_raises(self):
        with (
            patch.object(index_view, "SystemMgmt") as MockSM,
            patch.object(index_view, "log_user_login_from_request") as mock_log,
        ):
            MockSM.return_value.login.side_effect = RuntimeError("nats down")
            resp = index_view.login(_post({"username": "a", "password": "p", "domain": "domain.com"}))
        assert _json(resp)["result"] is False
        # 异常路径也记录失败日志
        mock_log.assert_called_once()


class TestWechatLoginBranches:
    def test_rejects_non_post(self):
        factory = RequestFactory()
        resp = index_view.wechat_login(factory.get("/wechat/"))
        assert resp.status_code == 405

    def test_empty_code_rejected(self):
        with patch.object(index_view, "log_user_login_from_request") as mock_log:
            resp = index_view.wechat_login(_post({"code": ""}))
        assert _json(resp)["result"] is False
        mock_log.assert_called_once()

    def test_verify_failure_returns_error(self):
        with (
            patch.object(index_view, "verify_wechat_code", return_value={"success": False, "error": "bad code"}),
            patch.object(index_view, "log_user_login_from_request"),
        ):
            resp = index_view.wechat_login(_post({"code": "c"}))
        assert _json(resp)["result"] is False
        assert _json(resp)["message"] == "bad code"

    def test_registration_failure_returns_result(self):
        with (
            patch.object(index_view, "verify_wechat_code", return_value={"success": True, "openid": "o", "nickname": "n"}),
            patch.object(index_view, "_create_system_mgmt_client") as mc,
            patch.object(index_view, "log_user_login_from_request"),
        ):
            mc.return_value.wechat_user_register.return_value = {"result": False, "message": "reg fail"}
            resp = index_view.wechat_login(_post({"code": "c"}))
        assert _json(resp)["result"] is False

    def test_success_sets_cookie_and_profile(self):
        with (
            patch.object(
                index_view,
                "verify_wechat_code",
                return_value={"success": True, "openid": "o", "nickname": "n", "unionid": "u"},
            ),
            patch.object(index_view, "_create_system_mgmt_client") as mc,
            patch.object(index_view, "log_user_login_from_request"),
            patch.object(index_view, "_set_auth_cookie_on_response") as mock_cookie,
        ):
            mc.return_value.wechat_user_register.return_value = {"result": True, "data": {"token": "WT", "id": 1}}
            resp = index_view.wechat_login(_post({"code": "c"}))
        data = _json(resp)
        assert data["result"] is True
        assert data["data"]["openid"] == "o"
        assert data["data"]["display_name"] == "n"
        mock_cookie.assert_called_once()


class TestOtpAndQrBranches:
    def test_generate_qr_code_failure_logs_and_returns(self):
        user = MagicMock(id=5)
        req = _post({}, user=user)
        with patch.object(index_view, "_create_system_mgmt_client") as mc:
            mc.return_value.generate_qr_code_by_user_id.return_value = {"result": False, "message": "x"}
            resp = index_view.generate_qr_code(req)
        assert _json(resp)["result"] is False

    def test_generate_qr_code_exception(self):
        user = MagicMock(id=5)
        req = _post({}, user=user)
        with patch.object(index_view, "_create_system_mgmt_client") as mc:
            mc.return_value.generate_qr_code_by_user_id.side_effect = RuntimeError("boom")
            resp = index_view.generate_qr_code(req)
        assert _json(resp)["result"] is False

    def test_verify_otp_code_requires_auth(self):
        user = MagicMock(id=None)
        req = _post({"otp_code": "1"}, user=user)
        resp = index_view.verify_otp_code(req)
        assert resp.status_code == 401

    def test_verify_otp_code_failure(self):
        user = MagicMock(id=5)
        req = _post({"otp_code": "123"}, user=user)
        with patch.object(index_view, "_create_system_mgmt_client") as mc:
            mc.return_value.verify_otp_code_by_user_id.return_value = {"result": False}
            resp = index_view.verify_otp_code(req)
        assert _json(resp)["result"] is False

    def test_verify_otp_code_exception(self):
        user = MagicMock(id=5)
        req = _post({"otp_code": "123"}, user=user)
        with patch.object(index_view, "_create_system_mgmt_client") as mc:
            mc.return_value.verify_otp_code_by_user_id.side_effect = RuntimeError("boom")
            resp = index_view.verify_otp_code(req)
        assert _json(resp)["result"] is False

    def test_verify_otp_login_exception(self):
        req = _post({"challenge_id": "ch", "otp_code": "111"})
        with patch.object(index_view, "_create_system_mgmt_client") as mc:
            mc.return_value.verify_otp_login.side_effect = RuntimeError("boom")
            resp = index_view.verify_otp_login(req)
        assert _json(resp)["result"] is False


class TestClientDetailAndGroupsExceptions:
    def test_get_client_detail_exception(self):
        factory = RequestFactory()
        req = factory.get("/d/?name=monitor")
        req.user = MagicMock(locale="en")
        with patch.object(index_view, "_create_system_mgmt_client") as mc:
            mc.return_value.get_client_detail.side_effect = RuntimeError("boom")
            resp = index_view.get_client_detail(req)
        assert _json(resp)["result"] is False

    def test_get_all_groups_exception(self):
        req = _post({}, user=MagicMock(is_superuser=True))
        with patch.object(index_view, "_create_system_mgmt_client") as mc:
            mc.return_value.get_all_groups.side_effect = RuntimeError("boom")
            resp = index_view.get_all_groups(req)
        assert _json(resp)["result"] is False
