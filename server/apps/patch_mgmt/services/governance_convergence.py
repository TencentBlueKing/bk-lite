"""治理任务的只读状态投影与收敛判断。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.patch_mgmt.config import DISPATCH_TIMEOUT, get_stage_timeout
from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType
from apps.patch_mgmt.utils.i18n import patch_message


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
        if task.execution_mode == "window" and task.execution_window_end and task.execution_window_end > current:
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
        reason = patch_message(
            None,
            "error.dispatch_timeout",
            "The host task was not claimed by an executor within 5 minutes",
        )
        return ProjectedHostState("failed", "error", "dispatch_timeout", "dispatch", reason, reason, True)
    if host.task.task_type in (GovernanceTaskType.ASSESS, GovernanceTaskType.VERIFY):
        task_type_label = patch_message(None, f"status.task_type.{host.task.task_type}", host.task.get_task_type_display())
        reason = patch_message(
            None,
            "error.stage_timeout",
            "{task_type} stage exceeded the time limit",
            task_type=task_type_label,
        )
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


def _terminal_host_stages(task_type: str) -> set[str]:
    stages = {
        "completed",
        "failed",
        "cancelled",
        "reboot_scheduled",
        "reboot_failed",
        "pending_confirmation",
    }
    if task_type != GovernanceTaskType.REBOOT:
        stages.add("pending_reboot")
    return stages


def project_task_status(task, *, now=None) -> str:
    """按投影后的全部子任务计算父任务展示状态。"""
    if task.status in GovernanceTaskStatus.TERMINAL_STATES:
        return task.status
    projected_hosts = getattr(task, "_visible_host_results", None)
    hosts = list(projected_hosts) if projected_hosts is not None else list(task.host_results.select_related("task").all())
    if not hosts:
        return task.status
    states = [project_host_state(host, now=now).stage for host in hosts]
    success_stages = {"completed", "reboot_scheduled"}
    if task.task_type != GovernanceTaskType.REBOOT:
        success_stages.add("pending_reboot")
    failure_stages = {"failed", "reboot_failed"}
    terminal_stages = _terminal_host_stages(task.task_type)
    if any(stage not in terminal_stages for stage in states):
        return task.status
    if all(stage == "cancelled" for stage in states):
        return GovernanceTaskStatus.CANCELLED
    if any(stage == "cancelled" for stage in states):
        return GovernanceTaskStatus.PARTIAL_CANCELLED
    if any(stage in success_stages for stage in states) and any(stage in failure_stages for stage in states):
        return GovernanceTaskStatus.PARTIAL_SUCCESS
    if any(stage in success_stages for stage in states):
        return GovernanceTaskStatus.COMPLETED
    return GovernanceTaskStatus.FAILED


def target_has_effective_active_tasks(target_ids: Iterable[int], *, now=None) -> dict[int, bool]:
    """按 target_id 批量判断是否仍有真实活动任务，复用 project_host_state。"""
    from apps.patch_mgmt.models import GovernanceTaskHost

    unique_ids = list(dict.fromkeys(int(target_id) for target_id in target_ids))
    projected = {target_id: False for target_id in unique_ids}
    if not unique_ids:
        return projected

    current = now or timezone.now()
    for start in range(0, len(unique_ids), _ASSESSMENT_STATUS_IN_CHUNK):
        chunk = unique_ids[start : start + _ASSESSMENT_STATUS_IN_CHUNK]
        hosts = GovernanceTaskHost.objects.filter(
            target_id__in=chunk,
            task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
        ).select_related("task")
        for host in hosts:
            if projected.get(host.target_id):
                continue
            if project_host_state(host, now=current).stage not in _terminal_host_stages(host.task.task_type):
                projected[host.target_id] = True
    return projected


def target_has_effective_active_task(target_id: int, *, now=None) -> bool:
    """按与展示一致的超时投影判断目标是否仍有真实活动任务。"""
    return bool(target_has_effective_active_tasks([target_id], now=now).get(int(target_id)))


_ASSESSMENT_STATUS_IN_CHUNK = 500
_TERMINAL_ASSESSMENT_STAGES = {"failed", "completed", "cancelled", "pending_confirmation"}


def _assessment_status_from_stages(stages: list[str]) -> str | None:
    if any(stage not in _TERMINAL_ASSESSMENT_STAGES for stage in stages):
        return "evaluating"
    if any(stage == "failed" for stage in stages):
        return "failed"
    return None


def project_target_assessment_statuses(target_ids: Iterable[int], *, now=None) -> dict[int, str | None]:
    """按 target_id 批量投影活动评估状态，复用 project_host_state。"""
    from apps.patch_mgmt.models import GovernanceTaskHost

    unique_ids = list(dict.fromkeys(int(target_id) for target_id in target_ids))
    projected = {target_id: None for target_id in unique_ids}
    if not unique_ids:
        return projected

    current = now or timezone.now()
    hosts_by_target: dict[int, list] = defaultdict(list)
    for start in range(0, len(unique_ids), _ASSESSMENT_STATUS_IN_CHUNK):
        chunk = unique_ids[start : start + _ASSESSMENT_STATUS_IN_CHUNK]
        hosts = (
            GovernanceTaskHost.objects.filter(
                target_id__in=chunk,
                task__task_type__in=(GovernanceTaskType.ASSESS, GovernanceTaskType.VERIFY),
                task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
            )
            .select_related("task")
            .order_by("-created_at")
        )
        for host in hosts:
            hosts_by_target[host.target_id].append(host)

    for target_id, hosts in hosts_by_target.items():
        stages = [project_host_state(host, now=current).stage for host in hosts]
        projected[target_id] = _assessment_status_from_stages(stages)
    return projected


def project_target_assessment_status(target_id: int, *, now=None) -> str | None:
    """返回目标活动评估的展示状态；无活动评估时返回 None。"""
    return project_target_assessment_statuses([target_id], now=now).get(int(target_id))


def project_latest_assessment_failure_reasons(target_ids: Iterable[int]) -> dict[int, str]:
    """批量取每个目标最近一次评估/验证失败原因。"""
    from apps.patch_mgmt.models import GovernanceTaskHost

    unique_ids = list(dict.fromkeys(int(target_id) for target_id in target_ids))
    reasons: dict[int, str] = {}
    if not unique_ids:
        return reasons

    for start in range(0, len(unique_ids), _ASSESSMENT_STATUS_IN_CHUNK):
        chunk = unique_ids[start : start + _ASSESSMENT_STATUS_IN_CHUNK]
        hosts = GovernanceTaskHost.objects.filter(
            target_id__in=chunk,
            task__task_type__in=(GovernanceTaskType.ASSESS, GovernanceTaskType.VERIFY),
            stage__in=("failed", "pending_confirmation"),
        ).order_by("-created_at")
        for host in hosts:
            if host.target_id in reasons:
                continue
            reasons[host.target_id] = host.reason or host.timeout_reason or ""
    return reasons


def reconcile_stale_history(
    *,
    dry_run: bool = False,
    limit: int = 100,
    after_id: int = 0,
    before_id: int | None = None,
    target_ids: Iterable[int] | None = None,
    now=None,
) -> dict[str, object]:
    """有界、幂等地把历史陈旧活动主机收敛为失败，不创建重跑任务。"""
    from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost
    from apps.patch_mgmt.services.patch_execution_service import _finalize_task_status

    current = now or timezone.now()
    bounded_limit = max(1, min(int(limit), 1000))
    expired = (
        (
            Q(
                stage="waiting",
                created_at__lt=current - timedelta(seconds=DISPATCH_TIMEOUT),
            )
            & ~Q(
                task__execution_mode="window",
                task__execution_window_end__gt=current,
            )
        )
        | Q(
            stage__in=("scanning", "installing", "rebooting"),
            stage_deadline_at__lt=current,
        )
        | Q(
            stage="reconciling",
            reconcile_deadline_at__lt=current,
        )
    )
    queryset = GovernanceTaskHost.objects.filter(
        expired,
        id__gt=max(0, int(after_id)),
        task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
    )
    if before_id is not None:
        queryset = queryset.filter(id__lt=max(1, int(before_id)))
    if target_ids is not None:
        normalized_target_ids = sorted({int(target_id) for target_id in target_ids})
        if not normalized_target_ids:
            return {
                "dry_run": bool(dry_run),
                "candidates": 0,
                "changed": 0,
                "host_ids": [],
                "last_id": int(after_id),
            }
        queryset = queryset.filter(target_id__in=normalized_target_ids)
    candidate_ids = list(queryset.order_by("id").values_list("id", flat=True)[:bounded_limit])
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
            host = GovernanceTaskHost.objects.select_for_update().select_related("task").get(pk=host_id)
            if host.task.status not in GovernanceTaskStatus.ACTIVE_STATES:
                continue
            waiting_deadline = _deadline(host, now=current) if host.stage == "waiting" else None
            still_expired = (
                (host.stage == "waiting" and waiting_deadline is not None and waiting_deadline < current)
                or (host.stage in {"scanning", "installing", "rebooting"} and host.stage_deadline_at is not None and host.stage_deadline_at < current)
                or (host.stage == "reconciling" and host.reconcile_deadline_at is not None and host.reconcile_deadline_at < current)
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
