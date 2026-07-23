"""作业终态副作用的 transactional outbox。

数据库事务只负责写终态与不可变投递意图；外部 I/O 由 worker 执行。Celery 入队只是
快速路径，Beat 会重扫待投递及租约过期记录，因此 broker 抖动或 worker 崩溃不会丢失
终态副作用。投递语义为 at-least-once，接收方使用 payload.delivery_id 去重。
"""

import hashlib
from datetime import timedelta
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from nats.js.errors import NotFoundError, ObjectNotFoundError

from apps.core.logger import job_logger as logger
from apps.core.utils.safe_requests import safe_post
from apps.core.utils.ssrf_validator import SSRFValidator
from apps.job_mgmt.constants import CallbackType, ExecutionStatus
from apps.job_mgmt.models import JobCompletionOutbox
from apps.job_mgmt.services.callback_service import build_callback_payload, publish_job_result_to_subject
from apps.job_mgmt.services.execution_stream_service import publish_done_sentinel
from apps.job_mgmt.utils.callback_signer import get_signed_headers
from apps.node_mgmt.utils.s3 import delete_s3_file
from apps.rpc.sensitive import sanitize_sensitive_data

OUTBOX_DISPATCH_BATCH_SIZE = 200
OUTBOX_LEASE_SECONDS = 300
OUTBOX_FAILED_COOLDOWN_SECONDS = 3600


def _stable_key(execution_id: int, terminal_status: str, kind: str, discriminator: str = "") -> str:
    raw = f"{execution_id}\0{terminal_status}\0{kind}\0{discriminator}".encode()
    digest = hashlib.sha256(raw).hexdigest()
    return f"job:{execution_id}:terminal:{kind}:{digest}"


def _web_callback_payload(execution, delivery_id: str) -> dict:
    return {
        "task_id": execution.id,
        "status": execution.status,
        "total_count": execution.total_count,
        "success_count": execution.success_count,
        "failed_count": execution.failed_count,
        "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
        "delivery_id": delivery_id,
    }


def _intent(kind: str, execution, payload: dict, discriminator: str = "") -> tuple[str, dict]:
    delivery_id = _stable_key(execution.id, execution.status, kind, discriminator)
    return delivery_id, {**payload, "delivery_id": delivery_id}


def _build_terminal_intents(execution) -> list[tuple[str, str, dict]]:
    intents = []
    seen_target_keys = set()
    for result in execution.execution_results or []:
        target_key = str(result.get("target_key", ""))
        if target_key in seen_target_keys:
            continue
        seen_target_keys.add(target_key)
        delivery_id, payload = _intent(
            JobCompletionOutbox.Kind.DONE_SENTINEL,
            execution,
            {
                "execution_id": execution.id,
                "target_key": target_key,
                "status": result.get("status", execution.status),
            },
            target_key,
        )
        intents.append((JobCompletionOutbox.Kind.DONE_SENTINEL, delivery_id, payload))

    if execution.playbook_id and execution.playbook:
        file_key = f"job-playbooks/{execution.id}/{execution.playbook.file_name}"
        delivery_id, payload = _intent(
            JobCompletionOutbox.Kind.PLAYBOOK_CLEANUP,
            execution,
            {"file_key": file_key},
            file_key,
        )
        intents.append((JobCompletionOutbox.Kind.PLAYBOOK_CLEANUP, delivery_id, payload))

    callback_type = execution.callback_type or CallbackType.WEB
    if CallbackType.use_web(callback_type) and execution.callback_url:
        delivery_id = _stable_key(execution.id, execution.status, JobCompletionOutbox.Kind.WEB_CALLBACK)
        payload = _web_callback_payload(execution, delivery_id)
        payload["url"] = execution.callback_url
        intents.append((JobCompletionOutbox.Kind.WEB_CALLBACK, delivery_id, payload))

    if CallbackType.use_nats(callback_type) and execution.callback_subject:
        delivery_id = _stable_key(execution.id, execution.status, JobCompletionOutbox.Kind.NATS_CALLBACK)
        callback_payload = build_callback_payload(execution)
        callback_payload["delivery_id"] = delivery_id
        intents.append(
            (
                JobCompletionOutbox.Kind.NATS_CALLBACK,
                delivery_id,
                {"subject": execution.callback_subject, "callback_payload": callback_payload, "delivery_id": delivery_id},
            )
        )
    return intents


def enqueue_terminal_effects(execution) -> list[JobCompletionOutbox]:
    """在调用方终态事务内持久化各副作用，返回新建或复用的记录。"""
    if execution.status not in ExecutionStatus.TERMINAL_STATES:
        raise ValueError(f"仅终态可创建完成 outbox: status={execution.status}")
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("终态与完成 outbox 必须在同一数据库事务内写入")

    records = []
    created_ids = []
    for kind, delivery_id, payload in _build_terminal_intents(execution):
        record, created = JobCompletionOutbox.objects.get_or_create(
            idempotency_key=delivery_id,
            defaults={
                "execution_id": execution.id,
                "kind": kind,
                "payload": payload,
            },
        )
        records.append(record)
        if created:
            created_ids.append(record.pk)

    if created_ids:
        transaction.on_commit(lambda record_ids=tuple(created_ids): _schedule_deliveries(record_ids))
    return records


def _schedule_deliveries(record_ids) -> None:
    from apps.job_mgmt.tasks import deliver_job_completion_outbox

    for record_id in record_ids:
        try:
            deliver_job_completion_outbox.delay(record_id)
        except Exception:
            logger.exception("job completion outbox broker enqueue failed: outbox_id=%s", record_id)


def _claim_delivery(record_id: int):
    now = timezone.now()
    with transaction.atomic():
        record = JobCompletionOutbox.objects.select_for_update().filter(pk=record_id).first()
        if not record or record.status == JobCompletionOutbox.Status.DELIVERED:
            return None
        if (
            record.status in (JobCompletionOutbox.Status.PENDING, JobCompletionOutbox.Status.FAILED)
            and record.next_retry_at
            and record.next_retry_at > now
        ):
            return None
        if record.status == JobCompletionOutbox.Status.DELIVERING and record.lease_expires_at and record.lease_expires_at > now:
            return None
        if record.status == JobCompletionOutbox.Status.FAILED:
            # 一个重试周期耗尽后自动冷却再开新周期，避免永久依赖人工复位。
            record.attempts = 0
        if record.attempts >= record.max_attempts:
            record.status = JobCompletionOutbox.Status.FAILED
            record.next_retry_at = now + timedelta(seconds=OUTBOX_FAILED_COOLDOWN_SECONDS)
            record.lease_token = None
            record.lease_expires_at = None
            record.save(
                update_fields=[
                    "status",
                    "next_retry_at",
                    "lease_token",
                    "lease_expires_at",
                    "updated_at",
                ]
            )
            return None

        lease_token = uuid4()
        record.status = JobCompletionOutbox.Status.DELIVERING
        record.attempts += 1
        record.next_retry_at = None
        record.lease_token = lease_token
        record.lease_expires_at = now + timedelta(seconds=OUTBOX_LEASE_SECONDS)
        record.last_error = ""
        record.save(
            update_fields=[
                "status",
                "attempts",
                "next_retry_at",
                "lease_token",
                "lease_expires_at",
                "last_error",
                "updated_at",
            ]
        )
        return record.kind, record.payload, lease_token


def _deliver_payload(kind: str, payload: dict) -> None:
    if kind == JobCompletionOutbox.Kind.DONE_SENTINEL:
        publish_done_sentinel(payload["execution_id"], payload["target_key"], payload["status"])
        return
    if kind == JobCompletionOutbox.Kind.PLAYBOOK_CLEANUP:
        try:
            async_to_sync(delete_s3_file)(payload["file_key"])
        except (NotFoundError, ObjectNotFoundError):
            # 外部删除成功、worker 尚未回写 delivered 就崩溃时，重投仍视为成功。
            pass
        return
    if kind == JobCompletionOutbox.Kind.WEB_CALLBACK:
        url = payload["url"]
        callback_payload = {key: value for key, value in payload.items() if key != "url"}
        SSRFValidator.validate_callback(url)
        response = safe_post(url, json=callback_payload, headers=get_signed_headers(callback_payload), timeout=10)
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"回调返回非 2xx: status_code={response.status_code}")
        return
    if kind == JobCompletionOutbox.Kind.NATS_CALLBACK:
        publish_job_result_to_subject(payload["subject"], payload["callback_payload"])
        return
    raise ValueError(f"不支持的作业完成 outbox 类型: {kind}")


def _mark_delivery_failed(record_id: int, lease_token, exc: Exception) -> None:
    with transaction.atomic():
        record = JobCompletionOutbox.objects.select_for_update().filter(pk=record_id, lease_token=lease_token).first()
        if not record:
            return
        exhausted = record.attempts >= record.max_attempts
        record.status = JobCompletionOutbox.Status.FAILED if exhausted else JobCompletionOutbox.Status.PENDING
        delay_seconds = min(3600, 15 * (2 ** min(record.attempts, 8)))
        if exhausted:
            delay_seconds = OUTBOX_FAILED_COOLDOWN_SECONDS
        record.next_retry_at = timezone.now() + timedelta(seconds=delay_seconds)
        record.lease_token = None
        record.lease_expires_at = None
        record.last_error = str(sanitize_sensitive_data(str(exc)))[:2000]
        record.save(
            update_fields=[
                "status",
                "next_retry_at",
                "lease_token",
                "lease_expires_at",
                "last_error",
                "updated_at",
            ]
        )


def _mark_delivery_succeeded(record_id: int, lease_token) -> bool:
    updated = JobCompletionOutbox.objects.filter(
        pk=record_id,
        lease_token=lease_token,
        status=JobCompletionOutbox.Status.DELIVERING,
    ).update(
        status=JobCompletionOutbox.Status.DELIVERED,
        delivered_at=timezone.now(),
        next_retry_at=None,
        lease_token=None,
        lease_expires_at=None,
        last_error="",
        updated_at=timezone.now(),
    )
    return bool(updated)


def deliver_outbox_record(record_id: int) -> bool:
    claim = _claim_delivery(record_id)
    if claim is None:
        return False
    kind, payload, lease_token = claim
    try:
        _deliver_payload(kind, payload)
    except Exception as exc:
        _mark_delivery_failed(record_id, lease_token, exc)
        raise
    return _mark_delivery_succeeded(record_id, lease_token)


def due_outbox_ids(now=None, batch_size: int = OUTBOX_DISPATCH_BATCH_SIZE) -> list[int]:
    now = now or timezone.now()
    due_retry = Q(status__in=[JobCompletionOutbox.Status.PENDING, JobCompletionOutbox.Status.FAILED]) & (
        Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now)
    )
    expired_delivery = Q(status=JobCompletionOutbox.Status.DELIVERING) & (Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
    return list(JobCompletionOutbox.objects.filter(due_retry | expired_delivery).order_by("pk").values_list("pk", flat=True)[:batch_size])
