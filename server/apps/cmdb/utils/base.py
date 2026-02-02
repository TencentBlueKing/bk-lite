# -- coding: utf-8 --
# @File: base.py
# @Time: 2025/7/21 14:00
# @Author: windyzhao
from apps.core.logger import cmdb_logger as logger
from apps.cmdb.constants.constants import PERMISSION_TASK


def get_cmdb_rules(request, permission_key=PERMISSION_TASK) -> dict:
    """
    获取cmdb的权限规则
    :param request:
    :param permission_key: 权限类型，默认为 PERMISSION_TASK
    :return: cmdb的权限规则
    """
    try:
        rules = request.user.rules.get("cmdb", {}).get("normal", {}).get(permission_key, {})
    except Exception as err:
        rules = {}
        logger.error(f"获取cmdb权限规则失败: {err}")
    return rules


def format_group_params(group_id):
    """
    格式化组织参数
    :param group_id: 组织ID
    :return: 格式化后的参数
    """
    return [{'id': int(group_id)}]


def format_groups_params(teams: list):
    """
    格式化组织参数
    :param teams: 组织ID列表
    :return: 格式化后的参数
    """
    return [{'id': team} for team in set(teams)]


def get_default_group_id():
    """
    获取默认组织ID
    :return: 默认组织ID
    """
    from apps.system_mgmt.models.user import Group
    default_group = Group.objects.get(name="Default", parent_id=0)
    return [default_group.id]


def get_user_groups_flat(group_list, is_superuser):
    """
    获取用户所属的组织及其所有子组织列表(打平为列表,不构建树状结构)
    :param group_list: 用户组织列表
    :param is_superuser: 是否超级用户
    :return: 组织列表,每个元素包含 id, name, hasAuth, role_ids, is_virtual 等字段
    """
    from apps.system_mgmt.models import Group
    from apps.system_mgmt.utils.group_utils import GroupUtils

    groups = [i["id"] for i in group_list]

    # 获取用户当前级组织及其所有子组织
    all_group_ids = set()
    if is_superuser:
        # 超级用户获取所有组织
        all_group_ids = set(Group.objects.values_list("id", flat=True))
    else:
        # 普通用户：获取当前级组织和所有子组织
        for group_id in groups:
            # 包含当前组织及其所有子组织
            child_groups = GroupUtils.get_all_child_groups(group_id, include_self=True)
            all_group_ids.update(child_groups)

    # 查询所有相关组织
    queryset = Group.objects.filter(id__in=all_group_ids)
    if not is_superuser:
        queryset = queryset.exclude(name="OpsPilotGuest", parent_id=0)

    # 构建打平的组织列表
    groups_data = set()
    for group in queryset:
        groups_data.add(group.id)

    return list(groups_data)


def get_organization_and_children_ids(tree_data: list, target_id: int) -> list:
    """
    从树状组织数据中获取指定组织及其所有子组织的ID列表

    Args:
        tree_data: 树状组织数据列表
        target_id: 目标组织ID

    Returns:
        list: 包含目标组织及其所有子组织的ID列表
    """

    def find_and_collect_ids(nodes: list, target_id: int) -> list:
        """递归查找目标节点并收集其所有子节点ID"""
        for node in nodes:
            if node.get('id') == target_id:
                # 找到目标节点，收集其所有子节点ID
                result = [target_id]

                def collect_children_ids(current_node: dict) -> None:
                    """递归收集所有子节点ID"""
                    sub_groups = current_node.get('subGroups', [])
                    for child in sub_groups:
                        child_id = child.get('id')
                        if child_id:
                            result.append(child_id)
                            collect_children_ids(child)

                collect_children_ids(node)
                return result

            # 在子组织中继续查找
            sub_groups = node.get('subGroups', [])
            if sub_groups:
                found = find_and_collect_ids(sub_groups, target_id)
                if found:
                    return found

        return []

    return find_and_collect_ids(tree_data, target_id)
