from unittest.mock import MagicMock, patch

from apps.system_mgmt.providers.adapters.wecom import WeComLoginAuthAdapter


CONFIG = {
    "corp_id": "ww123",
    "corp_secret": "secret",
    "agent_id": "100",
    "access_token_url": "https://wecom.internal/cgi-bin/gettoken",
    "login_auth_authorize_url": "https://wecom.internal/wwopen/sso/qrConnect",
    "login_auth_user_info_url": "https://wecom.internal/cgi-bin/auth/getuserinfo",
}


def response(payload):
    result = MagicMock()
    result.status_code = 200
    result.json.return_value = payload
    return result


def test_build_login_url_uses_login_auth_authorize_url():
    result = WeComLoginAuthAdapter.build_login_url(
        CONFIG,
        "wecom",
        "login_auth",
        redirect_uri="https://bk/callback",
        state="signed",
    )

    assert result.success is True
    assert result.payload["authorize_url"].startswith(
        "https://wecom.internal/wwopen/sso/qrConnect?"
    )
    assert "appid=ww123" in result.payload["authorize_url"]
    assert "agentid=100" in result.payload["authorize_url"]


def test_authenticate_uses_configured_access_token_url_and_user_info_url():
    get_responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "UserId": "alice"}),
    ]
    with patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        side_effect=get_responses,
    ) as get:
        result = WeComLoginAuthAdapter.authenticate(CONFIG, "wecom", "login_auth", auth_code="code")

    assert result.success is True
    assert result.payload["external_user"] == {"userid": "alice"}
    called_urls = [call.args[0] for call in get.call_args_list]
    assert called_urls == [
        "https://wecom.internal/cgi-bin/gettoken",
        "https://wecom.internal/cgi-bin/auth/getuserinfo",
    ]


def test_login_auth_uses_endpoint_overrides_without_base_url_concatenation():
    config = {
        **CONFIG,
        "login_auth_authorize_url": "https://internal.example/sso/qrConnect",
        "access_token_url": "https://internal.example/cgi-bin/gettoken",
        "login_auth_user_info_url": "https://internal.example/cgi-bin/auth/getuserinfo",
    }
    get_responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "UserId": "alice"}),
    ]
    with patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        side_effect=get_responses,
    ) as get:
        url_result = WeComLoginAuthAdapter.build_login_url(
            config,
            "wecom",
            "login_auth",
            redirect_uri="https://bk/callback",
            state="signed",
        )
        auth_result = WeComLoginAuthAdapter.authenticate(config, "wecom", "login_auth", auth_code="code")

    assert url_result.payload["authorize_url"].startswith("https://internal.example/sso/qrConnect?")
    assert auth_result.success is True
    assert [call.args[0] for call in get.call_args_list] == [
        "https://internal.example/cgi-bin/gettoken",
        "https://internal.example/cgi-bin/auth/getuserinfo",
    ]


def test_login_rejects_non_http_login_auth_authorize_url():
    config = {
        **CONFIG,
        "login_auth_authorize_url": "ftp://wecom.internal/wwopen/sso/qrConnect",
    }

    result = WeComLoginAuthAdapter.build_login_url(
        config,
        "wecom",
        "login_auth",
        redirect_uri="https://bk/callback",
        state="signed",
    )

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_config"


def test_login_auth_handles_non_object_json_response():
    array_response = MagicMock()
    array_response.status_code = 200
    array_response.json.return_value = [{"UserId": "alice"}]

    with patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        side_effect=[
            response({"errcode": 0, "access_token": "token"}),
            array_response,
        ],
    ):
        result = WeComLoginAuthAdapter.authenticate(CONFIG, "wecom", "login_auth", auth_code="code")

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_response"


def test_login_auth_falls_back_to_official_urls_when_addresses_missing():
    config = {
        "corp_id": "ww123",
        "corp_secret": "secret",
        "agent_id": "100",
    }
    get_responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "UserId": "alice"}),
    ]
    with patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        side_effect=get_responses,
    ) as get:
        url_result = WeComLoginAuthAdapter.build_login_url(
            config,
            "wecom",
            "login_auth",
            redirect_uri="https://bk/callback",
            state="signed",
        )
        auth_result = WeComLoginAuthAdapter.authenticate(config, "wecom", "login_auth", auth_code="code")

    assert url_result.success is True
    assert url_result.payload["authorize_url"].startswith(
        "https://open.work.weixin.qq.com/wwopen/sso/qrConnect?"
    )
    assert auth_result.success is True
    assert [call.args[0] for call in get.call_args_list] == [
        "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
        "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo",
    ]


def test_login_auth_uses_proxy_url_for_token_and_user_info_requests():
    config = {
        **CONFIG,
        "proxy_url": "http://127.0.0.1:8080",
    }
    get_responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "UserId": "alice"}),
    ]
    with patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        side_effect=get_responses,
    ) as get:
        WeComLoginAuthAdapter.authenticate(config, "wecom", "login_auth", auth_code="code")

    for call in get.call_args_list:
        assert call.kwargs.get("proxies") == {
            "http": "http://127.0.0.1:8080",
            "https": "http://127.0.0.1:8080",
        }, call.kwargs


def test_login_auth_proxy_url_rejects_non_http_scheme():
    config = {
        **CONFIG,
        "proxy_url": "socks5h://127.0.0.1:1080",
    }

    result = WeComLoginAuthAdapter.authenticate(config, "wecom", "login_auth", auth_code="code")

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_config"
    assert result.errors[0].field == "proxy_url"
