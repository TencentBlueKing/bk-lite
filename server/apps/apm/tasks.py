from dataclasses import asdict
from datetime import datetime

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from apps.apm.adapters import SystemMgmtNatsAlertPublisher, VictoriaMetricsMetricStore
from apps.apm.models import ApmPolicy
from apps.apm.services import DjangoApmPolicyService, TelemetryCatalogReconciler
from apps.apm.services.health import CATALOG_RECONCILE_HEALTH_KEY
from apps.core.logger import celery_logger as logger


CATALOG_RECONCILE_LOCK_KEY = "apm:catalog:reconcile:lock"
CATALOG_RECONCILE_LOCK_TIMEOUT = 300


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def reconcile_telemetry_catalog():
    """运行期对账入口；外部存储失败只触发有界任务重试，不参与 Server 启动。"""

    if not cache.add(CATALOG_RECONCILE_LOCK_KEY, "1", CATALOG_RECONCILE_LOCK_TIMEOUT):
        return {"skipped": True, "reason": "already_running"}
    observed_at = timezone.now()
    try:
        result = TelemetryCatalogReconciler(VictoriaMetricsMetricStore()).reconcile(observed_at=observed_at)
        payload = asdict(result)
        cache.set(
            CATALOG_RECONCILE_HEALTH_KEY,
            {"status": "ok", "last_succeeded_at": observed_at.isoformat()},
            timeout=None,
        )
        logger.info("APM telemetry catalog reconciled", extra=payload)
        return payload
    except Exception:
        cache.set(
            CATALOG_RECONCILE_HEALTH_KEY,
            {"status": "degraded", "last_failed_at": observed_at.isoformat()},
            timeout=None,
        )
        logger.exception("APM telemetry catalog reconcile failed")
        raise
    finally:
        cache.delete(CATALOG_RECONCILE_LOCK_KEY)


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def dispatch_apm_policy_evaluations():
    """仅分发启用策略；每条策略独立有界重试，互不阻塞。"""

    evaluated_at = timezone.now().replace(second=0, microsecond=0).isoformat()
    policy_ids = list(ApmPolicy.objects.filter(is_enabled=True).values_list("id", flat=True))
    for policy_id in policy_ids:
        evaluate_apm_policy.delay(str(policy_id), evaluated_at)
    return {"dispatched": len(policy_ids), "evaluated_at": evaluated_at}


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def evaluate_apm_policy(policy_id: str, evaluated_at: str):
    service = DjangoApmPolicyService(VictoriaMetricsMetricStore(), SystemMgmtNatsAlertPublisher())
    try:
        service.evaluate(policy_id, evaluated_at=datetime.fromisoformat(evaluated_at))
    except ApmPolicy.DoesNotExist:
        return {"policy_id": policy_id, "evaluated_at": evaluated_at, "skipped": "deleted"}
    return {"policy_id": policy_id, "evaluated_at": evaluated_at}


@shared_task
def deliver_apm_alert_outbox():
    result = DjangoApmPolicyService(
        VictoriaMetricsMetricStore(),
        SystemMgmtNatsAlertPublisher(),
    ).retry_pending_events(limit=100)
    payload = asdict(result)
    if result.failed:
        logger.warning("APM alert outbox delivery deferred", extra=payload)
    return payload
