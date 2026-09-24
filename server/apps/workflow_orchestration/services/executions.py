from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from django.db import connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.console_mgmt.services import create_targeted_notification
from apps.core.logger import workflow_orchestration_logger as logger
from apps.workflow_orchestration.models import WorkflowExecution, WorkflowInteraction
from apps.workflow_orchestration.services.conductor import ConductorClient
from apps.workflow_orchestration.services.data_contracts import mask_secret_envelopes

TERMINAL_STATUSES = {
    WorkflowExecution.Status.SUCCEEDED,
    WorkflowExecution.Status.FAILED,
    WorkflowExecution.Status.TIMED_OUT,
    WorkflowExecution.Status.TERMINATED,
}

_FENCED_LOCAL_STATUSES = TERMINAL_STATUSES | {WorkflowExecution.Status.TERMINATING}


def _epoch_ms_datetime(value: Any) -> datetime | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def _epoch_ms_iso(value: Any) -> str | None:
    timestamp = _epoch_ms_datetime(value)
    return timestamp.isoformat().replace("+00:00", "Z") if timestamp else None


def _duration_ms(started_at: Any, finished_at: Any) -> int | None:
    if not isinstance(started_at, (int, float)) or not isinstance(finished_at, (int, float)):
        return None
    if isinstance(started_at, bool) or isinstance(finished_at, bool) or finished_at < started_at:
        return None
    return int(finished_at - started_at)


def task_projection(task: dict[str, Any]) -> dict[str, Any]:
    started_at = task.get("startTime")
    finished_at = task.get("endTime")
    retry_count = task.get("retryCount", 0)
    return {
        "task_id": task.get("taskId", "") or "",
        "reference": task.get("referenceTaskName"),
        "type": task.get("taskDefName"),
        "system_type": task.get("taskType", "") or "",
        "status": task.get("status"),
        "worker_id": task.get("workerId", "") or "",
        "started_at": _epoch_ms_iso(started_at),
        "finished_at": _epoch_ms_iso(finished_at),
        "duration_ms": _duration_ms(started_at, finished_at),
        "retry_count": retry_count if isinstance(retry_count, int) and not isinstance(retry_count, bool) and retry_count >= 0 else 0,
        "iteration": task.get("iteration", 0) if isinstance(task.get("iteration", 0), int) else 0,
        "retried_task_id": task.get("retriedTaskId", "") or "",
        "pause_kind": (task.get("inputData", {}) or {}).get("pauseKind", ""),
        "input": mask_secret_envelopes(task.get("inputData", {}) or {}),
        "output": task.get("outputData", {}) or {},
        "reason": task.get("reasonForIncompletion", "") or "",
    }


def _notify_pending_approvals(execution: WorkflowExecution, interactions: list[WorkflowInteraction]) -> None:
    for interaction in interactions:
        try:
            create_targeted_notification(
                app_module="workflow-orchestration",
                content=f"待审批：{execution.workflow.name} · {interaction.title}",
                recipient_usernames=interaction.candidate_users,
                target_url="/workflow-orchestration/executions?scope=mine",
                source="workflow_approval",
                event_key=f"workflow_approval:{interaction.id}",
            )
        except Exception as error:
            logger.warning(
                "event=workflow_approval_notification_failed execution_id=%s interaction_id=%s error_type=%s",
                execution.id,
                interaction.id,
                type(error).__name__,
            )


def _sync_interactions(execution: WorkflowExecution, tasks: list[dict[str, Any]]) -> tuple[bool, list[WorkflowInteraction]]:
    waiting_for_human = False
    pending_notifications: list[WorkflowInteraction] = []
    for task in tasks:
        if task.get("taskType") != "HUMAN" or task.get("status") not in {"SCHEDULED", "IN_PROGRESS"}:
            continue
        task_id = str(task.get("taskId") or "")[:100]
        task_reference = str(task.get("referenceTaskName") or "")[:100]
        if not task_id or not task_reference:
            continue
        inputs = task.get("inputData") if isinstance(task.get("inputData"), dict) else {}
        interaction_type = WorkflowInteraction.Type.APPROVAL
        candidates = inputs.get("candidates")
        if not isinstance(candidates, list):
            candidates = []
        candidates = [str(item)[:32] for item in candidates if isinstance(item, str) and item.strip()][:20]
        if not candidates:
            continue
        public_context = inputs.get("publicContext") if isinstance(inputs.get("publicContext"), dict) else {}
        due_at = None
        raw_due_at = inputs.get("dueAt")
        if isinstance(raw_due_at, str):
            due_at = parse_datetime(raw_due_at)
        timeout_seconds = inputs.get("timeoutSeconds")
        if due_at is None and isinstance(timeout_seconds, int) and not isinstance(timeout_seconds, bool) and 1 <= timeout_seconds <= 2592000:
            due_at = (_epoch_ms_datetime(task.get("scheduledTime")) or timezone.now()) + timedelta(seconds=timeout_seconds)
        interaction, created = WorkflowInteraction.objects.get_or_create(
            execution=execution,
            conductor_task_id=task_id,
            defaults={
                "interaction_type": interaction_type,
                "task_reference": task_reference,
                "title": str(inputs.get("title") or "人工审批")[:120],
                "description": str(inputs.get("description") or "")[:500],
                "candidate_users": candidates,
                "public_context": public_context,
                "team": execution.team,
                "due_at": due_at,
            },
        )
        if interaction.status == WorkflowInteraction.Status.PENDING:
            waiting_for_human = True
            if created:
                pending_notifications.append(interaction)
    return waiting_for_human, pending_notifications


def _remote_maps_to_terminal(remote_status: Any) -> bool:
    if remote_status == "COMPLETED":
        return True
    return remote_status in TERMINAL_STATUSES


def apply_remote_execution(execution: WorkflowExecution, remote: dict[str, Any]) -> WorkflowExecution:
    remote_status = remote.get("status")
    valid_statuses = {choice for choice, _ in WorkflowExecution.Status.choices}
    local_status = execution.status
    fenced = local_status in _FENCED_LOCAL_STATUSES
    allow_status_overwrite = (not fenced) or _remote_maps_to_terminal(remote_status)

    if allow_status_overwrite and remote_status in valid_statuses:
        execution.status = remote_status
    execution.output = remote.get("output", {}) or {}
    remote_tasks = [task for task in remote.get("tasks", []) if isinstance(task, dict)]
    execution.tasks = [task_projection(task) for task in remote_tasks]
    waiting_for_human, pending_notifications = _sync_interactions(execution, remote_tasks)
    if allow_status_overwrite and remote_status == "RUNNING" and waiting_for_human:
        execution.status = WorkflowExecution.Status.WAITING_APPROVAL
    execution.error_message = str(remote.get("reasonForIncompletion", "") or "")[:500]
    if allow_status_overwrite and remote_status == "COMPLETED":
        execution.status = WorkflowExecution.Status.SUCCEEDED
        failed_targets = []
        for task in remote_tasks:
            output = task.get("outputData") if isinstance(task.get("outputData"), dict) else {}
            summary = output.get("summary") if isinstance(output.get("summary"), dict) else {}
            failed = summary.get("failed")
            if isinstance(failed, int) and not isinstance(failed, bool) and failed > 0:
                failed_targets.append(failed)
        execution.warning_count = sum(failed_targets)
        execution.has_warnings = execution.warning_count > 0
    if execution.status in TERMINAL_STATUSES:
        execution.finished_at = _epoch_ms_datetime(remote.get("endTime")) or execution.finished_at or timezone.now()
    execution.save(
        update_fields=(
            "status",
            "output",
            "tasks",
            "error_message",
            "has_warnings",
            "warning_count",
            "finished_at",
            "updated_at",
        )
    )
    if pending_notifications:

        def _notify() -> None:
            _notify_pending_approvals(execution, pending_notifications)

        if connection.in_atomic_block:
            transaction.on_commit(_notify)
        else:
            _notify()
    return execution


def sync_active_executions(*, client: ConductorClient | None = None, limit: int = 100) -> dict[str, int]:
    conductor = client or ConductorClient()
    active_statuses = {
        WorkflowExecution.Status.QUEUED,
        WorkflowExecution.Status.RUNNING,
        WorkflowExecution.Status.WAITING_APPROVAL,
        WorkflowExecution.Status.TERMINATING,
    }
    execution_ids = list(
        WorkflowExecution.objects.filter(
            status__in=active_statuses,
            conductor_workflow_id__isnull=False,
        )
        .exclude(conductor_workflow_id="")
        .order_by("updated_at", "id")
        .values_list("id", flat=True)[: max(1, min(int(limit), 100))]
    )
    summary = {"synchronized": 0, "failed": 0}
    for execution_id in execution_ids:
        try:
            execution = WorkflowExecution.objects.get(pk=execution_id)
            remote = conductor.get_execution(execution.conductor_workflow_id)
            apply_remote_execution(execution, remote)
            summary["synchronized"] += 1
        except Exception as error:
            summary["failed"] += 1
            safe_error = RuntimeError("workflow execution synchronization failed")
            logger.error(
                "event=workflow_execution_sync_failed execution_id=%s failed_stage=conductor_query error_type=%s",
                execution_id,
                type(error).__name__,
                exc_info=(type(safe_error), safe_error, error.__traceback__),
            )
    return summary
