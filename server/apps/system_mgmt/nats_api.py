import os

from django.utils.translation import gettext_lazy as _

import nats_client
from apps.core.backends import cache, logger
from apps.system_mgmt.models import Channel, ChannelChoices, UserRule
from apps.system_mgmt.services.group_manage import GroupManage
from apps.system_mgmt.services.role_manage import RoleManage
from apps.system_mgmt.services.user_manage import UserManage
from apps.system_mgmt.utils.channel_utils import send_by_bot, send_email, send_wechat
from apps.system_mgmt.utils.keycloak_client import KeyCloakClient


@nats_client.register
def verify_token(token, client_id):
    if not token:
        return {"result": False, "message": _("Token is missing")}
    client = KeyCloakClient()
    is_active, user_info = client.token_is_valid(token)
    if not is_active:
        return {"result": False, "message": _("Token is invalid")}
    roles = user_info["realm_access"]["roles"]
    is_superuser = "admin" in roles or f"{client_id}_admin" in roles
    groups = cache.get(f"group_{user_info.get('username')}")
    if not groups:
        groups = client.get_user_groups(user_info.get("sub"), is_superuser)
        cache.set(f"group_{user_info.get('username')}", groups, 60)
    return {
        "result": True,
        "data": {
            "username": user_info["username"],
            "email": user_info.get("email", ""),
            "is_superuser": is_superuser,
            "group_list": groups,
            "roles": roles,
            "locale": user_info.get("locale", "en"),
        },
    }


@nats_client.register
def get_user_menus(client_id, roles, username, is_superuser):
    client = RoleManage()
    client_id = client_id
    menus = []
    if not is_superuser:
        policy_ids = client.get_policy_by_by_roles(client_id, roles)
        for i in policy_ids:
            menus.extend(client.role_menus(client_id, i))
        menus = list(set(menus))
    user_menus = client.get_all_menus(client_id, user_menus=menus, username=username, is_superuser=is_superuser)
    return {"result": True, "data": user_menus}


@nats_client.register
def get_client(client_id=""):
    client = KeyCloakClient()
    res = client.realm_client.get_clients()
    if client_id:
        filter_client = client_id.split(";")
    else:
        filter_client = [i["clientId"] for i in res]
    return {
        "result": True,
        "data": [
            {
                "id": i["id"],
                "name": i["name"],
                "client_id": i["clientId"],
                "description": i["description"],
                "url": i["baseUrl"],
            }
            for i in res
            if i["clientId"] in filter_client and i.get("authorizationServicesEnabled")
        ],
    }


@nats_client.register
def get_client_detail(client_id):
    client = KeyCloakClient()
    res = client.realm_client.get_client(client_id=client_id)
    return {"result": True, "data": res}


@nats_client.register
def get_group_users(group):
    client = KeyCloakClient()
    users = client.realm_client.get_group_members(group)
    return_data = [
        {"username": i["username"], "first_name": i.get("firstName", ""), "last_name": i.get("lastName", "")}
        for i in users
    ]
    return {"result": True, "data": return_data}


@nats_client.register
def get_all_users():
    client = UserManage()
    res = client.user_all()
    return {"result": True, "data": res}


@nats_client.register
def search_groups(query_params):
    _first, _max = UserManage.get_first_and_max(query_params)
    kwargs = {
        "first": _first,
        "max": _max,
        "search": query_params.get("search", ""),
    }
    client = GroupManage()
    if query_params.get("page"):
        res = client.group_list(kwargs)
    else:
        res = client.group_list(query_params)
    return {"result": True, "data": res}


@nats_client.register
def search_users(query_params):
    _first, _max = UserManage.get_first_and_max(query_params)
    kwargs = {
        "first": _first,
        "max": _max,
        "search": query_params.get("search", ""),
    }
    client = UserManage()
    if query_params.get("page"):
        res = client.user_list(kwargs)
    else:
        res = client.user_list(query_params)
    return {"result": True, "data": res}


@nats_client.register
def init_user_default_attributes(user_id, group_name, default_group_id):
    client = KeyCloakClient()
    role_obj = client.realm_client.get_realm_roles(search_text="opspilot_normal")
    try:
        client.realm_client.assign_realm_roles(user_id, role_obj)
        client.realm_client.update_user(user_id, {"attributes": {"locale": ["zh-CN"], "zoneinfo": ["Asia/Shanghai"]}})
        top_group_name = os.getenv("TOP_GROUP", "Default")
        top_group = client.realm_client.get_groups({"search": top_group_name})
        top_group = [i["id"] for i in top_group if i["name"] == top_group_name]
        if top_group:
            top_group = top_group[0]
        else:
            top_group = client.realm_client.create_group({"name": top_group_name})
        group_id = client.realm_client.create_group({"name": group_name}, top_group, skip_exists=True)
        if not group_id:
            return {"result": False, "message": f"group named '{group_name}' already exists."}
        user = client.realm_client.get_user(user_id)
        client.realm_client.group_user_add(user_id, group_id)
        client.realm_client.group_user_remove(user_id, default_group_id)
        cache.delete(f"group_{user.get('username')}")
        return {"result": True, "data": {"group_id": group_id}}
    except Exception as e:
        logger.error(e)
        return {"result": False, "message": str(e)}


@nats_client.register
def get_all_groups():
    client = KeyCloakClient()
    return_data = client.get_user_groups("", True)
    return {"result": True, "data": return_data}


@nats_client.register
def search_channel_list(channel_type):
    channels = Channel.objects.all()
    if channel_type:
        channels = channels.filter(channel_type=channel_type)
    return {"result": True, "data": [i for i in channels.values("id", "name", "channel_type")]}


@nats_client.register
def send_msg_with_channel(channel_id, title, content, receivers):
    channel_obj = Channel.objects.filter(id=channel_id).first()
    if not channel_obj:
        return {"result": False, "message": _("Channel not found")}
    if channel_obj.channel_type == ChannelChoices.EMAIL:
        return send_email(channel_obj, title, content, receivers)
    elif channel_obj.channel_type == ChannelChoices.ENTERPRISE_WECHAT_BOT:
        return send_by_bot(channel_obj, content)
    return send_wechat(channel_obj, content, receivers)


@nats_client.register
def get_user_rules(app, group_id, username):
    rules = UserRule.objects.filter(username=username, group_rule__group_id=group_id, group_rule__app=app).first()
    if not rules:
        return {}
    return rules.group_rule.rules


@nats_client.register
def get_group_id(group_name):
    kwargs = {
        "first": 0,
        "max": 1,
        "search": group_name,
        "exact": True,
    }
    client = KeyCloakClient()
    res = client.realm_client.get_groups(kwargs)
    if not res:
        return {"result": False, "message": f"group named '{group_name}' not exists."}
    return {"result": True, "data": res[0]["id"]}
