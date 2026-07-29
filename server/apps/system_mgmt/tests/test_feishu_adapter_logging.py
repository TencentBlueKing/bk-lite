from unittest.mock import patch

import pytest

from apps.system_mgmt.providers.adapters import feishu
from apps.system_mgmt.providers.adapters.feishu import _request_tenant_access_token


class _SuccessfulTokenResponse:
    status_code = 200
    headers = {"X-Tt-Logid": "req-1"}

    @staticmethod
    def json():
        return {"code": 0, "tenant_access_token": "secret-token"}


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://user:secret@private.example:8443/token/path-secret?key=value#fragment",
            "https://private.example:8443",
        ),
        ("http://[2001:db8::1]:8080/private-secret", "http://[2001:db8::1]:8080"),
        ("/token/private-secret", "<invalid-url>"),
        ("private-secret", "<invalid-url>"),
        ("https://private.example:invalid/token", "<invalid-url>"),
    ],
)
def test_sanitize_url_for_log_only_keeps_valid_http_origin(url, expected):
    assert feishu._sanitize_url_for_log(url) == expected


def test_feishu_connection_probe_logs_success_start_at_debug_only():
    with patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        return_value=_SuccessfulTokenResponse(),
    ), patch("apps.system_mgmt.providers.adapters.feishu.logger") as logger:
        result = _request_tenant_access_token(
            {"app_id": "cli_123456789", "app_secret": "secret"},
            "login_auth",
        )

    assert result.success is True
    logger.info.assert_not_called()
    logger.debug.assert_called_once_with(
        "Testing Feishu connection for capability 'login_auth', app_id=cli***789"
    )


def test_feishu_connection_probe_returns_failure_without_adapter_warning():
    response = _SuccessfulTokenResponse()
    response.status_code = 401
    response.json = lambda: {"code": 99991663, "msg": "invalid token"}

    with patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        return_value=response,
    ), patch("apps.system_mgmt.providers.adapters.feishu.logger") as logger:
        result = _request_tenant_access_token(
            {"app_id": "cli_123456789", "app_secret": "secret"},
            "login_auth",
        )

    assert result.success is False
    logger.warning.assert_not_called()
    logger.exception.assert_not_called()


def test_feishu_token_refresh_logs_sanitized_debug_details_only():
    config = {
        "app_id": "cli_refresh_test",
        "app_secret": "secret",
        "tenant_access_token_url": "https://private.example/token?credential=hidden",
    }
    cache_key = feishu._get_feishu_token_cache_key(config)
    feishu._FEISHU_TENANT_TOKEN_CACHE[cache_key] = {
        "token": "old-token",
        "expires_at": 0,
    }

    try:
        with patch(
            "apps.system_mgmt.providers.adapters.feishu.requests.post",
            return_value=_SuccessfulTokenResponse(),
        ), patch("apps.system_mgmt.providers.adapters.feishu.logger") as logger:
            token, error = feishu._fetch_tenant_access_token(config)
    finally:
        feishu._FEISHU_TENANT_TOKEN_CACHE.pop(cache_key, None)

    assert token == "secret-token"
    assert error is None
    logger.info.assert_not_called()
    log_text = str(logger.debug.call_args_list)
    assert "Refreshing Feishu access token" in log_text
    assert "https://private.example" in log_text
    assert "/token" not in log_text
    assert "credential=hidden" not in log_text


def test_feishu_contact_auth_retry_is_debug_only():
    unauthorized_response = _SuccessfulTokenResponse()
    unauthorized_response.status_code = 401
    unauthorized_response.json = lambda: {
        "code": 99991663,
        "msg": "tenant_access_token expired",
    }
    successful_response = _SuccessfulTokenResponse()
    successful_response.json = lambda: {
        "code": 0,
        "data": {"items": [], "has_more": False},
    }

    with patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        side_effect=[unauthorized_response, successful_response],
    ), patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("new-token", None),
    ), patch("apps.system_mgmt.providers.adapters.feishu.logger") as logger:
        result, error = feishu._feishu_get_paginated(
            "https://private.example/contact?credential=hidden",
            "old-token",
            config={"app_id": "cli_test", "app_secret": "secret"},
        )

    assert error is None
    assert result == {"items": [], "request_id": "req-1"}
    logger.warning.assert_not_called()
    log_text = str(logger.debug.call_args_list)
    assert "refreshing token and retrying once" in log_text
    assert "credential=hidden" not in log_text
