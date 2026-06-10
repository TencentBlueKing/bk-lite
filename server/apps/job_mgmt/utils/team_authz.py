"""作业执行的团队归属授权校验工具（BL-NEW-002 水平越权修复）。

纯函数，无 Django / DB 依赖，便于单元测试。视图层在按 ID 加载
Script / Playbook / Target / DistributionFile 等对象后，用这里的
``is_team_authorized`` 校验对象的团队归属是否落在「当前用户授权团队」内，
防止 Team A 用户引用 Team B 的脚本 / 目标 / 文件越权执行。
"""
from __future__ import annotations


def normalize_team(value) -> set[int]:
    """把对象的 team 字段规整为 int 集合。

    兼容三种存储形态：
    - JSONField 列表（Script / Playbook / Target.team，如 ``[1, 2]``）
    - 单个整数（DistributionFile.team）
    - ``None`` / 空（无团队归属）→ 空集合
    """
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        result: set[int] = set()
        for item in value:
            try:
                result.add(int(item))
            except (TypeError, ValueError):
                continue
        return result
    try:
        return {int(value)}
    except (TypeError, ValueError):
        return set()


def normalize_authorized_team_ids(group_list) -> set[int]:
    """从用户的 ``group_list`` 提取其有权访问的团队 ID 集合。"""
    result: set[int] = set()
    for group in group_list or []:
        if isinstance(group, dict) and "id" in group:
            try:
                result.add(int(group["id"]))
            except (TypeError, ValueError):
                continue
    return result


def is_team_authorized(obj_team, authorized_team_ids) -> bool:
    """对象的团队归属是否落在授权团队集合内。

    Args:
        obj_team: 对象的 team 字段（list / int / None）。
        authorized_team_ids: 当前用户授权团队集合；``None`` 表示超管，放行一切。

    Returns:
        True 表示有权引用该对象。无团队归属（空）的对象对非超管一律拒绝
        （杜绝历史遗留的无 team 文件被任意引用）。
    """
    if authorized_team_ids is None:
        return True
    obj_teams = normalize_team(obj_team)
    if not obj_teams:
        return False
    return bool(obj_teams & set(authorized_team_ids))
