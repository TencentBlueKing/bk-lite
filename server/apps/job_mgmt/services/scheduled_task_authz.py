"""定时任务引用资源的团队边界校验。

定时任务继续沿用历史 ``team`` JSON 列表字段，但业务上只允许保存一个团队。
该团队是调度执行的唯一授权边界，不继承创建者权限，超级管理员也不能绕过
任务与 Script / Playbook / Target 的归属一致性。
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import DatabaseError, transaction

from apps.job_mgmt.constants import JobType, TargetSource
from apps.job_mgmt.models import ScheduledTask, Target
from apps.job_mgmt.services.scheduled_task_service import ScheduledTaskService
from apps.job_mgmt.utils.team_authz import is_team_authorized, normalize_team


@dataclass(frozen=True)
class ScheduledTaskTeamBoundaryError(ValueError):
    """可映射为 DRF 字段错误的团队边界异常。"""

    field: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class ScheduledTaskTeamMigrationPlan:
    """存量任务的只读评估结果。"""

    action: str
    team: int | None
    reason: str


def _resolve(attrs: dict, instance, key: str):
    if key in attrs:
        return attrs[key]
    return getattr(instance, key, None) if instance is not None else None


def _reload_resource(resource, *, lock_resources: bool):
    if resource is None or not lock_resources:
        return resource
    try:
        return resource.__class__.objects.select_for_update().get(pk=resource.pk)
    except resource.__class__.DoesNotExist:
        return None


def _load_targets(target_ids: set[int], *, lock_resources: bool) -> list[Target]:
    queryset = Target.objects.filter(id__in=target_ids)
    if lock_resources:
        queryset = queryset.select_for_update()
    return list(queryset)


def resolve_single_task_team(attrs: dict, *, instance=None) -> int:
    """返回任务唯一团队；空值、多值和不可解析值均拒绝。"""

    raw_team = _resolve(attrs, instance, "team")
    if not isinstance(raw_team, (list, tuple)) or len(raw_team) != 1:
        raise ScheduledTaskTeamBoundaryError("team", "定时任务必须归属单一团队，不能留空或多选")
    try:
        return int(raw_team[0])
    except (TypeError, ValueError) as exc:
        raise ScheduledTaskTeamBoundaryError("team", "定时任务团队 ID 无效") from exc


def validate_scheduled_task_resource_boundary(attrs: dict, *, instance=None, lock_resources: bool = False) -> int:
    """按合并后的任务配置校验所有稳定资源引用。

    ``attrs`` 可为 create 的完整数据或 partial update 的增量数据；未提供字段从
    ``instance`` 回退。返回唯一任务团队 ID，便于调用方复用。
    """

    task_team = resolve_single_task_team(attrs, instance=instance)
    job_type = _resolve(attrs, instance, "job_type")

    if job_type == JobType.FILE_DISTRIBUTION:
        raise ScheduledTaskTeamBoundaryError(
            "files",
            "定时文件分发暂不支持临时文件引用，请在永久团队制品能力可用后再配置",
        )

    if job_type == JobType.SCRIPT:
        script = _reload_resource(_resolve(attrs, instance, "script"), lock_resources=lock_resources)
        if instance is not None and lock_resources:
            instance.script = script
        if script is None and not _resolve(attrs, instance, "script_content"):
            raise ScheduledTaskTeamBoundaryError("script", "定时任务缺少可执行脚本")
        if script is not None and not is_team_authorized(script.team, {task_team}):
            raise ScheduledTaskTeamBoundaryError("script", "关联脚本未授权给定时任务所属团队")
    elif job_type == JobType.PLAYBOOK:
        playbook = _reload_resource(_resolve(attrs, instance, "playbook"), lock_resources=lock_resources)
        if instance is not None and lock_resources:
            instance.playbook = playbook
        if playbook is None:
            raise ScheduledTaskTeamBoundaryError("playbook", "定时任务缺少关联 Playbook")
        if not is_team_authorized(playbook.team, {task_team}):
            raise ScheduledTaskTeamBoundaryError("playbook", "关联 Playbook 未授权给定时任务所属团队")

    if _resolve(attrs, instance, "target_source") == TargetSource.MANUAL:
        target_list = _resolve(attrs, instance, "target_list") or []
        target_ids = [item.get("target_id") for item in target_list if isinstance(item, dict) and item.get("target_id")]
        if len(target_ids) != len(target_list):
            raise ScheduledTaskTeamBoundaryError("target_list", "手动目标必须提供有效的 target_id")

        unique_target_ids = set(target_ids)
        targets = _load_targets(unique_target_ids, lock_resources=lock_resources)
        if len(targets) != len(unique_target_ids):
            raise ScheduledTaskTeamBoundaryError("target_list", "部分目标不存在")
        if any(not is_team_authorized(target.team, {task_team}) for target in targets):
            raise ScheduledTaskTeamBoundaryError("target_list", "部分目标未授权给定时任务所属团队")

    return task_team


def plan_scheduled_task_team_migration(task, *, lock_resources: bool = False) -> ScheduledTaskTeamMigrationPlan:
    """评估存量任务能否唯一归一到一个团队。

    仅当任务原团队与全部稳定资源团队的交集唯一时才自动归一；无法唯一判定、
    引用缺失或仍使用临时文件快照时，一律计划禁用并留待人工确认。
    """

    if task.job_type == JobType.FILE_DISTRIBUTION:
        return ScheduledTaskTeamMigrationPlan("disable", None, "定时文件分发仍使用临时文件快照")

    candidates = normalize_team(task.team)
    if not candidates:
        return ScheduledTaskTeamMigrationPlan("disable", None, "任务没有可确认的原归属团队")

    if task.job_type == JobType.SCRIPT:
        if task.script_id:
            script = _reload_resource(task.script, lock_resources=lock_resources)
            script_teams = normalize_team(script.team)
            if not script_teams:
                return ScheduledTaskTeamMigrationPlan("disable", None, "关联脚本没有团队归属")
            candidates &= script_teams
        elif not task.script_content:
            return ScheduledTaskTeamMigrationPlan("disable", None, "任务缺少可执行脚本")
    elif task.job_type == JobType.PLAYBOOK:
        if not task.playbook_id:
            return ScheduledTaskTeamMigrationPlan("disable", None, "任务缺少关联 Playbook")
        playbook = _reload_resource(task.playbook, lock_resources=lock_resources)
        playbook_teams = normalize_team(playbook.team)
        if not playbook_teams:
            return ScheduledTaskTeamMigrationPlan("disable", None, "关联 Playbook 没有团队归属")
        candidates &= playbook_teams

    if task.target_source == TargetSource.MANUAL:
        target_list = task.target_list or []
        target_ids = [item.get("target_id") for item in target_list if isinstance(item, dict) and item.get("target_id")]
        if len(target_ids) != len(target_list):
            return ScheduledTaskTeamMigrationPlan("disable", None, "手动目标引用不完整")
        unique_target_ids = set(target_ids)
        targets = _load_targets(unique_target_ids, lock_resources=lock_resources)
        if len(targets) != len(unique_target_ids):
            return ScheduledTaskTeamMigrationPlan("disable", None, "部分手动目标已不存在")
        for target in targets:
            target_teams = normalize_team(target.team)
            if not target_teams:
                return ScheduledTaskTeamMigrationPlan("disable", None, f"目标 {target.id} 没有团队归属")
            candidates &= target_teams

    if len(candidates) != 1:
        return ScheduledTaskTeamMigrationPlan("disable", None, "任务与引用资源无法唯一确定同一团队")

    canonical_team = next(iter(candidates))
    if task.team == [canonical_team]:
        return ScheduledTaskTeamMigrationPlan("keep", canonical_team, "任务与全部稳定资源已归属同一团队")
    return ScheduledTaskTeamMigrationPlan("normalize", canonical_team, "任务与全部稳定资源唯一交集可自动归一")


def disable_scheduled_task_and_schedule(task_id: int) -> bool:
    """原子禁用业务任务与 Beat 调度；同步失败时保留原状态供下次重试。"""

    with transaction.atomic():
        try:
            task = ScheduledTask.objects.select_for_update().get(id=task_id)
        except ScheduledTask.DoesNotExist:
            return True
        try:
            with transaction.atomic():
                schedule_synced = ScheduledTaskService.toggle_periodic_task_or_raise(task_id, False)
        except DatabaseError:
            return False
        if not schedule_synced:
            return False
        if task.is_enabled:
            ScheduledTask.objects.filter(id=task_id, is_enabled=True).update(is_enabled=False)
    return True
