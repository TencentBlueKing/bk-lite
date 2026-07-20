# flake8: noqa
from .common import *  # noqa: F401,F403


@nats_client.register
def get_group_users(group=None, include_children=False):
    """
    获取组织下的用户列表
    :param group: 组织ID，如果为None则返回所有用户
    :param include_children: 是否包含子组织的用户
    :return: 用户列表
    """
    if not group:
        # 如果没有指定组织，返回所有用户
        users = User.objects.all().values("id", "username", "display_name")
    elif include_children:
        group_ids = GroupUtils.get_group_with_descendants(group)
        users = User.objects.filter(group_list__overlap=group_ids).values("id", "username", "display_name")
    else:
        users = User.objects.filter(group_list__contains=int(group)).values("id", "username", "display_name")
    return {"result": True, "data": list(users)}


def _get_actor_user_scope(actor_context, include_children=False):
    """
    根据调用方上下文解析允许访问的组织范围。

    :param actor_context: 调用方上下文，包含 username、domain、current_team、is_superuser 等字段
    :param include_children: 是否包含当前组织下的已授权子组织
    :return: (user_obj, authorized_groups)
        - user_obj: 当前调用用户对象，不存在时返回 None
        - authorized_groups: 当前调用方允许访问的组织 ID 列表
    """
    username = (actor_context or {}).get("username")
    domain = (actor_context or {}).get("domain", "domain.com")
    current_team = (actor_context or {}).get("current_team")
    is_superuser = (actor_context or {}).get("is_superuser", False)
    actor_group_list = (actor_context or {}).get("group_list")

    if not username or current_team in (None, ""):
        return None, []

    user_obj = User.objects.filter(username=username, domain=domain).first()
    if not user_obj:
        return None, []

    try:
        current_team = int(current_team)
    except (TypeError, ValueError):
        return user_obj, []

    if is_superuser:
        if include_children:
            return user_obj, GroupUtils.get_group_with_descendants(current_team)
        return user_obj, [current_team]

    user_group_list = actor_group_list if actor_group_list else user_obj.group_list
    authorized_groups = GroupUtils.get_user_authorized_child_groups(
        user_group_list,
        current_team,
        include_children=include_children,
    )
    return user_obj, authorized_groups


@nats_client.register
def get_group_users_scoped(actor_context, group=None, include_children=False):
    """
    在调用方授权范围内查询组织用户列表。

    :param actor_context: 调用方上下文，包含 username、domain、current_team、is_superuser 等字段
    :param group: 可选，指定查询的组织 ID；若不传则使用调用方当前授权范围
    :param include_children: 是否包含目标组织下的已授权子组织用户
    :return: 标准 NATS 返回结构，data 为用户列表
    """
    user_obj, authorized_groups = _get_actor_user_scope(actor_context, include_children=include_children)
    if not user_obj or not authorized_groups:
        return {"result": True, "data": []}

    if group is not None:
        try:
            group = int(group)
        except (TypeError, ValueError):
            return {"result": True, "data": []}
        if group not in authorized_groups:
            return {"result": True, "data": []}
        query_groups = GroupUtils.get_user_authorized_child_groups(
            user_obj.group_list,
            group,
            include_children=include_children,
        )
    else:
        query_groups = authorized_groups

    if not query_groups:
        return {"result": True, "data": []}

    user_filter = Q()
    for group_id in query_groups:
        user_filter |= Q(group_list__contains=int(group_id))
    users = User.objects.filter(user_filter).values("id", "username", "display_name")
    return {"result": True, "data": list(users)}


@nats_client.register
def get_authorized_groups_scoped(actor_context, include_children=False):
    """返回调用方在当前组织上下文下可访问的组织范围。"""
    _user_obj, authorized_groups = _get_actor_user_scope(actor_context, include_children=include_children)
    return {"result": True, "data": authorized_groups}


@nats_client.register
def get_assignable_groups(actor_context):
    """返回调用方可作为组织分配目标的真实组织范围。"""
    username = (actor_context or {}).get("username")
    domain = (actor_context or {}).get("domain", "domain.com")
    if not username:
        return {"result": True, "data": []}

    user_obj = User.objects.filter(username=username, domain=domain).first()
    if not user_obj:
        return {"result": True, "data": []}

    if getattr(user_obj, "is_superuser", False):
        return {"result": True, "data": list(Group.objects.values_list("id", flat=True))}

    user_group_list = list(user_obj.group_list or [])
    if not user_group_list:
        return {"result": True, "data": []}

    groups = GroupUtils.get_group_with_descendants_filtered(user_group_list, group_list=user_group_list)
    return {"result": True, "data": groups}


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
        role_ids = list(
            Role.objects.filter(name="guest", app__in=["opspilot", "cmdb", "monitor", "alarm", "log", "node", "mlops", "job"]).values_list(
                "id", flat=True
            )
        )
        normal_role = Role.objects.get(name="normal", app="opspilot")
        user = User.objects.get(id=user_id)
        top_group, _ = Group.objects.get_or_create(
            name=os.getenv("DEFAULT_GROUP_NAME", "Guest"),
            parent_id=0,
            defaults={"description": ""},
        )
        if Group.objects.filter(parent_id=top_group.id, name=group_name).exists():
            return {"result": False, "message": "Group already exists"}

        guest_group, _ = Group.objects.get_or_create(name="OpsPilotGuest", parent_id=0)
        with transaction.atomic():
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
    app_map = {
        "opspilot": OPSPILOT_GUEST_MENUS[:],
        "cmdb": CMDB_MENUS[:],
        "monitor": MONITOR_MENUS[:],
    }
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
                    "llm_model": [
                        {
                            "id": llm_model["id"],
                            "name": llm_model["name"],
                            "permission": ["View"],
                        }
                    ],
                    "ocr_model": [{"id": i["id"], "name": i["name"], "permission": ["View"]} for i in ocr_model],
                    "embed_model": [{"id": i["id"], "name": i["name"], "permission": ["View"]} for i in embed_model],
                    "rerank_model": [
                        {
                            "id": rerank_model["id"],
                            "name": rerank_model["name"],
                            "permission": ["View"],
                        }
                    ],
                },
                "knowledge": [{"id": 0, "name": "All", "permission": ["View"]}],
            },
        ),
    )
    return {"result": True}


@nats_client.register
def get_all_groups():
    groups = Group.objects.prefetch_related("roles").all()
    return_data = GroupUtils.build_group_tree(groups, True)
    return {"result": True, "data": return_data}


@nats_client.register
def get_group_id(group_name):
    group = Group.objects.filter(name=group_name, parent_id=0).first()
    if not group:
        return {"result": False, "message": f"group named '{group_name}' not exists."}
    return {"result": True, "data": group.id}


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
