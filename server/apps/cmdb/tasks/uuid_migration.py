"""部署后异步收敛 CMDB 实例 UUID 清洗。

batch_init 只注册周期任务并 delay 一次；真正 --apply 在 Celery Worker 起来后执行，
失败只打日志并由下轮 beat 重试，绝不阻断 supervisord。
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


def ensure_uuid_migration_periodic_task():
    """保证 UUID 清洗周期任务存在。可变快照会再次写入遗留 ID，任务保持启用。"""
    current = CeleryUtils.get_periodic_task(UUID_MIGRATION_PERIODIC_TASK_NAME)
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
    """幂等执行 CMDB/OA UUID 清洗；多 Worker 互斥；异常不打挂 Worker。"""
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
        logger.info("[uuid_migration] apply+verify completed")
        return {"status": "done", "skipped": False}
    except Exception:
        logger.exception("[uuid_migration] apply failed, will retry on next beat")
        return {"status": "retry", "reason": "apply_failed"}
    finally:
        cache.delete(UUID_MIGRATION_LOCK_KEY)
