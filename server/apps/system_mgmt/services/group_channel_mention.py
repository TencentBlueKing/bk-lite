import re

from apps.system_mgmt.models import ChannelChoices
from apps.system_mgmt.models.im_account_association import IMAccountAssociationStatusChoices
from apps.system_mgmt.services.im_notification_service import _receive_ids_for_requested_users

GROUP_BOT_PROVIDER = {
    ChannelChoices.ENTERPRISE_WECHAT_BOT: "wecom",
    ChannelChoices.FEISHU_BOT: "feishu",
    ChannelChoices.DINGTALK_BOT: "dingtalk",
}
_MOBILE_RECEIVE_FIELDS = {"mobile", "phone"}
_UNSAFE_MENTION = re.compile(r"""[<>"'\s]""")


def provider_for_group_channel(channel_type: str) -> str | None:
    return GROUP_BOT_PROVIDER.get(channel_type)


def mentions_for_group_channel(channel, receivers):
    """返回可安全写入群消息的提及文本，以及钉钉 at 列表。

    未选择、结果不可用、未关联、冲突、禁用或标识无法安全写入时，对应用户不产生提及。
    """
    empty = ("", [], [])
    if not receivers or getattr(channel, "account_association_id", None) is None:
        return empty
    association = channel.account_association
    if association is None or association.status != IMAccountAssociationStatusChoices.READY:
        return empty
    requested = list(receivers) if isinstance(receivers, (list, tuple)) else [receivers]
    receive_ids, _skipped = _receive_ids_for_requested_users(association, requested)
    safe_ids = [item for item in receive_ids if not _UNSAFE_MENTION.search(item)]
    if not safe_ids:
        return empty
    if channel.channel_type == ChannelChoices.ENTERPRISE_WECHAT_BOT:
        return " ".join(f"<@{item}>" for item in safe_ids), [], []
    if channel.channel_type == ChannelChoices.FEISHU_BOT:
        return " ".join(f'<at id="{item}"></at>' for item in safe_ids), [], []
    if channel.channel_type == ChannelChoices.DINGTALK_BOT:
        if association.external_receive_field in _MOBILE_RECEIVE_FIELDS:
            return " ".join(f"@{item}" for item in safe_ids), [], safe_ids
        return "", safe_ids, []
    return empty
