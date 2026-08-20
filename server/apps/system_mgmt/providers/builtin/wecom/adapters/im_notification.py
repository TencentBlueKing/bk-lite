import requests

from apps.system_mgmt.providers.base import BaseIMNotificationAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from .client import (
    WECOM_DEFAULT_IM_NOTIFICATION_SEND_MESSAGE_URL,
    WECOM_DEFAULT_IM_NOTIFICATION_USERS_URL,
    WECOM_TIMEOUT,
    _fetch_all_users,
    _get_access_token,
    _parse_json_response,
    _resolve_proxies,
    _resolved_url,
    _validate_credentials,
)


class WeComIMNotificationAdapter(BaseIMNotificationAdapter):
    capability_key = "im_notification"

    @classmethod
    def _token(cls, config):
        error = _validate_credentials(config)
        if error:
            return None, error
        return _get_access_token(config)

    @classmethod
    def list_external_users(cls, config, provider_key, capability_key, **kwargs):
        token, error = cls._token(config)
        if error:
            return error
        users_url = _resolved_url(
            config, "im_notification_users_url", WECOM_DEFAULT_IM_NOTIFICATION_USERS_URL
        )
        normalized_users, user_error = _fetch_all_users(
            config,
            token,
            users_url,
            {"department_id": "1", "fetch_child": 1},
        )
        if user_error:
            return user_error
        external_users = [
            {key: item[key] for key in ("userid", "name", "email", "mobile")}
            for item in normalized_users
        ]
        return CapabilityExecutionResult.success_result(
            "WeCom IM users fetched",
            payload={"external_users": external_users},
        )

    @classmethod
    def send_message(cls, config, provider_key, capability_key, **kwargs):
        config = config or {}
        if not config.get("agent_id"):
            return CapabilityExecutionResult.failed_result(
                "WeCom AgentId is missing",
                code="provider.invalid_config",
                field="agent_id",
            )
        receive_ids = kwargs.get("receive_ids") or []
        if not receive_ids:
            return CapabilityExecutionResult.failed_result(
                "No IM receivers provided",
                code="provider.invalid_config",
                field="receive_ids",
            )
        token, error = cls._token(config)
        if error:
            return error
        sent_count = 0
        failures = []
        endpoint = _resolved_url(
            config, "im_notification_send_message_url", WECOM_DEFAULT_IM_NOTIFICATION_SEND_MESSAGE_URL
        )
        proxies = _resolve_proxies(config)
        message_text = f"{kwargs.get('title', '')}\n{kwargs.get('content', '')}".strip()
        for receive_id in receive_ids:
            post_kwargs = {
                "params": {"access_token": token},
                "json": {
                    "touser": receive_id,
                    "msgtype": "text",
                    "agentid": config["agent_id"],
                    "text": {"content": message_text},
                },
                "timeout": WECOM_TIMEOUT,
            }
            if proxies is not None:
                post_kwargs["proxies"] = proxies
            try:
                response = requests.post(endpoint, **post_kwargs)
                data = _parse_json_response(response)
                if response.status_code != 200 or data.get("errcode"):
                    failures.append({
                        "receive_id": receive_id,
                        "message": data.get("errmsg") or "WeCom message send failed",
                    })
                    continue
                sent_count += 1
            except requests.Timeout:
                failures.append({"receive_id": receive_id, "message": "WeCom message request timed out"})
            except (requests.RequestException, ValueError):
                failures.append({"receive_id": receive_id, "message": "WeCom message request failed"})
        if failures:
            return CapabilityExecutionResult(
                success=sent_count > 0,
                summary=f"WeCom IM message sent to {sent_count} users, {len(failures)} failed",
                partial_success=sent_count > 0,
                retryable=True,
                payload={"sent_count": sent_count, "failures": failures},
            )
        return CapabilityExecutionResult.success_result(
            "WeCom IM message sent",
            payload={"sent_count": sent_count},
        )

    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        config = config or {}
        if not config.get("agent_id"):
            return CapabilityExecutionResult.failed_result(
                "WeCom AgentId is missing",
                code="provider.invalid_config",
                field="agent_id",
            )
        _, error = cls._token(config)
        return error or CapabilityExecutionResult.success_result("WeCom IM notification capability is ready")
