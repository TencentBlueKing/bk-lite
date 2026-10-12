"""编排执行终止时，对已登记的作业任务发起取消请求。"""

from __future__ import annotations

from typing import Any

from apps.core.logger import workflow_orchestration_logger as logger
from apps.workflow_orchestration.models import WorkflowExecution
from apps.workflow_orchestration.services.job_platform import JobPlatformError, JobPlatformExecutor


def collect_linked_job_task_ids(execution: WorkflowExecution) -> list[int]:
    """从原子执行记录收集去重后的作业任务 ID（字段与 output.job_task_ids）。"""
    ordered: list[int] = []
    seen: set[int] = set()
    for atom in execution.atom_executions.all().only("job_task_id", "output"):
        candidates: list[Any] = []
        if atom.job_task_id is not None:
            candidates.append(atom.job_task_id)
        raw_ids = (atom.output or {}).get("job_task_ids")
        if isinstance(raw_ids, list):
            candidates.extend(raw_ids)
        for raw in candidates:
            try:
                task_id = int(raw)
            except (TypeError, ValueError):
                continue
            if task_id in seen:
                continue
            seen.add(task_id)
            ordered.append(task_id)
    return ordered


def cancel_linked_job_tasks(
    execution: WorkflowExecution,
    *,
    actor: dict[str, Any],
    executor: JobPlatformExecutor | None = None,
) -> list[dict[str, Any]]:
    """对执行关联的作业逐个请求取消；单任务失败不阻断其余任务。"""
    runner = executor or JobPlatformExecutor()
    teams = [int(team) for team in (execution.team or [])]
    results: list[dict[str, Any]] = []
    task_ids = collect_linked_job_task_ids(execution)
    requested = 0
    failed = 0
    for task_id in task_ids:
        try:
            payload = runner.cancel(task_id, authorized_team_ids=teams, actor=actor)
            results.append({"task_id": task_id, "ok": True, **payload})
            requested += 1
        except JobPlatformError as error:
            failed += 1
            results.append(
                {
                    "task_id": task_id,
                    "ok": False,
                    "error_type": type(error).__name__,
                }
            )
            logger.warning(
                "workflow terminate job cancel failed: execution_id=%s job_task_id=%s error_type=%s",
                execution.id,
                task_id,
                type(error).__name__,
            )
    logger.info(
        "workflow terminate job cancel summary: execution_id=%s job_count=%s requested=%s failed=%s",
        execution.id,
        len(task_ids),
        requested,
        failed,
    )
    return results
