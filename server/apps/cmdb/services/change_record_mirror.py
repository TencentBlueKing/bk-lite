import uuid
from datetime import timedelta

from django.db.models import Q
from django.utils.timezone import now

from apps.cmdb.models.operation import (
    ChangeRecordMirrorOutbox,
    CmdbOperationOutboxStatus,
)
from apps.core.logger import cmdb_logger as logger
from apps.rpc.system_mgmt import SystemMgmt


def dispatch_change_record_mirror(event_id):
    from apps.cmdb.tasks.celery_tasks import consume_change_record_mirror_outbox

    try:
        consume_change_record_mirror_outbox.delay(str(event_id))
    except Exception as exc:
        logger.warning(
            "[ChangeRecordMirror] broker 派发失败，等待周期补偿 event_id=%s error_type=%s",
            event_id,
            exc.__class__.__name__,
        )
        return False
    return True


class ChangeRecordMirrorService:
    BATCH_SIZE = 100
    MAX_ATTEMPTS = 5
    LEASE_SECONDS = 300

    @classmethod
    def enqueue_payloads(cls, payloads: list[dict]) -> list[ChangeRecordMirrorOutbox]:
        rows = [
            ChangeRecordMirrorOutbox(payloads=payloads[offset: offset + cls.BATCH_SIZE])
            for offset in range(0, len(payloads), cls.BATCH_SIZE)
        ]
        return ChangeRecordMirrorOutbox.objects.bulk_create(rows)

    @classmethod
    def claim(cls, event_id, *, owner_token: str) -> bool:
        current_time = now()
        event = ChangeRecordMirrorOutbox.objects.filter(event_id=event_id).first()
        if not event:
            return False
        eligible = event.status in {
            CmdbOperationOutboxStatus.PENDING,
            CmdbOperationOutboxStatus.RETRY,
        } and event.next_attempt_at <= current_time
        eligible = eligible or (
            event.status == CmdbOperationOutboxStatus.SENDING
            and event.lease_expires_at is not None
            and event.lease_expires_at <= current_time
        )
        if not eligible:
            return False
        return bool(
            ChangeRecordMirrorOutbox.objects.filter(
                id=event.id,
                status=event.status,
                owner_token=event.owner_token,
                lease_expires_at=event.lease_expires_at,
            ).update(
                status=CmdbOperationOutboxStatus.SENDING,
                owner_token=owner_token,
                lease_expires_at=current_time + timedelta(seconds=cls.LEASE_SECONDS),
                attempt_count=event.attempt_count + 1,
            )
        )

    @classmethod
    def consume(cls, event_id, *, owner_token: str | None = None) -> bool:
        token = owner_token or uuid.uuid4().hex
        if not cls.claim(event_id, owner_token=token):
            return False
        event = ChangeRecordMirrorOutbox.objects.get(event_id=event_id)
        try:
            client = SystemMgmt()
            for payload in event.payloads[: cls.BATCH_SIZE]:
                client.save_operation_log(**payload)
        except Exception as exc:
            status = (
                CmdbOperationOutboxStatus.FAILED
                if event.attempt_count >= cls.MAX_ATTEMPTS
                else CmdbOperationOutboxStatus.RETRY
            )
            delay = min(3600, 2 ** max(0, event.attempt_count - 1) * 30)
            ChangeRecordMirrorOutbox.objects.filter(
                id=event.id, status=CmdbOperationOutboxStatus.SENDING, owner_token=token
            ).update(
                status=status,
                owner_token="",
                lease_expires_at=None,
                next_attempt_at=now() + timedelta(seconds=delay),
                last_error=f"{exc.__class__.__name__}: downstream operation log unavailable",
            )
            return False
        return bool(
            ChangeRecordMirrorOutbox.objects.filter(
                id=event.id, status=CmdbOperationOutboxStatus.SENDING, owner_token=token
            ).update(
                status=CmdbOperationOutboxStatus.SUCCESS,
                owner_token="",
                lease_expires_at=None,
                last_error="",
            )
        )

    @classmethod
    def recover_ready(cls, limit: int = 100) -> int:
        current_time = now()
        event_ids = list(
            ChangeRecordMirrorOutbox.objects.filter(
                Q(status__in=[CmdbOperationOutboxStatus.PENDING, CmdbOperationOutboxStatus.RETRY], next_attempt_at__lte=current_time)
                | Q(status=CmdbOperationOutboxStatus.SENDING, lease_expires_at__lte=current_time)
            )
            .order_by("next_attempt_at", "id")
            .values_list("event_id", flat=True)[: max(1, min(int(limit), 1000))]
        )
        for event_id in event_ids:
            dispatch_change_record_mirror(event_id)
        return len(event_ids)
