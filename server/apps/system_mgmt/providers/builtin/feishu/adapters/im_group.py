import json
import time

import requests

from apps.system_mgmt.providers.log import logger
from apps.system_mgmt.providers.base import BaseIMGroupAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from .client import (
    FEISHU_APPLICATION_INFO_URL,
    FEISHU_BOT_INFO_URL,
    FEISHU_CHAT_MEMBERS_URL,
    FEISHU_CHAT_URL,
    FEISHU_CREATE_CHAT_URL,
    FEISHU_SEND_MESSAGE_URL,
    FEISHU_TIMEOUT,
    _fetch_tenant_access_token,
    _get_config_value,
    _is_retryable_http_status,
)

_FEISHU_IM_GROUP_SCOPE_REQUIREMENTS = {
    "application_self_manage": frozenset(
        {
            "admin:app.info:readonly",
            "application:application:self_manage",
        }
    ),
    "chat_create": frozenset({"im:chat:create"}),
    "chat_read": frozenset({"im:chat", "im:chat:read"}),
    "member_write": frozenset({"im:chat", "im:chat.members:write_only"}),
    "message_send": frozenset({"im:message", "im:message:send_as_bot"}),
    "operate_as_owner": frozenset({"im:chat:operate_as_owner"}),
}

def _validate_group_members(member_id_type: str, member_ids: list[str]):
    if member_id_type not in {"user_id", "open_id"}:
        return CapabilityExecutionResult.failed_result(
            "Feishu group member_id_type must be user_id or open_id",
            code="provider.invalid_config",
            field="member_id_type",
        )
    if len(member_ids) > 50:
        return CapabilityExecutionResult.failed_result(
            "Feishu group requests support at most 50 members per batch",
            code="provider.invalid_config",
            field="member_ids",
        )
    return None


def _extract_feishu_scope_names(scopes) -> set[str]:
    names = set()
    for scope in scopes or []:
        if isinstance(scope, str):
            name = scope
        elif isinstance(scope, dict):
            if "grant_status" in scope and str(scope.get("grant_status")).lower() not in {
                "1",
                "true",
                "granted",
            }:
                continue
            if scope.get("granted") is False:
                continue
            name = scope.get("scope_name") or scope.get("name") or scope.get("key")
        else:
            continue
        if name:
            names.add(str(name))
    return names


def _fetch_feishu_application_info(config: dict, tenant_access_token: str):
    try:
        response = requests.get(
            FEISHU_APPLICATION_INFO_URL,
            headers={"Authorization": f"Bearer {tenant_access_token}"},
            params={"lang": "zh_cn"},
            timeout=FEISHU_TIMEOUT,
        )
        data = response.json()
    except requests.Timeout:
        return None, "", CapabilityExecutionResult.failed_result(
            "Feishu application capability verification timed out",
            code="provider.timeout",
            retryable=True,
        )
    except ValueError:
        return None, "", CapabilityExecutionResult.failed_result(
            "Feishu application capability verification returned invalid JSON",
            code="provider.invalid_response",
        )
    except requests.RequestException:
        return None, "", CapabilityExecutionResult.failed_result(
            "Feishu application capability verification request failed",
            code="provider.request_failed",
            retryable=True,
        )

    request_id = response.headers.get("X-Tt-Logid", "")
    if not isinstance(data, dict):
        return None, request_id, CapabilityExecutionResult.failed_result(
            "Feishu application capability verification returned an invalid response",
            code="provider.invalid_response",
            external_request_id=request_id,
        )
    if response.status_code == 400 and str(data.get("code") or "") == "99992402":
        error = data.get("error") or {}
        field_violations = (
            error.get("field_violations") or []
            if isinstance(error, dict)
            else []
        )
        first_violation = (
            field_violations[0]
            if field_violations and isinstance(field_violations[0], dict)
            else {}
        )
        return None, request_id, CapabilityExecutionResult.failed_result(
            "Feishu application capability verification request contains an invalid field",
            code="provider.invalid_config",
            field=str(first_violation.get("field") or ""),
            external_code="99992402",
            external_request_id=request_id,
        )
    if str(data.get("code") or "") == "99991672":
        return {"scopes": None}, request_id, None
    if response.status_code != 200 or data.get("code") not in (0, None):
        if _is_retryable_http_status(response.status_code):
            return None, request_id, CapabilityExecutionResult.failed_result(
                "Feishu application capability verification request failed",
                code="provider.request_failed",
                retryable=True,
                external_code=str(data.get("code") or response.status_code),
                external_request_id=request_id,
            )
        if response.status_code == 401:
            return None, request_id, CapabilityExecutionResult.failed_result(
                "Feishu application capability verification authentication failed",
                code="provider.auth_failed",
                external_code=str(data.get("code") or response.status_code),
                external_request_id=request_id,
            )
        if response.status_code != 403:
            return None, request_id, CapabilityExecutionResult.failed_result(
                "Feishu application capability verification returned an invalid response",
                code="provider.invalid_response",
                external_code=str(data.get("code") or response.status_code),
                external_request_id=request_id,
            )
        return None, request_id, CapabilityExecutionResult.failed_result(
            "Feishu application information permission is required to verify IM group capabilities",
            code="provider.permission_unverified",
            external_code=str(data.get("code") or response.status_code),
            external_request_id=request_id,
            payload={
                "missing_requirements": ["application_self_manage"],
                "external_request_id": request_id,
            },
        )
    application_data = data.get("data") or {}
    if not isinstance(application_data, dict):
        return None, request_id, CapabilityExecutionResult.failed_result(
            "Feishu application capability verification returned an invalid response",
            code="provider.invalid_response",
            external_request_id=request_id,
        )
    application = application_data.get("app") or {}
    if not isinstance(application, dict):
        return None, request_id, CapabilityExecutionResult.failed_result(
            "Feishu application capability verification returned an invalid response",
            code="provider.invalid_response",
            external_request_id=request_id,
        )
    return application, request_id, None


def _missing_feishu_im_group_scope_requirements(scopes) -> list[str]:
    granted_scopes = _extract_feishu_scope_names(scopes)
    return [
        requirement
        for requirement, accepted_scopes in _FEISHU_IM_GROUP_SCOPE_REQUIREMENTS.items()
        if granted_scopes.isdisjoint(accepted_scopes)
    ]


def _fetch_feishu_bot_info(config: dict, tenant_access_token: str):
    try:
        response = requests.get(
            FEISHU_BOT_INFO_URL,
            headers={"Authorization": f"Bearer {tenant_access_token}"},
            timeout=FEISHU_TIMEOUT,
        )
        data = response.json()
    except requests.Timeout:
        return None, "", CapabilityExecutionResult.failed_result(
            "Feishu bot capability verification timed out",
            code="provider.timeout",
            retryable=True,
        )
    except ValueError:
        return None, "", CapabilityExecutionResult.failed_result(
            "Feishu bot capability verification returned invalid JSON",
            code="provider.invalid_response",
        )
    except requests.RequestException:
        return None, "", CapabilityExecutionResult.failed_result(
            "Feishu bot capability verification request failed",
            code="provider.request_failed",
            retryable=True,
        )

    request_id = response.headers.get("X-Tt-Logid", "")
    if not isinstance(data, dict):
        return None, request_id, CapabilityExecutionResult.failed_result(
            "Feishu bot capability verification returned an invalid response",
            code="provider.invalid_response",
            external_request_id=request_id,
        )
    if response.status_code != 200 or data.get("code") not in (0, None):
        if _is_retryable_http_status(response.status_code):
            return None, request_id, CapabilityExecutionResult.failed_result(
                "Feishu bot capability verification request failed",
                code="provider.request_failed",
                retryable=True,
                external_code=str(data.get("code") or response.status_code),
                external_request_id=request_id,
            )
        if response.status_code in {401, 403}:
            return None, request_id, CapabilityExecutionResult.failed_result(
                "Feishu bot capability verification authentication failed",
                code="provider.auth_failed",
                external_code=str(data.get("code") or response.status_code),
                external_request_id=request_id,
            )
        return None, request_id, CapabilityExecutionResult.failed_result(
            "Feishu bot capability verification returned an invalid response",
            code="provider.invalid_response",
            external_code=str(data.get("code") or response.status_code),
            external_request_id=request_id,
        )
    bot = data.get("bot") or {}
    if not isinstance(bot, dict):
        return None, request_id, CapabilityExecutionResult.failed_result(
            "Feishu bot capability verification returned an invalid response",
            code="provider.invalid_response",
            external_request_id=request_id,
        )
    return bot, request_id, None


def _log_feishu_group_request(
    *,
    operation: str,
    started_at: float,
    result: CapabilityExecutionResult,
    request_id: str,
    member_count: int,
):
    error_code = result.errors[0].code if result.errors else "ok"
    outcome = (
        "partial"
        if result.partial_success
        else ("success" if result.success else "failed")
    )
    retryable = bool(
        result.retryable or any(error.retryable for error in result.errors)
    )
    duration_ms = max(0, round((time.monotonic() - started_at) * 1000))
    log = logger.info if result.success else logger.warning
    safe_request_id = _sanitize_external_log_value(request_id)
    try:
        log(
            "feishu im group provider request "
            "stage=group_request operation=%s result=%s error_code=%s "
            "request_id=%s member_count=%s duration_ms=%s retryable=%s",
            operation,
            outcome,
            error_code,
            safe_request_id,
            member_count,
            duration_ms,
            retryable,
            extra={
                "event": "feishu_im_group_provider_request",
                "operation": operation,
                "duration_ms": duration_ms,
                "result": outcome,
                "error_code": error_code,
                "request_id": safe_request_id,
                "member_count": member_count,
                "retryable": retryable,
            },
        )
    except Exception:
        # 可观测性不得改变外部能力调用的业务结果。
        pass


def _sanitize_external_log_value(value, *, max_length=200):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")[:max_length]
    )


def _execute_feishu_group_request(
    *,
    config: dict,
    operation: str,
    method: str,
    url: str,
    params: dict,
    payload: dict | None,
    success_payload,
    member_count: int,
):
    started_at = time.monotonic()

    def finish(result, request_id=""):
        _log_feishu_group_request(
            operation=operation,
            started_at=started_at,
            result=result,
            request_id=request_id,
            member_count=member_count,
        )
        return result

    tenant_access_token, error = _fetch_tenant_access_token(config)
    if error:
        return finish(error)

    try:
        request_kwargs = {
            "headers": {
                "Authorization": f"Bearer {tenant_access_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            "params": params,
            "timeout": FEISHU_TIMEOUT,
        }
        if payload is not None:
            request_kwargs["json"] = payload
        request = requests.get if method == "get" else requests.post
        response = request(url, **request_kwargs)
        data = response.json()
    except requests.Timeout:
        return finish(
            CapabilityExecutionResult.failed_result(
                "Feishu IM group request timed out",
                code="provider.timeout",
                retryable=True,
            )
        )
    except requests.RequestException:
        return finish(
            CapabilityExecutionResult.failed_result(
                "Feishu IM group request failed",
                code="provider.request_failed",
                retryable=True,
            )
        )
    except ValueError:
        return finish(
            CapabilityExecutionResult.failed_result(
                "Feishu IM group response returned invalid JSON",
                code="provider.invalid_response",
            )
        )

    request_id = response.headers.get("X-Tt-Logid", "")
    if response.status_code == 404:
        return finish(
            CapabilityExecutionResult.failed_result(
                (data or {}).get("msg") or "Feishu group was not found",
                code="provider.group_not_found",
                external_code=str((data or {}).get("code") or response.status_code),
                external_request_id=request_id,
            ),
            request_id,
        )
    if response.status_code in (401, 403):
        return finish(
            CapabilityExecutionResult.failed_result(
                (data or {}).get("msg") or "Feishu group request is unauthorized",
                code="provider.auth_failed",
                external_code=str((data or {}).get("code") or response.status_code),
                external_request_id=request_id,
            ),
            request_id,
        )
    if response.status_code == 429 or response.status_code >= 500:
        return finish(
            CapabilityExecutionResult.failed_result(
                (data or {}).get("msg") or "Feishu group request failed",
                code="provider.request_failed",
                retryable=True,
                external_code=str((data or {}).get("code") or response.status_code),
                external_request_id=request_id,
            ),
            request_id,
        )
    if response.status_code != 200 or (data or {}).get("code") not in (0, None):
        return finish(
            CapabilityExecutionResult.failed_result(
                (data or {}).get("msg") or "Feishu group request failed",
                code="provider.request_failed",
                external_code=str((data or {}).get("code") or response.status_code),
                external_request_id=request_id,
            ),
            request_id,
        )

    result = CapabilityExecutionResult.success_result(
        "Feishu IM group request succeeded",
        payload=success_payload(data or {}, request_id),
    )
    if (result.payload or {}).get("invalid_member_ids"):
        result.partial_success = True
    return finish(result, request_id)

class FeishuIMGroupAdapter(BaseIMGroupAdapter):
    capability_key = "im_group"

    @classmethod
    def get_constraints(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return CapabilityExecutionResult.success_result(
            "Feishu IM group constraints loaded",
            payload={
                "member_id_type": "open_id",
                "min_initial_members": 1,
                "max_initial_members": 50,
                "max_add_members": 50,
                "native_create_idempotency": True,
                "requirements": ["bot_enabled"],
            },
        )

    @classmethod
    def validate_create(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        member_ids = list(dict.fromkeys(kwargs.get("member_ids") or []))
        validation_error = _validate_group_members(
            kwargs.get("member_id_type"),
            member_ids,
        )
        if validation_error:
            return validation_error
        if (kwargs.get("owner_id") or "") not in member_ids:
            return CapabilityExecutionResult.failed_result(
                "Feishu group owner must be included in member_ids",
                code="provider.invalid_config",
                field="owner_id",
            )
        return CapabilityExecutionResult.success_result(
            "Feishu group create request is valid",
        )

    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        started_at = time.monotonic()

        def finish(result, request_id=""):
            _log_feishu_group_request(
                operation="test_connection",
                started_at=started_at,
                result=result,
                request_id=request_id,
                member_count=0,
            )
            return result

        tenant_access_token, token_error = _fetch_tenant_access_token(config)
        if token_error:
            return finish(token_error)

        application, request_id, application_error = _fetch_feishu_application_info(config, tenant_access_token)
        if application_error:
            return finish(application_error, request_id)

        permissions_verified = application.get("scopes") is not None
        missing_requirements = (
            _missing_feishu_im_group_scope_requirements(application.get("scopes"))
            if permissions_verified
            else []
        )
        if missing_requirements:
            return finish(
                CapabilityExecutionResult.failed_result(
                    "Feishu IM group permissions are not verified; "
                    "application information access is required for diagnostics; "
                    f"missing requirements: {', '.join(missing_requirements)}",
                    code="provider.permission_unverified",
                    external_request_id=request_id,
                    payload={
                        "missing_requirements": missing_requirements,
                        "external_request_id": request_id,
                    },
                ),
                request_id,
            )

        bot, request_id, bot_error = _fetch_feishu_bot_info(config, tenant_access_token)
        if bot_error:
            return finish(bot_error, request_id)
        if str(bot.get("activate_status") or "") != "2" or not bot.get("open_id"):
            return finish(
                CapabilityExecutionResult.failed_result(
                    "Feishu bot capability is not enabled for this tenant",
                    code="provider.bot_not_enabled",
                    external_request_id=request_id,
                    payload={
                        "missing_requirements": ["bot_enabled"],
                        "external_request_id": request_id,
                    },
                ),
                request_id,
            )

        payload = {"external_request_id": request_id}
        if not permissions_verified:
            payload["permissions_verified"] = False
        return finish(
            CapabilityExecutionResult.success_result(
                "Feishu IM group capability is ready",
                payload=payload,
            ),
            request_id,
        )

    @classmethod
    def create_group(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        member_id_type = kwargs["member_id_type"]
        member_ids = list(dict.fromkeys(kwargs.get("member_ids") or []))
        validation = cls.validate_create(
            config,
            provider_key,
            capability_key,
            member_id_type=member_id_type,
            member_ids=member_ids,
            owner_id=kwargs.get("owner_id"),
        )
        if not validation.success:
            _log_feishu_group_request(
                operation="create_group",
                started_at=time.monotonic(),
                result=validation,
                request_id="",
                member_count=len(member_ids),
            )
            return validation
        result = _execute_feishu_group_request(
            config=config,
            operation="create_group",
            method="post",
            url=_get_config_value(config, "im_group_create_chat_url", FEISHU_CREATE_CHAT_URL),
            params={"user_id_type": member_id_type},
            payload={
                "name": kwargs["group_name"],
                "owner_id": kwargs["owner_id"],
                "user_id_list": member_ids,
                "chat_mode": "group",
                "chat_type": "private",
                "set_bot_manager": True,
                "uuid": kwargs["idempotency_key"],
            },
            success_payload=lambda data, request_id: {
                "chat_id": str((data.get("data") or {}).get("chat_id") or ""),
                "invalid_member_ids": list(
                    (data.get("data") or {}).get("invalid_id_list") or []
                ),
                "external_request_id": request_id,
            },
            member_count=len(member_ids),
        )
        if result.success and result.payload["invalid_member_ids"]:
            result.partial_success = True
        return result

    @classmethod
    def get_group(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        chat_id = kwargs["chat_id"]
        return _execute_feishu_group_request(
            config=config,
            operation="get_group",
            method="get",
            url=_get_config_value(config, "im_group_chat_url", FEISHU_CHAT_URL).format(chat_id=chat_id),
            params={},
            payload=None,
            success_payload=lambda data, request_id: {
                "chat_id": str((data.get("data") or {}).get("chat_id") or chat_id),
                "external_request_id": request_id,
            },
            member_count=0,
        )

    @classmethod
    def add_members(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        member_id_type = kwargs["member_id_type"]
        member_ids = list(dict.fromkeys(kwargs.get("member_ids") or []))
        validation_error = _validate_group_members(member_id_type, member_ids)
        if validation_error:
            _log_feishu_group_request(
                operation="add_members",
                started_at=time.monotonic(),
                result=validation_error,
                request_id="",
                member_count=len(member_ids),
            )
            return validation_error
        result = _execute_feishu_group_request(
            config=config,
            operation="add_members",
            method="post",
            url=_get_config_value(config, "im_group_members_url", FEISHU_CHAT_MEMBERS_URL).format(chat_id=kwargs["chat_id"]),
            params={"member_id_type": member_id_type},
            payload={"id_list": member_ids},
            success_payload=lambda data, request_id: {
                "invalid_member_ids": list((data.get("data") or {}).get("invalid_id_list") or []),
                "external_request_id": request_id,
            },
            member_count=len(member_ids),
        )
        if result.success and result.payload["invalid_member_ids"]:
            result.partial_success = True
        return result

    @classmethod
    def send_group_message(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        chat_id = kwargs["chat_id"]
        return _execute_feishu_group_request(
            config=config,
            operation="send_group_message",
            method="post",
            url=_get_config_value(config, "im_group_send_message_url", FEISHU_SEND_MESSAGE_URL),
            params={"receive_id_type": "chat_id"},
            payload={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": kwargs["content"]}, ensure_ascii=False),
                "uuid": kwargs["idempotency_key"],
            },
            success_payload=lambda data, request_id: {
                "chat_id": str(chat_id),
                "external_request_id": request_id,
            },
            member_count=0,
        )
