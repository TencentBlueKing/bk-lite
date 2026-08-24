"""周期评估通知配置的授权候选数据。"""

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.user_group import normalize_user_group_ids
from apps.rpc.system_mgmt import SystemMgmt


def _build_actor_context(request) -> dict:
    current_team = get_current_team(request)
    if current_team in (None, ""):
        raise BaseAppException("缺少 current_team 参数")
    try:
        current_team = int(current_team)
    except (TypeError, ValueError) as exc:
        raise BaseAppException("current_team 参数非法") from exc

    return {
        "username": request.user.username,
        "domain": request.user.domain,
        "current_team": current_team,
        "include_children": request.COOKIES.get("include_children", "0") == "1",
        "is_superuser": request.user.is_superuser,
        "group_list": normalize_user_group_ids(getattr(request.user, "group_list", [])),
    }


def load_notification_candidates(request) -> dict:
    """返回调用方当前组织授权范围内的渠道与用户。"""
    actor_context = _build_actor_context(request)
    client = SystemMgmt()
    channels_result = client.search_channel_list_scoped(
        actor_context,
        teams=[actor_context["current_team"]],
        include_children=actor_context["include_children"],
    )
    users_result = client.get_group_users_scoped(
        actor_context,
        include_children=actor_context["include_children"],
    )
    return {
        "channels": channels_result.get("data") or [],
        "users": users_result.get("data") or [],
        "team_id": actor_context["current_team"],
    }
