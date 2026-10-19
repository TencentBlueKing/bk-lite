from datetime import datetime

from celery import shared_task
from django.utils import timezone

from apps.core.logger import rum_logger as logger
from apps.rum.services.alert_runtime import RumAlertRuntime
from apps.rum.services.alert_store import DjangoEventStore, DjangoPolicyStore
from apps.rum.services.analytics import get_analytics
from apps.rum.services.delivery import SystemMgmtAlertDispatcher
from apps.rum.services.projection import PublishService
from apps.rum.services.settings import load_rum_settings

OUTBOX_LOCK_KEY = "rum:projection:outbox:lock"
OUTBOX_LOCK_TIMEOUT = 55
RECONCILE_LOCK_KEY = "rum:projection:reconcile:lock"
RECONCILE_LOCK_TIMEOUT = 540


def _runtime(*, dispatcher=None) -> RumAlertRuntime:
    settings = load_rum_settings()
    return RumAlertRuntime(
        policies=DjangoPolicyStore(),
        alerts=DjangoEventStore(),
        analytics=get_analytics(),
        dispatcher=dispatcher,
        tenant_id=settings.tenant_id,
    )


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def dispatch_rum_policy_evaluations():
    """每分钟把启用策略拆成独立任务，一条慢查询不会挡住其它策略。"""

    from apps.rum.models import RumAlertPolicy

    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    policy_ids = list(RumAlertPolicy.objects.filter(enabled=True).values_list("id", flat=True))
    for policy_id in policy_ids:
        evaluate_rum_alert_policy.delay(str(policy_id), evaluated_at.isoformat())
    logger.info(
        "rum alert policies dispatched count=%s",
        len(policy_ids),
    )
    return {"dispatched": len(policy_ids), "evaluated_at": evaluated_at.isoformat()}


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def evaluate_rum_alert_policy(policy_id: str, evaluated_at: str):
    action = _runtime().evaluate_policy(policy_id, datetime.fromisoformat(evaluated_at))
    return {"policy_id": policy_id, "evaluated_at": evaluated_at, "action": action}


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def deliver_rum_alert_outbox():
    result = _runtime(dispatcher=SystemMgmtAlertDispatcher()).deliver_due()
    logger.info(
        "rum alert outbox delivered sent=%s failed=%s",
        result["sent"],
        result["failed"],
    )
    return result


@shared_task(max_retries=0)
def publish_pending_rum_outbox():
    """Republish pending projection rows in creation order."""

    from django.core.cache import cache

    from apps.rum.models import RumProjectionOutbox

    if not cache.add(OUTBOX_LOCK_KEY, "1", OUTBOX_LOCK_TIMEOUT):
        return {"skipped": True, "reason": "already_running"}
    try:
        pending_ids = list(
            RumProjectionOutbox.objects.filter(status="pending").order_by("created_at").values_list("id", flat=True)[:200]
        )
        published = 0
        service = PublishService()
        for outbox_id in pending_ids:
            ok, _data = service.publish(outbox_id)
            if ok:
                published += 1
        logger.info(
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

    from django.core.cache import cache

    if not cache.add(RECONCILE_LOCK_KEY, "1", RECONCILE_LOCK_TIMEOUT):
        return {"skipped": True, "reason": "already_running"}
    try:
        PublishService().reconcile()
        logger.info("rum projection reconcile requested")
        return {"ok": True}
    except Exception as exc:
        logger.warning(
            "rum projection reconcile failed failed_stage=%s error_type=%s",
            "reconcile",
            type(exc).__name__,
        )
        return {"ok": False, "error_type": type(exc).__name__}
    finally:
        cache.delete(RECONCILE_LOCK_KEY)
