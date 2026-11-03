from unittest.mock import MagicMock, patch

import pytest
import requests

from apps.system_mgmt.providers.builtin.feishu.adapters.client import FEISHU_JSAPI_TOKEN_URL
from apps.system_mgmt.providers.builtin.feishu.adapters.login_auth import FeishuLoginAuthAdapter

CONFIG = {
    "app_id": "cli_public",
    "app_secret": "secret-sentinel",
}


def _json_response(payload, status_code=200):
    response = MagicMock(status_code=status_code)
    response.json.return_value = payload
    return response


def test_describe_client_login_exposes_app_id_and_both_evidence_modes():
    result = FeishuLoginAuthAdapter.describe_client_login(
        config=CONFIG,
        provider_key="feishu",
        capability_key="login_auth",
    )

    assert result.success is True
    assert result.payload == {
        "evidence_modes": ["oauth", "jsapi"],
        "jsapi": {"app_id": "cli_public"},
    }
    assert "secret-sentinel" not in str(result.payload)


def test_describe_client_login_is_empty_without_app_id():
    result = FeishuLoginAuthAdapter.describe_client_login(
        config={},
        provider_key="feishu",
        capability_key="login_auth",
    )

    assert result.payload == {"evidence_modes": []}


def test_oauth_code_still_uses_tenant_access_token_exchange():
    token_response = _json_response({"code": 0, "data": {"access_token": "user-token"}})
    user_response = _json_response({"code": 0, "data": {"user_id": "u1", "name": "Ada"}})

    with patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ) as tenant, patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.requests.post",
        return_value=token_response,
    ) as post, patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.requests.get",
        return_value=user_response,
    ):
        result = FeishuLoginAuthAdapter.authenticate(
            config=CONFIG,
            provider_key="feishu",
            capability_key="login_auth",
            auth_code="oauth-code",
            binding=MagicMock(name="飞书登录"),
        )

    tenant.assert_called_once()
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer tenant-token"
    assert post.call_args.kwargs["json"] == {"grant_type": "authorization_code", "code": "oauth-code"}
    assert result.success is True
    assert result.payload["external_user"]["user_id"] == "u1"


def test_request_access_code_uses_oauth_v3_without_tenant_token():
    token_response = _json_response({"code": 0, "access_token": "user-token"})
    user_response = _json_response({"code": 0, "data": {"user_id": "u2", "open_id": "o2"}})

    with patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth._fetch_tenant_access_token",
    ) as tenant, patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.requests.post",
        return_value=token_response,
    ) as post, patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.requests.get",
        return_value=user_response,
    ) as get, patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.logger",
    ) as logger:
        result = FeishuLoginAuthAdapter.authenticate(
            config=CONFIG,
            provider_key="feishu",
            capability_key="login_auth",
            auth_code="jsapi-code",
            evidence_mode="jsapi",
            jsapi_code_type="request_access",
        )

    tenant.assert_not_called()
    assert post.call_args.args[0] == FEISHU_JSAPI_TOKEN_URL
    assert post.call_args.kwargs["json"]["client_id"] == "cli_public"
    assert post.call_args.kwargs["json"]["client_secret"] == "secret-sentinel"
    assert post.call_args.kwargs["json"]["code"] == "jsapi-code"
    assert "redirect_uri" not in post.call_args.kwargs["json"]
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer user-token"
    assert result.payload["external_user"]["open_id"] == "o2"
    logger.debug.assert_not_called()
    logger.info.assert_not_called()
    assert "secret-sentinel" not in str(logger.mock_calls)
    assert "jsapi-code" not in str(logger.mock_calls)


def test_legacy_request_auth_code_keeps_tenant_exchange():
    token_response = _json_response({"code": 0, "data": {"access_token": "user-token"}})
    user_response = _json_response({"code": 0, "data": {"user_id": "u3"}})

    with patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ) as tenant, patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.requests.post",
        return_value=token_response,
    ), patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.requests.get",
        return_value=user_response,
    ):
        result = FeishuLoginAuthAdapter.authenticate(
            config=CONFIG,
            provider_key="feishu",
            capability_key="login_auth",
            auth_code="legacy-code",
            evidence_mode="jsapi",
            jsapi_code_type="request_auth_code",
        )

    tenant.assert_called_once()
    assert result.payload["external_user"]["user_id"] == "u3"


def test_request_access_failure_logs_endpoint_without_secret():
    with patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.requests.post",
        side_effect=requests.ConnectionError("secret-sentinel"),
    ), patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.logger",
    ) as logger:
        result = FeishuLoginAuthAdapter.authenticate(
            config=CONFIG,
            provider_key="feishu",
            capability_key="login_auth",
            auth_code="jsapi-code",
            evidence_mode="jsapi",
        )

    assert result.success is False
    logger.debug.assert_called_once_with(
        "Feishu JSAPI login request failed: endpoint=%s, error_type=%s",
        "https://accounts.feishu.cn",
        "ConnectionError",
    )
    assert "secret-sentinel" not in str(logger.debug.call_args)
    assert "jsapi-code" not in str(logger.debug.call_args)


def test_describe_public_client_login_ignores_unregistered_provider_without_warning():
    from apps.system_mgmt.services.login_auth_binding_service import describe_public_client_login

    instance = MagicMock()
    instance.provider_key = "bk_lite_builtin"
    instance.get_runtime_config.return_value = {"secret-sentinel": "secret-sentinel"}

    with patch(
        "apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute",
        side_effect=ValueError("provider missing"),
    ), patch("apps.system_mgmt.services.login_auth_binding_service.logger") as logger:
        public = describe_public_client_login(instance)

    assert public == {"evidence_modes": []}
    logger.warning.assert_not_called()
    assert "secret-sentinel" not in str(logger.mock_calls)


def test_describe_public_client_login_logs_failure_without_secret():
    from apps.system_mgmt.services.login_auth_binding_service import describe_public_client_login

    instance = MagicMock()
    instance.provider_key = "feishu"
    instance.get_runtime_config.side_effect = RuntimeError("secret-sentinel")

    with patch("apps.system_mgmt.services.login_auth_binding_service.logger") as logger:
        public = describe_public_client_login(instance)

    assert public == {"evidence_modes": []}
    logger.warning.assert_called_once_with(
        "event=login_auth_client_login_describe_failed provider_key=%s error_type=%s",
        "feishu",
        "RuntimeError",
    )
    assert "secret-sentinel" not in str(logger.warning.call_args)


@pytest.mark.django_db
def test_public_binding_payload_includes_jsapi_app_id_only():
    from apps.system_mgmt.models import IntegrationInstance, IntegrationInstanceStatusChoices, LoginAuthBinding
    from apps.system_mgmt.services.login_auth_binding_service import serialize_public_login_auth_binding

    instance = IntegrationInstance.objects.create(
        name="Feishu",
        provider_key="feishu",
        config={"app_id": "cli_public", "app_secret": "secret-sentinel"},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    binding = LoginAuthBinding.objects.create(
        name="飞书",
        integration_instance=instance,
        enabled=True,
        external_field="user_id",
        platform_field="username",
        unmatched_user_action="deny",
    )

    payload = serialize_public_login_auth_binding(binding)

    assert payload["client_login"] == {
        "evidence_modes": ["oauth", "jsapi"],
        "jsapi": {"app_id": "cli_public"},
    }
    assert "secret-sentinel" not in str(payload)
