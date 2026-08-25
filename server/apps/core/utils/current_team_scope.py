import re
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
        organization_ids = list(organization_ids)
    except (TypeError, ValueError):
        raise BaseAppException("organization_ids 参数非法")

    normalized_ids = set()
    for organization_id in organization_ids:
        if type(organization_id) is int and organization_id > 0:
            normalized_ids.add(organization_id)
            continue
        if type(organization_id) is str and re.fullmatch(r"[1-9][0-9]*", organization_id):
            normalized_ids.add(int(organization_id))
            continue
        raise BaseAppException("organization_ids 参数非法")

    if not normalized_ids:
        raise BaseAppException("organization_ids 参数不能为空")

    return frozenset(normalized_ids)


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
        current_team = next(iter(_normalize_organization_ids([current_team])))
    except BaseAppException:
        raise BaseAppException("current_team 参数非法")

    from apps.system_mgmt.utils.group_utils import GroupUtils

    if not GroupUtils.active_queryset(id=current_team).exists():
        raise BaseAppException("current_team 对应组织已归档或不存在")

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


def actor_context_to_wire(actor_context: dict | None) -> dict | None:
    """跨模块 RPC 用：去掉 request / CurrentTeamDataScope，只留可 JSON 字段。"""
    if not isinstance(actor_context, dict):
        return None

    scope = actor_context.get("data_scope")
    if isinstance(scope, CurrentTeamDataScope):
        return {
            "username": scope.username,
            "domain": scope.domain,
            "current_team": int(scope.current_team),
            "include_children": bool(scope.include_children),
            "is_superuser": bool(scope.is_superuser),
            "group_list": list(actor_context.get("group_list") or []),
            "data_team_ids": sorted(int(x) for x in scope.data_team_ids),
        }

    current_team = actor_context.get("current_team")
    raw_ids = actor_context.get("data_team_ids") or []
    if current_team in (None, "") and not raw_ids:
        return None
    try:
        team_ids = sorted(int(x) for x in raw_ids)
        team = int(current_team) if current_team not in (None, "") else (team_ids[0] if team_ids else None)
    except (TypeError, ValueError):
        return None
    if team is None or not team_ids:
        return None
    return {
        "username": str(actor_context.get("username") or ""),
        "domain": str(actor_context.get("domain") or "domain.com"),
        "current_team": team,
        "include_children": bool(actor_context.get("include_children", False)),
        "is_superuser": bool(actor_context.get("is_superuser", False)),
        "group_list": list(actor_context.get("group_list") or []),
        "data_team_ids": team_ids,
    }


def hydrate_actor_context_data_scope(actor_context: dict | None) -> CurrentTeamDataScope | None:
    """从进程内对象或 RPC wire 字段还原 CurrentTeamDataScope；成功则写回 actor_context。"""
    if not isinstance(actor_context, dict):
        return None

    scope = actor_context.get("data_scope")
    if isinstance(scope, CurrentTeamDataScope) and scope.data_team_ids:
        return scope

    raw_ids = actor_context.get("data_team_ids") or []
    current_team = actor_context.get("current_team")
    if current_team in (None, "") or not raw_ids:
        return None
    try:
        rebuilt = CurrentTeamDataScope(
            current_team=int(current_team),
            data_team_ids=frozenset(int(x) for x in raw_ids),
            include_children=bool(actor_context.get("include_children", False)),
            username=str(actor_context.get("username") or ""),
            domain=str(actor_context.get("domain") or "domain.com"),
            is_superuser=bool(actor_context.get("is_superuser", False)),
        )
    except (TypeError, ValueError):
        return None
    if not rebuilt.data_team_ids:
        return None
    actor_context["data_scope"] = rebuilt
    return rebuilt


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
