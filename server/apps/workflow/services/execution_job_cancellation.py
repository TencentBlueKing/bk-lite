"""编排执行终止时，对已登记的作业任务发起取消请求。"""

from __future__ import annotations

from typing import Any

from apps.core.logger import workflow_logger as logger
from apps.workflow.models import WorkflowExecution
from apps.workflow.services.job_platform import JobPlatformError, JobPlatformExecutor


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


def merge_termination_cancel_results(
    prior: list[dict[str, Any]] | None,
    fresh: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge cancel attempts by task_id; successful cancel wins over prior failure."""

    merged: dict[int, dict[str, Any]] = {}
    for item in prior or []:
        if not isinstance(item, dict):
            continue
        try:
            task_id = int(item.get("task_id"))
        except (TypeError, ValueError):
            continue
        merged[task_id] = item
    for item in fresh:
        if not isinstance(item, dict):
            continue
        try:
            task_id = int(item.get("task_id"))
        except (TypeError, ValueError):
            continue
        previous = merged.get(task_id)
        if previous and previous.get("ok") is True and item.get("ok") is not True:
            continue
        merged[task_id] = item
    return [merged[key] for key in sorted(merged)]


def refresh_termination_job_cancels(
    execution: WorkflowExecution,
    *,
    actor: dict[str, Any] | None = None,
    executor: JobPlatformExecutor | None = None,
) -> list[dict[str, Any]]:
    """Re-cancel linked jobs after terminate; keep prior ledger and cover late-registered ids."""

    if execution.status not in {
        WorkflowExecution.Status.TERMINATING,
        WorkflowExecution.Status.TERMINATED,
    }:
        prior = (execution.output or {}).get("termination_job_cancels")
        return prior if isinstance(prior, list) else []

    resolved_actor = actor or {
        "username": execution.started_by or "system",
        "domain": execution.domain or "domain.com",
    }
    prior = (execution.output or {}).get("termination_job_cancels")
    prior_list = prior if isinstance(prior, list) else []
    ok_ids = {
        int(item["task_id"]) for item in prior_list if isinstance(item, dict) and item.get("ok") is True and item.get("task_id") not in (None, "")
    }
    pending_ids = [task_id for task_id in collect_linked_job_task_ids(execution) if task_id not in ok_ids]
    if not pending_ids:
        return merge_termination_cancel_results(prior_list, [])

    runner = executor or JobPlatformExecutor()
    teams = [int(team) for team in (execution.team or [])]
    fresh: list[dict[str, Any]] = []
    for task_id in pending_ids:
        try:
            payload = runner.cancel(task_id, authorized_team_ids=teams, actor=resolved_actor)
            fresh.append({"task_id": task_id, "ok": True, **payload})
        except JobPlatformError as error:
            fresh.append({"task_id": task_id, "ok": False, "error_type": type(error).__name__})
            logger.warning(
                "workflow terminate job cancel retry failed: execution_id=%s job_task_id=%s error_type=%s",
                execution.id,
                task_id,
                type(error).__name__,
            )
    return merge_termination_cancel_results(prior_list, fresh)
