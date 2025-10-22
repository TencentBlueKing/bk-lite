import base64
import io
import os
import time

import jwt
import pyotp
import qrcode
from django.contrib.auth.hashers import check_password, make_password
from django.db.models import Q
from django.utils import timezone

import nats_client
from apps.core.backends import cache
from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.guest_menus import CMDB_MENUS, MONITOR_MENUS, OPSPILOT_GUEST_MENUS
from apps.system_mgmt.models import App, Channel, ChannelChoices, Group, GroupDataRule, LoginModule, Menu, Role, User, UserRule
from apps.system_mgmt.models.system_settings import SystemSettings
from apps.system_mgmt.services.role_manage import RoleManage
from apps.system_mgmt.utils.bk_user_utils import get_bk_user_info
from apps.system_mgmt.utils.channel_utils import send_by_bot, send_email
from apps.system_mgmt.utils.group_utils import GroupUtils


def get_user_all_roles(user):
    """
    获取用户的所有角色（个人角色 + 组角色）
    :param user: User实例
    :return: 包含所有角色ID的列表
    """
    # 用户直接授权的角色
    personal_role_ids = set(user.role_list)

    # 用户所属组织的角色（只包含直接所属组织，不递归子组）
    group_role_ids = set()
    if user.group_list:
        # 使用ManyToMany关系获取组角色
        groups = Group.objects.filter(id__in=user.group_list)
        for group in groups:
            group_role_ids.update(group.roles.values_list("id", flat=True))

    # 合并去重
    all_role_ids = list(personal_role_ids | group_role_ids)
    return all_role_ids


def _verify_token(token):
    token = token.split("Basic ")[-1]
    secret_key = os.getenv("SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    user_info = jwt.decode(token, key=secret_key, algorithms=algorithm)
    time_now = int(time.time())
    login_expired_time_set = SystemSettings.objects.filter(key="login_expired_time").first()
    login_expired_time = 3600 * 24
    if login_expired_time_set:
        login_expired_time = int(login_expired_time_set.value) * 3600

    if time_now - login_expired_time > user_info["login_time"]:
        raise Exception("Token is invalid")
    user = User.objects.filter(id=user_info["user_id"]).first()
    if not user:
        raise Exception("User not found")
    return user


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
        return {"result": False, "message": str(e)}

    # 获取用户所有角色（个人角色 + 组角色）
    all_role_ids = get_user_all_roles(user)
    role_list = Role.objects.filter(id__in=all_role_ids)
    role_names = [f"{role.app}--{role.name}" if role.app else role.name for role in role_list]
    is_superuser = "admin" in role_names or "system-manager--admin" in role_names
    group_list = Group.objects.all()
    if not is_superuser:
        group_list = group_list.filter(id__in=user.group_list)
    # groups = GroupUtils.build_group_tree(group_list)
    groups = list(group_list.values("id", "name", "parent_id"))
    queryset = Group.objects.all()

    # 构建嵌套组结构
    groups_data = GroupUtils.build_group_tree(queryset, is_superuser, [i["id"] for i in groups])
    menus = cache.get(f"menus-user:{user.id}")
    if not menus:
        menus = {}
        if not is_superuser:
            menu_list = role_list.values_list("menu_list", flat=True)
            menu_ids = []
            for i in menu_list:
                menu_ids.extend(i)
            menu_data = Menu.objects.filter(id__in=list(set(menu_ids))).values_list("app", "name")
            for app, name in menu_data:
                menus.setdefault(app, []).append(name)
        cache.set(f"menus-user:{user.id}", menus, 60)
    return {
        "result": True,
        "data": {
            "username": user.username,
            "display_name": user.display_name,
            "domain": user.domain,
            "email": user.email,
            "is_superuser": is_superuser,
            "group_list": groups,
            "group_tree": groups_data,
            "roles": role_names,
            "role_ids": all_role_ids,  # 返回所有角色ID（个人+组）
            "locale": user.locale,
            "permission": menus,
        },
    }


@nats_client.register
def get_user_menus(client_id, roles, username, is_superuser):
    client = RoleManage()
    client_id = client_id
    menus = []
    if not is_superuser:
        menu_ids = []
        role_menus = Role.objects.filter(app=client_id, id__in=roles).values_list("menu_list", flat=True)
        for i in role_menus:
            menu_ids.extend(i)
        menus = list(Menu.objects.filter(app=client_id, id__in=list(set(menu_ids))).values_list("name", flat=True))
    user_menus = client.get_all_menus(client_id, user_menus=menus, username=username, is_superuser=is_superuser)
    return {"result": True, "data": user_menus}


@nats_client.register
def get_client(client_id="", username="", domain="domain.com"):
    app_list = App.objects.all()
    if client_id:
        app_list = app_list.filter(name__in=client_id.split(";"))
    if username:
        user = User.objects.filter(username=username, domain=domain).first()
        if not user:
            return {"result": False, "message": "User not found"}

        # 获取用户所有角色（个人角色 + 组角色）
        all_role_ids = get_user_all_roles(user)
        app_name_list = list(Role.objects.filter(id__in=all_role_ids).values_list("app", flat=True).distinct())
        if "" not in app_name_list:
            app_list = app_list.filter(name__in=app_name_list)
    return_data = list(app_list.order_by("name").values())
    return {"result": True, "data": return_data}


@nats_client.register
def get_client_detail(client_id):
    app_obj = App.objects.filter(name=client_id).first()
    if not app_obj:
        return {"result": False, "message": "Client not found"}
    return {
        "result": True,
        "data": {
            "id": app_obj.id,
            "name": app_obj.name,
            "description": app_obj.description,
            "description_cn": app_obj.description_cn,
        },
    }


@nats_client.register
def get_group_users(group):
    users = User.objects.filter(group_list__contains=int(group)).values("id", "username", "display_name")
    return {"result": True, "data": list(users)}


@nats_client.register
def get_all_users():
    data = User.objects.all().values(*User.display_fields())
    return {"result": True, "data": list(data)}


@nats_client.register
def search_groups(query_params):
    groups = Group.objects.filter(name__contains=query_params["search"]).values()
    return {"result": True, "data": list(groups)}


@nats_client.register
def search_users(query_params):
    page = int(query_params.get("page", 1))
    page_size = int(query_params.get("page_size", 10))
    search = query_params.get("search", "")
    queryset = User.objects.filter(Q(username__icontains=search) | Q(display_name__icontains=search) | Q(email__icontains=search))
    start = (page - 1) * page_size
    end = page * page_size
    total = queryset.count()
    display_fields = User.display_fields() + ["group_list"]
    data = queryset.values(*display_fields)[start:end]
    return {"result": True, "data": {"count": total, "users": list(data)}}


@nats_client.register
def init_user_default_attributes(user_id, group_name, default_group_id):
    try:
        role_ids = list(Role.objects.filter(name="guest", app__in=["opspilot", "cmdb", "monitor", "alarm", "node"]).values_list("id", flat=True))
        normal_role = Role.objects.get(name="normal", app="opspilot")
        user = User.objects.get(id=user_id)
        top_group, _ = Group.objects.get_or_create(name=os.getenv("DEFAULT_GROUP_NAME", "Guest"), parent_id=0, defaults={"description": ""})
        if Group.objects.filter(parent_id=top_group.id, name=group_name).exists():
            return {"result": False, "message": "Group already exists"}

        guest_group, _ = Group.objects.get_or_create(name="OpsPilotGuest", parent_id=0)
        group_obj = Group.objects.create(name=group_name, parent_id=top_group.id)
        user.locale = "zh-Hans"
        user.timezone = "Asia/Shanghai"
        user.role_list.extend(role_ids)
        user.role_list = list(set(user.role_list))  # 去重
        if normal_role.id in user.role_list:
            user.role_list.remove(normal_role.id)
        user.group_list.remove(int(default_group_id))
        user.group_list.append(guest_group.id)
        user.group_list.append(group_obj.id)
        user.save()
        set_opspilot_guest_group_default_rule(guest_group, user)
        cache.delete(f"group_{user.username}")
        return {"result": True, "data": {"group_id": group_obj.id}}
    except Exception as e:
        logger.exception(e)
        return {"result": False, "message": str(e)}


@nats_client.register
def create_guest_role():
    app_map = {"opspilot": OPSPILOT_GUEST_MENUS[:], "cmdb": CMDB_MENUS[:], "monitor": MONITOR_MENUS[:]}
    guest_group, _ = Group.objects.get_or_create(name="Guest", parent_id=0, defaults={"description": "Guest group"})
    app_guest_group, _ = Group.objects.get_or_create(name="OpsPilotGuest", parent_id=0)
    for app, app_menus in app_map.items():
        menus = dict(Menu.objects.filter(app=app).values_list("id", "name"))
        menu_list = [k for k, v in menus.items() if v in app_menus]
        Role.objects.update_or_create(name="guest", app=app, defaults={"menu_list": menu_list})
    return {"result": True, "data": {"group_id": app_guest_group.id}}


@nats_client.register
def create_default_rule(llm_model, ocr_model, embed_model, rerank_model):
    guest_group = Group.objects.get(name="OpsPilotGuest", parent_id=0)
    GroupDataRule.objects.get_or_create(
        name="OpsPilot内置规则",
        app="opspilot",
        defaults=dict(
            group_id=guest_group.id,
            description="Guest组数据权限规则",
            group_name=guest_group.name,
            rules={
                "skill": [{"id": 0, "name": "All", "permission": ["View"]}],
                "tools": [{"id": 0, "name": "All", "permission": ["View"]}],
                "provider": {
                    "llm_model": [{"id": llm_model["id"], "name": llm_model["name"], "permission": ["View"]}],
                    "ocr_model": [{"id": i["id"], "name": i["name"], "permission": ["View"]} for i in ocr_model],
                    "embed_model": [{"id": i["id"], "name": i["name"], "permission": ["View"]} for i in embed_model],
                    "rerank_model": [{"id": rerank_model["id"], "name": rerank_model["name"], "permission": ["View"]}],
                },
                "knowledge": [{"id": 0, "name": "All", "permission": ["View"]}],
            },
        ),
    )
    return {"result": True}


@nats_client.register
def get_all_groups():
    groups = Group.objects.all()
    return_data = GroupUtils.build_group_tree(groups, True)
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
        return {"result": False, "message": "Channel not found"}
    if channel_obj.channel_type == ChannelChoices.EMAIL:
        user_list = User.objects.filter(id__in=receivers)
        return send_email(channel_obj, title, content, user_list)
    elif channel_obj.channel_type == ChannelChoices.ENTERPRISE_WECHAT_BOT:
        return send_by_bot(channel_obj, content, receivers)
    return {"result": False, "message": "Unsupported channel type"}
    # return send_wechat(channel_obj, content, user_list)


@nats_client.register
def get_user_rules(group_id, username):
    rules = UserRule.objects.filter(username=username).filter(Q(group_rule__group_id=group_id) | Q(group_rule__group_name="OpsPilotGuest"))
    if not rules:
        return {}
    return_data = {}
    for i in rules:
        if i.group_rule.group_name == "OpsPilotGuest":
            return_data.setdefault(i.group_rule.app, {})["guest"] = i.group_rule.rules
        else:
            return_data.setdefault(i.group_rule.app, {})["normal"] = i.group_rule.rules
    return return_data


def _prepare_user_rules_query(group_id, username, domain, app, include_children=False):
    """
    准备用户权限规则查询的通用逻辑
    :param group_id: 组ID
    :param username: 用户名
    :param domain: 域
    :param app: 应用名称
    :param include_children: 是否包含子组（递归查询所有子孙组）
    :return: (user_obj, query_group_ids, admin_teams, has_guest_group, is_admin)
    """
    # 获取用户对象
    user_obj = User.objects.filter(username=username, domain=domain).first()
    if not user_obj:
        return None, None, None, None, None

    # 获取管理员角色列表
    admin_list = list(Role.objects.filter(name="admin").filter(Q(app="") | Q(app=app)).values_list("id", flat=True))

    # 获取用户所有角色（个人角色 + 组角色）
    all_role_ids = get_user_all_roles(user_obj)
    is_admin = bool(set(all_role_ids).intersection(admin_list))

    # 获取查询的组ID列表（包含子组）
    if include_children:
        query_group_ids = GroupUtils.get_all_child_groups(int(group_id), include_self=True)
    else:
        query_group_ids = [int(group_id)]

    # 设置管理员团队
    admin_teams = query_group_ids[:]

    # 检查是否有guest组权限
    guest_group = Group.objects.filter(name="OpsPilotGuest").first()
    has_guest_group = False
    if guest_group and guest_group.id in user_obj.group_list:
        has_guest_group = True
        admin_teams.append(guest_group.id)

    return user_obj, query_group_ids, admin_teams, has_guest_group, is_admin


@nats_client.register
def get_user_rules_by_module(group_id, username, domain, app, module, include_children=False):
    """
    获取用户在指定模块下的所有权限规则，按子模块分组返回
    :param group_id: 组ID
    :param username: 用户名
    :param domain: 域
    :param app: 应用名称
    :param module: 模块名称
    :param include_children: 是否包含子组（递归查询所有子孙组）
    """
    # 使用通用查询准备函数
    user_obj, query_group_ids, admin_teams, has_guest_group, is_admin = _prepare_user_rules_query(group_id, username, domain, app, include_children)

    if not user_obj:
        return {"result": False, "message": "User not found"}

    all_permission = {"all": {"instance": [], "team": admin_teams}}

    # 如果是管理员，返回所有权限
    if is_admin:
        return {"result": True, "data": all_permission, "team": admin_teams}

    # 构建查询过滤条件
    if has_guest_group:
        base_filter = Q(group_rule__group_id__in=query_group_ids) | Q(group_rule__group_name="OpsPilotGuest")
    else:
        base_filter = Q(group_rule__group_id__in=query_group_ids)
    module_filter = Q(group_rule__rules__has_key=module)

    rules = UserRule.objects.filter(username=username, domain=domain, group_rule__app=app).filter(base_filter & module_filter)
    if not rules:
        return {"result": True, "data": all_permission, "team": admin_teams}

    result = {}
    group_list = {i.group_rule.group_id for i in rules}
    all_permission_team = [i for i in admin_teams if i not in group_list]

    for rule in rules:
        # 获取模块数据
        module_data = rule.group_rule.rules.get(module, {})

        # 遍历模块下的所有分类和子模块
        for category, sub_modules in module_data.items():
            if isinstance(sub_modules, dict):
                # 嵌套结构（如 provider.llm_model）
                for sub_module_id, rule_data in sub_modules.items():
                    _accumulate_rule_result(result, sub_module_id, rule_data, rule.group_rule.group_id, all_permission_team)
            else:
                # 扁平结构（如 skill、bot）
                _accumulate_rule_result(result, category, sub_modules, rule.group_rule.group_id, all_permission_team)

    return {"result": True, "data": result, "team": admin_teams}


@nats_client.register
def get_user_rules_by_app(group_id, username, domain, app, module, child_module="", include_children=False):
    """
    获取用户在指定应用模块下的权限规则
    :param group_id: 组ID
    :param username: 用户名
    :param domain: 域
    :param app: 应用名称
    :param module: 模块名称
    :param child_module: 子模块名称
    :param include_children: 是否包含子组（递归查询所有子孙组）
    """
    # 使用通用查询准备函数
    user_obj, query_group_ids, admin_teams, has_guest_group, is_admin = _prepare_user_rules_query(group_id, username, domain, app, include_children)

    if not user_obj:
        return {"instance": [], "team": []}

    # 如果是管理员，返回所有权限
    if is_admin:
        return {"instance": [], "team": admin_teams}

    # 构建查询过滤条件
    if has_guest_group:
        base_filter = Q(group_rule__group_id__in=query_group_ids) | Q(group_rule__group_name="OpsPilotGuest")
    else:
        base_filter = Q(group_rule__group_id__in=query_group_ids)
    # 添加模块过滤条件
    module_filter = Q(group_rule__rules__has_key=module)

    # 如果指定了子模块，不在数据库层面过滤，在Python层面处理复杂嵌套
    rules = UserRule.objects.filter(username=username, domain=domain, group_rule__app=app).filter(base_filter & module_filter)

    if not rules:
        return {"instance": [], "team": admin_teams}

    group_list = {i.group_rule.group_id for i in rules}
    return_data = {"instance": [], "team": [i for i in admin_teams if i not in group_list]}

    for rule in rules:
        # 获取模块数据
        module_data = rule.group_rule.rules.get(module, [])

        # 如果指定了子模块，获取子模块数据
        if child_module:
            target_data = find_child_module_data(module_data, child_module)
        else:
            target_data = module_data
        # 处理规则数据
        has_all_permission, instance_data = process_rule_data(target_data)

        if has_all_permission:
            return_data["team"].append(rule.group_rule.group_id)
        else:
            return_data["instance"].extend(instance_data)

    return return_data


def find_child_module_data(module_data, target_child_module):
    """在模块数据中查找子模块数据，支持嵌套结构"""
    if not isinstance(module_data, dict):
        return []

    # 直接查找子模块
    if target_child_module in module_data:
        return module_data[target_child_module]

    # 在嵌套结构中查找子模块
    for key, value in module_data.items():
        if isinstance(value, dict) and target_child_module in value:
            return value[target_child_module]
    return []


def process_rule_data(rule_data):
    """处理规则数据，返回是否为全部权限和具体实例数据"""
    if not rule_data:
        return True, []
    if isinstance(rule_data, list):
        rule_data = [item for item in rule_data if isinstance(item, dict) and item.get("id") not in ["-1", -1]]
        ids = [item.get("id") for item in rule_data]
        has_all_permission = 0 in ids or "0" in ids
        return has_all_permission, rule_data if not has_all_permission else []

    return True, []


def _accumulate_rule_result(result, key, rule_data, group_id, all_permission_team):
    """
    累积规则结果到指定的 key 中
    :param result: 结果字典
    :param key: 子模块 ID 或分类名称
    :param rule_data: 规则数据
    :param group_id: 组 ID
    :param all_permission_team: 全权限团队列表
    """
    # 初始化结果键
    if key not in result:
        result[key] = {"instance": [], "team": all_permission_team[:]}

    # 处理规则数据
    has_all_permission, instance_data = process_rule_data(rule_data)

    if has_all_permission:
        # 如果有全部权限，添加组 ID 到团队列表
        if group_id not in result[key]["team"]:
            result[key]["team"].append(group_id)
    else:
        # 否则添加实例数据
        result[key]["instance"].extend(instance_data)


@nats_client.register
def get_group_id(group_name):
    group = Group.objects.filter(name=group_name, parent_id=0).first()
    if not group:
        return {"result": False, "message": f"group named '{group_name}' not exists."}
    return {"result": True, "data": group.id}


@nats_client.register
def login(username, password):
    user = User.objects.filter(username=username, domain="domain.com").first()
    if not user:
        return {"result": False, "message": "Username or password is incorrect"}

    # 使用 check_password 验证密码是否匹配
    if not check_password(password, user.password):
        return {"result": False, "message": "Username or password is incorrect"}
    return get_user_login_token(user, username)


@nats_client.register
def reset_pwd(username, password):
    user = User.objects.filter(username=username).first()
    if not user:
        return {"result": False, "message": "Username not exists"}
    user.password = make_password(password)
    user.temporary_pwd = False
    user.save()
    return {"result": True}


@nats_client.register
def wechat_user_register(user_id, nick_name):
    user, is_first_login = User.objects.update_or_create(username=user_id, defaults={"display_name": nick_name})
    default_group = Group.objects.filter(name="OpsPilotGuest", parent_id=0).first()
    if not user.group_list and default_group:
        user.group_list = [default_group.id]
    default_role = list(
        Role.objects.filter(
            Q(name="normal", app__in=["opspilot", "ops-console"]) | Q(name="guest", app__in=["opspilot", "cmdb", "monitor", "log", "alarm", "node"])
        ).values_list("id", flat=True)
    )
    default_role.extend(user.role_list)
    user.role_list = list(set(default_role))
    user.last_login = timezone.now()
    user.save()
    try:
        if default_group:
            set_opspilot_guest_group_default_rule(default_group, user)
    except Exception:  # noqa
        pass
    secret_key = os.getenv("SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    user_obj = {"user_id": user.id, "login_time": int(time.time())}
    token = jwt.encode(payload=user_obj, key=secret_key, algorithm=algorithm)
    return {
        "result": True,
        "data": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "is_first_login": is_first_login,
            "locale": user.locale,
            "token": token,
        },
    }


def set_opspilot_guest_group_default_rule(default_group, user):
    default_rule = GroupDataRule.objects.get(name="OpsPilot内置规则", app="opspilot", group_id=default_group.id)
    monitor_rule = GroupDataRule.objects.get(name="OpsPilotGuest数据权限", app="monitor", group_id=default_group.id)
    cmdb_rule = GroupDataRule.objects.get(name="游客数据权限", app="cmdb", group_id=default_group.id)
    log_rule = GroupDataRule.objects.get(name="log内置规则", app="log", group_id=default_group.id)
    node_rule = GroupDataRule.objects.get(name="节点管理内置数据权限", app="node", group_id=default_group.id)
    UserRule.objects.get_or_create(username=user.username, group_rule_id=cmdb_rule.id)
    UserRule.objects.get_or_create(username=user.username, group_rule_id=default_rule.id)
    UserRule.objects.get_or_create(username=user.username, group_rule_id=monitor_rule.id)
    UserRule.objects.get_or_create(username=user.username, group_rule_id=log_rule.id)
    UserRule.objects.get_or_create(username=user.username, group_rule_id=node_rule.id)


@nats_client.register
def get_wechat_settings():
    login_module = LoginModule.objects.filter(source_type="wechat", enabled=True).first()
    if not login_module:
        return {"result": True, "data": {"enabled": False}}

    return {
        "result": True,
        "data": {
            "enabled": True,
            "app_id": login_module.app_id,
            "app_secret": login_module.decrypted_app_secret,
            "redirect_uri": login_module.other_config.get("redirect_uri", ""),
            "callback_url": login_module.other_config.get("callback_url", ""),
        },
    }


# 生成二维码
@nats_client.register
def generate_qr_code(username):
    # 查找用户
    user = User.objects.filter(username=username).first()
    if not user:
        return {"result": False, "message": "User not found"}
    user.otp_secret = pyotp.random_base32()
    user.save()
    totp = pyotp.TOTP(user.otp_secret)
    # 创建用于Authenticator应用的配置URL
    provisioning_uri = totp.provisioning_uri(name=username, issuer_name="WeopsX")

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(provisioning_uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()

    return {"result": True, "data": {"qr_code": qr_code_base64}}


# 验证OTP代码
@nats_client.register
def verify_otp_code(username, otp_code):
    user = User.objects.get(username=username)
    totp = pyotp.TOTP(user.otp_secret)
    if totp.verify(otp_code):
        return {"result": True, "message": "Verification successful"}
    return {"result": False, "message": "Invalid OTP code"}


@nats_client.register
def get_namespace_by_domain(domain):
    login_module = LoginModule.objects.filter(source_type="bk_lite", other_config__contains={"domain": domain}).first()
    if not login_module:
        return {"result": False, "message": "Login module not found"}
    namespace = login_module.other_config.get("namespace", "")
    return {"result": True, "data": namespace}


@nats_client.register
def bk_lite_user_login(username, domain):
    user = User.objects.filter(username=username, domain=domain).first()
    if not user:
        return {"result": False, "message": "Username or password is incorrect"}
    return get_user_login_token(user, username)


def get_user_login_token(user, username):
    if user.disabled:
        return {"result": False, "message": "User is disabled"}
    secret_key = os.getenv("SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    user_obj = {"user_id": user.id, "login_time": int(time.time())}
    token = jwt.encode(payload=user_obj, key=secret_key, algorithm=algorithm)
    enable_otp = SystemSettings.objects.filter(key="enable_otp").first()
    user.last_login = timezone.now()
    user.save()
    if not enable_otp:
        enable_otp = False
    else:
        enable_otp = enable_otp.value == "1"
    return {
        "result": True,
        "data": {
            "token": token,
            "username": username,
            "display_name": user.display_name,
            "id": user.id,
            "domain": user.domain,
            "locale": user.locale,
            "temporary_pwd": user.temporary_pwd,
            "enable_otp": enable_otp,
            "qrcode": user.otp_secret is None or user.otp_secret == "",
        },
    }


@nats_client.register
def get_login_module_domain_list():
    login_module_list = list(LoginModule.objects.filter(source_type="bk_lite").values_list("other_config__domain", flat=True))
    login_module_list.insert(0, "domain.com")
    return {"result": True, "data": login_module_list}


@nats_client.register
def delete_rules(group_ids, instance_id, app, module, child_module):
    """
    删除权限规则中指定实例的权限配置
    """
    try:
        # 查询对应的 GroupDataRule
        rules_queryset = GroupDataRule.objects.filter(group_id__in=group_ids, app=app)

        updated_count = 0
        for rule_obj in rules_queryset:
            rules_data = rule_obj.rules

            # 如果没有对应的模块，跳过
            if module not in rules_data:
                continue

            # 获取目标数据结构
            if child_module:
                # 二级模块，如 provider.llm_model
                if child_module not in rules_data[module]:
                    continue
                target_list = rules_data[module][child_module]
            else:
                # 一级模块，如 skill、bot
                target_list = rules_data[module]

            # 删除指定 ID 的权限项
            original_length = len(target_list)
            if child_module:
                rules_data[module][child_module] = [item for item in target_list if str(item.get("id")) != str(instance_id)]
            else:
                rules_data[module] = [item for item in target_list if str(item.get("id")) != str(instance_id)]

            # 如果有删除操作，更新数据库
            new_length = len(rules_data[module][child_module] if child_module else rules_data[module])
            if new_length < original_length:
                rule_obj.rules = rules_data
                rule_obj.save()
                updated_count += 1

        return {"result": True, "message": f"Successfully deleted rules from {updated_count} group data rules"}

    except Exception as e:
        logger.exception(f"Error deleting rules: {e}")
        return {"result": False, "message": str(e)}


@nats_client.register
def verify_bk_token(bk_token):
    login_module = LoginModule.objects.filter(source_type="bk_login", enabled=True).first()
    if not login_module:
        return {"result": True, "data": {"bk_login_open": False}}
    bk_config = login_module.other_config
    if not bk_token:
        return {"result": True, "data": {"bk_login_open": True, "user": {}, "url": bk_config.get("bk_url")}}
    res, bk_user = get_bk_user_info(bk_token, bk_config.get("app_id"), bk_config.get("app_token"), bk_config.get("bk_url"))
    if not res:
        return {"result": True, "data": {"bk_login_open": True, "user": {}, "url": bk_config.get("bk_url")}}
    group_obj = Group.objects.get(name=login_module.other_config.get("root_group", "蓝鲸"), parent_id=0)
    user, _ = User.objects.get_or_create(
        username=bk_user["username"],
        domain=bk_user.get("domain"),
        defaults={
            "email": bk_user.get("email", ""),
            "group_list": [group_obj.id],
            "locale": bk_user.get("language", "zh-Hans"),
            "timezone": bk_user.get("time_zone", "Asia/Shanghai"),
            "role_list": login_module.other_config.get("default_roles", []),
        },
    )
    user.email = bk_user.get("email", "")
    user.locale = bk_user.get("language", user.locale)
    user.timezone = bk_user.get("time_zone", user.timezone)
    user.save()
    user_obj = {"user_id": user.id, "login_time": int(time.time())}
    secret_key = os.getenv("SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    token = jwt.encode(payload=user_obj, key=secret_key, algorithm=algorithm)
    return {
        "result": True,
        "data": {
            "bk_login_open": True,
            "user": {
                "token": token,
                "username": user.username,
                "display_name": user.display_name,
                "id": user.id,
                "domain": user.domain,
                "locale": user.locale,
                "qrcode": user.otp_secret is None or user.otp_secret == "",
            },
            "url": bk_config.get("bk_url"),
        },
    }
