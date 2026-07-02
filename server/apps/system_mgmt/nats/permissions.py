# flake8: noqa
from .common import *  # noqa: F401,F403


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
    query_group_ids = []
    if include_children:
        # 使用优化后的单次查询方法替代 N+1 的 get_all_child_groups
        query_group_ids = GroupUtils.get_group_with_descendants_filtered(int(group_id), group_list=user_obj.group_list)

    query_group_ids.append(int(group_id))
    query_group_ids = list(set(query_group_ids))
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
        # 普通用户无权限规则时，返回空数据，但保留 team 用于组织过滤
        # 注意：不返回 all_permission，避免被误认为管理员权限
        return {"result": True, "data": {}, "team": admin_teams}

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
    rules = list(UserRule.objects.filter(username=username, domain=domain, group_rule__app=app).filter(base_filter & module_filter))

    if not rules:
        return {"instance": [], "team": admin_teams}

    group_list = {i.group_rule.group_id for i in rules}
    return_data = {
        "instance": [],
        "team": [i for i in admin_teams if i not in group_list],
    }

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
def delete_rules(group_ids, instance_id, app, module, child_module):
    """
    删除权限规则中指定实例的权限配置
    """
    try:
        # 查询对应的 GroupDataRule
        rules_queryset = GroupDataRule.objects.filter(group_id__in=group_ids, app=app)

        updated_count = 0
        affected_rule_ids = []
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
                affected_rule_ids.append(rule_obj.id)

        # 清除受影响用户的权限缓存
        if affected_rule_ids:
            affected_users = list(UserRule.objects.filter(group_rule_id__in=affected_rule_ids).values("username", "domain"))
            if affected_users:
                clear_users_permission_cache(affected_users)

        return {
            "result": True,
            "message": f"Successfully deleted rules from {updated_count} group data rules",
        }

    except Exception as e:
        logger.exception(f"Error deleting rules: {e}")
        return {"result": False, "message": str(e)}
