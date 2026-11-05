from datetime import timedelta

import pytest
from django.utils import timezone

from apps.console_mgmt.models import Notification
from apps.workflow.models import Workflow, WorkflowExecution, WorkflowInteraction
from apps.workflow.services.executions import apply_remote_execution, sync_active_executions


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
    assert summary == {"synchronized": 1, "failed": 0, "reconciled": 0}
    assert execution.status == WorkflowExecution.Status.WAITING_APPROVAL
    assert interaction.candidate_users == ["alice"]
    notification = Notification.objects.get(event_key=f"workflow_approval:{interaction.id}")
    assert notification.recipient_usernames == ["alice"]
    assert notification.app_module == "workflow"
    assert notification.source == "workflow_approval"
    assert notification.target_url == (f"/workflow/executions/{execution.id}?scope=mine&node=approval&instance_id={interaction.id}")

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
def test_completed_workflow_with_failed_task_is_failed():
    from apps.workflow.models import AtomExecution

    workflow = Workflow.objects.create(name="健康巡检", team=[7], definition={})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="conductor-notify",
        status=WorkflowExecution.Status.RUNNING,
        team=[7],
    )
    AtomExecution.objects.create(
        execution=execution,
        conductor_task_id="notify-2",
        task_reference="notify",
        atom_key="bklite_notification",
        status=AtomExecution.Status.FAILED,
        attempt=2,
        error_message="通知渠道投递失败",
    )

    apply_remote_execution(
        execution,
        {
            "status": "COMPLETED",
            "output": {},
            "tasks": [
                {
                    "taskId": "scan-1",
                    "referenceTaskName": "scan",
                    "taskType": "SIMPLE",
                    "status": "COMPLETED",
                    "outputData": {"summary": {"failed": 2}},
                },
                {
                    "taskId": "notify-1",
                    "referenceTaskName": "notify",
                    "taskType": "SIMPLE",
                    "status": "FAILED",
                    "reasonForIncompletion": "ValueError: atom execution failed",
                },
                {
                    "taskId": "notify-2",
                    "referenceTaskName": "notify",
                    "taskType": "SIMPLE",
                    "status": "FAILED",
                    "reasonForIncompletion": "ValueError: atom execution failed",
                },
                {"taskId": "join-1", "referenceTaskName": "join", "taskType": "JOIN", "status": "COMPLETED"},
            ],
            "endTime": 1_700_000_000_000,
        },
    )

    execution.refresh_from_db()
    assert execution.status == WorkflowExecution.Status.FAILED
    assert execution.error_message == "通知渠道投递失败"
    assert execution.has_warnings is False


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
        output={"termination_job_cancels": [{"task_id": 101, "ok": False, "error_type": "JobPlatformError"}]},
    )

    apply_remote_execution(
        execution,
        {"status": "TERMINATED", "output": {}, "tasks": [], "endTime": 1_700_000_000_000, "reasonForIncompletion": "cancelled"},
    )

    execution.refresh_from_db()
    assert execution.status == WorkflowExecution.Status.TERMINATED
    assert execution.finished_at is not None
    assert execution.output.get("termination_job_cancels") == [{"task_id": 101, "ok": False, "error_type": "JobPlatformError"}]


@pytest.mark.django_db
def test_sync_budget_reserves_slots_for_non_unknown_executions(mocker):
    from apps.workflow.services.executions import sync_active_executions

    workflow = Workflow.objects.create(name="预算公平", team=[7], definition={})
    for index in range(100):
        WorkflowExecution.objects.create(
            workflow=workflow,
            workflow_version=1,
            status=WorkflowExecution.Status.UNKNOWN,
            team=[7],
        )
    running = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="conductor-running-fair",
        status=WorkflowExecution.Status.RUNNING,
        team=[7],
    )
    conductor = mocker.Mock()
    conductor.find_workflow_ids_by_correlation_id.return_value = []
    conductor.get_execution.return_value = {
        "status": "RUNNING",
        "output": {"ok": True},
        "tasks": [],
    }

    summary = sync_active_executions(client=conductor, limit=100)

    assert summary["synchronized"] >= 1
    conductor.get_execution.assert_any_call("conductor-running-fair")
    running.refresh_from_db()
    assert running.output.get("ok") is True


@pytest.mark.django_db
def test_sync_reconciles_queued_execution_without_engine_id(mocker):
    workflow = Workflow.objects.create(name="QUEUED 无 ID 对账", team=[7], definition={})
    queued = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        status=WorkflowExecution.Status.QUEUED,
        team=[7],
    )
    conductor = mocker.Mock()
    conductor.find_workflow_ids_by_correlation_id.return_value = ["recovered-queued-1"]
    conductor.get_execution.return_value = {
        "status": "RUNNING",
        "output": {"from": "queued"},
        "tasks": [],
    }

    summary = sync_active_executions(client=conductor, limit=10)

    queued.refresh_from_db()
    assert summary["reconciled"] == 1
    assert summary["synchronized"] == 1
    assert queued.status == WorkflowExecution.Status.RUNNING
    assert queued.conductor_workflow_id == "recovered-queued-1"
    assert queued.reconcile_attempts == 0
    assert queued.reconcile_next_at is None
    conductor.find_workflow_ids_by_correlation_id.assert_called_once_with(str(queued.id))


@pytest.mark.django_db
def test_sync_skips_unattached_until_reconcile_next_at(mocker):
    workflow = Workflow.objects.create(name="对账退避", team=[7], definition={})
    deferred = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        status=WorkflowExecution.Status.UNKNOWN,
        team=[7],
        reconcile_attempts=2,
        reconcile_next_at=timezone.now() + timedelta(hours=1),
    )
    due = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        status=WorkflowExecution.Status.UNKNOWN,
        team=[7],
        reconcile_attempts=1,
        reconcile_next_at=timezone.now() - timedelta(seconds=1),
    )
    conductor = mocker.Mock()
    conductor.find_workflow_ids_by_correlation_id.return_value = []

    summary = sync_active_executions(client=conductor, limit=10)

    assert summary == {"synchronized": 0, "failed": 0, "reconciled": 0}
    conductor.find_workflow_ids_by_correlation_id.assert_called_once_with(str(due.id))
    deferred.refresh_from_db()
    due.refresh_from_db()
    assert deferred.reconcile_attempts == 2
    assert due.reconcile_attempts == 2
    assert due.reconcile_next_at is not None
    assert due.reconcile_next_at > timezone.now()
