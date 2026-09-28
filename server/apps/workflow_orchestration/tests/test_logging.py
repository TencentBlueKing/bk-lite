from datetime import timedelta

import pytest
from django.utils import timezone

from apps.workflow_orchestration.models import Workflow, WorkflowExecution, WorkflowInteraction, WorkflowTrigger
from apps.workflow_orchestration.services.interactions import expire_due_interactions
from apps.workflow_orchestration.services.triggers import run_due_cron_triggers


def _assert_sanitized_error(call, sentinel):
    template, *parameters = call.args
    assert "%s" in template
    assert parameters
    assert sentinel not in template
    assert all(sentinel not in str(item) for item in parameters)
    assert sentinel not in str(call.kwargs["exc_info"][1])


@pytest.mark.django_db
def test_timeout_and_cron_logs_keep_stable_template_and_hide_external_error(mocker):
    sentinel = "SENSITIVE-PROVIDER-BODY"
    workflow = Workflow.objects.create(
        name="log",
        team=[7],
        definition={},
        status=Workflow.Status.PUBLISHED,
        current_version=1,
        enabled=True,
    )
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="log-execution",
        team=[7],
        status=WorkflowExecution.Status.WAITING_APPROVAL,
    )
    WorkflowInteraction.objects.create(
        execution=execution,
        interaction_type=WorkflowInteraction.Type.APPROVAL,
        task_reference="approval",
        conductor_task_id="log-task",
        title="approval",
        candidate_users=["log-admin"],
        team=[7],
        due_at=timezone.now() - timedelta(seconds=1),
    )
    conductor = mocker.Mock()
    conductor.complete_task.side_effect = RuntimeError(sentinel)
    interaction_logger = mocker.patch("apps.workflow_orchestration.services.interactions.logger")

    summary = expire_due_interactions(client=conductor)

    assert summary == {"timed_out": 0, "failed": 1}
    _assert_sanitized_error(interaction_logger.error.call_args, sentinel)
    execution.status = WorkflowExecution.Status.FAILED
    execution.finished_at = timezone.now()
    execution.save(update_fields=("status", "finished_at", "updated_at"))

    trigger = WorkflowTrigger.objects.create(
        workflow=workflow,
        name="cron",
        trigger_type=WorkflowTrigger.Type.SCHEDULE,
        enabled=True,
        team=[7],
        config={"expression": "* * * * *", "timezone": "Asia/Shanghai"},
        next_run_at=timezone.now() - timedelta(minutes=1),
    )
    mocker.patch(
        "apps.workflow_orchestration.services.triggers.invoke_trigger",
        side_effect=RuntimeError(sentinel),
    )
    trigger_logger = mocker.patch("apps.workflow_orchestration.services.triggers.logger")

    cron_summary = run_due_cron_triggers()

    assert cron_summary == {"succeeded": 0, "skipped": 0, "failed": 1}
    trigger.refresh_from_db()
    assert trigger.next_run_at > timezone.now()
    _assert_sanitized_error(trigger_logger.error.call_args, sentinel)
