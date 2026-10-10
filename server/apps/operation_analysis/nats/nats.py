# -- coding: utf-8 --
# @File: nats.py
# @Time: 2025/9/4 11:36
# @Author: windyzhao
from rest_framework.exceptions import PermissionDenied

import nats_client
from apps.operation_analysis.constants.constants import PERMISSION_DATASOURCE, PERMISSION_DIRECTORY
from apps.operation_analysis.nats.auth import verify_dashboard_request, verify_module_data_request
from apps.operation_analysis.services.directory_service import DictDirectoryService
from apps.rpc.system_mgmt import SystemMgmt


@nats_client.register
def get_operation_analysis_module_data_v2(module, child_module, page, page_size, group_id, _internal_auth=None):
    """版本化的签名查询入口，避免滚动发布时新 payload 被旧 handler 拒绝。"""

    request_params = verify_module_data_request(
        _internal_auth,
        module=module,
        child_module=child_module,
        page=page,
        page_size=page_size,
        group_id=group_id,
    )
    return DictDirectoryService.get_operation_analysis_module_data(**request_params)


@nats_client.register
def get_operation_analysis_module_list():
    """
    获取运维分析模块列表的NATS接口
    :return: 模块列表
    """
    result = [
        {
            "name": PERMISSION_DIRECTORY,
            "display_name": "目录",
            "children": [
                {"name": "dashboard", "display_name": "仪表盘"},
                {"name": "topology", "display_name": "拓扑图"},
                {"name": "architecture", "display_name": "架构图"},
            ],
        },
        {"name": PERMISSION_DATASOURCE, "display_name": "数据源", "children": []},
    ]
    return result


def _dashboard_group_ids(team_id: int, user_info) -> list[int]:
    """用用户名、域和 include_children 核对组织范围。对不上就拒绝。"""
    if not isinstance(user_info, dict):
        raise PermissionDenied("Operation analysis NATS authentication failed")
    username = user_info.get("user")
    domain = user_info.get("domain")
    include_children = user_info.get("include_children")
    if (
        not isinstance(username, str)
        or not username.strip()
        or not isinstance(domain, str)
        or not domain.strip()
        or type(include_children) is not bool
        or user_info.get("team") != team_id
    ):
        raise PermissionDenied("Operation analysis NATS authentication failed")
    scope = SystemMgmt().get_authorized_groups_scoped(
        {"username": username.strip(), "domain": domain.strip(), "current_team": team_id},
        include_children=include_children,
    )
    if not isinstance(scope, dict) or scope.get("result") is not True or not isinstance(scope.get("data"), list):
        raise PermissionDenied("Operation analysis NATS authentication failed")
    group_ids = []
    for item in scope["data"]:
        if type(item) is int and item > 0 and item not in group_ids:
            group_ids.append(item)
        elif isinstance(item, str) and item.isdecimal():
            parsed = int(item)
            if parsed > 0 and parsed not in group_ids:
                group_ids.append(parsed)
    if team_id not in group_ids:
        raise PermissionDenied("Operation analysis NATS authentication failed")
    return group_ids


@nats_client.register
def search_dashboard_data_sources(requirements, team_id, user_info=None, _internal_auth=None):
    from apps.operation_analysis.services.dashboard_proposal_service import list_visible_briefs, search_briefs

    verified_team = verify_dashboard_request(_internal_auth, team_id, "search_dashboard_data_sources")
    group_ids = _dashboard_group_ids(verified_team, user_info)
    items = requirements or []
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("requirements must be a list of objects")
    return {"candidates": search_briefs(items, list_visible_briefs(verified_team, group_ids))}


@nats_client.register
def prepare_dashboard_proposal(proposal, team_id, user_info=None, _internal_auth=None):
    from apps.operation_analysis.services.dashboard_proposal_service import list_visible_briefs
    from apps.operation_analysis.services.dashboard_proposal_service import prepare_dashboard_proposal as prepare

    verified_team = verify_dashboard_request(_internal_auth, team_id, "prepare_dashboard_proposal")
    group_ids = _dashboard_group_ids(verified_team, user_info)
    return prepare(proposal or {}, list_visible_briefs(verified_team, group_ids))
