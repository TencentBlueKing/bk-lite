import pytest
from django.utils import timezone

from apps.console_mgmt.models import Notification
from apps.workflow_orchestration.models import Workflow, WorkflowExecution, WorkflowInteraction
from apps.workflow_orchestration.services.executions import apply_remote_execution, sync_active_executions


@pytest.mark.django_db
def test_background_sync_discovers_pending_approval_without_opening_execution_detail(
    mocker,
    django_capture_on_commit_callbacks,
):
    workflow = Workflow.objects.create(name="审批流程", team=[7], definition={})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="conductor-1",
        status=WorkflowExecution.Status.RUNNING,
        team=[7],
        started_by="starter",
    )
    conductor = mocker.Mock()
    conductor.get_execution.return_value = {
        "status": "RUNNING",
        "tasks": [
            {
                "taskId": "human-1",
                "referenceTaskName": "approval",
                "taskType": "HUMAN",
                "status": "IN_PROGRESS",
                "inputData": {
                    "interactionType": "APPROVAL",
                    "title": "发布确认",
                    "candidates": ["alice"],
                    "publicContext": {"environment": "prod"},
                },
            }
        ],
    }

    with django_capture_on_commit_callbacks(execute=True):
        summary = sync_active_executions(client=conductor)

    execution.refresh_from_db()
    interaction = WorkflowInteraction.objects.get(execution=execution)
    assert summary == {"synchronized": 1, "failed": 0}
    assert execution.status == WorkflowExecution.Status.WAITING_APPROVAL
    assert interaction.candidate_users == ["alice"]
    notification = Notification.objects.get(event_key=f"workflow_approval:{interaction.id}")
    assert notification.recipient_usernames == ["alice"]
    assert notification.app_module == "workflow-orchestration"
    assert notification.source == "workflow_approval"
    assert notification.target_url == "/workflow-orchestration/executions?scope=mine"

    with django_capture_on_commit_callbacks(execute=True):
        apply_remote_execution(execution, conductor.get_execution.return_value)

    assert Notification.objects.filter(event_key=f"workflow_approval:{interaction.id}").count() == 1


@pytest.mark.django_db
def test_completed_with_warnings_is_success_with_warning_metadata():
    workflow = Workflow.objects.create(name="健康巡检", team=[7], definition={})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="conductor-warning",
        status=WorkflowExecution.Status.RUNNING,
        team=[7],
    )

    apply_remote_execution(
        execution,
        {
            "status": "COMPLETED",
            "output": {},
            "tasks": [{"outputData": {"summary": {"failed": 2}}}],
            "endTime": 1_700_000_000_000,
        },
    )

    execution.refresh_from_db()
    assert execution.status == WorkflowExecution.Status.SUCCEEDED
    assert execution.has_warnings is True
    assert execution.warning_count == 2


@pytest.mark.django_db
def test_remote_non_terminal_does_not_overwrite_terminating_or_terminal_status():
    workflow = Workflow.objects.create(name="终止保护", team=[7], definition={})
    terminating = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="conductor-terminating",
        status=WorkflowExecution.Status.TERMINATING,
        team=[7],
    )
    succeeded = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="conductor-succeeded",
        status=WorkflowExecution.Status.SUCCEEDED,
        team=[7],
        finished_at=timezone.now(),
    )
    remote_running = {
        "status": "RUNNING",
        "output": {"partial": True},
        "tasks": [
            {
                "taskId": "human-1",
                "referenceTaskName": "approval",
                "taskType": "HUMAN",
                "status": "IN_PROGRESS",
                "inputData": {
                    "title": "不应覆盖",
                    "candidates": ["alice"],
                },
            }
        ],
    }

    apply_remote_execution(terminating, remote_running)
    apply_remote_execution(succeeded, remote_running)

    terminating.refresh_from_db()
    succeeded.refresh_from_db()
    assert terminating.status == WorkflowExecution.Status.TERMINATING
    assert succeeded.status == WorkflowExecution.Status.SUCCEEDED
    assert terminating.output == {"partial": True}


@pytest.mark.django_db
def test_remote_terminal_can_finalize_terminating_execution():
    workflow = Workflow.objects.create(name="终止完成", team=[7], definition={})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="conductor-finalize",
        status=WorkflowExecution.Status.TERMINATING,
        team=[7],
    )

    apply_remote_execution(
        execution,
        {"status": "TERMINATED", "output": {}, "tasks": [], "endTime": 1_700_000_000_000, "reasonForIncompletion": "cancelled"},
    )

    execution.refresh_from_db()
    assert execution.status == WorkflowExecution.Status.TERMINATED
    assert execution.finished_at is not None
