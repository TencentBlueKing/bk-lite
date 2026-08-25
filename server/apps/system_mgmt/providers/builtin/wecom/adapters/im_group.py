import hashlib

import requests
from wechatpy.enterprise import WeChatClient
from wechatpy.exceptions import WeChatClientException

from apps.system_mgmt.providers.base import BaseIMGroupAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from .client import (
    WECOM_GROUP_CREATE_CANDIDATE_PROBE_LIMIT,
    WECOM_GROUP_MEMBER_ISOLATION_CALL_LIMIT,
    WECOM_TIMEOUT,
    _validate_credentials,
)


def _wecom_group_validation(config, member_id_type=None, member_ids=None):
    error = _validate_credentials(config)
    if error:
        return error
    if not (config or {}).get("agent_id"):
        return CapabilityExecutionResult.failed_result(
            "WeCom AgentId is missing",
            code="provider.invalid_config",
            field="agent_id",
        )
    if member_id_type is not None and member_id_type != "userid":
        return CapabilityExecutionResult.failed_result(
            "WeCom group members must use userid",
            code="provider.invalid_config",
            field="member_id_type",
        )
    if member_ids is not None and not member_ids:
        return CapabilityExecutionResult.failed_result(
            "No WeCom group members provided",
            code="provider.invalid_config",
            field="member_ids",
        )
    return None


def _wecom_group_client(config):
    return WeChatClient(
        config["corp_id"],
        config["corp_secret"],
        timeout=WECOM_TIMEOUT,
    )


def _wecom_chat_member_ids(response):
    if not isinstance(response, dict):
        return []
    chat_info = response.get("chat_info") or {}
    if not isinstance(chat_info, dict):
        return []
    user_list = chat_info.get("userlist") or []
    if not isinstance(user_list, list):
        return []
    return list(dict.fromkeys(str(member_id or "").strip() for member_id in user_list if str(member_id or "").strip()))


def _wecom_group_failure(error):
    if isinstance(error, WeChatClientException):
        external_code = str(error.errcode)
        summary = "WeCom group request failed"
        if error.errcode in {40014, 40097, 41001, 42001}:
            code, retryable = "provider.auth_failed", False
        elif error.errcode in {45009, 45011}:
            code, retryable = "provider.rate_limited", True
        elif error.errcode == 60020:
            code, retryable = "provider.permission_denied", False
            summary = "当前 BK-Lite 服务出口 IP 未加入企业微信自建应用的企业可信 IP，" "请在企业微信管理后台配置后重试"
        elif error.errcode in {60011, 84061}:
            code, retryable = "provider.permission_denied", False
        elif error.errcode == 86001:
            code, retryable = "provider.chat_id_invalid", False
        elif error.errcode == 86004:
            code, retryable = "provider.group_name_invalid", False
        elif error.errcode == 86005:
            code, retryable = "provider.owner_invalid", False
        elif error.errcode == 86006:
            code, retryable = "provider.member_count_invalid", False
        elif error.errcode == 86007:
            code, retryable = "provider.member_invalid", False
        elif error.errcode == 86207:
            code, retryable = "provider.owner_not_member", False
        else:
            code, retryable = "provider.request_failed", False
        return CapabilityExecutionResult.failed_result(
            summary,
            code=code,
            retryable=retryable,
            external_code=external_code,
        )
    if isinstance(error, requests.Timeout):
        return CapabilityExecutionResult.failed_result(
            "WeCom group request timed out",
            code="provider.timeout",
            retryable=True,
        )
    return CapabilityExecutionResult.failed_result(
        "WeCom group request failed",
        code="provider.request_failed",
        retryable=isinstance(error, requests.RequestException),
    )


class WeComIMGroupAdapter(BaseIMGroupAdapter):
    capability_key = "im_group"

    @classmethod
    def get_constraints(cls, config, provider_key, capability_key, **kwargs):
        return CapabilityExecutionResult.success_result(
            "WeCom IM group constraints loaded",
            payload={
                "member_id_type": "userid",
                "min_initial_members": 2,
                "max_initial_members": 500,
                "max_add_members": 50,
                "native_create_idempotency": False,
                "deterministic_create_recovery": True,
                "requirements": ["internal_members", "root_department_visibility"],
            },
        )

    @classmethod
    def validate_create(cls, config, provider_key, capability_key, **kwargs):
        member_ids = list(dict.fromkeys(kwargs.get("member_ids") or []))
        error = _wecom_group_validation(
            config,
            kwargs.get("member_id_type"),
            member_ids,
        )
        if error:
            return error
        if len(member_ids) < 2:
            return CapabilityExecutionResult.failed_result(
                "企业微信应用群聊至少需要两名成员",
                code="provider.invalid_config",
                field="member_ids",
            )
        if len(member_ids) > 500:
            return CapabilityExecutionResult.failed_result(
                "企业微信应用群聊初始成员不能超过 500 人",
                code="provider.invalid_config",
                field="member_ids",
            )
        if (kwargs.get("owner_id") or "") not in member_ids:
            return CapabilityExecutionResult.failed_result(
                "企业微信群主必须包含在初始成员中",
                code="provider.invalid_config",
                field="owner_id",
            )
        return CapabilityExecutionResult.success_result(
            "WeCom group create request is valid",
        )

    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        error = _wecom_group_validation(config)
        if error:
            return error
        client = _wecom_group_client(config)
        try:
            client.fetch_access_token()
            application = client.agent.get(config["agent_id"])
        except (WeChatClientException, requests.RequestException) as exc:
            return _wecom_group_failure(exc)
        allowed_departments = (application.get("allow_partys") or {}).get("partyid") or []
        if 1 not in {int(department_id) for department_id in allowed_departments if str(department_id).isdigit()}:
            return CapabilityExecutionResult.failed_result(
                "WeCom application must be visible to the root department",
                code="provider.permission_unverified",
                payload={"missing_requirements": ["root_department_visibility"]},
            )
        return CapabilityExecutionResult.success_result(
            "WeCom IM group capability is ready",
        )

    @classmethod
    def create_group(cls, config, provider_key, capability_key, **kwargs):
        member_ids = list(dict.fromkeys(kwargs.get("member_ids") or []))
        validation = cls.validate_create(
            config,
            provider_key,
            capability_key,
            member_id_type=kwargs.get("member_id_type"),
            member_ids=member_ids,
            owner_id=kwargs.get("owner_id"),
        )
        if not validation.success:
            return validation
        owner_id = kwargs.get("owner_id") or ""
        chat_id = hashlib.sha256(str(kwargs["idempotency_key"]).encode("utf-8")).hexdigest()[:32]
        client = _wecom_group_client(config)
        try:
            existing = client.appchat.get(chat_id)
        except WeChatClientException as exc:
            # 当前企微环境会对格式合法但尚未创建的 appchat ID 返回 86001；
            # 仅在创建前预检阶段把 86001/86003 视为“不存在”。86008 表示该 ID
            # 属于其他应用，必须失败，不能继续用同一 ID 创建。
            if exc.errcode not in {86001, 86003}:
                return _wecom_group_failure(exc)
        except requests.RequestException as exc:
            return _wecom_group_failure(exc)
        else:
            existing_members = _wecom_chat_member_ids(existing)
            return CapabilityExecutionResult.success_result(
                "WeCom group already exists",
                payload={
                    "chat_id": chat_id,
                    # GET 返回的群成员是 ACK 丢失恢复时唯一可信的成员事实。
                    # 旧网关未返回 userlist 时只确认群主，其他人留给增员流程幂等补偿。
                    "joined_member_ids": existing_members or [owner_id],
                    "invalid_member_ids": [],
                    "reused": True,
                },
            )

        # appchat/create 是整批失败接口，单个无效 userid 会拖垮所有有效成员。
        # 先用“群主 + 一名候选人”建立最小可用群，失败时只跳过明确的
        # 86007 无效候选人；群主、权限、群名等错误仍立即失败。
        invalid_member_ids = []
        candidates = [member_id for member_id in member_ids if member_id != owner_id]
        last_member_error = None
        for candidate_id in candidates[:WECOM_GROUP_CREATE_CANDIDATE_PROBE_LIMIT]:
            initial_member_ids = [owner_id, candidate_id]
            try:
                client.appchat.create(
                    chat_id=chat_id,
                    name=kwargs["group_name"],
                    owner=owner_id,
                    user_list=initial_member_ids,
                )
            except WeChatClientException as exc:
                if exc.errcode == 86007:
                    invalid_member_ids.append(candidate_id)
                    last_member_error = exc
                    continue
                return _wecom_group_failure(exc)
            except requests.RequestException as exc:
                return _wecom_group_failure(exc)
            return CapabilityExecutionResult(
                success=True,
                partial_success=bool(invalid_member_ids or len(member_ids) > 2),
                summary="WeCom group created",
                payload={
                    "chat_id": chat_id,
                    "joined_member_ids": initial_member_ids,
                    "invalid_member_ids": invalid_member_ids,
                    "reused": False,
                },
            )
        return _wecom_group_failure(last_member_error or WeChatClientException(86006, "insufficient valid members"))

    @classmethod
    def get_group(cls, config, provider_key, capability_key, **kwargs):
        error = _wecom_group_validation(config)
        if error:
            return error
        chat_id = kwargs["chat_id"]
        try:
            _wecom_group_client(config).appchat.get(chat_id)
        except WeChatClientException as exc:
            if exc.errcode in {86001, 86003, 86008}:
                return CapabilityExecutionResult.failed_result(
                    "WeCom group was not found",
                    code="provider.group_not_found",
                    external_code=str(exc.errcode),
                )
            return _wecom_group_failure(exc)
        except requests.RequestException as exc:
            return _wecom_group_failure(exc)
        return CapabilityExecutionResult.success_result(
            "WeCom group loaded",
            payload={"chat_id": chat_id},
        )

    @classmethod
    def add_members(cls, config, provider_key, capability_key, **kwargs):
        member_ids = list(dict.fromkeys(kwargs.get("member_ids") or []))
        error = _wecom_group_validation(
            config,
            kwargs.get("member_id_type"),
            member_ids,
        )
        if error:
            return error
        if len(member_ids) > 50:
            return CapabilityExecutionResult.failed_result(
                "企业微信应用群聊单次增员不能超过 50 人",
                code="provider.invalid_config",
                field="member_ids",
            )
        client = _wecom_group_client(config)
        try:
            existing = client.appchat.get(kwargs["chat_id"])
        except WeChatClientException as exc:
            if exc.errcode in {86001, 86003, 86008}:
                return CapabilityExecutionResult.failed_result(
                    "WeCom group was not found",
                    code="provider.group_not_found",
                    external_code=str(exc.errcode),
                )
            return _wecom_group_failure(exc)
        except requests.RequestException as exc:
            return _wecom_group_failure(exc)
        existing_member_ids = set(_wecom_chat_member_ids(existing))
        joined_member_ids = [member_id for member_id in member_ids if member_id in existing_member_ids]
        member_ids_to_add = [member_id for member_id in member_ids if member_id not in existing_member_ids]
        invalid_member_ids = []
        terminal_failure = None
        # The preflight GET is part of the same bounded provider-call budget.
        external_call_count = 1

        def add_batch(batch):
            nonlocal external_call_count, terminal_failure
            if not batch or terminal_failure is not None:
                return
            if external_call_count >= WECOM_GROUP_MEMBER_ISOLATION_CALL_LIMIT:
                terminal_failure = CapabilityExecutionResult.failed_result(
                    "WeCom invalid member isolation call budget exhausted",
                    code="provider.member_invalid",
                    external_code="86007",
                )
                return
            external_call_count += 1
            try:
                client.appchat.update(
                    kwargs["chat_id"],
                    add_user_list=batch,
                )
            except WeChatClientException as exc:
                if exc.errcode != 86007:
                    terminal_failure = _wecom_group_failure(exc)
                    return
                if len(batch) == 1:
                    invalid_member_ids.extend(batch)
                    return
                midpoint = len(batch) // 2
                add_batch(batch[:midpoint])
                add_batch(batch[midpoint:])
            except requests.RequestException as exc:
                terminal_failure = _wecom_group_failure(exc)
            else:
                joined_member_ids.extend(batch)

        add_batch(member_ids_to_add)
        if terminal_failure is not None and not joined_member_ids and not invalid_member_ids:
            return terminal_failure

        failed_member_ids = [member_id for member_id in member_ids if member_id not in joined_member_ids and member_id not in invalid_member_ids]
        payload = {
            "joined_member_ids": joined_member_ids,
            "invalid_member_ids": invalid_member_ids,
            "failed_member_ids": failed_member_ids,
        }
        if terminal_failure is not None and terminal_failure.retryable:
            return CapabilityExecutionResult(
                success=False,
                partial_success=bool(joined_member_ids or invalid_member_ids),
                retryable=True,
                summary=terminal_failure.summary,
                payload=payload,
                errors=terminal_failure.errors,
            )
        return CapabilityExecutionResult(
            success=True,
            partial_success=bool(invalid_member_ids or failed_member_ids),
            summary=("WeCom group members partially added" if invalid_member_ids or failed_member_ids else "WeCom group members added"),
            payload=payload,
            errors=(terminal_failure.errors if terminal_failure is not None else []),
        )

    @classmethod
    def send_group_message(cls, config, provider_key, capability_key, **kwargs):
        error = _wecom_group_validation(config)
        if error:
            return error
        try:
            _wecom_group_client(config).appchat.send_text(
                kwargs["chat_id"],
                kwargs["content"],
            )
        except (WeChatClientException, requests.RequestException) as exc:
            return _wecom_group_failure(exc)
        return CapabilityExecutionResult.success_result(
            "WeCom group message sent",
            payload={"chat_id": kwargs["chat_id"]},
        )
