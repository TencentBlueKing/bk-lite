from __future__ import absolute_import, unicode_literals

import hashlib
import json
import os
import sys
from datetime import timedelta

from celery import Celery
from celery.schedules import crontab
from django.db import transaction

from apps.core.logger import celery_logger as logger

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

app = Celery("bklite")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

MANAGED_TASK_DESCRIPTION_PREFIX = "[bklite:celery-beat-config:v1:"
RECONCILE_DISABLED_MARKER = "[bklite:celery-beat-config:v1:disabled-by-reconcile]"
RECONCILE_MODE_ENFORCE = "enforce"
RECONCILE_MODE_RESTORE = "restore"
RECONCILE_MODE_SHADOW = "shadow"
RECONCILE_TASK_LIMIT = 100


def _managed_task_marker(task):
    identity = {
        "args": task.args,
        "clocked_id": task.clocked_id,
        "crontab_id": task.crontab_id,
        "interval_id": task.interval_id,
        "kwargs": task.kwargs,
        "name": task.name,
        "solar_id": task.solar_id,
        "task": task.task,
    }
    digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]
    return f"{MANAGED_TASK_DESCRIPTION_PREFIX}{digest}]"


def _description_without_machine_markers(description):
    return "\n".join(
        line for line in description.split("\n") if not line.startswith(MANAGED_TASK_DESCRIPTION_PREFIX) and line != RECONCILE_DISABLED_MARKER
    )


def _mark_config_managed(task):
    description = task.description if isinstance(task.description, str) else ""
    human_description = _description_without_machine_markers(description)
    managed_description = _managed_task_marker(task)
    if human_description:
        managed_description = f"{managed_description}\n{human_description}"
    if description == managed_description:
        return

    task.description = managed_description
    task.save(update_fields=["description"])


def _has_managed_identity(task):
    description = task.description if isinstance(task.description, str) else ""
    return description.split("\n", 1)[0] == _managed_task_marker(task)


def _set_reconcile_provenance(task, *, disabled):
    lines = [line for line in task.description.split("\n") if line != RECONCILE_DISABLED_MARKER]
    if disabled:
        lines.insert(1, RECONCILE_DISABLED_MARKER)
    task.description = "\n".join(lines)


def _bounded_tasks(queryset):
    return list(queryset.order_by("name")[: RECONCILE_TASK_LIMIT + 1])


def _valid_owned_tasks(tasks, *, require_provenance=False):
    valid = []
    collisions = []
    invalid_provenance = []
    for task in tasks:
        if not _has_managed_identity(task):
            collisions.append(task.name)
        elif require_provenance and RECONCILE_DISABLED_MARKER not in task.description.splitlines():
            invalid_provenance.append(task.name)
        else:
            valid.append(task)
    if collisions:
        logger.error("Celery Beat 跳过所有权指纹不匹配的同名任务: %s", ", ".join(collisions))
    if invalid_provenance:
        logger.error("Celery Beat 跳过无精确禁用来源标记的任务: %s", ", ".join(invalid_provenance))
    return valid


def _apply_reconcile_state(stale_tasks, change_tracker, *, restore):
    with transaction.atomic():
        state_candidates = stale_tasks.filter(enabled=not restore)
        if restore:
            provenance_line = f"\n{RECONCILE_DISABLED_MARKER}"
            state_candidates = state_candidates.filter(description__contains=f"{provenance_line}\n") | state_candidates.filter(
                description__endswith=provenance_line
            )
        else:
            state_candidates = state_candidates.filter(description__contains=MANAGED_TASK_DESCRIPTION_PREFIX)
        candidates = _bounded_tasks(state_candidates.select_for_update())
        if len(candidates) > RECONCILE_TASK_LIMIT and not restore:
            logger.error("Celery Beat 对账候选超过单次上限 %s，拒绝修改", RECONCILE_TASK_LIMIT)
            return 0
        if len(candidates) > RECONCILE_TASK_LIMIT:
            candidates = candidates[:RECONCILE_TASK_LIMIT]
            logger.warning("Celery Beat restore 候选超过单次上限 %s，本次分批恢复并需再次运行 restore", RECONCILE_TASK_LIMIT)

        valid_tasks = _valid_owned_tasks(candidates, require_provenance=restore)
        for task in valid_tasks:
            _set_reconcile_provenance(task, disabled=not restore)
            task.enabled = restore
            task.last_run_at = None
            task.no_changes = True
            task.save(update_fields=["description", "enabled", "last_run_at"])
        if valid_tasks:
            change_tracker.update_changed()
        return len(valid_tasks)


def _reconcile_removed_config_tasks(periodic_task_model, change_tracker, current_names, snapshot_complete, reconcile_mode):
    reconcile_mode = str(reconcile_mode).strip().lower()
    if reconcile_mode not in {RECONCILE_MODE_SHADOW, RECONCILE_MODE_ENFORCE, RECONCILE_MODE_RESTORE}:
        logger.warning("未知 Celery Beat 对账模式 %r，按 shadow 处理", reconcile_mode)
        reconcile_mode = RECONCILE_MODE_SHADOW

    stale_tasks = periodic_task_model.objects.filter(description__startswith=MANAGED_TASK_DESCRIPTION_PREFIX).exclude(name__in=current_names)
    if reconcile_mode == RECONCILE_MODE_RESTORE:
        restored_count = _apply_reconcile_state(stale_tasks, change_tracker, restore=True)
        if restored_count:
            logger.warning("Celery Beat 已恢复 %s 个曾退出配置的受管任务", restored_count)
        return

    if not snapshot_complete:
        logger.warning("Celery Beat 配置快照不完整，跳过历史受管任务对账")
        return

    if reconcile_mode != RECONCILE_MODE_ENFORCE:
        candidates = _bounded_tasks(stale_tasks.filter(enabled=True))
        if len(candidates) > RECONCILE_TASK_LIMIT:
            logger.error("Celery Beat shadow 候选超过单次上限 %s，enforce 将拒绝修改", RECONCILE_TASK_LIMIT)
            return
        valid_tasks = _valid_owned_tasks(candidates)
        if valid_tasks:
            logger.warning(
                "Celery Beat shadow 对账发现退出配置的受管任务（上限 %s 个）: %s",
                RECONCILE_TASK_LIMIT,
                ", ".join(task.name for task in valid_tasks),
            )
        return

    disabled_count = _apply_reconcile_state(stale_tasks, change_tracker, restore=False)
    if disabled_count:
        logger.warning("Celery Beat 已禁用 %s 个退出配置的受管任务", disabled_count)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    """将 CELERY_BEAT_SCHEDULE 同步到 django_celery_beat 数据库表"""
    from django.conf import settings

    if "pytest" in sys.modules:
        return

    if not getattr(settings, "IS_USE_CELERY", False):
        return

    from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask, PeriodicTasks

    beat_schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {})
    current_names = set()
    snapshot_complete = getattr(settings, "CELERY_BEAT_SCHEDULE_COMPLETE", False)
    with transaction.atomic():
        for task_name, task_config in beat_schedule.items():
            task_path = task_config.get("task")
            task_schedule = task_config.get("schedule")
            task_args = task_config.get("args", [])
            task_kwargs = task_config.get("kwargs", {})

            if isinstance(task_schedule, crontab):
                schedule_obj, _ = CrontabSchedule.objects.get_or_create(
                    minute=task_schedule._orig_minute,
                    hour=task_schedule._orig_hour,
                    day_of_week=task_schedule._orig_day_of_week,
                    day_of_month=task_schedule._orig_day_of_month,
                    month_of_year=task_schedule._orig_month_of_year,
                )
                periodic_task, _ = PeriodicTask.objects.update_or_create(
                    name=task_name,
                    defaults={
                        "task": task_path,
                        "crontab": schedule_obj,
                        "interval": None,
                        "args": json.dumps(task_args),
                        "kwargs": json.dumps(task_kwargs),
                        "enabled": True,
                    },
                )
                _mark_config_managed(periodic_task)
                current_names.add(task_name)
            elif isinstance(task_schedule, (int, float, timedelta)):
                if isinstance(task_schedule, timedelta):
                    total_microseconds = task_schedule // timedelta(microseconds=1)
                    if total_microseconds >= 1_000_000 and total_microseconds % 1_000_000 == 0:
                        every = total_microseconds // 1_000_000
                        period = IntervalSchedule.SECONDS
                    else:
                        every = total_microseconds
                        period = IntervalSchedule.MICROSECONDS
                else:
                    every = int(task_schedule)
                    period = IntervalSchedule.SECONDS
                schedule_obj, _ = IntervalSchedule.objects.get_or_create(
                    every=every,
                    period=period,
                )
                periodic_task, _ = PeriodicTask.objects.update_or_create(
                    name=task_name,
                    defaults={
                        "task": task_path,
                        "interval": schedule_obj,
                        "crontab": None,
                        "args": json.dumps(task_args),
                        "kwargs": json.dumps(task_kwargs),
                        "enabled": True,
                    },
                )
                _mark_config_managed(periodic_task)
                current_names.add(task_name)
            else:
                snapshot_complete = False
                logger.error("Celery Beat 任务 %s 使用不支持的 schedule 类型 %s", task_name, type(task_schedule).__name__)

        _reconcile_removed_config_tasks(
            PeriodicTask,
            PeriodicTasks,
            current_names,
            snapshot_complete,
            getattr(settings, "CELERY_BEAT_SCHEDULE_RECONCILE_MODE", RECONCILE_MODE_SHADOW),
        )
