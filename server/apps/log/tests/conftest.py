"""Log 模块测试沿用仓库级 Django fixtures，并隔离 system_mgmt RPC 边界。"""

import pytest


@pytest.fixture(autouse=True)
def _stub_system_mgmt_team_scope(monkeypatch):
    """权限范围仍走公开 service，只把跨服务 RPC 替换为确定性响应。"""

    def authorized_groups(_self, actor_context, include_children=False):
        return {"result": True, "data": [int(actor_context["current_team"])]}

    def assignable_groups(_self, actor_context):
        group_ids = []
        for group in actor_context.get("group_list", []):
            group_id = group.get("id") if isinstance(group, dict) else group
            if group_id is not None:
                group_ids.append(int(group_id))
        return {"result": True, "data": group_ids or [1]}

    monkeypatch.setattr(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        authorized_groups,
    )
    monkeypatch.setattr(
        "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
        assignable_groups,
    )
