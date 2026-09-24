from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.workflow_orchestration.models import TriggerInvocation, Workflow, WorkflowExecution

EXECUTION_LIST_URL = "/api/v1/workflow_orchestration/api/executions/"


def _tasks(tasks):
    for task in tasks:
        yield task
        for branch in (task.get("decisionCases") or {}).values():
            yield from _tasks(branch)


@pytest.mark.django_db
def test_demo_command_rebuilds_seven_workflows_and_visible_scenarios(api_client, authenticated_user, mocker):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=("is_superuser",))
    api_client.cookies["current_team"] = "1"
    arguments = {
        "team_id": 1,
        "username": authenticated_user.username,
        "domain": authenticated_user.domain,
        "confirm": True,
        "stdout": StringIO(),
    }

    conductor = mocker.patch("apps.workflow_orchestration.management.commands.seed_workflow_orchestration_demo.ConductorClient").return_value
    mocker.patch(
        "apps.workflow_orchestration.management.commands.seed_workflow_orchestration_demo.seed_builtin_health_template_snapshot",
        side_effect=lambda fmt, team_id, store=None: {
            "object_key": f"workflow-orchestration/templates/demo/team-{team_id}/health.{fmt}",
            "format": fmt,
            "sha256": "a" * 64,
            "size": 128,
            "filename_prefix": f"health-inspection-{fmt}",
        },
    )

    call_command("seed_workflow_orchestration_demo", **arguments)
    previous = WorkflowExecution.objects.get(trigger_id="health-word-success")
    child = WorkflowExecution.objects.create(
        workflow=previous.workflow,
        workflow_version=1,
        conductor_workflow_id="old-demo-rerun",
        team=[1],
        parent_execution=previous,
    )
    trigger = previous.workflow.triggers.first()
    TriggerInvocation.objects.create(
        trigger=trigger,
        execution=child,
        team=[1],
        idempotency_key="old-demo-invocation",
        expires_at=previous.created_at,
    )
    call_command("seed_workflow_orchestration_demo", **arguments)

    response = api_client.get(EXECUTION_LIST_URL, {"query": "[TDD/BDD]", "page_size": 100})
    assert response.status_code == 200
    assert response.data["count"] == 11
    assert {item["status"] for item in response.data["items"]} == {"SUCCEEDED", "FAILED", "WAITING_APPROVAL"}
    workflows = Workflow.objects.filter(name__startswith="[TDD/BDD]")
    assert set(workflows.values_list("name", flat=True)) == {
        "[TDD/BDD] 主机健康巡检 Word",
        "[TDD/BDD] 主机健康巡检 Excel",
        "[TDD/BDD] 生产变更审批",
        "[TDD/BDD] Webhook 同步响应",
        "[TDD/BDD] 定时 HTTP 检查",
        "[TDD/BDD] NATS 事件通知",
        "[TDD/BDD] 多入口通知",
    }
    atom_keys = {task["name"] for workflow in workflows for task in _tasks(workflow.definition["tasks"]) if task["type"] == "SIMPLE"}
    assert atom_keys == {
        "bklite_document_render",
        "bklite_http_request",
        "bklite_job_execute",
        "bklite_notification",
    }
    health_word = workflows.get(name="[TDD/BDD] 主机健康巡检 Word")
    health_excel = workflows.get(name="[TDD/BDD] 主机健康巡检 Excel")
    assert [task["name"] for task in health_word.definition["tasks"]] == [
        "bklite_job_execute",
        "bklite_document_render",
        "bklite_notification",
    ]
    assert health_word.definition["tasks"][1]["inputParameters"]["template_snapshot"]["format"] == "docx"
    assert health_excel.definition["tasks"][1]["inputParameters"]["template_snapshot"]["format"] == "xlsx"
    health_execution = WorkflowExecution.objects.get(trigger_id="health-word-success")
    assert health_execution.output["job"]["results"][0]["target"]["ip"] == "10.10.90.120"
    health_data = health_execution.output["job"]["results"][0]["data"]
    assert {metric["category"] for metric in health_data["metrics"]} >= {"CPU", "内存", "磁盘", "网络"}
    assert all(
        {
            "object_type",
            "object_name",
            "dimensions",
            "metric_name",
            "value",
            "unit",
            "warning_threshold",
            "critical_threshold",
            "health_status",
            "collected_at",
            "detail",
        }.issubset(metric)
        for metric in health_data["metrics"]
    )
    pending = WorkflowExecution.objects.get(status=WorkflowExecution.Status.WAITING_APPROVAL)
    assert pending.interactions.get().candidate_users == [authenticated_user.username]
    assert conductor.register_task_definitions.call_count == 2
    assert conductor.register_workflow.call_count == 14
    registered_health = next(call.args[0] for call in conductor.register_workflow.call_args_list if call.args[0]["name"] == health_word.engine_name)
    assert registered_health["tasks"][0]["inputParameters"]["script_content"]
    assert "assessment_rules" not in registered_health["tasks"][0]["inputParameters"]
    multi_trigger = workflows.get(name="[TDD/BDD] 多入口通知")
    assert set(multi_trigger.triggers.values_list("trigger_type", flat=True)) == {"FORM", "WEBHOOK", "SCHEDULE"}
    multi_executions = WorkflowExecution.objects.filter(workflow=multi_trigger)
    assert multi_executions.count() == 3
    assert set(multi_executions.values_list("trigger_type", flat=True)) == {"FORM", "WEBHOOK", "SCHEDULE"}
    assert set(multi_executions.values_list("trigger_id", flat=True)) == {str(trigger.id) for trigger in multi_trigger.triggers.all()}


@pytest.mark.django_db
def test_demo_command_rejects_unknown_page_viewer():
    with pytest.raises(CommandError, match="找不到页面查看用户"):
        call_command(
            "seed_workflow_orchestration_demo",
            team_id=1,
            username="missing-user",
            domain="domain.com",
            confirm=True,
            stdout=StringIO(),
        )


@pytest.mark.django_db
def test_demo_command_rejects_team_not_visible_to_page_viewer(authenticated_user):
    authenticated_user.group_list = [{"id": 1, "name": "Default"}]
    authenticated_user.save(update_fields=("group_list",))

    with pytest.raises(CommandError, match="页面查看用户无权访问团队"):
        call_command(
            "seed_workflow_orchestration_demo",
            team_id=2,
            username=authenticated_user.username,
            domain=authenticated_user.domain,
            confirm=True,
            stdout=StringIO(),
        )
