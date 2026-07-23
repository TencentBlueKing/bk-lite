from urllib.parse import urlencode

import requests

from apps.core.logger import logger

from .base import BaseLoginAuthAdapter
from ..runtime import CapabilityExecutionResult

WECHAT_TIMEOUT = 10
WECHAT_AUTHORIZE_URL = "https://open.weixin.qq.com/connect/qrconnect"
WECHAT_ACCESS_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
WECHAT_USER_INFO_URL = "https://api.weixin.qq.com/sns/userinfo"


def _get_config_value(config: dict, key: str, default: str):
    return (config or {}).get(key) or default


class WechatLoginAuthAdapter(BaseLoginAuthAdapter):
    capability_key = "login_auth"

    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        app_id = (config or {}).get("app_id", "")
        app_secret = (config or {}).get("app_secret", "")
        if not app_id or not app_secret:
            return CapabilityExecutionResult.failed_result(
                "WeChat app_id or app_secret is missing",
                code="provider.invalid_config",
                field="app_id" if not app_id else "app_secret",
            )
        return CapabilityExecutionResult.success_result("WeChat login capability is ready")

    @classmethod
    def build_login_url(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        app_id = (config or {}).get("app_id", "")
        redirect_uri = kwargs.get("redirect_uri", "")
        state = kwargs.get("state", "")
        if not app_id or not redirect_uri:
            return CapabilityExecutionResult.failed_result(
                "WeChat login redirect configuration is incomplete",
                code="provider.invalid_config",
                field="app_id" if not app_id else "redirect_uri",
            )

        authorize_url = _get_config_value(config, "login_auth_authorize_url", WECHAT_AUTHORIZE_URL)
        query = urlencode(
            {
                "appid": app_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "snsapi_login",
                "state": state,
            }
        )
        return CapabilityExecutionResult.success_result(
            "WeChat login URL generated",
            payload={"authorize_url": f"{authorize_url}?{query}#wechat_redirect"},
        )

    @classmethod
    def authenticate(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        auth_code = kwargs.get("auth_code", "")
        app_id = (config or {}).get("app_id", "")
        app_secret = (config or {}).get("app_secret", "")
        if not auth_code:
            return CapabilityExecutionResult.failed_result(
                "WeChat login request is missing required parameters",
                code="provider.invalid_config",
                field="auth_code",
            )
        if not app_id or not app_secret:
            return CapabilityExecutionResult.failed_result(
                "WeChat app_id or app_secret is missing",
                code="provider.invalid_config",
                field="app_id" if not app_id else "app_secret",
            )

        access_token_url = _get_config_value(config, "login_auth_access_token_url", WECHAT_ACCESS_TOKEN_URL)
        user_info_url = _get_config_value(config, "login_auth_user_info_url", WECHAT_USER_INFO_URL)

        try:
            token_response = requests.get(
                access_token_url,
                params={
                    "appid": app_id,
                    "secret": app_secret,
                    "code": auth_code,
                    "grant_type": "authorization_code",
                },
                timeout=WECHAT_TIMEOUT,
            )
            token_data = token_response.json()
        except requests.Timeout:
            return CapabilityExecutionResult.failed_result("WeChat login request timed out", code="provider.timeout", retryable=True)
        except (requests.RequestException, ValueError) as error:
            logger.debug(
                f"WeChat login token exchange failed: error_type={type(error).__name__}"
            )
            return CapabilityExecutionResult.failed_result("WeChat login request failed", code="provider.request_failed", retryable=True)

        if token_response.status_code != 200 or token_data.get("errcode"):
            return CapabilityExecutionResult.failed_result(
                token_data.get("errmsg") or "WeChat login failed",
                code="provider.auth_failed",
                external_code=str(token_data.get("errcode") or token_response.status_code),
            )

        access_token = token_data.get("access_token", "")
        openid = token_data.get("openid", "")
        if not access_token or not openid:
            return CapabilityExecutionResult.failed_result("WeChat login token is missing", code="provider.invalid_response")

        try:
            user_response = requests.get(
                user_info_url,
                params={
                    "access_token": access_token,
                    "openid": openid,
                    "lang": "zh_CN",
                },
                timeout=WECHAT_TIMEOUT,
            )
            user_data = user_response.json()
        except requests.Timeout:
            return CapabilityExecutionResult.failed_result("WeChat user info request timed out", code="provider.timeout", retryable=True)
        except (requests.RequestException, ValueError) as error:
            logger.debug(
                f"WeChat user info request failed: error_type={type(error).__name__}"
            )
            return CapabilityExecutionResult.failed_result("WeChat user info request failed", code="provider.request_failed", retryable=True)

        if user_response.status_code != 200 or user_data.get("errcode"):
            return CapabilityExecutionResult.failed_result(
                user_data.get("errmsg") or "WeChat user info fetch failed",
                code="provider.auth_failed",
                external_code=str(user_data.get("errcode") or user_response.status_code),
            )

        # userinfo 200 + 无 errcode 时,openid 仍可能缺失(响应体畸形),
        # 与 token 缺字段时返回 failed_result 保持一致,避免 KeyError 抛出。
        userinfo_openid = user_data.get("openid") or openid
        if not userinfo_openid:
            return CapabilityExecutionResult.failed_result(
                "WeChat user info is missing openid", code="provider.invalid_response"
            )

        # WeChat provider 只负责 OAuth 认证并返回真实微信用户信息;
        # 账号匹配、用户创建、token 签发由通用登录认证链路负责。
        return CapabilityExecutionResult.success_result(
            "WeChat login authenticated",
            payload={
                "external_user": {
                    "openid": userinfo_openid,
                    "unionid": user_data.get("unionid", ""),
                    "nickname": user_data.get("nickname", ""),
                    "headimgurl": user_data.get("headimgurl", ""),
                }
            },
        )
