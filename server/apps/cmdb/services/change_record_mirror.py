import json
import uuid
from datetime import timedelta

from django.db.models import Q
from django.utils.timezone import now

from apps.cmdb.models.operation import ChangeRecordMirrorOutbox, CmdbOperationOutboxStatus
from apps.cmdb.services.unique_write_lock import UniqueWriteLockService
from apps.cmdb.utils.change_record import is_verify_only_message
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.database import bulk_create_with_primary_keys
from apps.rpc.system_mgmt import SystemMgmt

MIRROR_PUSH_LOCK = "cmdb-change-record-mirror"
MIRROR_PACKET_ITEMS = 200
MIRROR_PACKET_BYTES = 768 * 1024
MIRROR_SINGLE_PAYLOAD_MAX_BYTES = 7 * 1024 * 1024


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
        rows = []
        for offset in range(0, len(payloads), cls.BATCH_SIZE):
            chunk = [dict(item) for item in payloads[offset : offset + cls.BATCH_SIZE]]
            event_id = uuid.uuid4()
            for index, item in enumerate(chunk):
                item["idempotency_key"] = f"{event_id}:{index}"
            rows.append(ChangeRecordMirrorOutbox(event_id=event_id, payloads=chunk))
        return bulk_create_with_primary_keys(ChangeRecordMirrorOutbox.objects, rows)

    @classmethod
    def claim(cls, event_id, *, owner_token: str) -> bool:
        current_time = now()
        event = ChangeRecordMirrorOutbox.objects.filter(event_id=event_id).first()
        if not event:
            return False
        eligible = (
            event.status
            in {
                CmdbOperationOutboxStatus.PENDING,
                CmdbOperationOutboxStatus.RETRY,
            }
            and event.next_attempt_at <= current_time
        )
        eligible = eligible or (
            event.status == CmdbOperationOutboxStatus.SENDING and event.lease_expires_at is not None and event.lease_expires_at <= current_time
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
        payloads = _drop_verify_payloads(list(event.payloads))
        oversized, payloads = _split_oversized_payloads(payloads)
        if not payloads:
            status = CmdbOperationOutboxStatus.FAILED if oversized else CmdbOperationOutboxStatus.SUCCESS
            ChangeRecordMirrorOutbox.objects.filter(id=event.id, status=CmdbOperationOutboxStatus.SENDING, owner_token=token).update(
                status=status,
                owner_token="",
                lease_expires_at=None,
                last_error="payload_too_large" if oversized else "",
                payloads=[],
            )
            return not oversized
        payloads = _ensure_idempotency_keys(event.event_id, payloads)
        ChangeRecordMirrorOutbox.objects.filter(id=event.id, status=CmdbOperationOutboxStatus.SENDING, owner_token=token).update(payloads=payloads)
        try:
            client = SystemMgmt()
            remaining = payloads
            while remaining:
                packet, remaining = _take_packet(remaining)
                receipt = client.save_operation_logs(logs=packet)
                if isinstance(receipt, dict) and receipt.get("result") is True:
                    continue
                return _mark_retry(event.id, token, event.attempt_count, remaining, packet)
        except Exception as exc:
            _mark_retry(
                event.id,
                token,
                event.attempt_count,
                payloads,
                error=f"{exc.__class__.__name__}: downstream operation log unavailable",
            )
            return False
        return bool(
            ChangeRecordMirrorOutbox.objects.filter(id=event.id, status=CmdbOperationOutboxStatus.SENDING, owner_token=token).update(
                status=CmdbOperationOutboxStatus.SUCCESS,
                owner_token="",
                lease_expires_at=None,
                last_error="",
                payloads=[],
            )
        )

    @classmethod
    def push_ready(cls) -> dict:
        """同一时刻只允许一个推送。上一轮还在推时，本轮直接结束。"""
        owner_token = uuid.uuid4().hex
        if not UniqueWriteLockService.acquire(MIRROR_PUSH_LOCK, owner_token=owner_token, lease_seconds=UniqueWriteLockService.DEFAULT_LEASE_SECONDS):
            logger.info("[ChangeRecordMirror] 上一轮推送仍在进行，本轮结束")
            return {"status": "in_progress", "pushed": 0}
        pushed = 0
        try:
            while True:
                if not UniqueWriteLockService.renew(
                    MIRROR_PUSH_LOCK,
                    owner_token=owner_token,
                    lease_seconds=UniqueWriteLockService.DEFAULT_LEASE_SECONDS,
                ):
                    logger.info("[ChangeRecordMirror] 推送锁已失去，停止本轮 pushed=%s", pushed)
                    return {"status": "lost_lock", "pushed": pushed}
                event_ids = _ready_event_ids()
                if not event_ids:
                    break
                changed = 0
                for event_id in event_ids:
                    before = ChangeRecordMirrorOutbox.objects.filter(event_id=event_id).values_list("status", flat=True).first()
                    cls.consume(event_id)
                    after = ChangeRecordMirrorOutbox.objects.filter(event_id=event_id).values_list("status", flat=True).first()
                    if after != before:
                        changed += 1
                        pushed += 1
                if changed == 0:
                    break
        finally:
            UniqueWriteLockService.release(MIRROR_PUSH_LOCK, owner_token=owner_token)
        logger.info("[ChangeRecordMirror] 批量推送完成 pushed=%s", pushed)
        return {"status": "drained", "pushed": pushed}


def _ready_event_ids(limit: int = 20) -> list:
    current_time = now()
    return list(
        ChangeRecordMirrorOutbox.objects.filter(
            Q(status__in=[CmdbOperationOutboxStatus.PENDING, CmdbOperationOutboxStatus.RETRY], next_attempt_at__lte=current_time)
            | Q(status=CmdbOperationOutboxStatus.SENDING, lease_expires_at__lte=current_time)
        )
        .order_by("next_attempt_at", "id")
        .values_list("event_id", flat=True)[:limit]
    )


def _drop_verify_payloads(payloads: list[dict]) -> list[dict]:
    return [payload for payload in payloads if not is_verify_only_message(payload.get("summary", ""))]


def _payload_size(payload: dict) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))


def _split_oversized_payloads(payloads: list[dict]) -> tuple[bool, list[dict]]:
    kept = []
    oversized = False
    for payload in payloads:
        if _payload_size(payload) > MIRROR_SINGLE_PAYLOAD_MAX_BYTES:
            oversized = True
            continue
        kept.append(payload)
    return oversized, kept


def _ensure_idempotency_keys(event_id, payloads: list[dict]) -> list[dict]:
    for index, payload in enumerate(payloads):
        if not payload.get("idempotency_key"):
            payload["idempotency_key"] = f"{event_id}:{index}"
    return payloads


def _take_packet(payloads: list[dict]) -> tuple[list[dict], list[dict]]:
    packet = []
    size = 2
    for index, payload in enumerate(payloads):
        encoded = _payload_size(payload)
        extra = encoded + (1 if packet else 0)
        if packet and (len(packet) >= MIRROR_PACKET_ITEMS or size + extra > MIRROR_PACKET_BYTES):
            return packet, payloads[index:]
        if not packet and encoded + 2 > MIRROR_PACKET_BYTES:
            return [payload], payloads[index + 1 :]
        packet.append(payload)
        size += extra
    return packet, []


def _mark_retry(event_pk, token, attempt_count, remaining, failed_packet=None, error="operation_log_rejected") -> bool:
    status = CmdbOperationOutboxStatus.FAILED if attempt_count >= ChangeRecordMirrorService.MAX_ATTEMPTS else CmdbOperationOutboxStatus.RETRY
    delay = min(3600, 2 ** max(0, attempt_count - 1) * 30)
    payloads = list(failed_packet or []) + list(remaining or [])
    ChangeRecordMirrorOutbox.objects.filter(id=event_pk, status=CmdbOperationOutboxStatus.SENDING, owner_token=token).update(
        status=status,
        owner_token="",
        lease_expires_at=None,
        next_attempt_at=now() + timedelta(seconds=delay),
        last_error=error,
        payloads=payloads,
    )
    return False
