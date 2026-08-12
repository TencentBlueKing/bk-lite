"""Monitor 生命周期事件到告警中心的 transactional outbox。"""

import hashlib
import json
import os
from datetime import timedelta

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import MonitorAlert, MonitorAlertCenterDelivery, MonitorPolicy
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils


def _env_flag(name, *, default=False):
    return os.getenv(name, "true" if default else "false").lower() in {"1", "true", "yes"}


# The receiver must understand per-event acknowledgements before producers start
# writing outbox records.  Keep the producer disabled through mixed-version
# rollouts; operators enable it only after the receiver-first deployment.
ALERT_CENTER_OUTBOX_ENABLED = _env_flag("MONITOR_ALERT_CENTER_OUTBOX_ENABLED")
OUTBOX_BATCH_SIZE = 200
OUTBOX_LEASE_TIMEOUT = timedelta(minutes=5)


def _delivery_fingerprint(alert_id, action, payload):
    source = json.dumps(
        {"alert_id": str(alert_id), "action": action, "payload": payload},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def enqueue_alert_center_deliveries(alerts, action, *, notifier, operator="", reason=""):
    """在调用方事务内保存按 alert/action 代次排序的不可变载荷。"""
    if not ALERT_CENTER_OUTBOX_ENABLED or not alerts:
        return []

    alert_channels = {
        alert.id: [int(value) for value in notifier._resolve_notice_type_ids(alert) if str(value).isdigit()]
        for alert in alerts
    }
    target_alerts = [alert for alert in alerts if alert_channels[alert.id]]
    if not target_alerts:
        return []

    alert_ids = sorted({alert.id for alert in target_alerts})
    created_ids = []
    with transaction.atomic():
        locked_by_id = {
            alert.id: alert
            for alert in MonitorAlert.objects.select_for_update().filter(id__in=alert_ids).order_by("id")
        }
        instance_org_map = notifier._build_instance_org_map(target_alerts)
        for original in target_alerts:
            alert = locked_by_id.get(original.id, original)
            payload = notifier._build_alert_center_payload(alert, action, operator, reason, instance_org_map)
            for channel_id in alert_channels[alert.id]:
                delivery_id = _delivery_fingerprint(alert.id, action, {"channel_id": channel_id, **payload})
                existing = MonitorAlertCenterDelivery.objects.filter(delivery_id=delivery_id).first()
                if existing:
                    continue
                generation = (
                    MonitorAlertCenterDelivery.objects.filter(alert_id=alert.id).aggregate(value=Max("generation"))["value"] or 0
                ) + 1
                delivery = MonitorAlertCenterDelivery.objects.create(
                    alert_id=alert.id,
                    action=action,
                    generation=generation,
                    delivery_id=delivery_id,
                    channel_id=channel_id,
                    payload=payload,
                )
                created_ids.append(delivery.id)

        if created_ids:
            MonitorAlert.objects.filter(id__in=alert_ids).update(alert_center_notified=False)
            transaction.on_commit(lambda ids=tuple(created_ids): _schedule_deliveries(ids))
        MonitorAlert.objects.filter(id__in=alert_ids).update(alert_center_delivery_backfilled=True)
    return created_ids


def _schedule_deliveries(delivery_ids):
    from apps.monitor.tasks.monitor_policy import deliver_alert_center_lifecycle_delivery

    for delivery_id in delivery_ids:
        try:
            deliver_alert_center_lifecycle_delivery.delay(delivery_id)
        except Exception:
            logger.exception("告警中心 outbox 调度失败，等待周期补偿: delivery_id=%s", delivery_id)


def _ack_result(send_result, delivery_id):
    if not isinstance(send_result, dict):
        return False, True, "invalid response"
    for item in (send_result.get("data") or {}).get("event_results") or []:
        if isinstance(item, dict) and item.get("delivery_id") == delivery_id:
            status = item.get("status")
            if status in {"accepted", "duplicate"}:
                return True, False, ""
            return False, bool(item.get("retryable", status == "errored")), status or "invalid acknowledgement"
    if send_result.get("result") is True:
        return True, False, ""
    return (
        False,
        bool(send_result.get("retryable", True)),
        send_result.get("code") or send_result.get("message") or "delivery failed",
    )


def deliver_alert_center_delivery(record_id):
    """按代次 claim/finalize；旧执行不能覆盖新 claim，后继动作不得越过前驱。"""
    now = timezone.now()
    with transaction.atomic():
        record = MonitorAlertCenterDelivery.objects.select_for_update().filter(id=record_id).first()
        if not record or record.status in {record.Status.DELIVERED, record.Status.FAILED}:
            return False
        earlier_unfinished = MonitorAlertCenterDelivery.objects.filter(
            alert_id=record.alert_id,
            generation__lt=record.generation,
        ).exclude(status=record.Status.DELIVERED).exists()
        if earlier_unfinished:
            return False
        if record.status == record.Status.DELIVERING and record.updated_at > now - OUTBOX_LEASE_TIMEOUT:
            return False
        if record.attempts >= record.max_attempts:
            record.status = record.Status.FAILED
            record.next_retry_at = None
            record.last_error = record.last_error or "retries exhausted"
            record.save(update_fields=["status", "next_retry_at", "last_error", "updated_at"])
            return False
        record.status = record.Status.DELIVERING
        record.attempts += 1
        record.last_error = ""
        record.save(update_fields=["status", "attempts", "last_error", "updated_at"])
        claim_generation = record.attempts
        delivery_id = record.delivery_id
        payload = dict(record.payload)

    payload["delivery_id"] = delivery_id
    try:
        send_result = SystemMgmtUtils.dispatch_notification(
            delivery_key=delivery_id,
            channel_id=record.channel_id,
            organization_ids=payload.get("organizations") or [],
            recipients=[],
            title="",
            body=payload.get("description") or payload.get("title") or "alert event",
            event_payload=payload,
            required_delivery_mode="alert_event_copy",
            producer="lite-monitor",
            ack_mode="per_event_v1",
        )
        success, retryable, error = _ack_result(send_result, delivery_id)
    except Exception as exc:
        success, retryable, error = False, True, str(exc)

    finished_at = timezone.now()
    if success:
        with transaction.atomic():
            # Enqueue takes the same alert-row lock. This makes finalization and
            # the "all generations delivered" decision one ordered state change.
            MonitorAlert.objects.select_for_update().get(id=record.alert_id)
            finalized = MonitorAlertCenterDelivery.objects.filter(
                id=record_id,
                status=MonitorAlertCenterDelivery.Status.DELIVERING,
                attempts=claim_generation,
            ).update(
                status=MonitorAlertCenterDelivery.Status.DELIVERED,
                delivered_at=finished_at,
                next_retry_at=None,
                last_error="",
                updated_at=finished_at,
            )
            if finalized and not MonitorAlertCenterDelivery.objects.filter(alert_id=record.alert_id).exclude(
                status=MonitorAlertCenterDelivery.Status.DELIVERED
            ).exists():
                MonitorAlert.objects.filter(id=record.alert_id).update(alert_center_notified=True, alert_center_retry_count=0)
        return bool(finalized)

    terminal = not retryable or claim_generation >= record.max_attempts
    next_status = MonitorAlertCenterDelivery.Status.FAILED if terminal else MonitorAlertCenterDelivery.Status.PENDING
    next_retry_at = None if terminal else finished_at + timedelta(seconds=min(3600, 15 * (2 ** min(claim_generation, 8))))
    MonitorAlertCenterDelivery.objects.filter(
        id=record_id,
        status=MonitorAlertCenterDelivery.Status.DELIVERING,
        attempts=claim_generation,
    ).update(
        status=next_status,
        next_retry_at=next_retry_at,
        last_error=error[:2000],
        updated_at=finished_at,
    )
    return False


def backfill_legacy_alerts():
    """有界对账存量告警；成功旧投递会由接收端幂等去重。"""
    alerts = list(
        MonitorAlert.objects.filter(
            alert_center_delivery_backfilled=False
        )
        .filter(Q(alert_center_notified=False) | Q(status="new"))
        .order_by("id")[:OUTBOX_BATCH_SIZE]
    )
    if not alerts:
        return 0
    policies = MonitorPolicy.objects.in_bulk({alert.policy_id for alert in alerts if alert.policy_id})
    from apps.monitor.services.alert_lifecycle_notify import AlertLifecycleNotifier

    for alert in alerts:
        action = "created" if alert.status == "new" else alert.status
        notifier = AlertLifecycleNotifier(policies.get(alert.policy_id), policies_by_id=policies)
        enqueue_alert_center_deliveries([alert], action, notifier=notifier)
    return len(alerts)


def due_delivery_ids():
    now = timezone.now()
    stale_before = now - OUTBOX_LEASE_TIMEOUT
    return list(
        MonitorAlertCenterDelivery.objects.filter(
            Q(status=MonitorAlertCenterDelivery.Status.PENDING)
            | Q(status=MonitorAlertCenterDelivery.Status.DELIVERING, updated_at__lte=stale_before),
            Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now),
        )
        .order_by("alert_id", "generation")
        .values_list("id", flat=True)[:OUTBOX_BATCH_SIZE]
    )
