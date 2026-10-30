"""作业管理统一 OpenAPI 端点。"""

import os

from apps.core.logger import job_logger as logger
from apps.core.openapi.decorators import openapi_expose
from apps.job_mgmt.constants import CallbackType
from apps.job_mgmt.models import JobExecution, Script
from apps.job_mgmt.nats_api import _run_script_execute, _validate_openapi_target_scope, job_detail_query, job_list, job_status_batch_query
from apps.job_mgmt.openapi_serializers import (
    AsyncAcceptedSerializer,
    AsyncScriptExecuteRequestSerializer,
    JobDetailRequestSerializer,
    JobStatusRequestSerializer,
    ScriptExecuteRequestSerializer,
    ScriptListRequestSerializer,
    ScriptListResponseSerializer,
    TargetListV2RequestSerializer,
)
from apps.job_mgmt.services.target_list_v2 import query_target_list_v2
from apps.job_mgmt.utils.i18n import job_message
from apps.job_mgmt.utils.team_authz import is_team_authorized, normalize_team
from apps.system_mgmt.utils.group_utils import GroupUtils


def _require_single_active_team(team):
    authorized_team_ids = normalize_team(team)
    authorized_team_id = next(iter(authorized_team_ids), None)
    if len(authorized_team_ids) != 1 or not GroupUtils.active_queryset(id=authorized_team_id).exists():
        return None, {
            "result": False,
            "message": job_message(None, "error.user_no_active_team", "User is not associated with an active team"),
        }
    return authorized_team_id, None


def _apply_library_script(payload, authorized_team_id):
    """按脚本库 ID 填充执行正文；调用方传入的 script_content/script_type 不生效。"""
    script_id = payload.get("script_id")
    if not script_id:
        return payload, None
    script = Script.objects.filter(id=script_id).first()
    if not script or not is_team_authorized(script.team, {authorized_team_id}):
        return None, {
            "result": False,
            "message": job_message(None, "error.script_not_found", "Script not found: id={id}", id=script_id),
        }
    resolved = dict(payload)
    resolved["script_type"] = script.script_type
    resolved["script_content"] = script.content
    resolved["timeout"] = script.timeout
    if not (resolved.get("name") or "").strip():
        resolved["name"] = script.name
    return resolved, None


@openapi_expose(
    path="job-mgmt/scripts",
    method="POST",
    schema=ScriptListRequestSerializer,
    response_schema=ScriptListResponseSerializer,
    inject="team_list",
    summary="分页查询当前授权组织的脚本库作业（不含脚本内容；组织口径：API 令牌绑定组织精确匹配，不级联子组织）",
)
def openapi_script_list(name="", page=1, page_size=20, *, team=None):
    """供第三方（如 ITSM 下拉）选择可执行脚本；id 为字符串，执行时回传 script_id。"""
    authorized_team_id, error = _require_single_active_team(team)
    if error:
        return error

    result = job_list({"team": [authorized_team_id], "name": name, "page": page, "page_size": page_size})
    if not result.get("result"):
        return result
    scripts = (result.get("data") or {}).get("scripts") or {}
    items = []
    for item in scripts.get("items") or []:
        items.append(
            {
                "id": str(item.get("id") or ""),
                "name": item.get("name") or "",
                "description": item.get("description") or "",
                "script_type": item.get("script_type") or "",
                "timeout": item.get("timeout") or 60,
                "is_built_in": bool(item.get("is_built_in")),
            }
        )
    return {"count": scripts.get("count") or 0, "items": items}


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
        return {
            "result": False,
            "message": job_message(
                None,
                "error.org_access_no_active_team",
                "No access to this organization: user is not associated with an active team",
            ),
        }
    result = query_target_list_v2(
        {"name": name, "ip": ip, "os_type": os_type, "page_size": page_size, "cursor": cursor},
        caller_team,
    )
    if not result.get("result"):
        return result
    return result.get("data") or {}


@openapi_expose(
    path="job-mgmt/script-execute",
    method="POST",
    schema=ScriptExecuteRequestSerializer,
    inject="team_list_with_user",
    summary="提交脚本执行作业（组织口径：API 令牌绑定组织精确匹配，不级联子组织）",
)
def openapi_script_execute(
    name="",
    target_source="",
    target_list=None,
    script_type="",
    script_content="",
    params=None,
    timeout=600,
    script_id=None,
    *,
    team=None,
    user_info=None,
):
    """经统一网关绑定可信组织后复用脚本执行实现。"""
    authorized_team_id, error = _require_single_active_team(team)
    if error:
        return error

    payload, resolve_error = _apply_library_script(
        {
            "name": name,
            "target_source": target_source,
            "target_list": target_list or [],
            "script_type": script_type,
            "script_content": script_content,
            "params": params or [],
            "timeout": timeout,
            "script_id": script_id,
        },
        authorized_team_id,
    )
    if resolve_error:
        return resolve_error

    scope_error = _validate_openapi_target_scope(payload["target_source"], payload["target_list"], {authorized_team_id})
    if scope_error:
        id_field = "target_id" if payload["target_source"] == "manual" else "node_id"
        target_ids = [item.get(id_field) for item in payload["target_list"]]
        logger.warning(
            "[openapi_script_execute] scope rejected: user=%s domain=%s team=%s " "target_source=%s target_count=%s target_ids=%s reason=%s",
            (user_info or {}).get("user", ""),
            (user_info or {}).get("domain", ""),
            authorized_team_id,
            payload["target_source"],
            len(target_ids),
            target_ids[:20],
            scope_error,
        )
        return {"result": False, "message": scope_error}

    result = _run_script_execute(
        {
            "name": payload["name"],
            "target_source": payload["target_source"],
            "target_list": payload["target_list"],
            "script_type": payload["script_type"],
            "script_content": payload["script_content"],
            "params": payload["params"] or [],
            "timeout": payload["timeout"],
            "team": [authorized_team_id],
            "callback_type": CallbackType.WEB,
            "callback_url": "",
        },
        trusted_actor=user_info,
    )
    if not result.get("result"):
        return result
    return result.get("data") or {}


@openapi_expose(
    path="job-mgmt/script-execute-async",
    method="POST",
    schema=AsyncScriptExecuteRequestSerializer,
    response_schema=AsyncAcceptedSerializer,
    inject="team_list_with_user",
    summary="异步提交脚本执行，完成后经网关回调调用方（组织口径：API 令牌绑定组织精确匹配，不级联子组织）",
)
def openapi_script_execute_async(
    name="",
    target_source="",
    target_list=None,
    script_type="",
    script_content="",
    params=None,
    timeout=600,
    callback_context=None,
    script_id=None,
    *,
    team=None,
    user_info=None,
):
    """经统一网关绑定可信组织后提交脚本，终态按 callback_context 回传。"""
    authorized_team_id, error = _require_single_active_team(team)
    if error:
        return error

    payload, resolve_error = _apply_library_script(
        {
            "name": name,
            "target_source": target_source,
            "target_list": target_list or [],
            "script_type": script_type,
            "script_content": script_content,
            "params": params or [],
            "timeout": timeout,
            "script_id": script_id,
        },
        authorized_team_id,
    )
    if resolve_error:
        return resolve_error

    scope_error = _validate_openapi_target_scope(payload["target_source"], payload["target_list"], {authorized_team_id})
    if scope_error:
        id_field = "target_id" if payload["target_source"] == "manual" else "node_id"
        target_ids = [item.get(id_field) for item in payload["target_list"]]
        logger.warning(
            "[openapi_script_execute_async] scope rejected: user=%s domain=%s team=%s " "target_source=%s target_count=%s target_ids=%s reason=%s",
            (user_info or {}).get("user", ""),
            (user_info or {}).get("domain", ""),
            authorized_team_id,
            payload["target_source"],
            len(target_ids),
            target_ids[:20],
            scope_error,
        )
        return {"result": False, "message": scope_error}

    result = _run_script_execute(
        {
            "name": payload["name"],
            "target_source": payload["target_source"],
            "target_list": payload["target_list"],
            "script_type": payload["script_type"],
            "script_content": payload["script_content"],
            "params": payload["params"] or [],
            "timeout": payload["timeout"],
            "team": [authorized_team_id],
            "callback_type": CallbackType.WEB,
            "callback_url": "",
            "async_callback_context": callback_context,
        },
        trusted_actor=user_info,
    )
    if not result.get("result"):
        return result
    data = result.get("data") or {}
    if data.get("accepted") is True:
        return {"accepted": True, "execution_id": str(data.get("execution_id") or "")}
    return {"accepted": True, "execution_id": str(data.get("task_id") or "")}


@openapi_expose(
    path="job-mgmt/job-status",
    method="POST",
    schema=JobStatusRequestSerializer,
    inject="team_list",
    summary="批量查询作业状态（跨组织任务按不存在返回；组织口径：API 令牌绑定组织精确匹配，不级联子组织）",
)
def openapi_job_status(task_ids, *, team=None):
    """经统一网关绑定可信组织后查询作业状态，非本组织任务伪装为不存在。"""
    authorized_team_id, error = _require_single_active_team(team)
    if error:
        return error

    result = job_status_batch_query({"task_ids": task_ids})
    if not result.get("result"):
        return result

    owned_ids = {
        execution.id for execution in JobExecution.objects.filter(id__in=task_ids) if is_team_authorized(execution.team, {authorized_team_id})
    }
    items = []
    for item in result.get("data") or []:
        task_id = item.get("task_id")
        if task_id not in owned_ids:
            items.append({"task_id": task_id, "status": "not_found"})
        else:
            items.append(item)
    return items


@openapi_expose(
    path="job-mgmt/job-detail",
    method="GET",
    schema=JobDetailRequestSerializer,
    inject="team_list",
    summary="查询作业执行详情（跨组织与不存在统一按不存在返回；组织口径：API 令牌绑定组织精确匹配，不级联子组织）",
)
def openapi_job_detail(task_id, *, team=None):
    """经统一网关绑定可信组织后查询作业详情，跨组织与不存在不区分。"""
    authorized_team_id, error = _require_single_active_team(team)
    if error:
        return error

    result = job_detail_query({"task_id": task_id, "team": [authorized_team_id]})
    if not result.get("result"):
        return {"result": False, "message": job_message(None, "error.task_not_found", "Task not found")}
    return result.get("data") or {}
