from apps.core.openapi.decorators import openapi_expose
from apps.core.utils.viewset_utils import build_json_membership_query
from apps.workflow.models import WorkflowTrigger
from apps.workflow.openapi_serializers import WorkflowTriggerInvokeRequestSerializer, WorkflowWebhookTestRequestSerializer
from apps.workflow.permissions import actor_can_operate_workflow_for_teams
from apps.workflow.services.conductor import ConductorClient, ConductorUnavailable
from apps.workflow.services.definitions import DefinitionValidationError
from apps.workflow.services.triggers import TriggerConflict, invoke_trigger
from apps.workflow.services.validation_messages import render_definition_error, render_known_message, render_workflow_error
from apps.workflow.services.webhook_contracts import WebhookResponseError, wait_for_webhook_response
from apps.workflow.services.webhook_test_sessions import WebhookTestSessionError, capture_webhook_test_event


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
