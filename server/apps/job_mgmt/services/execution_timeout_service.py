"""作业执行超时状态收敛。"""

from datetime import timedelta

from celery import current_app
from django.db import transaction
from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.job_mgmt.config import EXECUTION_PENDING_TIMEOUT_SECONDS, EXECUTION_TIMEOUT_CALLBACK_GRACE_SECONDS
from apps.job_mgmt.constants import ExecutionStatus
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.services.completion_outbox_service import enqueue_terminal_effects


class ExecutionTimeoutService:
    """在数据库行锁内把超过持久化截止时间的执行收敛到终态。"""

    @staticmethod
    def running_deadline(timeout_seconds: int, *, now=None, work_units: int = 1):
        """按用户的单次执行超时计算当前工作窗口截止时间。"""
        now = now or timezone.now()
        timeout_seconds = max(1, int(timeout_seconds))
        work_units = max(1, int(work_units))
        return now + timedelta(seconds=timeout_seconds * work_units + EXECUTION_TIMEOUT_CALLBACK_GRACE_SECONDS)

    @staticmethod
    def pending_deadline(*, now=None):
        now = now or timezone.now()
        return now + timedelta(seconds=EXECUTION_PENDING_TIMEOUT_SECONDS)

    @classmethod
    def arm_pending(cls, execution_id: int, *, now=None):
        """为已落库但尚未被 worker 领取的执行持久化调度截止时间。"""
        now = now or timezone.now()
        deadline = cls.pending_deadline(now=now)
        updated = JobExecution.objects.filter(id=execution_id, status=ExecutionStatus.PENDING).update(
            converge_deadline_at=deadline,
            updated_at=now,
        )
        return deadline if updated else None

    @classmethod
    def renew_running(cls, execution_id: int, *, now=None, work_units: int = 1):
        """按当前批次工作量续期；只允许仍处于 RUNNING 的 worker 更新。"""
        now = now or timezone.now()
        timeout_seconds = JobExecution.objects.filter(id=execution_id, status=ExecutionStatus.RUNNING).values_list("timeout", flat=True).first()
        if timeout_seconds is None:
            return None
        deadline = cls.running_deadline(timeout_seconds, now=now, work_units=work_units)
        updated = JobExecution.objects.filter(id=execution_id, status=ExecutionStatus.RUNNING).update(
            converge_deadline_at=deadline,
            updated_at=now,
        )
        return deadline if updated else None

    @classmethod
    def converge(cls, execution_id: int, *, now=None) -> bool:
        now = now or timezone.now()
        with transaction.atomic():
            execution = JobExecution.objects.select_for_update().filter(id=execution_id).first()
            if not cls._is_due(execution, now):
                return False

            pending = execution.status == ExecutionStatus.PENDING
            terminal_status = ExecutionStatus.FAILED if pending else ExecutionStatus.TIMEOUT
            terminal_source = JobExecution.TerminalSource.DISPATCH_TIMEOUT if pending else JobExecution.TerminalSource.EXECUTION_TIMEOUT
            error_message = "任务调度超时，Worker 未接单" if pending else "执行超时，未收到最终结果"
            results = cls._supplement_missing_results(execution, terminal_status, error_message)

            execution.status = terminal_status
            execution.terminal_source = terminal_source
            execution.converge_deadline_at = None
            execution.finished_at = now
            execution.execution_results = results
            execution.success_count = sum(1 for result in results if result.get("status") == ExecutionStatus.SUCCESS)
            execution.failed_count = sum(1 for result in results if result.get("status") in (ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT))
            execution.save(
                update_fields=[
                    "status",
                    "terminal_source",
                    "converge_deadline_at",
                    "finished_at",
                    "execution_results",
                    "success_count",
                    "failed_count",
                    "updated_at",
                ]
            )
            enqueue_terminal_effects(execution)
            if execution.celery_task_id:
                transaction.on_commit(lambda task_id=execution.celery_task_id: cls._revoke_task(execution_id, task_id))

        logger.info(
            "job execution deadline converged: execution_id=%s, terminal_status=%s, terminal_source=%s",
            execution_id,
            terminal_status,
            terminal_source,
        )
        return True

    @staticmethod
    def _revoke_task(execution_id: int, task_id: str) -> None:
        try:
            current_app.control.revoke(task_id)
        except Exception as error:
            logger.warning(
                "job execution timeout revoke failed: execution_id=%s, failed_stage=%s, error_type=%s",
                execution_id,
                "revoke_celery_task",
                type(error).__name__,
            )

    @staticmethod
    def _is_due(execution: JobExecution | None, now) -> bool:
        return bool(
            execution
            and execution.status in (ExecutionStatus.PENDING, ExecutionStatus.RUNNING)
            and execution.converge_deadline_at
            and execution.converge_deadline_at <= now
        )

    @staticmethod
    def _supplement_missing_results(execution: JobExecution, status: str, error_message: str) -> list[dict]:
        results = list(execution.execution_results or [])
        have_keys = {str(result.get("target_key", "")) for result in results}
        for target in execution.target_list or []:
            target_key = str(target.get("node_id") or target.get("target_id", ""))
            if target_key in have_keys:
                continue
            results.append(
                {
                    "target_key": target_key,
                    "name": target.get("name", ""),
                    "ip": target.get("ip", ""),
                    "status": status,
                    "error_message": error_message,
                }
            )
            have_keys.add(target_key)
        return results
