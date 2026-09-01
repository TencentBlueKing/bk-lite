from collections.abc import Iterable

from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info


def dispatch_operation_outbox(event_ids: Iterable[str]) -> int:
    """尽力即时派发已提交的 operation outbox，失败时保留给周期补偿。"""
    from apps.cmdb.tasks.celery_tasks import consume_cmdb_operation_outbox

    dispatched = 0
    for event_id in event_ids:
        try:
            consume_cmdb_operation_outbox.delay(str(event_id))
        except Exception as exc:
            logger.error(
                "event=cmdb_operation_outbox_dispatch_failed event_id=%s failed_stage=%s error_type=%s",
                event_id,
                "broker_dispatch",
                exc.__class__.__name__,
                exc_info=safe_exception_info(exc),
            )
            continue
        dispatched += 1
    return dispatched
