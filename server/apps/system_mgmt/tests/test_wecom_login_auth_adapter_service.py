from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest

from apps.system_mgmt.providers.builtin.wecom.adapters.login_auth import WeComLoginAuthAdapter

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
    assert result.payload["authorize_url"].startswith("https://wecom.internal/wwopen/sso/qrConnect?")
    assert "appid=ww123" in result.payload["authorize_url"]
    assert "agentid=100" in result.payload["authorize_url"]
    assert "snsapi_base" not in result.payload["authorize_url"]


def test_build_login_url_qr_channel_stays_on_scan_url():
    omitted = WeComLoginAuthAdapter.build_login_url(
        CONFIG,
        "wecom",
        "login_auth",
        redirect_uri="https://bk/callback",
        state="signed",
    )
    explicit = WeComLoginAuthAdapter.build_login_url(
        CONFIG,
        "wecom",
        "login_auth",
        redirect_uri="https://bk/callback",
        state="signed",
        login_channel="qr",
    )
    unknown = WeComLoginAuthAdapter.build_login_url(
        CONFIG,
        "wecom",
        "login_auth",
        redirect_uri="https://bk/callback",
        state="signed",
        login_channel="jsapi",
    )

    assert omitted.payload["authorize_url"] == explicit.payload["authorize_url"]
    assert unknown.payload["authorize_url"] == explicit.payload["authorize_url"]
    assert explicit.payload["authorize_url"].startswith("https://wecom.internal/wwopen/sso/qrConnect?")


def test_build_login_url_oauth_channel_uses_snsapi_base():
    result = WeComLoginAuthAdapter.build_login_url(
        CONFIG,
        "wecom",
        "login_auth",
        redirect_uri="https://bk/callback",
        state="signed",
        login_channel="oauth",
    )

    parsed = urlsplit(result.payload["authorize_url"])
    query = parse_qs(parsed.query)
    assert result.success is True
    assert parsed.scheme == "https"
    assert parsed.netloc == "open.weixin.qq.com"
    assert parsed.path == "/connect/oauth2/authorize"
    assert parsed.fragment == "wechat_redirect"
    assert query["appid"] == ["ww123"]
    assert query["redirect_uri"] == ["https://bk/callback"]
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["snsapi_base"]
    assert query["agentid"] == ["100"]
    assert query["state"] == ["signed"]
    assert "secret" not in result.payload["authorize_url"]
    assert "qrConnect" not in result.payload["authorize_url"]


def test_build_login_url_oauth_channel_uses_configured_authorize_url():
    config = {
        **CONFIG,
        "login_auth_oauth_authorize_url": "https://wecom.internal/connect/oauth2/authorize",
    }

    result = WeComLoginAuthAdapter.build_login_url(
        config,
        "wecom",
        "login_auth",
        redirect_uri="https://bk/callback",
        state="signed",
        login_channel="oauth",
    )

    assert result.payload["authorize_url"].startswith("https://wecom.internal/connect/oauth2/authorize?")
    assert "scope=snsapi_base" in result.payload["authorize_url"]
    assert result.payload["authorize_url"].endswith("#wechat_redirect")
    assert "qrConnect" not in result.payload["authorize_url"]


def test_build_login_url_oauth_channel_rejects_non_http_authorize_url():
    config = {
        **CONFIG,
        "login_auth_oauth_authorize_url": "ftp://wecom.internal/connect/oauth2/authorize",
    }

    result = WeComLoginAuthAdapter.build_login_url(
        config,
        "wecom",
        "login_auth",
        redirect_uri="https://bk/callback",
        state="signed",
        login_channel="oauth",
    )

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_config"
    assert result.errors[0].field == "login_auth_oauth_authorize_url"


def test_describe_client_login_advertises_oauth_without_secret():
    result = WeComLoginAuthAdapter.describe_client_login(CONFIG, "wecom", "login_auth")

    assert result.success is True
    assert result.payload == {"evidence_modes": ["oauth"]}
    assert "secret" not in str(result.payload)


@pytest.mark.parametrize("config", [{}, {"corp_id": "ww123"}, {"agent_id": "100"}, {"corp_secret": "secret"}])
def test_describe_client_login_is_empty_without_corp_id_and_agent_id(config):
    result = WeComLoginAuthAdapter.describe_client_login(config, "wecom", "login_auth")

    assert result.payload == {"evidence_modes": []}


def test_authenticate_reuses_getuserinfo_for_oauth_channel():
    get_responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "userid": "alice"}),
    ]
    with patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.client.requests.get",
        side_effect=get_responses,
    ) as get:
        result = WeComLoginAuthAdapter.authenticate(
            CONFIG,
            "wecom",
            "login_auth",
            auth_code="code",
            login_channel="oauth",
        )

    assert result.success is True
    assert result.payload["external_user"] == {"userid": "alice"}
    assert [call.args[0] for call in get.call_args_list] == [
        "https://wecom.internal/cgi-bin/gettoken",
        "https://wecom.internal/cgi-bin/auth/getuserinfo",
    ]


@pytest.mark.django_db
def test_public_wecom_binding_advertises_oauth_without_secret():
    from apps.system_mgmt.models import IntegrationInstance, IntegrationInstanceStatusChoices, LoginAuthBinding
    from apps.system_mgmt.services.login_auth_binding_service import serialize_public_login_auth_binding

    instance = IntegrationInstance.objects.create(
        name="WeCom",
        provider_key="wecom",
        config={"corp_id": "ww123", "corp_secret": "secret-sentinel", "agent_id": "100"},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    binding = LoginAuthBinding.objects.create(
        name="企业微信",
        integration_instance=instance,
        enabled=True,
        external_field="userid",
        platform_field="username",
        unmatched_user_action="deny",
    )

    payload = serialize_public_login_auth_binding(binding)

    assert payload["client_login"] == {"evidence_modes": ["oauth"]}
    assert "secret-sentinel" not in str(payload)
    assert "jsapi" not in payload["client_login"]


def test_authenticate_uses_configured_access_token_url_and_user_info_url():
    get_responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "UserId": "alice"}),
    ]
    with patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.client.requests.get",
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


def test_authenticate_accepts_official_lowercase_userid_response():
    get_responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "userid": "alice"}),
    ]
    with patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.client.requests.get",
        side_effect=get_responses,
    ):
        result = WeComLoginAuthAdapter.authenticate(CONFIG, "wecom", "login_auth", auth_code="code")

    assert result.success is True
    assert result.payload["external_user"] == {"userid": "alice"}


def test_login_identity_missing_logs_sanitized_response_metadata():
    get_responses = [
        response({"errcode": 0, "access_token": "secret-token"}),
        response({"errcode": 0, "errmsg": "ok", "OpenId": "sensitive-open-id"}),
    ]
    with patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.client.requests.get",
        side_effect=get_responses,
    ), patch("apps.system_mgmt.providers.builtin.wecom.adapters.login_auth.logger") as logger:
        result = WeComLoginAuthAdapter.authenticate(CONFIG, "wecom", "login_auth", auth_code="secret-code")

    assert result.success is False
    logger.warning.assert_called_once_with(
        "WeCom login identity response has no userid or UserId, "
        "endpoint=https://wecom.internal/cgi-bin/auth/getuserinfo, "
        "status=200, errcode=0, errmsg='ok', response_keys=['OpenId', 'errcode', 'errmsg']"
    )
    assert "secret-token" not in str(logger.warning.call_args)
    assert "secret-code" not in str(logger.warning.call_args)
    assert "sensitive-open-id" not in str(logger.warning.call_args)


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
        "apps.system_mgmt.providers.builtin.wecom.adapters.client.requests.get",
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
        "apps.system_mgmt.providers.builtin.wecom.adapters.client.requests.get",
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
        "apps.system_mgmt.providers.builtin.wecom.adapters.client.requests.get",
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
    assert url_result.payload["authorize_url"].startswith("https://open.work.weixin.qq.com/wwopen/sso/qrConnect?")
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
        "apps.system_mgmt.providers.builtin.wecom.adapters.client.requests.get",
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
