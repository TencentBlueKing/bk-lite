from celery import shared_task
from django.core.cache import cache

from apps.core.logger import celery_logger as logger
from apps.core.logger import rum_logger
from apps.rum.services.evaluator import AlertEvaluator
from apps.rum.services.monitors import DjangoEventStore, DjangoPolicyStore
from apps.rum.services.notify import SystemMgmtNotifier
from apps.rum.services.projection import PublishService

EVAL_LOCK_KEY = "rum:alert:evaluate:lock"
EVAL_LOCK_TIMEOUT = 25
OUTBOX_LOCK_KEY = "rum:projection:outbox:lock"
OUTBOX_LOCK_TIMEOUT = 55
RECONCILE_LOCK_KEY = "rum:projection:reconcile:lock"
RECONCILE_LOCK_TIMEOUT = 540


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


@shared_task(max_retries=0)
def publish_pending_rum_outbox():
    """Republish pending projection rows in creation order."""

    if not cache.add(OUTBOX_LOCK_KEY, "1", OUTBOX_LOCK_TIMEOUT):
        return {"skipped": True, "reason": "already_running"}
    try:
        from apps.rum.models import RumProjectionOutbox

        pending_ids = list(
            RumProjectionOutbox.objects.filter(status="pending").order_by("created_at").values_list("id", flat=True)[:200]
        )
        published = 0
        service = PublishService()
        for outbox_id in pending_ids:
            ok, _data = service.publish(outbox_id)
            if ok:
                published += 1
        rum_logger.info(
            "rum projection outbox republished pending=%s published=%s",
            len(pending_ids),
            published,
        )
        return {"pending": len(pending_ids), "published": published}
    finally:
        cache.delete(OUTBOX_LOCK_KEY)


@shared_task(max_retries=0)
def reconcile_rum_projection():
    """Ask the controller to drop unknown apps and repair revisions that differ."""

    if not cache.add(RECONCILE_LOCK_KEY, "1", RECONCILE_LOCK_TIMEOUT):
        return {"skipped": True, "reason": "already_running"}
    try:
        PublishService().reconcile()
        rum_logger.info("rum projection reconcile requested")
        return {"ok": True}
    except Exception as exc:
        rum_logger.warning(
            "rum projection reconcile failed failed_stage=%s error_type=%s",
            "reconcile",
            type(exc).__name__,
        )
        return {"ok": False, "error_type": type(exc).__name__}
    finally:
        cache.delete(RECONCILE_LOCK_KEY)
