"""智能体渠道发布：组同步与准入。"""

from apps.opspilot.enum import SKILL_CHANNEL_SKIP_ORG_CHECK, SkillChannelChoices
from apps.opspilot.models import SkillChannel
from apps.opspilot.services.usage_team import merge_usage_team


def sync_skill_channel_usage_teams(skill) -> int:
    """将 Skill.usage_team 全量同步到其所有渠道绑定的组副本。返回更新条数。"""
    usage_team = list(skill.usage_team or [])
    return SkillChannel.objects.filter(skill_id=skill.id).exclude(usage_team=usage_team).update(usage_team=usage_team)


def copy_usage_team_for_channel(skill) -> list:
    """新建渠道绑定时拷贝当前 Skill.usage_team。"""
    return list(skill.usage_team or merge_usage_team(skill.team, []))


def channel_allows_team(channel: SkillChannel, team_id) -> bool:
    """组织是否可使用该渠道。IM 渠道跳过组织校验。"""
    if channel.channel_type in SKILL_CHANNEL_SKIP_ORG_CHECK:
        return True
    try:
        team_id = int(team_id)
    except (TypeError, ValueError):
        return False
    usage = channel.usage_team or []
    if team_id in usage:
        return True
    return False


def resolve_ops_pilot_guest_id(group_list) -> int | None:
    for group in group_list or []:
        if isinstance(group, dict) and group.get("name") == "OpsPilotGuest" and group.get("id") is not None:
            try:
                return int(group["id"])
            except (TypeError, ValueError):
                return None
    return None


def saas_channels_for_team(team_id, group_list=None, channel_types=None):
    """当前组织有权使用的已启用 SaaS 渠道（平台弹窗 / Web 对话）。含 Guest 特例。"""
    try:
        team_id = int(team_id)
    except (TypeError, ValueError):
        return SkillChannel.objects.none()

    types = set(channel_types or {SkillChannelChoices.PLATFORM})
    guest_id = resolve_ops_pilot_guest_id(group_list)
    allowed = {team_id}
    if guest_id is not None:
        allowed.add(guest_id)

    matched_ids = []
    for ch in SkillChannel.objects.filter(enabled=True, channel_type__in=types).only("id", "usage_team"):
        usage = ch.usage_team or []
        if any(t in usage for t in allowed):
            matched_ids.append(ch.id)
    return SkillChannel.objects.filter(id__in=matched_ids).select_related("skill")


def platform_channels_for_team(team_id, group_list=None):
    """当前组织有权使用的已启用平台渠道（含 Guest 特例）。"""
    return saas_channels_for_team(team_id, group_list, {SkillChannelChoices.PLATFORM})


def web_chat_channels_for_team(team_id, group_list=None):
    """当前组织有权使用的已启用 Web 对话渠道。"""
    return saas_channels_for_team(team_id, group_list, {SkillChannelChoices.WEB_CHAT})
