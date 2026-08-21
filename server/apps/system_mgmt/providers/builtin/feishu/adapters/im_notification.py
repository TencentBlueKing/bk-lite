import json

import requests

from apps.system_mgmt.providers.base import BaseIMNotificationAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from .client import (
    FEISHU_DEFAULT_DEPARTMENT_ID_TYPE,
    FEISHU_DEFAULT_USER_ID_TYPE,
    FEISHU_SEND_MESSAGE_URL,
    FEISHU_TIMEOUT,
    _collect_visible_department_ids,
    _fetch_tenant_access_token,
    _get_config_value,
    _list_users_in_departments,
    _request_tenant_access_token,
)


class FeishuIMNotificationAdapter(BaseIMNotificationAdapter):
    capability_key = "im_notification"

    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return _request_tenant_access_token(config, capability_key)

    @classmethod
    def list_external_users(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        tenant_access_token, error = _fetch_tenant_access_token(config)
        if error:
            return error

        visible_departments, error = _collect_visible_department_ids(
            config, tenant_access_token, FEISHU_DEFAULT_DEPARTMENT_ID_TYPE
        )
        if error:
            return error

        users_payload, error = _list_users_in_departments(
            config,
            tenant_access_token,
            visible_departments["department_ids"],
            department_id_type=FEISHU_DEFAULT_DEPARTMENT_ID_TYPE,
            user_id_type=FEISHU_DEFAULT_USER_ID_TYPE,
        )
        if error:
            return error

        return CapabilityExecutionResult.success_result(
            "Feishu IM users fetched",
            payload={
                "external_users": users_payload["external_users"],
                "external_request_id": users_payload.get("external_request_id")
                or visible_departments.get("request_id")
                or "",
            },
        )

    @classmethod
    def send_message(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        tenant_access_token, error = _fetch_tenant_access_token(config)
        if error:
            return error

        receive_ids = kwargs.get("receive_ids") or []
        receive_id_type = kwargs.get("receive_id_type") or "user_id"
        title = kwargs.get("title", "")
        content = kwargs.get("content", "")
        if not receive_ids:
            return CapabilityExecutionResult.failed_result("No IM receivers provided", code="provider.invalid_config", field="receive_ids")

        failures = []
        sent_count = 0
        send_message_url = _get_config_value(config, "im_notification_send_message_url", FEISHU_SEND_MESSAGE_URL)
        for receive_id in receive_ids:
            message_text = f"{title}\n{content}".strip()
            payload = {
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": message_text}, ensure_ascii=False),
            }
            try:
                response = requests.post(
                    f"{send_message_url}?receive_id_type={receive_id_type}",
                    headers={
                        "Authorization": f"Bearer {tenant_access_token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    json=payload,
                    timeout=FEISHU_TIMEOUT,
                )
                data = response.json()
            except requests.Timeout:
                failures.append({"receive_id": receive_id, "message": "Feishu message request timed out"})
                continue
            except (requests.RequestException, ValueError) as request_error:
                failures.append({"receive_id": receive_id, "message": str(request_error)})
                continue

            if response.status_code != 200 or data.get("code") not in (0, None):
                failures.append({"receive_id": receive_id, "message": data.get("msg") or "Feishu message send failed"})
                continue
            sent_count += 1

        if failures:
            return CapabilityExecutionResult(
                success=sent_count > 0,
                summary=f"Feishu IM message sent to {sent_count} users, {len(failures)} failed",
                partial_success=sent_count > 0,
                retryable=True,
                payload={"sent_count": sent_count, "failures": failures},
            )
        return CapabilityExecutionResult.success_result("Feishu IM message sent", payload={"sent_count": sent_count})
