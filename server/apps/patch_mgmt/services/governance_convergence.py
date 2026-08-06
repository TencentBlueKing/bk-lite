"""治理任务的只读状态投影与收敛判断。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.patch_mgmt.config import DISPATCH_TIMEOUT, get_stage_timeout
from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType


@dataclass(frozen=True)
class ProjectedHostState:
    stage: str
    stage_color: str
    error_code: str
    failed_stage: str
    reason: str
    timeout_reason: str
    can_retry: bool


def _deadline(host, *, now=None):
    if host.stage == "waiting":
        task = host.task
        current = now or timezone.now()
        if (
            task.execution_mode == "window"
            and task.execution_window_end
            and task.execution_window_end > current
        ):
            return None
        return host.created_at + timedelta(seconds=DISPATCH_TIMEOUT)
    if host.stage in {"scanning", "installing", "rebooting"}:
        if host.stage_deadline_at:
            return host.stage_deadline_at
        started_at = host.stage_started_at or host.started_at
        if started_at:
            return started_at + timedelta(seconds=get_stage_timeout(host.task.task_type))
    return None


def project_host_state(host, *, now=None) -> ProjectedHostState:
    """只读计算主机当前应展示的状态，不保存模型。"""
    current = now or timezone.now()
    deadline = _deadline(host, now=current)
    if deadline is None or deadline >= current:
        return ProjectedHostState(
            host.stage,
            host.stage_color,
            host.error_code,
            host.failed_stage,
            host.reason,
            host.timeout_reason,
            host.can_retry,
        )
    if host.stage == "waiting":
        reason = "主机任务超过 5 分钟未被执行器领取"
        return ProjectedHostState(
            "failed", "error", "dispatch_timeout", "dispatch", reason, reason, True
        )
    if host.task.task_type in (GovernanceTaskType.ASSESS, GovernanceTaskType.VERIFY):
        reason = f"{host.task.get_task_type_display()}阶段超过时限"
        return ProjectedHostState(
            "failed",
            "error",
            f"{host.task.task_type}_timeout",
            host.task.task_type,
            reason,
            reason,
            True,
        )
    return ProjectedHostState(
        host.stage,
        host.stage_color,
        host.error_code,
        host.failed_stage,
        host.reason,
        host.timeout_reason,
        host.can_retry,
    )


def project_task_status(task, *, now=None) -> str:
    """按投影后的全部子任务计算父任务展示状态。"""
    if task.status in GovernanceTaskStatus.TERMINAL_STATES:
        return task.status
    hosts = list(task.host_results.select_related("task").all())
    if not hosts:
        return task.status
    states = [project_host_state(host, now=now).stage for host in hosts]
    success_stages = {"completed", "reboot_scheduled"}
    if task.task_type != GovernanceTaskType.REBOOT:
        success_stages.add("pending_reboot")
    failure_stages = {"failed", "reboot_failed"}
    terminal_stages = success_stages | failure_stages | {"cancelled", "pending_confirmation"}
    if any(stage not in terminal_stages for stage in states):
        return task.status
    if all(stage == "cancelled" for stage in states):
        return GovernanceTaskStatus.CANCELLED
    if any(stage == "cancelled" for stage in states):
        return GovernanceTaskStatus.PARTIAL_CANCELLED
    if any(stage in success_stages for stage in states) and any(
        stage in failure_stages for stage in states
    ):
        return GovernanceTaskStatus.PARTIAL_SUCCESS
    if any(stage in success_stages for stage in states):
        return GovernanceTaskStatus.COMPLETED
    return GovernanceTaskStatus.FAILED


def project_target_assessment_status(target_id: int, *, now=None) -> str | None:
    """返回目标活动评估的展示状态；无活动评估时返回 None。"""
    from apps.patch_mgmt.models import GovernanceTaskHost

    hosts = list(
        GovernanceTaskHost.objects.filter(
            target_id=target_id,
            task__task_type__in=(GovernanceTaskType.ASSESS, GovernanceTaskType.VERIFY),
            task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
        )
        .select_related("task")
        .order_by("-created_at")
    )
    if not hosts:
        return None
    states = [project_host_state(host, now=now).stage for host in hosts]
    if any(stage not in {"failed", "completed", "cancelled", "pending_confirmation"} for stage in states):
        return "evaluating"
    if any(stage == "failed" for stage in states):
        return "failed"
    return None


def reconcile_stale_history(
    *,
    dry_run: bool = False,
    limit: int = 100,
    after_id: int = 0,
    before_id: int | None = None,
    now=None,
) -> dict[str, object]:
    """有界、幂等地把历史陈旧活动主机收敛为失败，不创建重跑任务。"""
    from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost
    from apps.patch_mgmt.services.patch_execution_service import _finalize_task_status

    current = now or timezone.now()
    bounded_limit = max(1, min(int(limit), 1000))
    expired = Q(
        stage="waiting",
        created_at__lt=current - timedelta(seconds=DISPATCH_TIMEOUT),
    ) | Q(
        stage__in=("scanning", "installing", "rebooting"),
        stage_deadline_at__lt=current,
    ) | Q(
        stage="reconciling",
        reconcile_deadline_at__lt=current,
    )
    queryset = GovernanceTaskHost.objects.filter(
        expired,
        id__gt=max(0, int(after_id)),
        task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
    )
    if before_id is not None:
        queryset = queryset.filter(id__lt=max(1, int(before_id)))
    candidate_ids = list(
        queryset.order_by("id").values_list("id", flat=True)[:bounded_limit]
    )
    result = {
        "dry_run": bool(dry_run),
        "candidates": len(candidate_ids),
        "changed": 0,
        "host_ids": candidate_ids,
        "last_id": candidate_ids[-1] if candidate_ids else int(after_id),
    }
    if dry_run:
        return result

    changed_task_ids: set[int] = set()
    changed = 0
    for host_id in candidate_ids:
        with transaction.atomic():
            host = (
                GovernanceTaskHost.objects.select_for_update()
                .select_related("task")
                .get(pk=host_id)
            )
            if host.task.status not in GovernanceTaskStatus.ACTIVE_STATES:
                continue
            still_expired = (
                host.stage == "waiting"
                and host.created_at < current - timedelta(seconds=DISPATCH_TIMEOUT)
            ) or (
                host.stage in {"scanning", "installing", "rebooting"}
                and host.stage_deadline_at is not None
                and host.stage_deadline_at < current
            ) or (
                host.stage == "reconciling"
                and host.reconcile_deadline_at is not None
                and host.reconcile_deadline_at < current
            )
            if not still_expired:
                continue
            failed_stage = "dispatch" if host.stage == "waiting" else host.task.task_type
            reason = "历史治理记录超过业务时限，已由一次性对账收敛；未自动重跑"
            host.stage = "failed"
            host.stage_color = "error"
            host.failed_stage = failed_stage
            host.error_code = f"historical_{failed_stage}_timeout"
            host.reason = reason
            host.timeout_reason = reason
            host.can_retry = True
            host.save(
                update_fields=[
                    "stage",
                    "stage_color",
                    "failed_stage",
                    "error_code",
                    "reason",
                    "timeout_reason",
                    "can_retry",
                    "updated_at",
                ]
            )
            changed += 1
            changed_task_ids.add(host.task_id)

    for parent in GovernanceTask.objects.filter(pk__in=changed_task_ids):
        _finalize_task_status(parent)
    result["changed"] = changed
    return result
