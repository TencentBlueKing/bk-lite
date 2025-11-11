from django.db.models import Q

from apps.core.constants import DEFAULT_PERMISSION
from apps.core.logger import nats_logger as logger
from apps.rpc.system_mgmt import SystemMgmt


def get_permission_rules(user, current_team, app_name, permission_key, include_children=False):
    """获取某app某类权限的某个对象的规则"""
    app, child_module, client, module = set_rules_module_params(app_name, permission_key)
    try:
        permission_data = client.get_user_rules_by_app(int(current_team), user.username, app, module, child_module, user.domain, include_children)
        return permission_data
    except Exception:
        import traceback
        logger.error(traceback.format_exc())
        return {}


def set_rules_module_params(app_name, permission_key):
    app_name_map = {
        "system_mgmt": "system-manager",
        "node_mgmt": "node",
        "console_mgmt": "ops-console",
        "mlops": "mlops",
        "operation_analysis": "ops-analysis"
    }
    client = SystemMgmt(is_local_client=True)
    app_name = app_name_map.get(app_name, app_name)
    module = permission_key
    child_module = ""
    if "." in permission_key:
        module, child_module = permission_key.split(".")
    return app_name, child_module, client, module


def get_permissions_rules(user, current_team, app_name, permission_key, include_children=False):
    """获取某app某类权限规则"""
    app_name_map = {
        "system_mgmt": "system-manager",
        "node_mgmt": "node",
        "console_mgmt": "ops-console",
        "mlops": "mlops",
        "operation_analysis": "ops-analysis"
    }
    app_name = app_name_map.get(app_name, app_name)
    module = permission_key
    client = SystemMgmt(is_local_client=True)
    try:
        permission_data = client.get_user_rules_by_module(int(current_team), user.username, app_name, module, user.domain, include_children)
        return permission_data
    except Exception:
        return {}


def permission_filter(model, permission, team_key="teams__id__in", id_key="id__in"):
    """
    模型权限过滤（单对象查询）
    model: Django model to filter.
    permission: {
        "instance":[{"id": 1, permission: ["view", "Operate"]}],
        "team":[1, 2, 3]
    }
    """

    qs = model.objects.all()

    per_instance_ids = [i["id"] for i in permission.get("instance", [])]
    per_team_ids = permission.get("team", [])

    if not per_instance_ids and not per_team_ids:
        return qs

    # 实例权限过滤
    if per_team_ids and not per_instance_ids:
        qs = qs.filter(Q(**{team_key: per_team_ids}) | Q(**{id_key: per_instance_ids}))
    elif per_instance_ids and not per_team_ids:
        qs = qs.filter(**{id_key: per_instance_ids})
    else:
        qs = qs.filter(Q(**{team_key: per_team_ids}) | Q(**{id_key: per_instance_ids}))

    return qs


def delete_instance_rules(app_name, permission_key, instance_id, group_ids):
    app, child_module, client, module = set_rules_module_params(app_name, permission_key)
    result = client.delete_rules(group_ids, instance_id, app, module, child_module)
    return result


def check_instance_permission(object_type_id, instance_id, teams, permissions, cur_team):
    """
    通用实例权限检查逻辑

    Args:
        object_type_id: 对象类型ID（如monitor_object_id, collect_type_id）
        instance_id: 实例ID（如策略ID、监控实例ID）
        teams: 实例关联的团队集合
        permissions: 权限数据结构
        cur_team: 当前用户团队

    Returns:
        bool: 是否有权限

    Examples:
        # 监控模块使用
        has_permission = check_instance_permission(monitor_object_id, instance_id, teams, permissions, cur_team)

        # 日志模块使用
        has_permission = check_instance_permission(collect_type_id, policy_id, teams, permissions, cur_team)
    """
    # 超管权限检查
    admin_cur_team = permissions.get("all", {}).get("team")
    if admin_cur_team:
        if teams & set(admin_cur_team):
            return True

    cur_team = set(cur_team)

    # 普通用户权限检查 - 未设置实例权限时，根据当前组判断
    permission = permissions.get(str(object_type_id))
    if not permission:
        if cur_team & teams:
            # 此实例组织在当前组中，有权限
            return True
        else:
            # 此实例组织不在当前组，无权限
            return False

    # 安全获取实例权限，确保类型正确
    instance_data = permission.get("instance", [])
    if isinstance(instance_data, list):
        inst_permission = {i["id"] for i in instance_data if isinstance(i, dict) and "id" in i}
    else:
        inst_permission = set()

    # 安全获取团队权限，确保类型正确
    team_data = permission.get("team", [])
    if isinstance(team_data, list):
        team_permission = {i["id"] if isinstance(i, dict) and "id" in i else i for i in team_data if i is not None}
    else:
        team_permission = set()

    # 存在实例权限，但是都为空时，代表此对象当前组没有任何此类对象的实例权限
    if not inst_permission and not team_permission:
        return False

    # 如果实例权限中包含当前实例ID，直接返回True
    if instance_id in inst_permission:
        return True

    team_permission = set(team_permission)
    # 如果当前组在团队权限中有权限，直接返回True
    if teams & team_permission:
        return True

    return False


def filter_instances_with_permissions(instances_result, policy_permissions, current_teams):
    """
    过滤实例并返回权限映射

    Args:
        instances_result: 实例列表，格式: [{'instance_id': 'xxx', 'organizations': [1,2], 'collect_type_id': 1}]
        policy_permissions: 权限数据结构
        current_teams: 当前用户团队列表

    Returns:
        dict: {instance_id: [permissions]} 格式的权限映射
    """
    result = {}
    current_teams_set = set(current_teams)

    for item in instances_result:
        collect_type_id_str = str(item["collect_type_id"])
        instance_id = item["instance_id"]
        organizations_set = set(item["organizations"])

        # 检查超管权限
        admin_team_permission = policy_permissions.get("all", {}).get("team", [])
        if admin_team_permission and organizations_set & set(admin_team_permission):
            result[instance_id] = DEFAULT_PERMISSION
            continue

        # 检查特定采集类型权限
        type_permission = policy_permissions.get(collect_type_id_str, {})
        if not type_permission:
            # 如果没有配置权限规则，检查组织匹配
            if current_teams_set & organizations_set:
                result[instance_id] = DEFAULT_PERMISSION
            continue

        # 检查实例级权限
        instance_permissions = type_permission.get("instance", {})
        if instance_id in instance_permissions:
            permissions = instance_permissions[instance_id]
            if permissions:  # 如果有具体权限
                result[instance_id] = permissions
            else:  # 如果权限为空列表，使用默认权限
                result[instance_id] = DEFAULT_PERMISSION
            continue

        # 检查团队权限
        team_permissions = set(type_permission.get("team", []))
        if current_teams_set & team_permissions or organizations_set & team_permissions:
            result[instance_id] = DEFAULT_PERMISSION

    return result
