from dataclasses import asdict
from datetime import datetime

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from apps.apm.adapters import SystemMgmtNotificationDispatcher, VictoriaTracesTelemetryStore
from apps.apm.models import ApmAlertOutbox, ApmEventSnapshot, ApmPolicy
from apps.apm.services import ApmEventSnapshotStore, DjangoApmPolicyService, TelemetryCatalogReconciler
from apps.apm.services.health import (
    CATALOG_RECONCILE_HEALTH_KEY,
    NOTIFICATION_DELIVERY_HEALTH_KEY,
    POLICY_EVALUATION_HEALTH_KEY,
    RUNTIME_DEPENDENCIES_HEALTH_KEY,
    RuntimeDependencyHealthProbe,
)
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
        result = TelemetryCatalogReconciler(VictoriaTracesTelemetryStore()).reconcile(observed_at=observed_at)
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


@shared_task
def probe_apm_runtime_dependencies():
    """运行期有界探测；不可用只进入健康状态，不触发启动或任务无限重试。"""
    result = RuntimeDependencyHealthProbe().probe()
    cache.set(RUNTIME_DEPENDENCIES_HEALTH_KEY, result, timeout=None)
    return result


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def dispatch_apm_policy_evaluations():
    """仅分发启用策略；每条策略独立有界重试，互不阻塞。"""

    evaluated_at_value = timezone.now().replace(second=0, microsecond=0)
    evaluated_at = evaluated_at_value.isoformat()
    epoch_minute = int(evaluated_at_value.timestamp() // 60)
    candidates = ApmPolicy.objects.filter(is_enabled=True).values_list("id", "evaluation_interval")
    policy_ids = [policy_id for policy_id, interval in candidates if epoch_minute % max(interval, 1) == 0]
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
    service = DjangoApmPolicyService(VictoriaTracesTelemetryStore(), SystemMgmtNotificationDispatcher())
    try:
        service.evaluate(policy_id, evaluated_at=datetime.fromisoformat(evaluated_at))
    except ApmPolicy.DoesNotExist:
        return {"policy_id": policy_id, "evaluated_at": evaluated_at, "skipped": "deleted"}
    except Exception:
        cache.set(
            POLICY_EVALUATION_HEALTH_KEY,
            {"status": "degraded", "last_failed_at": timezone.now().isoformat()},
            timeout=None,
        )
        raise
    cache.set(
        POLICY_EVALUATION_HEALTH_KEY,
        {"status": "ok", "last_succeeded_at": timezone.now().isoformat()},
        timeout=None,
    )
    return {"policy_id": policy_id, "evaluated_at": evaluated_at}


@shared_task
def deliver_apm_alert_outbox():
    result = DjangoApmPolicyService(
        VictoriaTracesTelemetryStore(),
        SystemMgmtNotificationDispatcher(),
    ).retry_pending_events(limit=100)
    payload = asdict(result)
    terminal_failures = ApmAlertOutbox.objects.filter(
        delivery_status=ApmAlertOutbox.DeliveryStatus.FAILED,
    ).count()
    if result.failed or terminal_failures:
        cache.set(
            NOTIFICATION_DELIVERY_HEALTH_KEY,
            {
                "status": "degraded",
                "last_failed_at": timezone.now().isoformat(),
                "failed_deliveries": terminal_failures,
            },
            timeout=None,
        )
        logger.warning("APM alert outbox delivery deferred", extra=payload)
    else:
        cache.set(
            NOTIFICATION_DELIVERY_HEALTH_KEY,
            {"status": "ok", "last_succeeded_at": timezone.now().isoformat(), "failed_deliveries": 0},
            timeout=None,
        )
    return payload


@shared_task
def persist_apm_event_snapshot_payloads():
    ids = list(
        ApmEventSnapshot.objects.filter(
            payload_status__in=(
                ApmEventSnapshot.PayloadStatus.PENDING,
                ApmEventSnapshot.PayloadStatus.UNAVAILABLE,
            ),
            payload_attempts__lt=8,
            retention_expires_at__gt=timezone.now(),
        )
        .exclude(pending_payload={})
        .order_by("id")
        .values_list("id", flat=True)[:100]
    )
    available = unavailable = 0
    for snapshot_id in ids:
        snapshot = ApmEventSnapshotStore.persist(snapshot_id)
        if snapshot.payload_status == ApmEventSnapshot.PayloadStatus.AVAILABLE:
            available += 1
        else:
            unavailable += 1
    return {"processed": len(ids), "available": available, "unavailable": unavailable}


@shared_task
def expire_apm_event_snapshot_payloads():
    return {"expired": ApmEventSnapshotStore.expire_due(limit=100)}
