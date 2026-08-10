"""REST 与 NATS 共用的作业取消状态机。"""

from datetime import timedelta

from celery import current_app
from django.db import transaction
from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.job_mgmt.config import CANCEL_CONVERGE_BUFFER_SECONDS
from apps.job_mgmt.constants import ExecutionStatus
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.services.completion_outbox_service import enqueue_terminal_effects
from apps.job_mgmt.utils.team_authz import is_team_authorized


class ExecutionCancellationError(Exception):
    pass


class ExecutionCancellationAuthorizationError(ExecutionCancellationError):
    pass


def _run_cancel_fast_path(execution_id: int, celery_task_id: str, countdown: int | None) -> None:
    if celery_task_id:
        try:
            current_app.control.revoke(celery_task_id)
        except Exception as error:
            logger.warning("[cancel] revoke 失败: execution_id=%s, error=%s", execution_id, error)
    if countdown is not None:
        try:
            from apps.job_mgmt.tasks import finalize_cancelling_execution

            finalize_cancelling_execution.apply_async(args=[execution_id], countdown=countdown)
        except Exception:
            logger.exception("[cancel] 兜底任务入队失败，等待 Beat 补偿: execution_id=%s", execution_id)


def request_execution_cancel(
    execution_id: int,
    *,
    authorized_team_ids: set[int] | None,
) -> tuple[JobExecution, str]:
    """锁定执行记录后重验授权并推进取消；所有外部 I/O 都在提交后执行。"""
    with transaction.atomic():
        execution = JobExecution.objects.select_for_update().filter(id=execution_id).first()
        if execution is None:
            raise JobExecution.DoesNotExist
        if not is_team_authorized(execution.team, authorized_team_ids):
            raise ExecutionCancellationAuthorizationError("无权取消该任务")
        if execution.status in ExecutionStatus.TERMINAL_STATES:
            raise ExecutionCancellationError(f"任务已处于终态({execution.get_status_display()})，无法取消")
        if execution.status == ExecutionStatus.CANCELLING:
            raise ExecutionCancellationError("任务正在取消中，请勿重复操作")

        now = timezone.now()
        countdown = None
        if execution.status == ExecutionStatus.PENDING:
            execution.status = ExecutionStatus.CANCELLED
            execution.finished_at = now
            execution.cancel_finalize_at = None
            execution.save(update_fields=["status", "finished_at", "cancel_finalize_at", "updated_at"])
            enqueue_terminal_effects(execution)
            message = "已取消执行"
        elif execution.status == ExecutionStatus.RUNNING:
            countdown = max(0, execution.timeout) + CANCEL_CONVERGE_BUFFER_SECONDS
            execution.status = ExecutionStatus.CANCELLING
            execution.cancel_finalize_at = now + timedelta(seconds=countdown)
            execution.save(update_fields=["status", "cancel_finalize_at", "updated_at"])
            message = "正在取消执行"
        else:
            raise ExecutionCancellationError("状态已变更，请刷新后重试")

        transaction.on_commit(
            lambda: _run_cancel_fast_path(execution.id, execution.celery_task_id, countdown)
        )
    return execution, message
