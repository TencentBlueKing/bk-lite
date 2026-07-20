from dataclasses import dataclass

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.permission_utils import permission_filter
from apps.core.utils.team_utils import get_current_team
from apps.rpc.system_mgmt import SystemMgmt


@dataclass(frozen=True)
class CurrentTeamDataScope:
    current_team: int
    data_team_ids: frozenset[int]
    include_children: bool
    username: str
    domain: str
    is_superuser: bool


def _get_actor_context(request):
    user = request.user
    return {
        "username": user.username,
        "domain": getattr(user, "domain", "domain.com"),
        "group_list": list(getattr(user, "group_list", []) or []),
        "is_superuser": bool(getattr(user, "is_superuser", False)),
    }


def _normalize_organization_ids(organization_ids):
    if isinstance(organization_ids, (str, bytes)):
        raise BaseAppException("organization_ids 参数非法")

    try:
        return frozenset(int(organization_id) for organization_id in organization_ids)
    except (TypeError, ValueError):
        raise BaseAppException("organization_ids 参数非法")


def _get_assignable_groups(actor_context):
    try:
        response = SystemMgmt().get_assignable_groups(actor_context)
    except Exception as error:
        raise BaseAppException("获取可分配组织失败") from error

    if not isinstance(response, dict) or not response.get("result") or not isinstance(response.get("data"), list):
        raise BaseAppException("获取可分配组织失败")

    return _normalize_organization_ids(response["data"])


def resolve_current_team_data_scope(request):
    current_team = get_current_team(request)
    if current_team in (None, ""):
        raise BaseAppException("缺少 current_team")

    try:
        current_team = int(current_team)
    except (TypeError, ValueError):
        raise BaseAppException("current_team 参数非法")

    actor_context = _get_actor_context(request)
    actor_context["current_team"] = current_team
    include_children = request.COOKIES.get("include_children", "0") == "1"

    try:
        response = SystemMgmt().get_authorized_groups_scoped(actor_context, include_children=include_children)
    except Exception as error:
        raise BaseAppException("获取 current_team 权限范围失败") from error

    if not isinstance(response, dict) or not response.get("result") or not isinstance(response.get("data"), list):
        raise BaseAppException("获取 current_team 权限范围失败")

    data_team_ids = _normalize_organization_ids(response["data"])
    if not data_team_ids or current_team not in data_team_ids:
        raise BaseAppException("current_team 不在授权范围内")

    return CurrentTeamDataScope(
        current_team=current_team,
        data_team_ids=data_team_ids,
        include_children=include_children,
        username=actor_context["username"],
        domain=actor_context["domain"],
        is_superuser=actor_context["is_superuser"],
    )


def scope_permission_queryset(model, permission, scope, *, team_key, id_key="id__in"):
    organization_qs = model.objects.filter(**{team_key: list(scope.data_team_ids)})
    permission_qs = permission_filter(model, permission, team_key=team_key, id_key=id_key)
    return organization_qs.filter(id__in=permission_qs.values("id")).distinct()


def resolve_assignable_organization_ids(request):
    return _get_assignable_groups(_get_actor_context(request))


def validate_assignable_organizations(request, organization_ids):
    requested_organization_ids = _normalize_organization_ids(organization_ids)
    assignable_organization_ids = resolve_assignable_organization_ids(request)
    if not requested_organization_ids.issubset(assignable_organization_ids):
        raise BaseAppException("organization_ids 包含无权分配的组织")
    return requested_organization_ids
