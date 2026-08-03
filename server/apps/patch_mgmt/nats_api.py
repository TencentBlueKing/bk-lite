"""补丁管理与系统管理数据权限交互的 NATS API。"""

import nats_client

from apps.core.utils.viewset_utils import build_json_membership_query
from apps.patch_mgmt.models import (
    GovernanceTask,
    Patch,
    PatchBaseline,
    PatchSource,
    PatchTarget,
)


@nats_client.register
def get_patch_mgmt_module_list():
    return [
        {"name": "patch", "display_name": "补丁库"},
        {"name": "patch_target", "display_name": "目标管理"},
        {"name": "patch_source", "display_name": "补丁源"},
        {"name": "patch_baseline", "display_name": "基线管理"},
        {"name": "patch_governance", "display_name": "治理任务"},
        {"name": "patch_risk", "display_name": "风险治理"},
        {"name": "patch_dashboard", "display_name": "补丁看板"},
    ]


@nats_client.register
def get_patch_mgmt_module_data(
    module, child_module, page, page_size, group_id, *, team=None
):
    """返回数据权限规则可选的补丁管理实例。"""
    del child_module

    model_map = {
        "patch": (Patch, "title"),
        "patch_target": (PatchTarget, "name"),
        "patch_source": (PatchSource, "name"),
        "patch_baseline": (PatchBaseline, "name"),
        "patch_governance": (GovernanceTask, "name"),
    }
    model_config = model_map.get(module)
    if model_config is None and module not in {"patch_risk", "patch_dashboard"}:
        return {"result": False, "message": f"Unknown module: {module}"}

    try:
        normalized_group_id = int(group_id)
        normalized_page = max(int(page), 1)
        normalized_page_size = min(max(int(page_size), 1), 500)
    except (TypeError, ValueError):
        return {
            "result": False,
            "message": "group_id, page and page_size must be integers",
        }

    authorized_team_ids = {
        int(team_id)
        for team_id in (team or [])
        if str(team_id).isdigit()
    }
    if normalized_group_id not in authorized_team_ids:
        return {"result": False, "message": "无权访问该组织数据"}

    # 风险治理和看板是聚合视图，不存在可独立授权的实例 ID。
    if module in {"patch_risk", "patch_dashboard"}:
        return {"count": 0, "items": []}

    model, name_field = model_config
    queryset = model.objects.filter(
        build_json_membership_query(
            model.objects.all(), "team", [normalized_group_id]
        )
    ).order_by("id")
    start = (normalized_page - 1) * normalized_page_size
    rows = queryset.values("id", name_field)[
        start : start + normalized_page_size
    ]
    return {
        "count": queryset.count(),
        "items": [
            {"id": row["id"], "name": row[name_field]} for row in rows
        ],
    }
