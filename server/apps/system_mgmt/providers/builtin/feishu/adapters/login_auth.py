from urllib.parse import urlencode

import requests

from apps.system_mgmt.providers.log import logger
from apps.system_mgmt.providers.base import BaseLoginAuthAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from .client import (
    FEISHU_AUTH_ACCESS_TOKEN_URL,
    FEISHU_AUTH_USER_INFO_URL,
    FEISHU_AUTHORIZE_URL,
    FEISHU_TIMEOUT,
    _fetch_tenant_access_token,
    _get_config_value,
    _request_tenant_access_token,
    _sanitize_url_for_log,
)


class FeishuLoginAuthAdapter(BaseLoginAuthAdapter):
    capability_key = "login_auth"

    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return _request_tenant_access_token(config, capability_key)

    @classmethod
    def build_login_url(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        app_id = (config or {}).get("app_id", "")
        redirect_uri = kwargs.get("redirect_uri", "")
        state = kwargs.get("state", "")
        if not app_id or not redirect_uri:
            return CapabilityExecutionResult.failed_result(
                "Feishu login redirect configuration is incomplete",
                code="provider.invalid_config",
                field="app_id" if not app_id else "redirect_uri",
            )

        authorize_url = _get_config_value(config, "login_auth_authorize_url", FEISHU_AUTHORIZE_URL)
        authorize_url = f"{authorize_url}?{urlencode({'app_id': app_id, 'redirect_uri': redirect_uri, 'state': state})}"
        return CapabilityExecutionResult.success_result(
            "Feishu login URL generated",
            payload={"authorize_url": authorize_url},
        )

    @classmethod
    def authenticate(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        auth_code = kwargs.get("auth_code", "")
        binding = kwargs.get("binding")
        tenant_access_token, error = _fetch_tenant_access_token(config)
        if error:
            return error

        if not auth_code:
            return CapabilityExecutionResult.failed_result(
                "Feishu login request is missing required parameters",
                code="provider.invalid_config",
                field="auth_code",
            )

        try:
            access_token_url = _get_config_value(config, "login_auth_access_token_url", FEISHU_AUTH_ACCESS_TOKEN_URL)
            token_response = requests.post(
                access_token_url,
                json={"grant_type": "authorization_code", "code": auth_code},
                headers={"Authorization": f"Bearer {tenant_access_token}"},
                timeout=FEISHU_TIMEOUT,
            )
        except requests.Timeout:
            return CapabilityExecutionResult.failed_result("Feishu login request timed out", code="provider.timeout", retryable=True)
        except requests.RequestException as error:
            logger.debug(
                f"Feishu login request failed: endpoint={_sanitize_url_for_log(access_token_url)}, "
                f"error_type={type(error).__name__}"
            )
            return CapabilityExecutionResult.failed_result("Feishu login request failed", code="provider.request_failed", retryable=True)

        try:
            token_data = token_response.json()
        except ValueError:
            return CapabilityExecutionResult.failed_result("Feishu login response is invalid", code="provider.invalid_response")

        if token_response.status_code != 200 or token_data.get("code") not in (0, None):
            return CapabilityExecutionResult.failed_result(
                token_data.get("msg") or "Feishu login failed",
                code="provider.auth_failed",
                external_code=str(token_data.get("code") or token_response.status_code),
            )

        access_token = token_data.get("data", {}).get("access_token") or token_data.get("access_token", "")
        if not access_token:
            return CapabilityExecutionResult.failed_result("Feishu login token is missing", code="provider.invalid_response")

        try:
            user_info_url = _get_config_value(config, "login_auth_user_info_url", FEISHU_AUTH_USER_INFO_URL)
            user_response = requests.get(
                user_info_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=FEISHU_TIMEOUT,
            )
            user_data = user_response.json()
        except requests.Timeout:
            return CapabilityExecutionResult.failed_result("Feishu user info request timed out", code="provider.timeout", retryable=True)
        except (requests.RequestException, ValueError) as error:
            logger.debug(
                f"Feishu user info request failed: endpoint={_sanitize_url_for_log(user_info_url)}, "
                f"error_type={type(error).__name__}"
            )
            return CapabilityExecutionResult.failed_result("Feishu user info request failed", code="provider.request_failed", retryable=True)

        if user_response.status_code != 200 or user_data.get("code") not in (0, None):
            return CapabilityExecutionResult.failed_result(
                user_data.get("msg") or "Feishu user info fetch failed",
                code="provider.auth_failed",
                external_code=str(user_data.get("code") or user_response.status_code),
            )

        data = user_data.get("data") or {}
        return CapabilityExecutionResult.success_result(
            f"Feishu login authenticated for binding '{getattr(binding, 'name', '')}'",
            payload={
                "external_user": {
                    "user_id": data.get("user_id", ""),
                    "open_id": data.get("open_id", ""),
                    "union_id": data.get("union_id", ""),
                    "name": data.get("name", ""),
                    "email": data.get("email", ""),
                    "mobile": data.get("mobile", ""),
                    "avatar_url": data.get("avatar_url", ""),
                    "tenant_key": data.get("tenant_key", ""),
                }
            },
        )
