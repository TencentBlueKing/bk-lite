from datetime import timedelta

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from apps.core.logger import node_mgmt_logger as logger
from apps.core.logger import safe_exception_info, safe_log_value
from apps.node_mgmt.models.sidecar import CollectorDefaultBackfill
from apps.node_mgmt.services.collector_default_backfill import execute_collector_default_backfill

MAX_ATTEMPTS = 5
STALE_LOCK = timedelta(minutes=15)
COMPLETED_LOG = "event=collector_default_backfill_completed collector_id=%s status=%s created=%s failed=%s"
EXHAUSTED_LOG = "event=collector_default_backfill_exhausted collector_id=%s failed_stage=node error_type=%s attempts=%s"
TASK_FAILED_LOG = "event=collector_default_backfill_failed collector_id=%s failed_stage=%s error_type=%s"
SCHEDULE_FAILED_LOG = "event=collector_default_backfill_schedule_failed failed_stage=%s error_type=%s"
CATALOG_ETAG_FAILED_LOG = "event=collector_catalog_etag_invalidate_failed failed_stage=cache error_type=%s"


def enqueue_collector_default_backfill(*, schedule_task):
    """有待补齐记录时清采集器目录缓存并投递任务。投递失败不抛出。"""
    if not schedule_task:
        return
    try:
        cache.delete("collectors_etag")
    except Exception as exc:
        logger.warning(CATALOG_ETAG_FAILED_LOG, type(exc).__name__)
    try:
        backfill_collector_default_configs.delay()
    except Exception as exc:
        logger.warning(SCHEDULE_FAILED_LOG, "enqueue", type(exc).__name__)


def _reclaim_stale_locks():
    cutoff = timezone.now() - STALE_LOCK
    CollectorDefaultBackfill.objects.filter(status=CollectorDefaultBackfill.STATUS_RUNNING, locked_at__lt=cutoff).update(
        status=CollectorDefaultBackfill.STATUS_PENDING,
        locked_at=None,
        updated_at=timezone.now(),
    )


def _claim_next_backfill():
    _reclaim_stale_locks()
    candidate_id = (
        CollectorDefaultBackfill.objects.filter(status=CollectorDefaultBackfill.STATUS_PENDING)
        .order_by("created_at", "collector_id")
        .values_list("collector_id", flat=True)
        .first()
    )
    if not candidate_id:
        return None
    now = timezone.now()
    claimed = CollectorDefaultBackfill.objects.filter(
        collector_id=candidate_id,
        status=CollectorDefaultBackfill.STATUS_PENDING,
    ).update(
        status=CollectorDefaultBackfill.STATUS_RUNNING,
        locked_at=now,
        updated_at=now,
    )
    if not claimed:
        return None
    locked_at = CollectorDefaultBackfill.objects.filter(collector_id=candidate_id).values_list("locked_at", flat=True).first()
    return candidate_id, locked_at


def _owned_update(collector_id, locked_at, **fields):
    fields["locked_at"] = None
    fields["updated_at"] = timezone.now()
    return CollectorDefaultBackfill.objects.filter(
        collector_id=collector_id,
        status=CollectorDefaultBackfill.STATUS_RUNNING,
        locked_at=locked_at,
    ).update(**fields)


def _log_completed(collector_id, status, created, failed):
    log = logger.warning if failed else logger.info
    log(COMPLETED_LOG, safe_log_value(collector_id), status, created, failed)


def _consume_attempt(collector_id, locked_at):
    row = CollectorDefaultBackfill.objects.filter(
        collector_id=collector_id,
        status=CollectorDefaultBackfill.STATUS_RUNNING,
        locked_at=locked_at,
    ).first()
    if row is None:
        return None
    attempts = row.attempts + 1
    status = CollectorDefaultBackfill.STATUS_FAILED if attempts >= MAX_ATTEMPTS else CollectorDefaultBackfill.STATUS_PENDING
    updated = CollectorDefaultBackfill.objects.filter(
        collector_id=collector_id,
        status=CollectorDefaultBackfill.STATUS_RUNNING,
        locked_at=locked_at,
        attempts=row.attempts,
    ).update(
        attempts=attempts,
        status=status,
        cursor_id="",
        saw_failure=False,
        locked_at=None,
        updated_at=timezone.now(),
    )
    if not updated:
        return None
    return status, attempts


def _apply_result(collector_id, locked_at, result):
    row = CollectorDefaultBackfill.objects.filter(
        collector_id=collector_id,
        status=CollectorDefaultBackfill.STATUS_RUNNING,
        locked_at=locked_at,
    ).first()
    if row is None:
        return None
    saw_failure = row.saw_failure or result["failed"] > 0
    if result["hit_limit"]:
        updated = _owned_update(
            collector_id,
            locked_at,
            status=CollectorDefaultBackfill.STATUS_PENDING,
            cursor_id=result["cursor_id"],
            saw_failure=saw_failure,
        )
        if not updated:
            return None
        _log_completed(collector_id, CollectorDefaultBackfill.STATUS_PENDING, result["created"], result["failed"])
        return CollectorDefaultBackfill.STATUS_PENDING

    if saw_failure:
        consumed = _consume_attempt(collector_id, locked_at)
        if consumed is None:
            return None
        status, attempts = consumed
        if status == CollectorDefaultBackfill.STATUS_FAILED:
            last_error = result.get("last_error")
            logger.error(
                EXHAUSTED_LOG,
                safe_log_value(collector_id),
                type(last_error).__name__ if last_error else "node",
                attempts,
                exc_info=safe_exception_info(last_error) if last_error else None,
            )
        else:
            _log_completed(collector_id, status, result["created"], result["failed"])
        return status

    updated = _owned_update(
        collector_id,
        locked_at,
        status=CollectorDefaultBackfill.STATUS_DONE,
        cursor_id="",
        saw_failure=False,
    )
    if not updated:
        return None
    _log_completed(collector_id, CollectorDefaultBackfill.STATUS_DONE, result["created"], result["failed"])
    return CollectorDefaultBackfill.STATUS_DONE


def _record_hard_failure(collector_id, locked_at):
    _consume_attempt(collector_id, locked_at)


def _process_claimed(collector_id, locked_at):
    cursor_id = (
        CollectorDefaultBackfill.objects.filter(collector_id=collector_id, locked_at=locked_at).values_list("cursor_id", flat=True).first()
        or ""
    )
    try:
        result = execute_collector_default_backfill(collector_id, after_id=cursor_id)
    except Exception as exc:
        logger.error(
            TASK_FAILED_LOG,
            safe_log_value(collector_id),
            "backfill",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        _record_hard_failure(collector_id, locked_at)
        return
    _apply_result(collector_id, locked_at, result)


@shared_task
def backfill_collector_default_configs():
    """领取一条待补齐记录并处理有限数量的节点。没有待处理记录时直接返回。"""
    claimed = _claim_next_backfill()
    if not claimed:
        return {"claimed": False}
    collector_id, locked_at = claimed
    _process_claimed(collector_id, locked_at)
    return {"claimed": True, "collector_id": collector_id}
