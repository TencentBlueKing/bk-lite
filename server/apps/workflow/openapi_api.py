import hashlib
from datetime import timedelta

from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone

from apps.core.openapi.decorators import openapi_expose
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.core.utils.viewset_utils import build_json_membership_query
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.workflow.models import Workflow, WorkflowExecution, WorkflowTrigger, WorkflowVersion
from apps.workflow.openapi_serializers import (
    WorkflowExecuteAsyncRequestSerializer,
    WorkflowExecuteAsyncResponseSerializer,
    WorkflowListRequestSerializer,
    WorkflowListResponseSerializer,
    WorkflowTriggerInvokeRequestSerializer,
    WorkflowWebhookTestRequestSerializer,
)
from apps.workflow.permissions import actor_can_operate_workflow_for_teams
from apps.workflow.services.conductor import ConductorClient, ConductorUnavailable, ExecutionStartUnknown
from apps.workflow.services.definitions import DefinitionValidationError, validate_workflow_inputs
from apps.workflow.services.launch_plans import extract_target_fields
from apps.workflow.services.runtime import start_execution
from apps.workflow.services.triggers import TriggerConflict, invoke_trigger
from apps.workflow.services.validation_messages import render_definition_error, render_known_message, render_workflow_error
from apps.workflow.services.webhook_contracts import WebhookResponseError, wait_for_webhook_response
from apps.workflow.services.webhook_test_sessions import WebhookTestSessionError, capture_webhook_test_event


def _require_single_active_team(team):
    teams = [item for item in (team or []) if isinstance(item, int) and not isinstance(item, bool)]
    authorized_team_id = teams[0] if len(teams) == 1 else None
    if authorized_team_id is None or not GroupUtils.active_queryset(id=authorized_team_id).exists():
        return None, {"result": False, "message": render_known_message(None, "调用方未绑定有效组织")}
    return authorized_team_id, None


@openapi_expose(
    path="workflow/trigger",
    method="POST",
    schema=WorkflowTriggerInvokeRequestSerializer,
    inject="team_list_with_user",
    permission="workflow-Execute",
    permission_app="workflow",
    summary="使用已配置 Webhook 触发器启动编排中心流程",
)
def openapi_workflow_trigger(trigger_id, idempotency_key, inputs=None, *, team=None, user_info=None):
    teams = [item for item in (team or []) if isinstance(item, int) and not isinstance(item, bool)]
    queryset = WorkflowTrigger.objects.select_related("workflow").filter(
        trigger_type=WorkflowTrigger.Type.WEBHOOK,
        enabled=True,
        workflow__deleted_at__isnull=True,
    )
    trigger = queryset.filter(build_json_membership_query(queryset, "team", teams), pk=trigger_id).first()
    if trigger is None:
        return {"result": False, "message": render_known_message(None, "触发器不存在或不属于调用方组织")}
    username = str((user_info or {}).get("user") or "openapi")[:32]
    domain = str((user_info or {}).get("domain") or "domain.com")[:100]
    if not actor_can_operate_workflow_for_teams(
        username=username,
        domain=domain,
        team_ids=teams,
        workflow=trigger.workflow,
    ):
        return {"result": False, "message": render_known_message(None, "缺少流程实例操作权限")}
    client = ConductorClient()
    try:
        execution, created = invoke_trigger(
            trigger,
            inputs=inputs or {},
            idempotency_key=idempotency_key,
            started_by=username,
            domain=domain,
            client=client,
        )
        if trigger.config.get("response_mode", "IMMEDIATE") == "WAIT":
            response = wait_for_webhook_response(execution, trigger, client=client)
            return {"execution_id": str(execution.id), "created": created, "status": "SUCCEEDED", "response": response}
    except (DefinitionValidationError, TriggerConflict, ConductorUnavailable, WebhookResponseError) as error:
        return {
            "result": False,
            "message": render_definition_error(
                None,
                error,
                definition=trigger.workflow.definition,
                metadata=trigger.workflow.canvas_metadata,
            ),
        }
    return {"execution_id": str(execution.id), "created": created, "status": "ACCEPTED"}


@openapi_expose(
    path="workflow/webhook-test",
    method="POST",
    schema=WorkflowWebhookTestRequestSerializer,
    inject="team_list_with_user",
    permission="workflow-Execute",
    permission_app="workflow",
    summary="向编排中心 Webhook 临时监听会话发送测试请求",
)
def openapi_workflow_webhook_test(token, body=None, *, team=None, user_info=None):
    try:
        capture_webhook_test_event(token, body or {}, team_ids=list(team or []))
    except WebhookTestSessionError as error:
        return {"result": False, "message": render_workflow_error(None, error)}
    return {"captured": True}


@openapi_expose(
    path="workflow/workflows",
    method="POST",
    schema=WorkflowListRequestSerializer,
    response_schema=WorkflowListResponseSerializer,
    inject="team_list",
    summary="分页查询当前授权组织已发布且启用的编排中心流程",
)
def openapi_workflow_list(name="", page=1, page_size=20, *, team=None):
    """供第三方（如 ITSM 下拉）选择可执行流程；id 为字符串，执行时回传 workflow_id。"""
    authorized_team_id, error = _require_single_active_team(team)
    if error:
        return error

    queryset = Workflow.objects.filter(current_version__gt=0, enabled=True, status=Workflow.Status.PUBLISHED)
    queryset = queryset.filter(build_json_membership_query(queryset, "team", [authorized_team_id]))
    if (name or "").strip():
        query = name.strip()[:120]
        queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))
    total = queryset.count()
    start = (page - 1) * page_size
    items = []
    for workflow in queryset.order_by("-updated_at", "-id")[start : start + page_size]:
        items.append(
            {
                "id": str(workflow.id),
                "name": workflow.name,
                "description": workflow.description or "",
                "current_version": workflow.current_version,
                "enabled": workflow.enabled,
            }
        )
    return {"count": total, "items": items}


@openapi_expose(
    path="workflow/execute-async",
    method="POST",
    schema=WorkflowExecuteAsyncRequestSerializer,
    response_schema=WorkflowExecuteAsyncResponseSerializer,
    inject="team_list_with_user",
    permission="workflow-Execute",
    permission_app="workflow",
    summary="异步启动编排中心已发布流程，完成后经网关回调调用方",
)
def openapi_workflow_execute_async(workflow_id, callback_context, inputs=None, *, team=None, user_info=None):
    """经统一网关绑定可信组织后启动流程，终态按 callback_context 回传。"""
    authorized_team_id, error = _require_single_active_team(team)
    if error:
        return error

    async_ctx = callback_context if isinstance(callback_context, dict) else {}
    callback_url = (async_ctx.get("callback_url") or "").strip()
    callback_token = async_ctx.get("callback_token") or ""
    if not callback_url or not callback_token:
        return {"result": False, "message": render_known_message(None, "callback_context.callback_url 与 callback_token 必填")}
    try:
        SSRFValidator.validate_callback(callback_url)
    except SSRFError as exc:
        return {"result": False, "message": render_known_message(None, f"Invalid callback_url: {exc}")}

    try:
        numeric_id = int(str(workflow_id).strip())
    except (TypeError, ValueError):
        return {"result": False, "message": render_known_message(None, "流程不存在或不属于调用方组织")}

    queryset = Workflow.objects.filter(current_version__gt=0, enabled=True, status=Workflow.Status.PUBLISHED, pk=numeric_id)
    workflow = queryset.filter(build_json_membership_query(queryset, "team", [authorized_team_id])).first()
    if workflow is None:
        return {"result": False, "message": render_known_message(None, "流程不存在或不属于调用方组织")}

    username = str((user_info or {}).get("user") or "openapi")[:32]
    domain = str((user_info or {}).get("domain") or "domain.com")[:100]
    if not actor_can_operate_workflow_for_teams(
        username=username,
        domain=domain,
        team_ids=[authorized_team_id],
        workflow=workflow,
    ):
        return {"result": False, "message": render_known_message(None, "缺少流程实例操作权限")}

    callback_key = hashlib.sha256(str(callback_token).encode("utf-8")).hexdigest()
    existing = WorkflowExecution.objects.filter(async_callback_key=callback_key).first()
    if existing:
        if authorized_team_id not in (existing.team or []):
            return {"result": False, "message": render_known_message(None, "流程不存在或不属于调用方组织")}
        return {"accepted": True, "execution_id": str(existing.id)}

    version = WorkflowVersion.objects.filter(workflow=workflow, version=workflow.current_version).first()
    if version is None:
        return {"result": False, "message": render_known_message(None, "流程生效版本不存在")}
    try:
        if extract_target_fields(version.canvas_metadata):
            return {"result": False, "message": render_known_message(None, "该流程包含运行时主机目标字段，暂不支持通过 OpenAPI 启动")}
        sealed_inputs = validate_workflow_inputs(inputs or {}, version.canvas_metadata.get("input_schema") or {})
    except (DefinitionValidationError, ValueError) as error:
        return {"result": False, "message": render_workflow_error(None, error)}

    timeout_seconds = int(async_ctx.get("timeout") or 3600)
    callback_fields = {
        "async_callback_context": {
            "callback_url": callback_url,
            "callback_token": callback_token,
            "operator": async_ctx.get("operator") or "system",
            "timeout": timeout_seconds,
            "user": username,
            "domain": domain,
            "team_id": authorized_team_id,
        },
        "async_callback_deadline_at": timezone.now() + timedelta(seconds=timeout_seconds),
        "async_callback_key": callback_key,
    }
    try:
        execution = start_execution(
            workflow,
            inputs=sealed_inputs,
            started_by=username,
            domain=domain,
            client=ConductorClient(),
            version_number=version.version,
            trigger_type="FORM",
            trigger_id="openapi",
            **callback_fields,
        )
    except ExecutionStartUnknown as error:
        execution = error.execution
    except IntegrityError:
        existing = WorkflowExecution.objects.filter(async_callback_key=callback_key).first()
        if existing is None:
            raise
        if authorized_team_id not in (existing.team or []):
            return {"result": False, "message": render_known_message(None, "流程不存在或不属于调用方组织")}
        return {"accepted": True, "execution_id": str(existing.id)}
    except (DefinitionValidationError, ValueError) as error:
        return {"result": False, "message": render_workflow_error(None, error)}
    except ConductorUnavailable as error:
        return {"result": False, "message": render_workflow_error(None, error)}
    return {"accepted": True, "execution_id": str(execution.id)}
