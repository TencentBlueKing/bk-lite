"""ITSM 用户目录、组织目录与通知渠道统一 OpenAPI 网关端点。"""

import uuid

from django.db.models import Q

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.openapi.decorators import openapi_expose
from apps.core.utils.current_team_scope import _normalize_organization_ids
from apps.system_mgmt.models import Group, Role
from apps.system_mgmt.models import User as SystemUser
from apps.system_mgmt.models.channel import Channel, ChannelChoices
from apps.system_mgmt.nats.channels import _channel_has_organization, _notification_channel_capabilities, dispatch_notification
from apps.system_mgmt.openapi_serializers import (
    NotificationChannelPageResponseSerializer,
    NotificationSendResponseSerializer,
    SystemMgmtGroupsQuerySerializer,
    SystemMgmtNotificationChannelQuerySerializer,
    SystemMgmtNotificationSendSerializer,
    SystemMgmtUsersQuerySerializer,
)
from apps.system_mgmt.utils.group_utils import GroupUtils

_ORG_SCOPE = (
    "组织口径：系统令牌授权范围为单个 Acting-Team；不传 group_id 时从该组织查起；"
    "include_children 默认 false，为 true 时只加入执行身份有权访问的子组织。"
    "平台超管（内置 admin 或 system-manager 的 admin，含组织继承角色）不受该范围限制，"
    "不传 group_id 时返回全部活动组织与全部用户"
)
_TEAM_OUT_OF_SCOPE_MESSAGE = "无权访问该组织"
_GROUP_UNAVAILABLE_MESSAGE = "指定组织不存在或已归档"
_CHANNEL_NOT_FOUND_MESSAGE = "通知渠道不存在。"
_CHANNEL_UNSUPPORTED_MESSAGE = "该通知渠道不支持外部投递。"
_RECIPIENT_OUT_OF_SCOPE_MESSAGE = "通知接收人不在授权组织内。"
_RECIPIENT_INVALID_MESSAGE = "通知接收人不符合渠道能力。"
_DELIVERY_FAILED_MESSAGE = "通知渠道投递失败。"
# 只放可对 ITSM 投递的渠道类型。NATS 会转到内部方法，实例增减也不在这里注册新路径。
_EXTERNAL_NOTIFICATION_CHANNEL_TYPES = frozenset(
    {
        ChannelChoices.EMAIL,
        ChannelChoices.ENTERPRISE_WECHAT,
        ChannelChoices.ENTERPRISE_WECHAT_BOT,
        ChannelChoices.FEISHU_BOT,
        ChannelChoices.DINGTALK_BOT,
        ChannelChoices.CUSTOM_WEBHOOK,
    }
)
_CHANNEL_CATALOG_SUMMARY = (
    "分页查询当前组织可外部投递的通知渠道。每条渠道的 send_parameters 说明投递接口要传的字段，"
    "渠道类型不同，标题是否生效、接收人怎么填会不一样。渠道实例以本接口实时返回为准，"
    "新增或停用渠道不新增、不删除网关路径。不返回连接配置。NATS 等内部通道不在此目录。" + _ORG_SCOPE
)
_TITLE_PARAMETER_DESCRIPTION = {
    ChannelChoices.EMAIL: "邮件主题。可以留空。",
    ChannelChoices.ENTERPRISE_WECHAT: "企微应用消息不使用标题，传空字符串即可。",
    ChannelChoices.ENTERPRISE_WECHAT_BOT: "企微机器人只发送正文，标题不会出现在消息里，传空字符串即可。",
    ChannelChoices.FEISHU_BOT: "飞书卡片标题。留空时渠道侧显示为「通知」。",
    ChannelChoices.DINGTALK_BOT: "钉钉 markdown 标题。留空时渠道侧显示为「通知」。",
    ChannelChoices.CUSTOM_WEBHOOK: "自定义 Webhook 不使用标题，传空字符串即可。",
}
_CONTENT_PARAMETER_DESCRIPTION = {
    ChannelChoices.EMAIL: "邮件正文。换行会保留。",
    ChannelChoices.ENTERPRISE_WECHAT: "企微应用文本消息正文。",
    ChannelChoices.ENTERPRISE_WECHAT_BOT: "企微机器人 markdown 正文。接收人名会追加在正文后面。",
    ChannelChoices.FEISHU_BOT: "飞书卡片 markdown 正文。接收人名会追加在正文后面。",
    ChannelChoices.DINGTALK_BOT: "钉钉 markdown 正文。接收人名会追加在正文后面。",
    ChannelChoices.CUSTOM_WEBHOOK: "通知正文，会替换该渠道模板中的 {{content}}。接收人名会追加在正文后面。",
}
_RECEIVER_PARAMETER_DESCRIPTION = {
    "system_user": "平台用户 ID 字符串，取自 GET /openapi/v1/system-mgmt/users 返回的 id，且必须属于当前组织。不要传用户名。1 到 100 个，不能重复。",
    "free_text": "渠道侧接收人名，原样附在消息里，不是平台用户 ID。1 到 100 个，每个最长 150 个字符，不能重复。",
}
_CHANNEL_SEND_SUMMARY = (
    "按通知渠道目录中的 channel_id 投递一条消息。"
    "recipient_mode=system_user 时 receivers 为用户目录中的用户 ID 字符串；"
    "recipient_mode=free_text 时 receivers 为渠道侧接收人名。不接受附件，不投递内部 NATS 通道。" + _ORG_SCOPE
)


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


def _platform_admin_role_ids():
    return set(Role.objects.filter(name="admin").filter(Q(app="") | Q(app="system-manager")).values_list("id", flat=True))


def _actor_is_platform_superuser(actor):
    """平台超管只认持久化角色，不接受请求参数声明。"""
    from apps.system_mgmt.nats.common import get_user_all_roles

    role_ids = get_user_all_roles(actor)
    if not role_ids:
        return False
    admin_role_ids = _platform_admin_role_ids()
    return bool(admin_role_ids.intersection(role_ids))


def _users_platform_superuser_flags(users):
    """与 _actor_is_platform_superuser 同一口径：个人角色 + 组织角色（含继承）。"""
    from apps.system_mgmt.nats.common import _collect_ancestor_group_ids

    flags = {user.id: False for user in users}
    admin_role_ids = _platform_admin_role_ids()
    if not admin_role_ids:
        return flags

    pending = []
    for user in users:
        if admin_role_ids.intersection(user.role_list or []):
            flags[user.id] = True
        else:
            pending.append(user)
    if not pending:
        return flags

    seed_ids = []
    for user in pending:
        for raw in user.group_list or []:
            try:
                seed_ids.append(int(raw))
            except (TypeError, ValueError):
                continue
    ancestor_ids = _collect_ancestor_group_ids(seed_ids) if seed_ids else set()
    groups = {group.id: group for group in GroupUtils.active_queryset(id__in=ancestor_ids).prefetch_related("roles")} if ancestor_ids else {}
    for user in pending:
        stack = []
        for raw in user.group_list or []:
            try:
                stack.append(int(raw))
            except (TypeError, ValueError):
                continue
        visited = set()
        group_role_ids = set()
        while stack:
            group_id = stack.pop()
            if group_id in visited:
                continue
            visited.add(group_id)
            group = groups.get(group_id)
            if not group:
                continue
            for role in group.roles.all():
                group_role_ids.add(role.id)
            parent_id = group.parent_id
            if parent_id:
                parent = groups.get(parent_id)
                if parent and parent.allow_inherit_roles:
                    stack.append(parent_id)
        flags[user.id] = bool(group_role_ids & admin_role_ids)
    return flags


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


def _serialize_user(user, authorized_group_ids, *, is_superuser=False):
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
        "is_superuser": bool(is_superuser),
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
            "role_list",
        )
        .order_by("id")
        .distinct()
    )
    visible_group_ids = _active_group_ids() if superuser else query_ids
    superuser_flags = _users_platform_superuser_flags(users)
    serialized = [_serialize_user(user, visible_group_ids, is_superuser=superuser_flags.get(user.id, False)) for user in users]
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


def _send_parameter(name, value_type, required, description):
    return {"name": name, "type": value_type, "required": required, "description": description}


def _notification_send_parameters(channel):
    capability = _notification_channel_capabilities(channel)
    return [
        _send_parameter("channel_id", "integer", True, f"固定填写 {channel.id}，对应渠道「{channel.name}」。"),
        _send_parameter("title", "string", False, _TITLE_PARAMETER_DESCRIPTION.get(channel.channel_type, "标题。可以留空。最长 512 个字符。")),
        _send_parameter("content", "string", True, _CONTENT_PARAMETER_DESCRIPTION.get(channel.channel_type, "通知正文，不能为空。最长 20000 个字符。")),
        _send_parameter(
            "receivers",
            "string[]",
            True,
            _RECEIVER_PARAMETER_DESCRIPTION.get(capability["recipient_mode"], "接收人列表。"),
        ),
    ]


def _openapi_notification_channel(channel):
    item = _notification_channel_capabilities(channel)
    item["send_parameters"] = _notification_send_parameters(channel)
    return item


def _external_notification_channels(query_ids):
    return [
        channel
        for channel in Channel.objects.order_by("id")
        if channel.channel_type in _EXTERNAL_NOTIFICATION_CHANNEL_TYPES and _channel_has_organization(channel, query_ids)
    ]


def _user_in_groups(user, query_ids):
    allowed = {int(group_id) for group_id in query_ids}
    for value in user.group_list or []:
        try:
            group_id = int(value.get("id") if isinstance(value, dict) else value)
        except (TypeError, ValueError, AttributeError):
            continue
        if group_id in allowed:
            return True
    return False


def _system_user_recipients_in_scope(receivers, query_ids):
    try:
        recipient_ids = [int(item) for item in receivers]
    except (TypeError, ValueError):
        return _soft_error(_RECIPIENT_INVALID_MESSAGE)
    if any(item <= 0 for item in recipient_ids):
        return _soft_error(_RECIPIENT_INVALID_MESSAGE)
    users = list(SystemUser.objects.filter(id__in=set(recipient_ids)).only("id", "group_list"))
    if len(users) != len(set(recipient_ids)) or any(not _user_in_groups(user, query_ids) for user in users):
        return _soft_error(_RECIPIENT_OUT_OF_SCOPE_MESSAGE)
    return None


@openapi_expose(
    path="system-mgmt/notification-channels",
    method="GET",
    schema=SystemMgmtNotificationChannelQuerySerializer,
    response_schema=NotificationChannelPageResponseSerializer,
    inject="team_list_with_user",
    permission="channel_list-View",
    permission_app="system-manager",
    summary=_CHANNEL_CATALOG_SUMMARY,
)
def openapi_list_notification_channels(
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
    serialized = [_openapi_notification_channel(channel) for channel in _external_notification_channels(query_ids)]
    return _paginate(serialized, page, page_size)


@openapi_expose(
    path="system-mgmt/notification-channels/send",
    method="POST",
    schema=SystemMgmtNotificationSendSerializer,
    response_schema=NotificationSendResponseSerializer,
    inject="team_list_with_user",
    permission="channel_list-Edit",
    permission_app="system-manager",
    summary=_CHANNEL_SEND_SUMMARY,
)
def openapi_send_notification(
    channel_id,
    content,
    receivers,
    title="",
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
    channel = Channel.objects.filter(id=channel_id).first()
    if channel is None or not query_ids:
        return _soft_error(_CHANNEL_NOT_FOUND_MESSAGE)
    in_scope = _channel_has_organization(channel, query_ids)
    if channel.channel_type not in _EXTERNAL_NOTIFICATION_CHANNEL_TYPES:
        if not in_scope:
            return _soft_error(_TEAM_OUT_OF_SCOPE_MESSAGE)
        return _soft_error(_CHANNEL_UNSUPPORTED_MESSAGE)
    if not in_scope:
        return _soft_error(_TEAM_OUT_OF_SCOPE_MESSAGE)
    capability = _notification_channel_capabilities(channel)
    if capability["recipient_mode"] == "system_user":
        recipient_error = _system_user_recipients_in_scope(receivers, query_ids)
        if recipient_error is not None:
            return recipient_error
    result = dispatch_notification(
        delivery_key=uuid.uuid4().hex,
        channel_id=channel.id,
        organization_ids=query_ids,
        recipients=list(receivers),
        title=title or "",
        body=content,
        event_payload={},
        producer="itsm",
    )
    if not isinstance(result, dict) or result.get("result") is not True or result.get("code") != "delivered":
        message = _DELIVERY_FAILED_MESSAGE
        if isinstance(result, dict) and result.get("message"):
            message = str(result["message"])
        return _soft_error(message)
    return {
        "channel_id": channel.id,
        "channel_type": channel.channel_type,
        "delivery_code": "delivered",
    }
