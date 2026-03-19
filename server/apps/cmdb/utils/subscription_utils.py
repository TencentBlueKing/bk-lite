# -- coding: utf-8 --
# @File: subscription_utils.py
# @Time: 2026/3/19 10:00
# @Author: windyzhao
"""
订阅功能公共工具函数

提供订阅任务和触发检测共用的工具方法，包括：
- 值截断：`truncate_value`
- 实例名称提取：`get_inst_display_name`
- 组织权限检查：`check_subscription_manage_permission`
"""
from typing import Any


def truncate_value(value: Any, max_length: int = 50) -> str:
    """
    截断过长的值用于日志或通知展示。

    Args:
        value: 待截断的值，可以是任意类型
        max_length: 最大长度，超出部分用 '...' 替代

    Returns:
        截断后的字符串表示
    """
    if value is None:
        return "(空)"
    str_value = str(value)
    if len(str_value) > max_length:
        return str_value[: max_length - 3] + "..."
    return str_value


def get_inst_display_name(
    inst: dict[str, Any] | None,
    fallback_id: int | str | None = None,
) -> str:
    """
    获取实例的展示名称，按优先级尝试 inst_name → ip_addr → id。

    Args:
        inst: 实例字典，可为 None
        fallback_id: 当 inst 为空或无有效字段时使用的回退 ID

    Returns:
        实例展示名称
    """
    if inst:
        name = inst.get("inst_name") or inst.get("ip_addr")
        if name:
            return str(name)
    if fallback_id is not None:
        return str(fallback_id)
    return "(未知)"


def check_subscription_manage_permission(
    rule_organization: int,
    current_team: str | int | None,
    include_descendants: bool = True,
) -> bool:
    """
    检查当前用户是否有权限管理指定订阅规则。

    Args:
        rule_organization: 规则所属组织 ID
        current_team: 当前用户所属团队（从 Cookie 获取）
        include_descendants: 是否包含子组织权限检查，默认 True

    Returns:
        是否有管理权限

    规则：
    - include_descendants=True：当前组织及其所有子组织的规则都可管理
    - include_descendants=False：仅当前组织的规则可管理
    """
    if current_team in (None, ""):
        return False
    try:
        current_team_id = int(current_team)
    except (TypeError, ValueError):
        return False

    if include_descendants:
        from apps.system_mgmt.utils.group_utils import GroupUtils

        allowed_org_ids = GroupUtils.get_group_with_descendants(current_team_id)
        return rule_organization in allowed_org_ids

    return rule_organization == current_team_id
