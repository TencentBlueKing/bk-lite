from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.alerts.models.outbox import AlertOutbox
from apps.core.logger import alert_logger as logger


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
        from apps.alerts.tasks import deliver_alert_outbox

        deliver_alert_outbox.delay(record_id)
    except Exception:
        logger.exception("alert outbox broker enqueue failed: outbox_id=%s", record_id)


def _deliver_payload(kind: str, payload: dict) -> None:
    if kind == "notification":
        from apps.alerts.tasks import sync_notify

        sync_notify(payload.get("params") or [])
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


def deliver_outbox_record(record_id: int) -> bool:
    now = timezone.now()
    with transaction.atomic():
        record = AlertOutbox.objects.select_for_update().filter(pk=record_id).first()
        if not record or record.status == AlertOutbox.Status.DELIVERED:
            return False
        if (
            record.status == AlertOutbox.Status.DELIVERING
            and record.updated_at > now - timedelta(minutes=5)
        ):
            return False
        if record.status == AlertOutbox.Status.FAILED and record.attempts >= record.max_attempts:
            return False
        record.status = AlertOutbox.Status.DELIVERING
        record.attempts += 1
        record.last_error = ""
        record.save(update_fields=["status", "attempts", "last_error", "updated_at"])
        kind = record.kind
        payload = record.payload

    try:
        _deliver_payload(kind, payload)
    except Exception as exc:
        with transaction.atomic():
            record = AlertOutbox.objects.select_for_update().get(pk=record_id)
            record.status = (
                AlertOutbox.Status.FAILED
                if record.attempts >= record.max_attempts
                else AlertOutbox.Status.PENDING
            )
            delay_seconds = min(3600, 2 ** min(record.attempts, 10) * 15)
            record.next_retry_at = timezone.now() + timedelta(seconds=delay_seconds)
            record.last_error = str(exc)[:2000]
            record.save(
                update_fields=["status", "next_retry_at", "last_error", "updated_at"]
            )
        raise

    with transaction.atomic():
        record = AlertOutbox.objects.select_for_update().get(pk=record_id)
        record.status = AlertOutbox.Status.DELIVERED
        record.delivered_at = timezone.now()
        record.next_retry_at = None
        record.save(update_fields=["status", "delivered_at", "next_retry_at", "updated_at"])
    return True
