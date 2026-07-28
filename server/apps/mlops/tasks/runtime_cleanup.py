from celery import shared_task

from apps.core.logger import mlops_logger as logger
from apps.mlops.services.timeseries_runtime_cleanup import (
    reconcile_orphan_timeseries_runtime,
)


@shared_task(
    bind=True,
    max_retries=None,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=60,
    time_limit=90,
)
def cleanup_orphan_timeseries_runtime(self, container_id: str, serving_id: int) -> dict:
    """持续退避重试，直到确认 orphan runtime 不存在或 ID 已被数据库重新接管。"""
    try:
        return reconcile_orphan_timeseries_runtime(container_id, serving_id)
    except Exception as error:
        countdown = min(3600, 30 * (2 ** min(self.request.retries, 7)))
        logger.warning(
            "时序 orphan runtime 清理未确认，将自动重试: container_id=%s, retry=%s, error_type=%s",
            container_id,
            self.request.retries + 1,
            type(error).__name__,
        )
        raise self.retry(exc=error, countdown=countdown)
