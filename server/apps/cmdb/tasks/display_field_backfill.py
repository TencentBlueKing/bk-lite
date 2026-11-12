"""部署后异步回填 CMDB 实例 _display。

batch_init 只注册周期任务并 delay 一次。真正扫描在 Celery Worker 起来后执行，
按页跳过未变化的值，失败不阻断 supervisord。
"""

from __future__ import annotations

import json
from typing import Any

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone

from apps.cmdb.display_field.initializer import DisplayFieldInitializer
from apps.cmdb.models.repair_state import DISPLAY_BACKFILL_STAGE, CmdbRepairState
from apps.cmdb.services.unique_write_lock import UniqueWriteLockService
from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info
from apps.core.utils.celery_utils import CeleryUtils

DISPLAY_BACKFILL_PERIODIC_TASK_NAME = "cmdb_display_field_backfill"
DISPLAY_BACKFILL_TASK = "apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields"
DISPLAY_BACKFILL_CRONTAB = "*/5 * * * *"
DISPLAY_BACKFILL_CURSOR_KEY = "cmdb:display-field-backfill-cursor"
DISPLAY_BACKFILL_COMPLETED_KEY = "cmdb:display-field-backfill-completed"
DISPLAY_BACKFILL_CURSOR_TTL = 24 * 60 * 60
DISPLAY_BACKFILL_COOLDOWN = 24 * 60 * 60
DISPLAY_BACKFILL_BUDGET = 2000
DISPLAY_BACKFILL_LOCK = "cmdb-display-field-sync"
DISPLAY_BACKFILL_LOCK_LEASE = 310


def _periodic_task_matches(task, *, enabled: bool) -> bool:
    if (
        task is None
        or task.enabled != enabled
        or task.task != DISPLAY_BACKFILL_TASK
        or task.crontab_id is None
        or task.interval_id is not None
        or task.solar_id is not None
        or task.clocked_id is not None
    ):
        return False

    minute, hour, day_of_month, month_of_year, day_of_week = DISPLAY_BACKFILL_CRONTAB.split()
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


def ensure_display_field_backfill_periodic_task():
    """保证显示字段回填周期任务存在。未完成的游标由周期任务接着跑。"""
    current = CeleryUtils.get_periodic_task(DISPLAY_BACKFILL_PERIODIC_TASK_NAME)
    if _periodic_task_matches(current, enabled=True):
        return current
    return CeleryUtils.create_or_update_periodic_task(
        name=DISPLAY_BACKFILL_PERIODIC_TASK_NAME,
        crontab=DISPLAY_BACKFILL_CRONTAB,
        task=DISPLAY_BACKFILL_TASK,
        enabled=True,
    )


def _display_state() -> CmdbRepairState:
    row, _created = CmdbRepairState.objects.get_or_create(
        stage=DISPLAY_BACKFILL_STAGE,
        defaults={"completed": False, "cursor": ""},
    )
    return row


def _load_cursor(row: CmdbRepairState):
    if not row.cursor:
        return None
    try:
        return json.loads(row.cursor)
    except json.JSONDecodeError:
        return None


def _store_cursor(row: CmdbRepairState, cursor) -> None:
    row.cursor = "" if not cursor else json.dumps(cursor, ensure_ascii=False)
    row.completed = False
    row.save(update_fields=["cursor", "completed", "updated_at"])


def _idle(row: CmdbRepairState) -> bool:
    return bool(row.completed) and not row.cursor


@shared_task(name=DISPLAY_BACKFILL_TASK, soft_time_limit=240, time_limit=300)
def backfill_cmdb_display_fields(force: bool = False) -> dict[str, Any]:
    """分页回填实例 _display。与组织/用户同步共用写锁，避免两路同时改同一字段。"""
    ensure_display_field_backfill_periodic_task()
    row = _display_state()
    if force:
        row.completed = False
        row.cursor = ""
        row.save(update_fields=["completed", "cursor", "updated_at"])
    elif _idle(row):
        return {"status": "idle"}

    try:
        with UniqueWriteLockService.serialize(DISPLAY_BACKFILL_LOCK, lease_seconds=DISPLAY_BACKFILL_LOCK_LEASE):
            return _backfill_under_lock()
    except TimeoutError:
        logger.info("event=display_backfill_locked")
        return {"status": "locked"}
    except SoftTimeLimitExceeded as exc:
        logger.warning(
            "event=display_backfill_soft_timeout failed_stage=backfill error_type=%s",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        return {"status": "retry", "reason": "soft_timeout"}
    except Exception as exc:
        logger.error(
            "event=display_backfill_failed failed_stage=backfill error_type=%s",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        return {"status": "retry", "reason": "backfill_failed"}


def _backfill_under_lock() -> dict[str, Any]:
    row = _display_state()
    cursor = _load_cursor(row)
    initializer = DisplayFieldInitializer()
    if cursor is None:
        initializer.initialize_all(instances=False)
    result = initializer.backfill_bounded(max_instances=DISPLAY_BACKFILL_BUDGET, cursor=cursor)
    if result["query_failed"]:
        _store_cursor(row, result["next_cursor"])
        logger.warning(
            "event=display_backfill_query_paused model_id=%s",
            (result.get("next_cursor") or {}).get("model_id"),
        )
        return {"status": "retry", "reason": "query_failed", "instances_updated": result["instances_updated"]}
    if result["done"]:
        row.completed = True
        row.cursor = ""
        row.save(update_fields=["completed", "cursor", "updated_at"])
        logger.info(
            "event=display_backfill_finished instances_seen=%s instances_updated=%s error_count=%s",
            result["instances_seen"],
            result["instances_updated"],
            len(result["errors"]),
        )
        return {
            "status": "done",
            "instances_seen": result["instances_seen"],
            "instances_updated": result["instances_updated"],
        }

    _store_cursor(row, result["next_cursor"])
    backfill_cmdb_display_fields.apply_async(countdown=1)
    logger.info(
        "event=display_backfill_continue instances_seen=%s instances_updated=%s",
        result["instances_seen"],
        result["instances_updated"],
    )
    return {
        "status": "continue",
        "instances_seen": result["instances_seen"],
        "instances_updated": result["instances_updated"],
    }
