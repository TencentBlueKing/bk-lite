import pytest
from django.test import override_settings

from apps.workflow_orchestration.models import Workflow, WorkflowExecution, WorkflowTrigger, WorkflowVersion
from apps.workflow_orchestration.openapi_api import openapi_workflow_trigger, openapi_workflow_webhook_test
from apps.workflow_orchestration.services.webhook_test_sessions import create_webhook_test_session, wait_for_webhook_test_event


@pytest.mark.django_db
def test_openapi_trigger_uses_trusted_team_and_rejects_other_tenant(mocker):
    workflow = Workflow.objects.create(name="API 流程", team=[7], definition={"tasks": []}, current_version=1, status=Workflow.Status.PUBLISHED)
    trigger = WorkflowTrigger.objects.create(workflow=workflow, name="API", trigger_type=WorkflowTrigger.Type.WEBHOOK, enabled=True, team=[7])
    invoke = mocker.patch("apps.workflow_orchestration.openapi_api.invoke_trigger")
    execution = WorkflowExecution.objects.create(workflow=workflow, workflow_version=1, team=[7])
    invoke.return_value = (execution, True)

    allowed = openapi_workflow_trigger(
        str(trigger.id),
        "evt-1",
        {"message": "ok"},
        team=[7],
        user_info={"user": "alice", "domain": "example.com"},
    )
    denied = openapi_workflow_trigger(
        str(trigger.id),
        "evt-2",
        {"message": "no"},
        team=[8],
        user_info={"user": "mallory", "domain": "example.com"},
    )

    assert allowed["execution_id"] == str(execution.id)
    assert denied == {"result": False, "message": "触发器不存在或不属于调用方组织"}
    assert invoke.call_count == 1


@pytest.mark.django_db
def test_openapi_wait_webhook_returns_selected_task_output(mocker):
    workflow = Workflow.objects.create(name="同步 API", team=[7], definition={"tasks": []}, current_version=1, status=Workflow.Status.PUBLISHED)
    metadata = {
        "trigger_nodes": [{"id": "trigger_webhook", "trigger_type": "WEBHOOK", "config": {"response_mode": "WAIT"}}],
        "return_nodes": [{"id": "return_webhook", "return_type": "WEBHOOK", "config": {"body": "${report.output.result}"}}],
        "edges": [
            {"source": "trigger_webhook", "target": "report"},
            {"source": "report", "target": "return_webhook"},
        ],
    }
    WorkflowVersion.objects.create(workflow=workflow, version=1, definition={"tasks": []}, canvas_metadata=metadata)
    trigger = WorkflowTrigger.objects.create(
        workflow=workflow,
        node_key="trigger_webhook",
        name="API",
        trigger_type=WorkflowTrigger.Type.WEBHOOK,
        enabled=True,
        team=[7],
        config={"response_mode": "WAIT"},
    )
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="conductor-1",
        status=WorkflowExecution.Status.RUNNING,
        team=[7],
    )
    mocker.patch("apps.workflow_orchestration.openapi_api.invoke_trigger", return_value=(execution, True))
    conductor = mocker.patch("apps.workflow_orchestration.openapi_api.ConductorClient").return_value
    conductor.get_execution.return_value = {
        "status": "COMPLETED",
        "output": {},
        "tasks": [{"referenceTaskName": "report", "status": "COMPLETED", "outputData": {"result": {"download_url": "/reports/1"}}}],
    }

    result = openapi_workflow_trigger(
        str(trigger.id),
        "evt-sync-1",
        {"body": {"host": "10.0.0.8"}},
        team=[7],
        user_info={"user": "alice", "domain": "example.com"},
    )

    assert result == {
        "execution_id": str(execution.id),
        "created": True,
        "status": "SUCCEEDED",
        "response": {"download_url": "/reports/1"},
    }


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "webhook-test-sessions"}})
@pytest.mark.django_db
def test_webhook_test_session_captures_body_only_for_its_tenant():
    session = create_webhook_test_session(team_id=7, workflow_id=1, node_key="trigger_webhook")

    denied = openapi_workflow_webhook_test(
        session["token"],
        {"host": "other"},
        team=[8],
        user_info={"user": "mallory", "domain": "example.com"},
    )
    allowed = openapi_workflow_webhook_test(
        session["token"],
        {"host": "10.0.0.8", "severity": "critical"},
        team=[7],
        user_info={"user": "alice", "domain": "example.com"},
    )

    assert denied == {"result": False, "message": "Webhook 测试会话不属于调用方组织"}
    assert allowed == {"captured": True}
    assert wait_for_webhook_test_event(session["token"], timeout_seconds=0.1) == {"body": {"host": "10.0.0.8", "severity": "critical"}}
