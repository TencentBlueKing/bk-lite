"""CMDB 实例 UUID 清洗：手工管理命令执行，启动时拆除历史周期任务。

存量清洗不再由 Beat 每 5 分钟扫描。`batch_init` 只删除历史 PeriodicTask，
不 delay、不同步 --apply。运维按维护窗口执行
`manage.py migrate_cmdb_instance_uuid_runtime`。
Celery 任务名保留，仅用于消化升级前已入队的消息，执行时不再注册周期任务。
"""

from __future__ import annotations

from typing import Any

from celery import shared_task
from django.core.cache import cache
from django.core.management import call_command

from apps.cmdb.services.uuid_migration_runtime import mark_uuid_runtime_migration_complete
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.celery_utils import CeleryUtils

UUID_MIGRATION_PERIODIC_TASK_NAME = "cmdb_instance_uuid_migration"
UUID_MIGRATION_TASK = "apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime"
UUID_MIGRATION_LOCK_KEY = "cmdb:uuid-migration-runtime-lock"
UUID_MIGRATION_LOCK_TTL = 30 * 60


def disable_uuid_migration_periodic_task() -> None:
    """删除历史 UUID 清洗周期任务。清洗改为手工 manage.py。"""
    CeleryUtils.delete_periodic_task(UUID_MIGRATION_PERIODIC_TASK_NAME)


def run_uuid_runtime_migration(*, apply: bool = True, verify: bool = True, dry_run: bool = False) -> dict[str, Any]:
    """幂等执行 CMDB/OA UUID 清洗；多进程互斥；异常不打挂调用方。"""
    if not cache.add(UUID_MIGRATION_LOCK_KEY, "1", timeout=UUID_MIGRATION_LOCK_TTL):
        logger.info("[uuid_migration] another worker holds the lock, skip")
        return {"status": "locked"}

    try:
        if dry_run:
            call_command("migrate_cmdb_instance_uuid_refs", dry_run=True)
            call_command("migrate_oa_cmdb_instance_uuid_refs", dry_run=True)
            return {"status": "dry_run"}

        if apply:
            call_command("migrate_cmdb_instance_uuid_refs", apply=True)
            call_command("migrate_oa_cmdb_instance_uuid_refs", apply=True)

        if verify:
            try:
                call_command("migrate_cmdb_instance_uuid_refs", verify=True)
                call_command("migrate_oa_cmdb_instance_uuid_refs", verify=True)
            except Exception as exc:
                logger.warning("[uuid_migration] verify incomplete, will retry: %s", exc)
                return {"status": "retry", "reason": "verify_failed"}

        if apply and verify:
            mark_uuid_runtime_migration_complete()
            logger.info("[uuid_migration] apply+verify completed")
        return {"status": "done", "skipped": False}
    except Exception:
        logger.exception("[uuid_migration] apply failed, will retry on next manual run")
        return {"status": "retry", "reason": "apply_failed"}
    finally:
        cache.delete(UUID_MIGRATION_LOCK_KEY)


@shared_task(name=UUID_MIGRATION_TASK)
def migrate_cmdb_instance_uuid_runtime() -> dict[str, Any]:
    """消化升级前已入队的清洗消息；不再注册或续期 Beat。"""
    return run_uuid_runtime_migration()
