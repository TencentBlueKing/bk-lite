from django.db import models, transaction
from django.utils import timezone

from apps.workflow_orchestration.models import Workflow, WorkflowExecution

NON_TERMINAL_EXECUTION_STATUSES = {
    WorkflowExecution.Status.QUEUED,
    WorkflowExecution.Status.RUNNING,
    WorkflowExecution.Status.WAITING_APPROVAL,
    WorkflowExecution.Status.TERMINATING,
}


class WorkflowDeleteConflict(ValueError):
    pass


@transaction.atomic
def soft_delete_workflow(workflow_id: int, *, deleted_by: str, deleted_by_domain: str) -> tuple[Workflow, dict]:
    workflow = Workflow.all_objects.select_for_update().get(pk=workflow_id)
    if workflow.deleted_at is not None:
        raise Workflow.DoesNotExist
    if workflow.executions.filter(status__in=NON_TERMINAL_EXECUTION_STATUSES).exists():
        raise WorkflowDeleteConflict("流程存在正在运行、等待或取消中的执行，请先终止或等待执行结束")

    now = timezone.now()
    enabled_triggers = workflow.triggers.filter(enabled=True)
    trigger_summary = dict(enabled_triggers.values_list("trigger_type").order_by().annotate(total=models.Count("id")))
    enabled_trigger_count = sum(trigger_summary.values())
    enabled_triggers.update(enabled=False, next_run_at=None, updated_at=now)
    workflow.deleted_at = now
    workflow.deleted_by = deleted_by
    workflow.deleted_by_domain = deleted_by_domain
    workflow.updated_by = deleted_by
    workflow.updated_by_domain = deleted_by_domain
    workflow.save(
        update_fields=(
            "deleted_at",
            "deleted_by",
            "deleted_by_domain",
            "updated_by",
            "updated_by_domain",
            "updated_at",
        )
    )
    return workflow, {
        "workflow_id": workflow.pk,
        "workflow_name": workflow.name,
        "last_version": workflow.current_version,
        "team": workflow.team,
        "disabled_trigger_count": enabled_trigger_count,
        "trigger_summary": trigger_summary,
        "deleted_at": workflow.deleted_at.isoformat(),
    }
