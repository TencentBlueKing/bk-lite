from urllib.parse import urlencode

import requests

from apps.system_mgmt.providers.log import logger
from apps.system_mgmt.providers.base import BaseLoginAuthAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from .client import (
    WECOM_DEFAULT_LOGIN_AUTH_AUTHORIZE_URL,
    WECOM_DEFAULT_LOGIN_AUTH_USER_INFO_URL,
    _get_access_token,
    _request_get,
    _resolved_url,
    _sanitize_url_for_log,
    _validate_credentials,
)


class WeComLoginAuthAdapter(BaseLoginAuthAdapter):
    capability_key = "login_auth"

    @classmethod
    def build_login_url(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        config = config or {}
        corp_id = config.get("corp_id", "")
        agent_id = config.get("agent_id", "")
        redirect_uri = kwargs.get("redirect_uri", "")
        if not corp_id or not agent_id or not redirect_uri:
            return CapabilityExecutionResult.failed_result(
                "WeCom login redirect configuration is incomplete",
                code="provider.invalid_config",
            )
        authorize_url = _resolved_url(
            config, "login_auth_authorize_url", WECOM_DEFAULT_LOGIN_AUTH_AUTHORIZE_URL
        )
        query = urlencode({
            "appid": corp_id,
            "agentid": agent_id,
            "redirect_uri": redirect_uri,
            "state": kwargs.get("state", ""),
        })
        return CapabilityExecutionResult.success_result(
            "WeCom login URL generated",
            payload={"authorize_url": f"{authorize_url}?{query}"},
        )

    @classmethod
    def authenticate(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        code = kwargs.get("auth_code", "")
        if error or not code:
            return error or CapabilityExecutionResult.failed_result(
                "WeCom login request is missing code",
                code="provider.invalid_config",
                field="auth_code",
            )
        token, error = _get_access_token(config)
        if error:
            return error
        user_info_url = _resolved_url(
            config, "login_auth_user_info_url", WECOM_DEFAULT_LOGIN_AUTH_USER_INFO_URL
        )
        try:
            identity, response = _request_get(
                user_info_url, config, token, {"code": code}, return_response=True
            )
        except requests.Timeout:
            return CapabilityExecutionResult.failed_result(
                "WeCom login request timed out",
                code="provider.timeout",
                retryable=True,
            )
        except ValueError as error:
            return CapabilityExecutionResult.failed_result(
                str(error) or "WeCom login response is invalid",
                code="provider.invalid_response",
            )
        except requests.RequestException:
            return CapabilityExecutionResult.failed_result(
                "WeCom login request failed",
                code="provider.request_failed",
                retryable=True,
            )
        # 企业微信当前 /cgi-bin/auth/getuserinfo 文档返回小写 userid；
        # 保留 UserId 兼容历史接口响应，统一输出平台约定的 userid。
        user_id = identity.get("userid") or identity.get("UserId")
        if not user_id:
            logger.warning(
                "WeCom login identity response has no userid or UserId, "
                f"endpoint={_sanitize_url_for_log(user_info_url)}, "
                f"status={response.status_code}, errcode={identity.get('errcode')}, "
                f"errmsg={identity.get('errmsg')!r}, response_keys={sorted(identity.keys())}"
            )
            return CapabilityExecutionResult.failed_result(
                "WeCom user identity is missing",
                code="provider.auth_failed",
            )
        return CapabilityExecutionResult.success_result(
            "WeCom login authenticated",
            payload={"external_user": {"userid": user_id}},
        )

    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        _, error = _get_access_token(config)
        return error or CapabilityExecutionResult.success_result("WeCom login capability is ready")
