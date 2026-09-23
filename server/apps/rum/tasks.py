from celery import shared_task
from django.core.cache import cache

from apps.core.logger import celery_logger as logger
from apps.rum.services.evaluator import AlertEvaluator
from apps.rum.services.monitors import DjangoEventStore, DjangoPolicyStore
from apps.rum.services.notify import SystemMgmtNotifier

EVAL_LOCK_KEY = "rum:alert:evaluate:lock"
EVAL_LOCK_TIMEOUT = 25


@shared_task(max_retries=0)
def evaluate_rum_alert_policies():
    """Periodic RUM monitor evaluation; skips when analytics is unavailable."""

    if not cache.add(EVAL_LOCK_KEY, "1", EVAL_LOCK_TIMEOUT):
        return {"skipped": True, "reason": "already_running"}
    try:
        result = AlertEvaluator(
            policies=DjangoPolicyStore(),
            events=DjangoEventStore(),
            notifier=SystemMgmtNotifier(),
        ).evaluate_all()
        logger.info("rum alert policies evaluated", extra=result)
        return result
    except Exception as exc:
        logger.exception(
            "rum alert policy evaluation failed",
            extra={"failed_stage": "evaluate_all", "error_type": type(exc).__name__},
        )
        raise
    finally:
        cache.delete(EVAL_LOCK_KEY)
