"""WechatLoginAuthAdapter 直接单元测试。

覆盖:
- token exchange 成功 + sns/userinfo 成功 → 返回真实字段 external_user
- sns/userinfo 返回 errcode → failed_result
- userinfo 缺 openid 时 fallback 到 token 的 openid
- token 和 userinfo 都缺 openid → failed_result(防御 KeyError)
- 不调用 wechat_user_register,payload 无 login_result
"""
from unittest.mock import patch, MagicMock

import pytest

from apps.system_mgmt.providers.adapters.wechat import WechatLoginAuthAdapter


WECHAT_CONFIG = {
    "app_id": "wx-test-app",
    "app_secret": "wx-test-secret",
}


def _mock_response(json_data, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    return response


def test_authenticate_returns_external_user_with_real_field_names():
    """token + userinfo 成功 → payload.external_user 用 openid/unionid/nickname/headimgurl。"""
    token_response = _mock_response({"access_token": "AT", "openid": "oxxx", "unionid": "uxxx"})
    userinfo_response = _mock_response({
        "openid": "oxxx",
        "unionid": "uxxx",
        "nickname": "Alice",
        "headimgurl": "https://wx.qq.com/avatar.png",
    })

    with patch("apps.system_mgmt.providers.adapters.wechat.requests.get", side_effect=[token_response, userinfo_response]), \
         patch("apps.system_mgmt.nats_api.wechat_user_register") as mock_register:
        result = WechatLoginAuthAdapter.authenticate(
            config=WECHAT_CONFIG, provider_key="wechat", capability_key="login_auth", auth_code="auth-code-123"
        )

    assert result.success is True
    assert result.payload == {
        "external_user": {
            "openid": "oxxx",
            "unionid": "uxxx",
            "nickname": "Alice",
            "headimgurl": "https://wx.qq.com/avatar.png",
        }
    }
    assert "login_result" not in result.payload
    mock_register.assert_not_called()


def test_authenticate_handles_userinfo_missing_fields_gracefully():
    """userinfo 响应缺 unionid/nickname/headimgurl → 仍成功,缺省字段填空字符串。"""
    token_response = _mock_response({"access_token": "AT", "openid": "oxxx"})
    userinfo_response = _mock_response({"openid": "oxxx"})  # 只返回 openid

    with patch("apps.system_mgmt.providers.adapters.wechat.requests.get", side_effect=[token_response, userinfo_response]):
        result = WechatLoginAuthAdapter.authenticate(
            config=WECHAT_CONFIG, provider_key="wechat", capability_key="login_auth", auth_code="auth-code"
        )

    assert result.success is True
    assert result.payload["external_user"] == {
        "openid": "oxxx",
        "unionid": "",
        "nickname": "",
        "headimgurl": "",
    }


def test_authenticate_falls_back_to_token_openid_when_userinfo_lacks_openid():
    """userinfo 200 + 无 errcode 但缺 openid → fallback 到 token 的 openid(防御 KeyError)。"""
    token_response = _mock_response({"access_token": "AT", "openid": "oxxx"})
    userinfo_response = _mock_response({"errcode": 0, "errmsg": "ok"})  # 畸形:无 openid

    with patch("apps.system_mgmt.providers.adapters.wechat.requests.get", side_effect=[token_response, userinfo_response]):
        result = WechatLoginAuthAdapter.authenticate(
            config=WECHAT_CONFIG, provider_key="wechat", capability_key="login_auth", auth_code="auth-code"
        )

    assert result.success is True
    assert result.payload["external_user"]["openid"] == "oxxx"


def test_authenticate_rejects_when_both_token_and_userinfo_lack_openid():
    """token 和 userinfo 都缺 openid → failed_result(防御 KeyError)。"""
    token_response = _mock_response({"access_token": "AT"})  # 缺 openid
    userinfo_response = _mock_response({"errcode": 0, "errmsg": "ok"})  # 也缺 openid

    with patch("apps.system_mgmt.providers.adapters.wechat.requests.get", side_effect=[token_response, userinfo_response]):
        result = WechatLoginAuthAdapter.authenticate(
            config=WECHAT_CONFIG, provider_key="wechat", capability_key="login_auth", auth_code="auth-code"
        )

    # 实际是 token 阶段就 fail(openid 缺失),这是现有逻辑
    assert result.success is False
    assert result.errors[0].code == "provider.invalid_response"


def test_authenticate_rejects_userinfo_errcode():
    """userinfo 返回 errcode → failed_result,code=provider.auth_failed。"""
    token_response = _mock_response({"access_token": "AT", "openid": "oxxx"})
    userinfo_response = _mock_response({"errcode": 40001, "errmsg": "invalid credential"})

    with patch("apps.system_mgmt.providers.adapters.wechat.requests.get", side_effect=[token_response, userinfo_response]):
        result = WechatLoginAuthAdapter.authenticate(
            config=WECHAT_CONFIG, provider_key="wechat", capability_key="login_auth", auth_code="auth-code"
        )

    assert result.success is False
    assert result.errors[0].code == "provider.auth_failed"
    assert result.errors[0].external_code == "40001"
    assert "invalid credential" in result.errors[0].message


def test_authenticate_rejects_token_missing_openid():
    """token 响应缺 openid → failed_result(已有逻辑保留)。"""
    token_response = _mock_response({"access_token": "AT"})  # 缺 openid

    with patch("apps.system_mgmt.providers.adapters.wechat.requests.get", return_value=token_response):
        result = WechatLoginAuthAdapter.authenticate(
            config=WECHAT_CONFIG, provider_key="wechat", capability_key="login_auth", auth_code="auth-code"
        )

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_response"
