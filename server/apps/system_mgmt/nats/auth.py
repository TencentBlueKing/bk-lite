# flake8: noqa
from .common import *  # noqa: F401,F403
from .common import _collect_ancestor_group_ids, _verify_token


def build_user_authorization_context(user):
    """Build the current authorization context without relying on a login token cache."""
    all_role_ids = get_user_all_roles(user)
    role_list = Role.objects.filter(id__in=all_role_ids)
    role_names = [f"{role.app}--{role.name}" if role.app else role.name for role in role_list]
    is_superuser = "admin" in role_names or "system-manager--admin" in role_names

    if is_superuser:
        queryset = list(Group.objects.prefetch_related("roles").all().order_by("id"))
        groups = [{"id": group.id, "name": group.name, "parent_id": group.parent_id} for group in queryset]
    else:
        visible_ids = _collect_ancestor_group_ids(user.group_list)
        queryset = list(
            Group.objects.prefetch_related("roles").filter(id__in=visible_ids).order_by("id")
        )
        direct_group_ids = set(user.group_list)
        groups = [
            {"id": group.id, "name": group.name, "parent_id": group.parent_id}
            for group in queryset
            if group.id in direct_group_ids
        ]

    group_tree = GroupUtils.build_group_tree(queryset, is_superuser, [group["id"] for group in groups])
    permissions = {}
    if not is_superuser:
        menu_ids = {
            menu_id
            for menu_list in role_list.values_list("menu_list", flat=True)
            for menu_id in menu_list
        }
        for app, name in Menu.objects.filter(id__in=menu_ids).values_list("app", "name"):
            permissions.setdefault(app, []).append(name)

    return {
        "username": user.username,
        "display_name": user.display_name,
        "domain": user.domain,
        "email": user.email,
        "is_superuser": is_superuser,
        "group_list": groups,
        "group_tree": group_tree,
        "roles": role_names,
        "role_ids": all_role_ids,
        "locale": user.locale,
        "permission": permissions,
        "timezone": user.timezone,
    }


@nats_client.register
def get_pilot_permission_by_token(token, bot_id, group_list):
    try:
        user = _verify_token(token)
    except Exception:
        return {"result": False}

    # 获取用户所有角色（个人角色 + 组角色）
    all_role_ids = get_user_all_roles(user)
    role_list = Role.objects.filter(id__in=all_role_ids)
    role_names = {f"{role.app}--{role.name}" if role.app else role.name for role in role_list}
    if {"admin", "system-manager--admin", "opspilot--admin"}.intersection(role_names):
        return {"result": True, "data": {"username": user.username}}
    real_groups = set(group_list).intersection(user.group_list)
    if not real_groups:
        return {"result": False}
    rules = UserRule.objects.filter(
        username=user.username,
        domain=user.domain,
        group_rule__app="opspilot",
        group_rule__group_id__in=list(real_groups),
    )
    if not rules:
        return {"result": True, "data": {"username": user.username}}
    for i in rules:
        rule_obj = i.group_rule.rules.get("bot")
        if rule_obj is None:
            return {"result": True, "data": {"username": user.username}}
        bot_ids = [u["id"] for u in rule_obj]
        if bot_id in bot_ids or 0 in bot_ids:
            return {"result": True, "data": {"username": user.username}}
    return {"result": False}


@nats_client.register
def verify_token(token):
    if not token:
        return {"result": False, "message": "Token is missing"}

    try:
        user = _verify_token(token)
    except Exception as e:
        error_message = str(e)
        return_data = {"result": False, "message": error_message}
        if error_message == VERIFY_TOKEN_USER_NOT_FOUND_MESSAGE:
            return_data["error_code"] = VERIFY_TOKEN_USER_NOT_FOUND_CODE
        return return_data

    # 命中缓存直接返回，跳过全量数据库查询
    cached = get_cached_token_info(user.username, user.domain)
    if cached is not None:
        return cached

    result = {"result": True, "data": build_user_authorization_context(user)}
    set_cached_token_info(user.username, user.domain, result)
    return result


@nats_client.register
def revoke_token(token):
    """撤销 token：将 jti 加入黑名单并清除用户验证缓存。"""
    if not token:
        return {"result": False, "message": "Token is missing"}

    try:
        token = token.split("Basic ")[-1]
        secret_key = os.getenv("SECRET_KEY")
        algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        user_info = jwt.decode(token, key=secret_key, algorithms=[algorithm], options={"verify_exp": False})
    except Exception as e:
        return {"result": False, "message": f"Invalid token: {e}"}

    jti = user_info.get("jti")
    exp = user_info.get("exp")
    if not jti or not exp:
        return {"result": False, "message": "Token does not support revocation (missing jti/exp)"}

    blacklist_token(jti, exp)

    # Clear verify_token cache for this user
    user = User.objects.filter(id=user_info.get("user_id")).first()
    if user:
        clear_token_info_cache(user.username, user.domain)

    return {"result": True, "message": "Token revoked"}
