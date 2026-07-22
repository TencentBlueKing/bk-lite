from datetime import timedelta

from django.db import transaction
from django.utils import timezone

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
        from apps.alerts.tasks import deliver_alert_outbox

        deliver_alert_outbox.delay(record_id)
    except Exception:
        logger.exception("alert outbox broker enqueue failed: outbox_id=%s", record_id)


def _deliver_payload(kind: str, payload: dict) -> None:
    if kind.startswith("incident_im_group."):
        from apps.alerts.service.incident_im.delivery import (
            OUTBOX_ADD_MEMBERS,
            OUTBOX_CREATE,
            OUTBOX_SEND_SUMMARY,
            deliver_add_members,
            deliver_create_group,
            deliver_summary,
        )

        handlers = {
            OUTBOX_CREATE: deliver_create_group,
            OUTBOX_ADD_MEMBERS: deliver_add_members,
            OUTBOX_SEND_SUMMARY: deliver_summary,
        }
        handler = handlers.get(kind)
        if handler is None:
            raise ValueError(f"unsupported alert outbox kind: {kind}")
        handler(payload["group_id"])
        return
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
            and record.updated_at > now - OUTBOX_LEASE_TIMEOUT
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
        claim_generation = record.attempts
        max_attempts = record.max_attempts

    try:
        _deliver_payload(kind, payload)
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
        if exhausted and kind.startswith("incident_im_group."):
            try:
                from apps.alerts.service.incident_im.delivery import handle_delivery_exhausted

                handle_delivery_exhausted(kind, payload, str(exc))
            except Exception:
                logger.exception(
                    "incident im outbox exhausted hook failed: outbox_id=%s kind=%s",
                    record_id,
                    kind,
                )
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
    return bool(finalized)
