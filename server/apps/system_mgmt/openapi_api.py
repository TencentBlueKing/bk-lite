"""ITSM 用户目录 / 组织目录统一 OpenAPI 网关端点。"""

from django.db.models import Q

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.openapi.decorators import openapi_expose
from apps.core.utils.current_team_scope import _normalize_organization_ids
from apps.system_mgmt.models import Group, Role
from apps.system_mgmt.models import User as SystemUser
from apps.system_mgmt.openapi_serializers import SystemMgmtGroupsQuerySerializer, SystemMgmtUsersQuerySerializer
from apps.system_mgmt.utils.group_utils import GroupUtils

_ORG_SCOPE = (
    "组织口径：系统令牌授权范围为单个 Acting-Team；不传 group_id 时从该组织查起；"
    "include_children 默认 false，为 true 时只加入执行身份有权访问的子组织。"
    "平台超管（内置 admin 或 system-manager 的 admin，含组织继承角色）不受该范围限制，"
    "不传 group_id 时返回全部活动组织与全部用户"
)
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


def _actor_is_platform_superuser(actor):
    """平台超管只认持久化角色，不接受请求参数声明。"""
    from apps.system_mgmt.nats.common import get_user_all_roles

    role_ids = get_user_all_roles(actor)
    if not role_ids:
        return False
    return Role.objects.filter(id__in=role_ids, name="admin").filter(Q(app="") | Q(app="system-manager")).exists()


def _active_group_ids():
    return list(GroupUtils.active_queryset().order_by("id").values_list("id", flat=True))


def _superuser_query_group_ids(group_id, include_children):
    if group_id is None:
        return _active_group_ids()
    if include_children:
        return sorted(int(gid) for gid in GroupUtils.get_group_with_descendants(group_id))
    return [int(group_id)]


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
    """按网关注入身份解析本次可查询的活动组织 id 集合。

    返回 (query_ids, error, superuser)。平台超管豁免组织范围：
    不传 group_id 时 query_ids 为全部活动组织；传了则按该组织（及子组织）查询，不再校验归属。
    """
    injected = _injected_team_ids(team)
    if group_id is not None and _group_unavailable(group_id):
        return None, _soft_error(_GROUP_UNAVAILABLE_MESSAGE), False

    actor = _load_actor(user_info)
    if actor is None:
        return None, _soft_error(_TEAM_OUT_OF_SCOPE_MESSAGE), False
    if _actor_is_platform_superuser(actor):
        return _superuser_query_group_ids(group_id, include_children), None, True

    if not injected:
        return None, _soft_error(_TEAM_OUT_OF_SCOPE_MESSAGE), False
    if group_id is None and len(injected) == 1 and _group_unavailable(injected[0]):
        return None, _soft_error(_GROUP_UNAVAILABLE_MESSAGE), False

    user_groups = _actor_group_ids(actor)
    allowed = _authorized_group_ids(user_groups, injected, include_children)
    query_root = group_id if group_id is not None else None
    if query_root is not None:
        if query_root not in allowed:
            return None, _soft_error(_TEAM_OUT_OF_SCOPE_MESSAGE), False
        query_ids = GroupUtils.get_user_authorized_child_groups(
            user_groups,
            query_root,
            include_children=bool(include_children),
        )
    else:
        query_ids = sorted(allowed)
    if not query_ids:
        return None, _soft_error(_TEAM_OUT_OF_SCOPE_MESSAGE), False
    return [int(group_pk) for group_pk in query_ids], None, False


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
        queryset = queryset.filter(Q(username__icontains=search) | Q(display_name__icontains=search) | Q(email__icontains=search))
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
    query_ids, error, superuser = _resolve_query_group_ids(
        team=team,
        user_info=user_info,
        group_id=group_id,
        include_children=include_children,
    )
    if error is not None:
        return error
    if superuser and group_id is None:
        queryset = SystemUser.objects.all()
    elif not query_ids:
        return _paginate([], page, page_size)
    else:
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
    visible_group_ids = _active_group_ids() if superuser else query_ids
    serialized = [_serialize_user(user, visible_group_ids) for user in users]
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
    query_ids, error, _ = _resolve_query_group_ids(
        team=team,
        user_info=user_info,
        group_id=group_id,
        include_children=include_children,
    )
    if error is not None:
        return error
    if not query_ids:
        return _paginate([], page, page_size)
    groups = list(GroupUtils.active_queryset(id__in=query_ids).only("id", "name", "parent_id", "is_virtual").order_by("id"))
    result_ids = {group.id for group in groups}
    serialized = [_serialize_group(group, result_ids) for group in groups]
    return _paginate(serialized, page, page_size)
