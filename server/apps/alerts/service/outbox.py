from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.alerts.extensions.outbox import outbox_handlers
from apps.alerts.models.outbox import AlertOutbox
from apps.core.logger import alert_logger as logger


OUTBOX_LEASE_TIMEOUT = timedelta(minutes=5)


def enqueue_outbox(kind: str, payload: dict, idempotency_key: str):
    record, created = AlertOutbox.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={"kind": kind, "payload": payload},
    )
    if created:
        transaction.on_commit(lambda record_id=record.pk: _schedule_delivery(record_id))
    return record, created


def _schedule_delivery(record_id: int) -> None:
    try:
        kind = AlertOutbox.objects.filter(pk=record_id).values_list("kind", flat=True).first()
        if outbox_handlers.schedule(kind, record_id):
            return
        from apps.alerts.tasks import deliver_alert_outbox

        deliver_alert_outbox.delay(record_id)
    except Exception:
        logger.exception("alert outbox broker enqueue failed: outbox_id=%s", record_id)


def _deliver_payload(kind: str, payload: dict, *, delivery_claim=None) -> None:
    if outbox_handlers.deliver(kind, payload, delivery_claim=delivery_claim):
        return
    if kind == "action":
        from apps.alerts.tasks.action_tasks import process_alert_actions

        process_alert_actions(payload["alert_id"], payload["event_name"])
        return
    if kind == "auto_assignment":
        from apps.alerts.tasks.tasks import async_auto_assignment_for_alerts

        async_auto_assignment_for_alerts(payload.get("alert_ids") or [])
        return
    raise ValueError(f"unsupported alert outbox kind: {kind}")


def _notify_delivery_exhausted(record_id, kind, payload, error):
    outbox_handlers.notify_exhausted(
        kind,
        payload,
        error,
        record_id=record_id,
    )


def deliver_outbox_record(record_id: int) -> bool:
    now = timezone.now()
    lease_exhausted = False
    with transaction.atomic():
        record = AlertOutbox.objects.select_for_update().filter(pk=record_id).first()
        if not record or record.status == AlertOutbox.Status.DELIVERED:
            return False
        if (
            record.status == AlertOutbox.Status.DELIVERING
            and record.updated_at > now - OUTBOX_LEASE_TIMEOUT
        ):
            return False
        if record.status == AlertOutbox.Status.FAILED and record.attempts >= record.max_attempts:
            return False
        kind = record.kind
        payload = record.payload
        if (
            record.status == AlertOutbox.Status.DELIVERING
            and record.attempts >= record.max_attempts
        ):
            error = "delivery lease expired after retries exhausted"
            record.status = AlertOutbox.Status.FAILED
            record.next_retry_at = None
            record.last_error = error
            record.save(
                update_fields=["status", "next_retry_at", "last_error", "updated_at"]
            )
            lease_exhausted = True
        else:
            record.status = AlertOutbox.Status.DELIVERING
            record.attempts += 1
            record.last_error = ""
            record.save(update_fields=["status", "attempts", "last_error", "updated_at"])
            claim_generation = record.attempts
            max_attempts = record.max_attempts

    if lease_exhausted:
        _notify_delivery_exhausted(record_id, kind, payload, error)
        return False

    try:
        notification_delivery_ids = []
        if kind == "notification":
            handled = outbox_handlers.deliver(
                kind,
                payload,
                delivery_claim={
                    "record_id": record_id,
                    "generation": claim_generation,
                },
            )
            if not handled:
                from apps.alerts.service.notification_delivery import (
                    ensure_notification_deliveries,
                )

                notification_delivery_ids = ensure_notification_deliveries(record_id)
        else:
            _deliver_payload(
                kind,
                payload,
                delivery_claim={
                    "record_id": record_id,
                    "generation": claim_generation,
                },
            )
    except Exception as exc:
        next_status = (
            AlertOutbox.Status.FAILED
            if claim_generation >= max_attempts
            else AlertOutbox.Status.PENDING
        )
        delay_seconds = min(3600, 2 ** min(claim_generation, 10) * 15)
        finalized = AlertOutbox.objects.filter(
            pk=record_id,
            status=AlertOutbox.Status.DELIVERING,
            attempts=claim_generation,
        ).update(
            status=next_status,
            next_retry_at=timezone.now() + timedelta(seconds=delay_seconds),
            last_error=str(exc)[:2000],
            updated_at=timezone.now(),
        )
        if not finalized:
            return False
        exhausted = next_status == AlertOutbox.Status.FAILED
        if exhausted:
            _notify_delivery_exhausted(record_id, kind, payload, str(exc))
        raise

    delivered_at = timezone.now()
    finalized = AlertOutbox.objects.filter(
        pk=record_id,
        status=AlertOutbox.Status.DELIVERING,
        attempts=claim_generation,
    ).update(
        status=AlertOutbox.Status.DELIVERED,
        delivered_at=delivered_at,
        next_retry_at=None,
        updated_at=delivered_at,
    )
    if finalized and kind == "notification":
        from apps.alerts.service.notification_delivery import (
            schedule_notification_deliveries,
        )

        schedule_notification_deliveries(notification_delivery_ids)
    return bool(finalized)
