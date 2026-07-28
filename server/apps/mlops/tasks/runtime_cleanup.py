from celery import shared_task

from apps.core.logger import mlops_logger as logger
from apps.mlops.services.timeseries_runtime_cleanup import (
    claim_pending_runtime_cleanup_intents,
    create_runtime_cleanup_intent,
    process_runtime_cleanup_intent,
    release_runtime_cleanup_intent,
)


@shared_task(
    bind=True,
    max_retries=None,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=60,
    time_limit=90,
)
def cleanup_orphan_timeseries_runtime(self, intent_id: int) -> dict:
    """持续退避重试持久意图，直到 orphan 不存在或 ID 已被业务记录接管。"""
    try:
        return process_runtime_cleanup_intent(intent_id)
    except Exception as error:
        countdown = min(3600, 30 * (2 ** min(self.request.retries, 7)))
        logger.warning(
            "时序 orphan runtime 清理未确认，将自动重试: intent_id=%s, retry=%s, error_type=%s",
            intent_id,
            self.request.retries + 1,
            type(error).__name__,
        )
        raise self.retry(exc=error, countdown=countdown)


@shared_task(
    bind=True,
    max_retries=None,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=60,
    time_limit=90,
)
def bootstrap_timeseries_runtime_cleanup(
    self,
    container_id: str,
    serving_id: int,
    cleanup_token: str,
) -> dict:
    """数据库恢复后重建未能持久化的 intent，并进入同一清理闭环。"""
    try:
        intent = create_runtime_cleanup_intent(
            container_id,
            serving_id,
            cleanup_token,
        )
        return process_runtime_cleanup_intent(intent.pk)
    except Exception as error:
        countdown = min(3600, 30 * (2 ** min(self.request.retries, 7)))
        logger.warning(
            "时序 cleanup intent 尚未持久化，将自动重试: "
            "container_id=%s, retry=%s, error_type=%s",
            container_id,
            self.request.retries + 1,
            type(error).__name__,
        )
        raise self.retry(exc=error, countdown=countdown)


@shared_task
def dispatch_pending_timeseries_runtime_cleanup() -> dict:
    """周期补投持久意图，覆盖首次发布失败和消息丢失。"""
    intent_ids = claim_pending_runtime_cleanup_intents()
    scheduled = 0
    for intent_id in intent_ids:
        try:
            cleanup_orphan_timeseries_runtime.delay(intent_id)
            scheduled += 1
        except Exception:
            release_runtime_cleanup_intent(intent_id)
            logger.exception(
                "时序 orphan runtime 补偿任务投递失败，保留意图等待下一轮: intent_id=%s",
                intent_id,
            )
    return {"claimed": len(intent_ids), "scheduled": scheduled}
