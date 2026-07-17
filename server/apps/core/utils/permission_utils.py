from django.db.models import Q

from apps.core.constants import DEFAULT_PERMISSION
from apps.core.logger import nats_logger as logger
from apps.core.utils.permission_cache import get_cached_permission_rules, set_cached_permission_rules
from apps.rpc.system_mgmt import SystemMgmt


def get_permission_rules(user, current_team, app_name, permission_key, include_children=False):
    """获取某app某类权限的某个对象的规则"""
    # 尝试从缓存获取
    cached = get_cached_permission_rules(
        username=user.username,
        domain=user.domain,
        current_team=int(current_team),
        app_name=app_name,
        permission_key=permission_key,
        include_children=include_children,
    )
    if cached is not None:
        return cached

    # 缓存未命中，发起 RPC 调用
    app, child_module, client, module = set_rules_module_params(app_name, permission_key)
    try:
        permission_data = client.get_user_rules_by_app(
            int(current_team),
            user.username,
            app,
            module,
            child_module,
            user.domain,
            include_children,
        )
        # 缓存结果
        set_cached_permission_rules(
            username=user.username,
            domain=user.domain,
            current_team=int(current_team),
            app_name=app_name,
            permission_key=permission_key,
            permission_data=permission_data,
            include_children=include_children,
        )
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
        "operation_analysis": "ops-analysis",
        "job_mgmt": "job",
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
    cached = get_cached_permission_rules(
        username=user.username,
        domain=user.domain,
        current_team=int(current_team),
        app_name=app_name,
        permission_key=permission_key,
        include_children=include_children,
        query_scope="module",
    )
    if cached is not None:
        return cached

    cache_app_name = app_name
    app_name_map = {
        "system_mgmt": "system-manager",
        "node_mgmt": "node",
        "console_mgmt": "ops-console",
        "mlops": "mlops",
        "operation_analysis": "ops-analysis",
        "job_mgmt": "job",
    }
    app_name = app_name_map.get(app_name, app_name)
    module = permission_key
    client = SystemMgmt(is_local_client=True)
    try:
        permission_data = client.get_user_rules_by_module(
            int(current_team),
            user.username,
            app_name,
            module,
            user.domain,
            include_children,
        )
        set_cached_permission_rules(
            username=user.username,
            domain=user.domain,
            current_team=int(current_team),
            app_name=cache_app_name,
            permission_key=permission_key,
            permission_data=permission_data,
            include_children=include_children,
            query_scope="module",
        )
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
        return qs.none()

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


def _normalize_permission_ids(values):
    result = set()
    if not isinstance(values, list):
        return result

    for value in values:
        if isinstance(value, dict):
            value = value.get("id")
        if value is None:
            continue
        result.add(value)
        result.add(str(value))

    return result


def _normalize_instance_permissions(values):
    permission_map = {}
    if not isinstance(values, list):
        return permission_map

    for value in values:
        if not isinstance(value, dict) or "id" not in value:
            continue
        instance_id = str(value["id"])
        current_permissions = permission_map.get(instance_id, [])
        next_permissions = value.get("permission") or DEFAULT_PERMISSION
        merged_permissions = []
        for permission in list(current_permissions) + list(next_permissions):
            if permission not in merged_permissions:
                merged_permissions.append(permission)
        permission_map[instance_id] = merged_permissions or DEFAULT_PERMISSION

    return permission_map


def get_instance_permission_map(permission):
    """从权限规则中提取实例权限映射，并合并重复实例权限。"""
    if not isinstance(permission, dict):
        return {}
    return _normalize_instance_permissions(permission.get("instance", []))


def get_instance_permissions(object_type_id, instance_id, teams, permissions, cur_team):
    """返回实例具备的权限列表，无权限时返回空列表。"""
    teams = {team for team in teams if team is not None}

    admin_cur_team = _normalize_permission_ids(permissions.get("all", {}).get("team", []))
    if admin_cur_team and (teams & admin_cur_team):
        return DEFAULT_PERMISSION

    permission = permissions.get(str(object_type_id))
    if not permission:
        return DEFAULT_PERMISSION if teams & set(cur_team) else []

    instance_permissions = get_instance_permission_map(permission)
    normalized_instance_id = str(instance_id)
    if normalized_instance_id in instance_permissions:
        return instance_permissions[normalized_instance_id]

    team_permission = _normalize_permission_ids(permission.get("team", []))
    if teams & team_permission:
        return DEFAULT_PERMISSION

    return []


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
    return bool(get_instance_permissions(object_type_id, instance_id, teams, permissions, cur_team))


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

        permissions = get_instance_permissions(
            collect_type_id_str,
            instance_id,
            organizations_set,
            policy_permissions,
            current_teams_set,
        )
        if permissions:
            result[instance_id] = permissions

    return result
