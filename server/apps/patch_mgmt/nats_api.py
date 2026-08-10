"""补丁管理与系统管理数据权限交互的 NATS API。"""

import nats_client

from apps.core.utils.viewset_utils import build_json_membership_query
from apps.patch_mgmt.models import PatchTarget


@nats_client.register
def get_patch_mgmt_module_list():
    return [{"name": "patch_target", "display_name": "目标管理"}]


@nats_client.register
def get_patch_mgmt_module_data(
    module, child_module, page, page_size, group_id, *, team=None
):
    """返回数据权限规则可选的补丁管理实例。"""
    del child_module

    if module != "patch_target":
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

    queryset = PatchTarget.objects.filter(
        build_json_membership_query(
            PatchTarget.objects.all(), "team", [normalized_group_id]
        )
    )
    queryset = queryset.order_by("id")
    start = (normalized_page - 1) * normalized_page_size
    rows = queryset.values("id", "name")[
        start : start + normalized_page_size
    ]
    return {
        "count": queryset.count(),
        "items": [
            {"id": row["id"], "name": row["name"]} for row in rows
        ],
    }
