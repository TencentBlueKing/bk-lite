"""部署后异步收敛 CMDB 实例 UUID 清洗。

batch_init 在未完成时只注册周期任务并 delay 一次。真正 --apply 在 Celery Worker
起来后执行，失败只打日志并由下轮 beat 重试，绝不阻断 supervisord。全部阶段完成后
禁用周期任务，后续启动不再投递。
"""

from __future__ import annotations

import json
from typing import Any

from celery import shared_task
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone

from apps.cmdb.services.uuid_migration_runtime import mark_uuid_runtime_migration_complete
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.celery_utils import CeleryUtils

UUID_MIGRATION_PERIODIC_TASK_NAME = "cmdb_instance_uuid_migration"
UUID_MIGRATION_TASK = "apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime"
UUID_MIGRATION_CRONTAB = "*/5 * * * *"
UUID_MIGRATION_LOCK_KEY = "cmdb:uuid-migration-runtime-lock"
UUID_MIGRATION_LOCK_TTL = 30 * 60


def _periodic_task_matches(task, *, enabled: bool) -> bool:
    if (
        task is None
        or task.enabled != enabled
        or task.task != UUID_MIGRATION_TASK
        or task.crontab_id is None
        or task.interval_id is not None
        or task.solar_id is not None
        or task.clocked_id is not None
    ):
        return False

    minute, hour, day_of_month, month_of_year, day_of_week = UUID_MIGRATION_CRONTAB.split()
    schedule = task.crontab
    if (
        schedule.minute != minute
        or schedule.hour != hour
        or schedule.day_of_month != day_of_month
        or schedule.month_of_year != month_of_year
        or schedule.day_of_week != day_of_week
        or str(schedule.timezone) != str(timezone.get_default_timezone())
    ):
        return False

    try:
        return json.loads(task.args or "[]") == [] and json.loads(task.kwargs or "{}") == {}
    except (TypeError, ValueError):
        return False


def _disable_uuid_migration_periodic_task() -> None:
    current = CeleryUtils.get_periodic_task(UUID_MIGRATION_PERIODIC_TASK_NAME)
    if current is None or not current.enabled:
        return
    CeleryUtils.disable_periodic_task(UUID_MIGRATION_PERIODIC_TASK_NAME)


def ensure_uuid_migration_periodic_task():
    """未完成时保证周期重试存在。verify 通过后保持禁用。出现新阶段时重新打开。"""
    from apps.cmdb.services.uuid_migration_runtime import clear_stale_uuid_runtime_done, is_uuid_migration_periodic_retired

    clear_stale_uuid_runtime_done()
    current = CeleryUtils.get_periodic_task(UUID_MIGRATION_PERIODIC_TASK_NAME)
    if is_uuid_migration_periodic_retired():
        if current is not None and current.enabled:
            CeleryUtils.disable_periodic_task(UUID_MIGRATION_PERIODIC_TASK_NAME)
            current.enabled = False
        return current
    if _periodic_task_matches(current, enabled=True):
        return current
    return CeleryUtils.create_or_update_periodic_task(
        name=UUID_MIGRATION_PERIODIC_TASK_NAME,
        crontab=UUID_MIGRATION_CRONTAB,
        task=UUID_MIGRATION_TASK,
        enabled=True,
    )


@shared_task(name=UUID_MIGRATION_TASK)
def migrate_cmdb_instance_uuid_runtime() -> dict[str, Any]:
    """未完成时幂等清洗；完成后停用周期任务，不再调用管理命令。"""
    from apps.cmdb.services.uuid_migration_runtime import clear_stale_uuid_runtime_done, is_uuid_migration_periodic_retired

    clear_stale_uuid_runtime_done()
    if is_uuid_migration_periodic_retired():
        _disable_uuid_migration_periodic_task()
        logger.info("event=uuid_migration_skipped reason=already_complete")
        return {"status": "done", "skipped": True}

    ensure_uuid_migration_periodic_task()

    if not cache.add(UUID_MIGRATION_LOCK_KEY, "1", timeout=UUID_MIGRATION_LOCK_TTL):
        logger.info("[uuid_migration] another worker holds the lock, skip")
        return {"status": "locked"}

    try:
        call_command("migrate_cmdb_instance_uuid_refs", apply=True)
        call_command("migrate_oa_cmdb_instance_uuid_refs", apply=True)
        try:
            call_command("migrate_cmdb_instance_uuid_refs", verify=True)
            call_command("migrate_oa_cmdb_instance_uuid_refs", verify=True)
        except Exception as exc:
            logger.warning("[uuid_migration] verify incomplete, will retry: %s", exc)
            return {"status": "retry", "reason": "verify_failed"}

        mark_uuid_runtime_migration_complete()
        _disable_uuid_migration_periodic_task()
        logger.info("[uuid_migration] apply+verify completed")
        return {"status": "done", "skipped": False}
    except Exception:
        logger.exception("[uuid_migration] apply failed, will retry on next beat")
        return {"status": "retry", "reason": "apply_failed"}
    finally:
        cache.delete(UUID_MIGRATION_LOCK_KEY)
