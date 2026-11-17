"""智能机器人按已选账号关联反查平台用户。未选择时不改变现有执行身份。"""

from __future__ import annotations

from django.db.models import Q

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.services.skill_channel_service import resolve_ops_pilot_guest_id
from apps.system_mgmt.models import IMAccountAssociation, IMAccountAssociationStatusChoices, IMNotificationUserMapping
from apps.system_mgmt.services.im_notification_service import _conflict_user_ids

ASSOCIATION_CHANNEL_TYPES = frozenset(
    {
        SkillChannelChoices.ENTERPRISE_WECHAT,
        SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT,
        SkillChannelChoices.DINGTALK,
        SkillChannelChoices.FEISHU,
    }
)
PROVIDER_BY_CHANNEL = {
    SkillChannelChoices.ENTERPRISE_WECHAT: "wecom",
    SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT: "wecom",
    SkillChannelChoices.DINGTALK: "dingtalk",
    SkillChannelChoices.FEISHU: "feishu",
}
IDENTITY_KEYS_BY_CHANNEL = {
    SkillChannelChoices.ENTERPRISE_WECHAT: ("corp_id", "agent_id"),
    SkillChannelChoices.FEISHU: ("app_id",),
    SkillChannelChoices.DINGTALK: ("client_id",),
}
SENDER_FIELD_BY_CHANNEL = {
    SkillChannelChoices.ENTERPRISE_WECHAT: "userid",
    SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT: "userid",
    SkillChannelChoices.DINGTALK: "userid",
    SkillChannelChoices.FEISHU: "open_id",
}

SENDER_DENIED_TEXT = {
    "not_associated": "未找到对应的平台用户，未执行",
    "forbidden": "已找到平台用户，但不在可用组织内，无权限，未执行",
    "conflict": "该 IM 身份对应了多个平台用户，未执行",
    "disabled": "对应的平台用户已停用，未执行",
    "not_ready": "账号关联尚未可用，未执行",
}
SENDER_NOT_EXECUTABLE_LOG = "event=skill_channel_sender_not_executable channel_id=%s association_id=%s reason=%s"


def sender_denied_text(reason: str) -> str:
    return SENDER_DENIED_TEXT.get(reason) or SENDER_DENIED_TEXT["not_associated"]


class SkillChannelSenderDenied(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def log_sender_denied(channel, exc: SkillChannelSenderDenied) -> None:
    logger.info(
        SENDER_NOT_EXECUTABLE_LOG,
        getattr(channel, "id", 0) or 0,
        getattr(channel, "account_association_id", 0) or 0,
        exc.reason,
    )


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _instance_config(instance) -> dict:
    config = getattr(instance, "config", None) or {}
    return config if isinstance(config, dict) else {}


def association_matches_channel(channel_type: str, config: dict, association: IMAccountAssociation) -> bool:
    provider = PROVIDER_BY_CHANNEL.get(channel_type)
    instance = association.integration_instance
    if not provider or instance.provider_key != provider:
        return False
    keys = IDENTITY_KEYS_BY_CHANNEL.get(channel_type)
    if not keys:
        return True
    runtime = _instance_config(instance)
    source = config or {}
    for key in keys:
        left = _text(source.get(key))
        right = _text(runtime.get(key))
        if not left or not right or left != right:
            return False
    return True


def list_account_association_options(channel_type: str, identity: dict | None = None) -> list[dict]:
    provider = PROVIDER_BY_CHANNEL.get(channel_type)
    if not provider:
        return []
    identity = identity or {}
    keys = IDENTITY_KEYS_BY_CHANNEL.get(channel_type, ())
    if keys and any(not _text(identity.get(key)) for key in keys):
        return []
    rows = (
        IMAccountAssociation.objects.select_related("integration_instance").filter(integration_instance__provider_key=provider).order_by("name", "id")
    )
    matched = []
    for association in rows:
        if not association_matches_channel(channel_type, identity, association):
            continue
        instance = association.integration_instance
        matched.append(
            {
                "id": association.id,
                "name": association.name,
                "integration_instance_id": instance.id,
                "integration_instance_name": instance.name,
            }
        )
    return matched


def _group_ids(group_list) -> set[int]:
    ids: set[int] = set()
    for group in group_list or []:
        raw = group.get("id") if isinstance(group, dict) else group
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    return ids


def _usage_ids(channel) -> set[int]:
    return _group_ids(getattr(channel, "usage_team", None) or [])


def identified_user_allowed(channel, user) -> bool:
    """识别成功后按渠道使用组织判断。不走 IM 渠道的组织校验短路。"""
    allowed = _usage_ids(channel)
    if not allowed:
        return False
    group_ids = _group_ids(getattr(user, "group_list", None))
    if group_ids & allowed:
        return True
    guest_id = resolve_ops_pilot_guest_id(getattr(user, "group_list", None))
    return guest_id is not None and guest_id in allowed


def resolve_skill_channel_actor(channel, sender_value: str):
    """返回平台用户。未选择账号关联时返回 None，调用方保持原执行身份。"""
    association_id = getattr(channel, "account_association_id", None)
    if not association_id or getattr(channel, "channel_type", "") not in ASSOCIATION_CHANNEL_TYPES:
        return None
    association = IMAccountAssociation.objects.select_related("integration_instance").filter(pk=association_id).first()
    if association is None or association.status != IMAccountAssociationStatusChoices.READY:
        raise SkillChannelSenderDenied("not_ready")
    field = SENDER_FIELD_BY_CHANNEL.get(channel.channel_type)
    value = _text(sender_value)
    if not field or not value:
        raise SkillChannelSenderDenied("not_associated")
    mappings = list(
        IMNotificationUserMapping.objects.select_related("user").filter(
            Q(account_association_id=association.id),
            Q(external_snapshot__contains={field: value}) | Q(external_identity_key=field, external_identity_value=value),
        )
    )
    users = []
    seen = set()
    for mapping in mappings:
        if mapping.user_id in seen:
            continue
        seen.add(mapping.user_id)
        users.append(mapping.user)
    if len(users) != 1:
        raise SkillChannelSenderDenied("conflict" if len(users) > 1 else "not_associated")
    user = users[0]
    if user.id in _conflict_user_ids(association):
        raise SkillChannelSenderDenied("conflict")
    if user.disabled:
        raise SkillChannelSenderDenied("disabled")
    if not identified_user_allowed(channel, user):
        raise SkillChannelSenderDenied("forbidden")
    return user
