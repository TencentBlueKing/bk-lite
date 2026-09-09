from functools import reduce
from operator import or_

from django.db.models import Q

import nats_client
from apps.core.utils.team_utils import group_tree_allows_team
from apps.system_mgmt.models.channel import Channel
from apps.system_mgmt.models.im_notification_channel import IMNotificationChannel
from apps.system_mgmt.models.user import User
from apps.system_mgmt.utils.group_utils import GroupUtils


def _usage_team_ids(user_info):
    user_info = user_info or {}
    team = user_info.get("team")
    if team in (None, ""):
        return None
    try:
        current_team = int(team)
    except (TypeError, ValueError):
        return None
    if not group_tree_allows_team(user_info.get("group_tree"), current_team):
        return None
    if user_info.get("include_children"):
        return GroupUtils.get_group_with_descendants(current_team)
    return [current_team]


def _json_team_q(team_ids):
    queries = [Q(team__contains=[team_id]) | Q(team__contains=[str(team_id)]) for team_id in team_ids]
    return reduce(or_, queries) if queries else Q(pk__in=[])


def _user_group_q(team_ids):
    queries = [Q(group_list__contains=team_id) | Q(group_list__contains=[team_id]) for team_id in team_ids]
    return reduce(or_, queries) if queries else Q(pk__in=[])


@nats_client.register
def get_system_usage_statistics(user_info=None, **kwargs):
    """组织数、用户数、通知渠道数，以及已启用渠道 / 已配置渠道。

    组织数固定为「选中组织及其下级」数量，不跟随 include_children。
    用户数 / 渠道仍按选中组织上下文（并遵守 include_children）。

    普通 Channel 无独立启停字段，产品口径为「已配置即已启用」；
    即时通讯渠道按 IMNotificationChannel.enabled 计启用。
    """
    team_ids = _usage_team_ids(user_info)
    if team_ids is None:
        return {
            "result": True,
            "data": {
                "organization_count": 0,
                "user_count": 0,
                "channel_count": 0,
                "enabled_channel_count": 0,
                "enabled_channel_rate": 0,
            },
            "message": "",
        }

    current_team = int(user_info.get("team"))
    organization_count = GroupUtils.active_queryset(id__in=GroupUtils.get_group_with_descendants(current_team)).count()
    user_count = User.objects.filter(_user_group_q(team_ids)).distinct().count()
    team_q = _json_team_q(team_ids)
    channel_qs = Channel.objects.filter(team_q)
    im_qs = IMNotificationChannel.objects.filter(team_q)
    channel_count = channel_qs.count() + im_qs.count()
    # Channel 无 enabled：已配置 = 已启用；IM 才看 enabled
    enabled_channel_count = channel_qs.count() + im_qs.filter(enabled=True).count()
    return {
        "result": True,
        "data": {
            "organization_count": organization_count,
            "user_count": user_count,
            "channel_count": channel_count,
            "enabled_channel_count": enabled_channel_count,
            "enabled_channel_rate": round(enabled_channel_count / channel_count * 100, 1) if channel_count else 0,
        },
        "message": "",
    }
