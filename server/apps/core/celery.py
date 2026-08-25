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
LEGACY_IMPORTED_MARKER = "[bklite:celery-beat-legacy-import:v1]"
RECONCILE_MODE_ENFORCE = "enforce"
RECONCILE_MODE_RESTORE = "restore"
RECONCILE_MODE_SHADOW = "shadow"
RECONCILE_TASK_LIMIT = 100
LEGACY_IMPORT_LIMIT = 100


def _managed_task_marker(task):
    def stable_value(field):
        value = getattr(task, field, None)
        return value.isoformat() if hasattr(value, "isoformat") else value

    identity = {
        field: stable_value(field)
        for field in (
            "args",
            "clocked_id",
            "crontab_id",
            "enabled",
            "exchange",
            "expire_seconds",
            "expires",
            "headers",
            "interval_id",
            "kwargs",
            "name",
            "one_off",
            "priority",
            "queue",
            "routing_key",
            "solar_id",
            "start_time",
            "task",
        )
    }
    digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]
    return f"{MANAGED_TASK_DESCRIPTION_PREFIX}{digest}]"


def _description_without_machine_markers(description):
    return "\n".join(
        line
        for line in description.split("\n")
        if not line.startswith(MANAGED_TASK_DESCRIPTION_PREFIX)
        and line not in {RECONCILE_DISABLED_MARKER, LEGACY_IMPORTED_MARKER}
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


def _refresh_managed_identity(task):
    description_lines = [
        line
        for line in task.description.split("\n")
        if line == RECONCILE_DISABLED_MARKER or not line.startswith(MANAGED_TASK_DESCRIPTION_PREFIX)
    ]
    task.description = "\n".join([_managed_task_marker(task), *description_lines])


def _normalize_legacy_managed_names(raw_names):
    if raw_names in (None, "", (), [], set()):
        return (), True
    if isinstance(raw_names, str):
        names = raw_names.split(",")
    elif isinstance(raw_names, (list, tuple, set)):
        names = list(raw_names)
    else:
        logger.error("Celery Beat 历史静态任务基线必须是逗号分隔字符串或字符串列表")
        return (), False
    if any(not isinstance(name, str) or not name.strip() for name in names):
        logger.error("Celery Beat 历史静态任务基线包含空值或非字符串名称，拒绝迁移")
        return (), False
    normalized = []
    seen_names = set()
    for item in names:
        item = item.strip()
        name, separator, expected_fingerprint = item.rpartition("@")
        if not separator:
            name, expected_fingerprint = item, None
        elif not name or len(expected_fingerprint) != 20 or any(char not in "0123456789abcdef" for char in expected_fingerprint):
            logger.error("Celery Beat 历史静态任务基线指纹格式无效，拒绝迁移")
            return (), False
        if name in seen_names:
            logger.error("Celery Beat 历史静态任务基线包含重复名称，拒绝迁移")
            return (), False
        seen_names.add(name)
        normalized.append((name, expected_fingerprint))
    normalized = tuple(sorted(normalized))
    if len(normalized) > LEGACY_IMPORT_LIMIT:
        logger.error("Celery Beat 历史静态任务基线超过上限 %s，拒绝迁移", LEGACY_IMPORT_LIMIT)
        return (), False
    return normalized, True


def _legacy_import_candidates(periodic_task_model, names, current_names):
    candidates = []
    already_owned = []
    collisions = []
    missing = []
    configured_names = [name for name, _ in names]
    tasks = {task.name: task for task in periodic_task_model.objects.filter(name__in=configured_names).order_by("name")}
    drifted = []
    for name, expected_fingerprint in names:
        task = tasks.get(name)
        if task is None:
            missing.append(name)
        elif name in current_names:
            already_owned.append(name)
        elif isinstance(task.description, str) and task.description.startswith(MANAGED_TASK_DESCRIPTION_PREFIX):
            (already_owned if _has_managed_identity(task) else collisions).append(name)
        elif expected_fingerprint and _managed_task_marker(task) != f"{MANAGED_TASK_DESCRIPTION_PREFIX}{expected_fingerprint}]":
            drifted.append(name)
        else:
            candidates.append(task)
    if collisions:
        logger.error("Celery Beat 历史基线跳过所有权冲突任务: %s", ", ".join(collisions))
    if missing:
        logger.warning("Celery Beat 历史基线未找到数据库任务: %s", ", ".join(missing))
    if drifted:
        logger.error("Celery Beat 历史基线行指纹已漂移，拒绝接管: %s", ", ".join(drifted))
    return candidates, already_owned, missing, collisions, drifted


def _prepare_legacy_managed_tasks(periodic_task_model, current_names, reconcile_mode, raw_names):
    names, valid = _normalize_legacy_managed_names(raw_names)
    if not valid:
        return (), False
    if not names:
        return (), True
    candidates, already_owned, missing, collisions, drifted = _legacy_import_candidates(
        periodic_task_model, names, current_names
    )
    if reconcile_mode != RECONCILE_MODE_ENFORCE:
        logger.warning(
            "Celery Beat 历史基线预检: candidates=%s already_owned=%s",
            ", ".join(f"{task.name}@{_managed_task_marker(task)[len(MANAGED_TASK_DESCRIPTION_PREFIX):-1]}" for task in candidates)
            or "-",
            ", ".join(already_owned) or "-",
        )
        return tuple(name for name, _ in names), True
    if any(expected_fingerprint is None for _, expected_fingerprint in names):
        logger.error("Celery Beat enforce 要求使用 shadow 输出的名称与行指纹，拒绝迁移")
        return (), False
    if missing or collisions or drifted:
        logger.error("Celery Beat 历史基线与 shadow 快照不一致，拒绝迁移")
        return (), False
    for task in candidates:
        task.no_changes = True
        _mark_config_managed(task)
        description_lines = task.description.splitlines()
        description_lines.insert(1, LEGACY_IMPORTED_MARKER)
        task.description = "\n".join(description_lines)
        task.save(update_fields=["description"])
        transaction.on_commit(
            lambda task_name=task.name: logger.warning(
                "Celery Beat 历史基线逐项结果: task=%s action=import-ownership result=success",
                task_name,
            )
        )
    return tuple(name for name, _ in names), True


def _release_legacy_managed_tasks(periodic_task_model, change_tracker, names):
    if not names:
        return
    tasks = list(
        periodic_task_model.objects.select_for_update()
        .filter(
            name__in=names,
            description__startswith=MANAGED_TASK_DESCRIPTION_PREFIX,
            description__contains=LEGACY_IMPORTED_MARKER,
        )
        .order_by("name")[:LEGACY_IMPORT_LIMIT]
    )
    released_count = 0
    for task in tasks:
        if LEGACY_IMPORTED_MARKER not in task.description.splitlines():
            continue
        if not task.enabled and RECONCILE_DISABLED_MARKER in task.description.splitlines():
            continue
        task.description = _description_without_machine_markers(task.description)
        task.no_changes = True
        task.save(update_fields=["description"])
        released_count += 1
        transaction.on_commit(
            lambda task_name=task.name: logger.warning(
                "Celery Beat 历史基线逐项结果: task=%s action=release-imported-ownership result=success",
                task_name,
            )
        )
    if released_count:
        change_tracker.update_changed()


def _bounded_tasks(queryset):
    return list(queryset.order_by("name")[: RECONCILE_TASK_LIMIT + 1])


def _valid_owned_tasks(tasks, *, require_provenance=False, release_invalid=False):
    valid = []
    collisions = []
    invalid_provenance = []
    released = []
    for task in tasks:
        if not _has_managed_identity(task):
            collisions.append(task.name)
        elif require_provenance and RECONCILE_DISABLED_MARKER not in task.description.splitlines():
            invalid_provenance.append(task.name)
        else:
            valid.append(task)
            continue
        if release_invalid:
            task.description = _description_without_machine_markers(task.description)
            task.no_changes = True
            task.save(update_fields=["description"])
            released.append(task.name)
    if collisions:
        logger.error("Celery Beat 跳过所有权指纹不匹配的同名任务: %s", ", ".join(collisions))
    if invalid_provenance:
        logger.error("Celery Beat 跳过无精确禁用来源标记的任务: %s", ", ".join(invalid_provenance))
    return valid, released


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
        if len(candidates) > RECONCILE_TASK_LIMIT:
            candidates = candidates[:RECONCILE_TASK_LIMIT]
            logger.warning(
                "Celery Beat %s 候选超过单次上限 %s，本次分批处理并需再次运行",
                RECONCILE_MODE_RESTORE if restore else RECONCILE_MODE_ENFORCE,
                RECONCILE_TASK_LIMIT,
            )

        valid_tasks, released_tasks = _valid_owned_tasks(candidates, require_provenance=restore, release_invalid=True)
        action = RECONCILE_MODE_RESTORE if restore else "disable"
        for task in valid_tasks:
            task.enabled = restore
            task.last_run_at = None
            task.no_changes = True
            _set_reconcile_provenance(task, disabled=not restore)
            _refresh_managed_identity(task)
            task.save(update_fields=["description", "enabled", "last_run_at"])
            transaction.on_commit(
                lambda task_name=task.name: logger.warning(
                    "Celery Beat 对账逐项结果: task=%s action=%s result=success",
                    task_name,
                    action,
                )
            )
        for task_name in released_tasks:
            transaction.on_commit(
                lambda released_name=task_name: logger.warning(
                    "Celery Beat 对账逐项结果: task=%s action=release-stale-ownership result=success",
                    released_name,
                )
            )
        if valid_tasks or released_tasks:
            change_tracker.update_changed()
            transaction.on_commit(
                lambda changed_count=len(valid_tasks), released_count=len(released_tasks): logger.warning(
                    "Celery Beat 已%s %s 个退出配置的受管任务，释放 %s 个失效所有权标记",
                    "恢复" if restore else "禁用",
                    changed_count,
                    released_count,
                )
            )
        return len(valid_tasks)


def _reconcile_removed_config_tasks(periodic_task_model, change_tracker, current_names, snapshot_complete, reconcile_mode):
    reconcile_mode = str(reconcile_mode).strip().lower()
    if reconcile_mode not in {RECONCILE_MODE_SHADOW, RECONCILE_MODE_ENFORCE, RECONCILE_MODE_RESTORE}:
        logger.warning("未知 Celery Beat 对账模式 %r，按 shadow 处理", reconcile_mode)
        reconcile_mode = RECONCILE_MODE_SHADOW

    stale_tasks = periodic_task_model.objects.filter(description__startswith=MANAGED_TASK_DESCRIPTION_PREFIX).exclude(name__in=current_names)
    if reconcile_mode == RECONCILE_MODE_RESTORE:
        _apply_reconcile_state(stale_tasks, change_tracker, restore=True)
        return

    if not snapshot_complete:
        logger.warning("Celery Beat 配置快照不完整，跳过历史受管任务对账")
        return

    if reconcile_mode != RECONCILE_MODE_ENFORCE:
        candidates = _bounded_tasks(stale_tasks.filter(enabled=True))
        if len(candidates) > RECONCILE_TASK_LIMIT:
            candidates = candidates[:RECONCILE_TASK_LIMIT]
            logger.warning("Celery Beat shadow 候选超过单次展示上限 %s，仅输出本批明细", RECONCILE_TASK_LIMIT)
        valid_tasks, _ = _valid_owned_tasks(candidates)
        if valid_tasks:
            logger.warning(
                "Celery Beat shadow 对账发现退出配置的受管任务（上限 %s 个）: %s",
                RECONCILE_TASK_LIMIT,
                ", ".join(task.name for task in valid_tasks),
            )
        return

    _apply_reconcile_state(stale_tasks, change_tracker, restore=False)


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

        reconcile_mode = getattr(settings, "CELERY_BEAT_SCHEDULE_RECONCILE_MODE", RECONCILE_MODE_SHADOW)
        normalized_reconcile_mode = str(reconcile_mode).strip().lower()
        legacy_names, legacy_names_valid = _prepare_legacy_managed_tasks(
            PeriodicTask,
            current_names,
            normalized_reconcile_mode,
            getattr(settings, "CELERY_BEAT_SCHEDULE_LEGACY_MANAGED_NAMES", ""),
        )
        if not legacy_names_valid:
            return
        _reconcile_removed_config_tasks(
            PeriodicTask,
            PeriodicTasks,
            current_names,
            snapshot_complete,
            reconcile_mode,
        )
        if normalized_reconcile_mode == RECONCILE_MODE_RESTORE:
            _release_legacy_managed_tasks(PeriodicTask, PeriodicTasks, legacy_names)
