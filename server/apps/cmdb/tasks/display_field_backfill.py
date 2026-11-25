"""部署后异步回填 CMDB 实例 _display。

batch_init 在阶段未完成时 delay 一次，并停用历史周期任务。真正扫描在 Celery Worker
起来后执行，按页跳过未变化的值。查询失败、软超时和锁冲突 60 秒后自己续跑。
"""

from __future__ import annotations

import json
from typing import Any

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone

from apps.cmdb.display_field.initializer import DisplayFieldInitializer
from apps.cmdb.models.repair_state import DISPLAY_BACKFILL_STAGE, CmdbRepairState, mark_display_backfill_dirty
from apps.cmdb.services.unique_write_lock import UniqueWriteLockService
from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info
from apps.core.utils.celery_utils import CeleryUtils

DISPLAY_BACKFILL_PERIODIC_TASK_NAME = "cmdb_display_field_backfill"
DISPLAY_BACKFILL_TASK = "apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields"
DISPLAY_BACKFILL_CURSOR_KEY = "cmdb:display-field-backfill-cursor"
DISPLAY_BACKFILL_COMPLETED_KEY = "cmdb:display-field-backfill-completed"
DISPLAY_BACKFILL_BUDGET = 2000
DISPLAY_BACKFILL_CONTINUE_COUNTDOWN = 1
DISPLAY_BACKFILL_RETRY_COUNTDOWN = 60
DISPLAY_BACKFILL_LOCK = "cmdb-display-field-sync"
DISPLAY_BACKFILL_LOCK_LEASE = 310


def display_backfill_pending() -> bool:
    """没有完成记录、未完成，或游标还在，都还要清洗。"""
    row = CmdbRepairState.objects.filter(stage=DISPLAY_BACKFILL_STAGE).first()
    if row is None:
        return True
    return not (row.completed and not row.cursor)


def disable_display_field_backfill_periodic_task():
    """停用历史上每 5 分钟的回填任务。没有这条记录时不创建。"""
    current = CeleryUtils.get_periodic_task(DISPLAY_BACKFILL_PERIODIC_TASK_NAME)
    if current is None or not current.enabled:
        return current
    current.enabled = False
    current.save(update_fields=["enabled"])
    return current


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


def _store_if_same_generation(row: CmdbRepairState, generation: str, *, completed: bool, cursor) -> bool:
    """只在代数没变时写游标或完成标记。新的展示字段已经把代数往前推时，旧任务必须停手。"""
    updated = CmdbRepairState.objects.filter(pk=row.pk, fingerprint=generation).update(
        completed=completed,
        cursor="" if not cursor else json.dumps(cursor, ensure_ascii=False),
        updated_at=timezone.now(),
    )
    return updated == 1


def _idle(row: CmdbRepairState) -> bool:
    return bool(row.completed) and not row.cursor


def _schedule_again(countdown: int) -> None:
    try:
        backfill_cmdb_display_fields.apply_async(countdown=countdown)
    except Exception as exc:
        logger.warning(
            "event=display_backfill_enqueue_failed failed_stage=enqueue error_type=%s countdown=%s",
            type(exc).__name__,
            countdown,
            exc_info=safe_exception_info(exc),
        )


def enqueue_display_instance_backfill() -> None:
    """投递一次回填。失败只记类型，留到下次启动。"""
    try:
        backfill_cmdb_display_fields.delay(force=False)
    except Exception as exc:
        logger.warning(
            "event=display_backfill_enqueue_failed failed_stage=enqueue error_type=%s",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )


def request_display_instance_backfill() -> None:
    """新的展示字段出现后清掉完成标记，并投递一次。"""
    mark_display_backfill_dirty()
    enqueue_display_instance_backfill()


@shared_task(name=DISPLAY_BACKFILL_TASK, soft_time_limit=240, time_limit=300)
def backfill_cmdb_display_fields(force: bool = False) -> dict[str, Any]:
    """分页回填实例 _display。与组织/用户同步共用写锁，避免两路同时改同一字段。"""
    if force:
        mark_display_backfill_dirty()
    elif _idle(_display_state()):
        disable_display_field_backfill_periodic_task()
        return {"status": "idle"}

    try:
        with UniqueWriteLockService.serialize(DISPLAY_BACKFILL_LOCK, lease_seconds=DISPLAY_BACKFILL_LOCK_LEASE):
            return _backfill_under_lock()
    except TimeoutError:
        logger.info("event=display_backfill_locked")
        _schedule_again(DISPLAY_BACKFILL_RETRY_COUNTDOWN)
        return {"status": "locked"}
    except SoftTimeLimitExceeded as exc:
        logger.warning(
            "event=display_backfill_soft_timeout failed_stage=backfill error_type=%s",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        _schedule_again(DISPLAY_BACKFILL_RETRY_COUNTDOWN)
        return {"status": "retry", "reason": "soft_timeout"}
    except Exception as exc:
        logger.error(
            "event=display_backfill_failed failed_stage=backfill error_type=%s",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        _schedule_again(DISPLAY_BACKFILL_RETRY_COUNTDOWN)
        return {"status": "retry", "reason": "backfill_failed"}


def _backfill_under_lock() -> dict[str, Any]:
    row = _display_state()
    cursor = _load_cursor(row)
    initializer = DisplayFieldInitializer()
    if cursor is None:
        initializer.initialize_all(instances=False)
        row.refresh_from_db()
        cursor = _load_cursor(row)
    generation = row.fingerprint
    result = initializer.backfill_bounded(max_instances=DISPLAY_BACKFILL_BUDGET, cursor=cursor)
    row.refresh_from_db()
    if row.fingerprint != generation:
        logger.info("event=display_backfill_reset")
        return {"status": "reset", "instances_updated": result["instances_updated"]}
    if result["query_failed"]:
        if not _store_if_same_generation(row, generation, completed=False, cursor=result["next_cursor"]):
            logger.info("event=display_backfill_reset")
            return {"status": "reset", "instances_updated": result["instances_updated"]}
        logger.warning(
            "event=display_backfill_query_paused model_id=%s",
            (result.get("next_cursor") or {}).get("model_id"),
        )
        _schedule_again(DISPLAY_BACKFILL_RETRY_COUNTDOWN)
        return {"status": "retry", "reason": "query_failed", "instances_updated": result["instances_updated"]}
    if result["done"]:
        if not _store_if_same_generation(row, generation, completed=True, cursor=None):
            logger.info("event=display_backfill_reset")
            return {"status": "reset", "instances_updated": result["instances_updated"]}
        disable_display_field_backfill_periodic_task()
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

    if not _store_if_same_generation(row, generation, completed=False, cursor=result["next_cursor"]):
        logger.info("event=display_backfill_reset")
        return {"status": "reset", "instances_updated": result["instances_updated"]}
    _schedule_again(DISPLAY_BACKFILL_CONTINUE_COUNTDOWN)
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
