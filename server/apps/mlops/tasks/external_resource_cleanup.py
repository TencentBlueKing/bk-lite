from celery import shared_task
from django.conf import settings
from django.db import connections

from apps.core.logger import mlops_logger as logger
from apps.mlops.services.external_resource_cleanup import (
    claim_cleanup_intent,
    claim_due_cleanup_intents,
    process_cleanup_intent,
    release_cleanup_claim,
)


@shared_task(
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=60,
    time_limit=90,
)
def cleanup_external_resource(
    self,
    intent_id: int,
    claim_token: str,
    using: str = "default",
) -> dict:
    try:
        return process_cleanup_intent(intent_id, claim_token, using=using)
    except Exception as error:
        logger.warning(
            "外部资源持久清理失败，处理状态已写入意图: intent_id=%s, error_type=%s",
            intent_id,
            type(error).__name__,
        )
        raise


def _publish_cleanup_claim(
    intent_id: int,
    claim_token: str,
    *,
    using: str = "default",
) -> bool:
    try:
        cleanup_external_resource.apply_async(
            kwargs={
                "intent_id": intent_id,
                "claim_token": claim_token,
                "using": using,
            },
            delivery_mode=2,
            retry=False,
        )
        return True
    except Exception as error:
        release_cleanup_claim(intent_id, claim_token, using=using)
        logger.error(
            "外部资源清理任务投递失败，已释放 claim 等待周期补投: intent_id=%s, error_type=%s",
            intent_id,
            type(error).__name__,
        )
        return False


def enqueue_external_resource_cleanup_intent(
    intent_id: int,
    *,
    using: str = "default",
) -> bool:
    claim_token = claim_cleanup_intent(intent_id, using=using)
    if claim_token is None:
        return False
    if not settings.IS_USE_CELERY:
        try:
            result = process_cleanup_intent(intent_id, claim_token, using=using)
        except Exception as error:
            logger.warning(
                "Celery 未启用，外部资源同步清理失败且意图已保留: intent_id=%s, error_type=%s",
                intent_id,
                type(error).__name__,
            )
            return False
        return result["result"]
    return _publish_cleanup_claim(intent_id, claim_token, using=using)


@shared_task
def dispatch_pending_external_resource_cleanup() -> dict:
    claimed = 0
    scheduled = 0
    database_aliases = list(connections)
    remaining = 100
    for index, using in enumerate(database_aliases):
        aliases_left = len(database_aliases) - index
        alias_limit = max(1, remaining // aliases_left)
        claims = claim_due_cleanup_intents(limit=alias_limit, using=using)
        claimed += len(claims)
        remaining -= len(claims)
        scheduled += sum(_publish_cleanup_claim(intent_id, claim_token, using=using) for intent_id, claim_token in claims)
        if remaining == 0:
            break
    return {"claimed": claimed, "scheduled": scheduled}
