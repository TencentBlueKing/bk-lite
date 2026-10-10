"""ITSM 用户目录 / 组织目录统一 OpenAPI 网关端点。"""

from django.db.models import Q

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.openapi.decorators import openapi_expose
from apps.core.utils.current_team_scope import _normalize_organization_ids
from apps.system_mgmt.models import Group
from apps.system_mgmt.models import User as SystemUser
from apps.system_mgmt.openapi_serializers import (
    SystemMgmtGroupsQuerySerializer,
    SystemMgmtUsersQuerySerializer,
)
from apps.system_mgmt.utils.group_utils import GroupUtils

_ORG_SCOPE = "组织口径：系统令牌授权范围为单个 Acting-Team；不传 group_id 时从该组织查起；include_children 默认 false，为 true 时只加入执行身份有权访问的子组织"
_TEAM_OUT_OF_SCOPE_MESSAGE = "无权访问该组织"
_GROUP_UNAVAILABLE_MESSAGE = "指定组织不存在或已归档"


def _soft_error(message):
    return {"result": False, "message": message}


def _injected_team_ids(team):
    try:
        return sorted(_normalize_organization_ids(team or []))
    except BaseAppException:
        return []


def _load_actor(user_info):
    username = (user_info or {}).get("user")
    domain = (user_info or {}).get("domain") or "domain.com"
    if not username:
        return None
    return SystemUser.objects.filter(username=username, domain=domain).first()


def _group_unavailable(group_id):
    if group_id is None:
        return True
    group = Group.objects.filter(pk=group_id).first()
    return group is None or bool(group.is_delete)


def _actor_group_ids(actor):
    try:
        return list(_normalize_organization_ids(getattr(actor, "group_list", None) or []))
    except BaseAppException:
        return []


def _authorized_group_ids(user_groups, team_ids, include_children):
    allowed = set()
    for team_id in team_ids:
        allowed.update(
            GroupUtils.get_user_authorized_child_groups(
                user_groups,
                team_id,
                include_children=bool(include_children),
            )
        )
    return allowed


def _resolve_query_group_ids(*, team, user_info, group_id, include_children):
    """按网关注入身份解析本次可查询的活动组织 id 集合。越权/缺失返回软错误。"""
    injected = _injected_team_ids(team)
    if group_id is not None:
        if _group_unavailable(group_id):
            return None, _soft_error(_GROUP_UNAVAILABLE_MESSAGE)
    elif len(injected) == 1 and _group_unavailable(injected[0]):
        return None, _soft_error(_GROUP_UNAVAILABLE_MESSAGE)

    actor = _load_actor(user_info)
    if actor is None or not injected:
        return None, _soft_error(_TEAM_OUT_OF_SCOPE_MESSAGE)

    user_groups = _actor_group_ids(actor)
    allowed = _authorized_group_ids(user_groups, injected, include_children)
    query_root = group_id if group_id is not None else None
    if query_root is not None:
        if query_root not in allowed:
            return None, _soft_error(_TEAM_OUT_OF_SCOPE_MESSAGE)
        query_ids = GroupUtils.get_user_authorized_child_groups(
            user_groups,
            query_root,
            include_children=bool(include_children),
        )
    else:
        query_ids = sorted(allowed)
    if not query_ids:
        return None, _soft_error(_TEAM_OUT_OF_SCOPE_MESSAGE)
    return [int(group_pk) for group_pk in query_ids], None


def _users_in_groups_query(group_ids):
    query = Q()
    for group_id in group_ids:
        gid = int(group_id)
        query |= Q(group_list__contains=gid) | Q(group_list__contains=[gid])
    return query


def _paginate(items, page, page_size):
    count = len(items)
    start = (page - 1) * page_size
    return {
        "count": count,
        "page": page,
        "page_size": page_size,
        "results": items[start : start + page_size],
    }


def _text(value):
    return "" if value is None else str(value)


def _serialize_user(user, authorized_group_ids):
    allowed = set(authorized_group_ids)
    group_ids = []
    seen = set()
    for raw in user.group_list or []:
        try:
            gid = int(raw)
        except (TypeError, ValueError):
            continue
        if gid in allowed and gid not in seen:
            seen.add(gid)
            group_ids.append(gid)
    group_ids.sort()
    return {
        "id": str(user.id),
        "username": _text(user.username),
        "domain": _text(user.domain),
        "display_name": _text(user.display_name),
        "email": _text(user.email),
        "disabled": bool(user.disabled),
        "locale": _text(user.locale),
        "group_list": [str(gid) for gid in group_ids],
    }


def _serialize_group(group, result_ids):
    parent_id = group.parent_id
    if not parent_id or parent_id not in result_ids:
        serialized_parent = None
    else:
        serialized_parent = str(parent_id)
    return {
        "id": str(group.id),
        "name": group.name,
        "parent_id": serialized_parent,
        "is_virtual": bool(group.is_virtual),
    }


def _apply_user_selectors(queryset, *, user_id, username, usernames, search, disabled):
    if user_id not in (None, ""):
        queryset = queryset.filter(pk=int(user_id))
    elif username:
        queryset = queryset.filter(username=username)
    elif usernames:
        queryset = queryset.filter(username__in=list(usernames))
    elif search:
        queryset = queryset.filter(
            Q(username__icontains=search)
            | Q(display_name__icontains=search)
            | Q(email__icontains=search)
        )
    if disabled is not None:
        queryset = queryset.filter(disabled=bool(disabled))
    return queryset


@openapi_expose(
    path="system-mgmt/users",
    method="GET",
    schema=SystemMgmtUsersQuerySerializer,
    inject="team_list_with_user",
    permission="user_group-View",
    permission_app="system-manager",
    summary=f"分页查询用户目录（{_ORG_SCOPE}）",
)
def openapi_list_users(
    page=1,
    page_size=200,
    group_id=None,
    include_children=False,
    user_id="",
    username="",
    usernames=None,
    search="",
    disabled=None,
    *,
    team=None,
    user_info=None,
):
    query_ids, error = _resolve_query_group_ids(
        team=team,
        user_info=user_info,
        group_id=group_id,
        include_children=include_children,
    )
    if error is not None:
        return error
    queryset = SystemUser.objects.filter(_users_in_groups_query(query_ids))
    queryset = _apply_user_selectors(
        queryset,
        user_id=user_id,
        username=username,
        usernames=usernames,
        search=search,
        disabled=disabled,
    )
    users = list(
        queryset.only(
            "id",
            "username",
            "domain",
            "display_name",
            "email",
            "disabled",
            "locale",
            "group_list",
        )
        .order_by("id")
        .distinct()
    )
    serialized = [_serialize_user(user, query_ids) for user in users]
    return _paginate(serialized, page, page_size)


@openapi_expose(
    path="system-mgmt/groups",
    method="GET",
    schema=SystemMgmtGroupsQuerySerializer,
    inject="team_list_with_user",
    permission="user_group-View",
    permission_app="system-manager",
    summary=f"分页查询组织目录（{_ORG_SCOPE}）",
)
def openapi_list_groups(
    page=1,
    page_size=200,
    group_id=None,
    include_children=False,
    *,
    team=None,
    user_info=None,
):
    query_ids, error = _resolve_query_group_ids(
        team=team,
        user_info=user_info,
        group_id=group_id,
        include_children=include_children,
    )
    if error is not None:
        return error
    groups = list(
        GroupUtils.active_queryset(id__in=query_ids)
        .only("id", "name", "parent_id", "is_virtual")
        .order_by("id")
    )
    result_ids = {group.id for group in groups}
    serialized = [_serialize_group(group, result_ids) for group in groups]
    return _paginate(serialized, page, page_size)
