# -- coding: utf-8 --
# @File: base.py
# @Time: 2025/7/21 14:00
# @Author: windyzhao
from apps.core.logger import cmdb_logger as logger
from apps.cmdb.constants import PERMISSION_TASK


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
    default_group = Group.objects.get(name="Default")
    return [default_group.id]
