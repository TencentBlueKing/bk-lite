"""作业管理统一 OpenAPI 端点。"""

import os

from apps.core.openapi.decorators import openapi_expose
from apps.job_mgmt.openapi_serializers import TargetListV2RequestSerializer
from apps.job_mgmt.services.target_list_v2 import query_target_list_v2
from apps.job_mgmt.utils.team_authz import normalize_team
from apps.system_mgmt.utils.group_utils import GroupUtils


@openapi_expose(
    path="job-mgmt/targets-v2",
    method="POST",
    schema=TargetListV2RequestSerializer,
    inject="team_list",
    permission="target-View",
    permission_app="job",
    summary="按调用方授权组织键集分页查询作业目标（最多 100 条）",
)
def openapi_target_list_v2(name="", ip="", os_type="", page_size=20, cursor=None, *, team=None):
    """由统一网关认证、审计并注入不可伪造的精确团队集合。"""
    if os.getenv("JOB_TARGET_LIST_V2_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        return {"result": False, "message": "target list v2 is not enabled"}
    caller_team = set(GroupUtils.active_queryset(id__in=normalize_team(team)).values_list("id", flat=True))
    if not caller_team:
        return {"result": False, "message": "无权访问该组织：用户未关联活动团队"}
    result = query_target_list_v2(
        {"name": name, "ip": ip, "os_type": os_type, "page_size": page_size, "cursor": cursor},
        caller_team,
    )
    if not result.get("result"):
        return result
    return result.get("data") or {}
