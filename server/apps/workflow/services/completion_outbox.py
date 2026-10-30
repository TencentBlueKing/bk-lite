"""编排执行终态的异步回调 outbox。HTTP 投递失败只更新 outbox，不回写执行状态。"""

from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.logger import workflow_logger as logger
from apps.core.openapi.async_callback import deliver_gateway_callback
from apps.rpc.sensitive import sanitize_sensitive_data
from apps.workflow.models import WorkflowCompletionOutbox, WorkflowExecution

TERMINAL_STATUSES = {
    WorkflowExecution.Status.SUCCEEDED,
    WorkflowExecution.Status.FAILED,
    WorkflowExecution.Status.TIMED_OUT,
    WorkflowExecution.Status.TERMINATED,
}

OUTBOX_DISPATCH_BATCH_SIZE = 50
OUTBOX_LEASE_SECONDS = 300
OUTBOX_FAILED_COOLDOWN_SECONDS = 3600


def _async_callback_payload(execution) -> dict:
    async_ctx = execution.async_callback_context if isinstance(execution.async_callback_context, dict) else {}
    result = execution.status == WorkflowExecution.Status.SUCCEEDED
    finished_at = execution.finished_at.isoformat() if execution.finished_at else None
    return {
        "execution_id": str(execution.id),
        "callback_key": execution.async_callback_key or "",
        "url": async_ctx["callback_url"],
        "deadline_at": execution.async_callback_deadline_at.isoformat() if execution.async_callback_deadline_at else None,
        "identity": {
            "user": async_ctx.get("user") or execution.started_by,
            "domain": async_ctx.get("domain") or execution.domain,
            "team_id": async_ctx.get("team_id"),
        },
        "request_body": {
            "callback_token": async_ctx["callback_token"],
            "operator": async_ctx.get("operator") or "system",
            "output_data": {
                "result": result,
                "data": {
                    "execution_id": str(execution.id),
                    "workflow_id": str(execution.workflow_id),
                    "status": execution.status,
                    "finished_at": finished_at,
                    "error_message": execution.error_message or "",
                    "output": execution.output or {},
                },
            },
        },
    }


def enqueue_async_callback(execution) -> WorkflowCompletionOutbox | None:
    """在执行已进入终态后记录回调意图。调用方必须已提交执行终态。"""
    if execution.status not in TERMINAL_STATUSES:
        return None
    async_ctx = execution.async_callback_context if isinstance(execution.async_callback_context, dict) else None
    if not async_ctx or not async_ctx.get("callback_url") or not async_ctx.get("callback_token"):
        return None
    delivery_id = f"workflow:{execution.id}:async:{execution.async_callback_key or execution.id}"
    payload = {**_async_callback_payload(execution), "delivery_id": delivery_id}
    record, _ = WorkflowCompletionOutbox.objects.get_or_create(
        idempotency_key=delivery_id,
        defaults={
            "execution_id": execution.id,
            "kind": WorkflowCompletionOutbox.Kind.ASYNC_CALLBACK,
            "payload": payload,
        },
    )
    return record


def enqueue_async_callback_safely(execution) -> None:
    try:
        with transaction.atomic():
            enqueue_async_callback(execution)
    except Exception:
        logger.exception(
            "event=workflow_async_callback_enqueue_failed execution_id=%s",
            execution.id,
        )


def reconcile_terminal_async_callbacks(*, limit: int = 100) -> int:
    """补偿终态已落库但 outbox 未写入的窗口。"""
    queued = 0
    executions = (
        WorkflowExecution.objects.filter(status__in=TERMINAL_STATUSES)
        .exclude(async_callback_context=None)
        .order_by("updated_at", "id")[: max(1, min(int(limit), 100))]
    )
    for execution in executions:
        async_ctx = execution.async_callback_context if isinstance(execution.async_callback_context, dict) else None
        if not async_ctx:
            continue
        try:
            if enqueue_async_callback(execution) is not None:
                queued += 1
        except Exception:
            logger.exception(
                "event=workflow_async_callback_reconcile_failed execution_id=%s",
                execution.id,
            )
    return queued


def _claim_delivery(record_id: int):
    with transaction.atomic():
        record = WorkflowCompletionOutbox.objects.select_for_update().filter(pk=record_id).first()
        if not record or record.status in (WorkflowCompletionOutbox.Status.DELIVERED, WorkflowCompletionOutbox.Status.STOPPED):
            return None
        deadline = (record.payload or {}).get("deadline_at")
        if deadline:
            try:
                deadline_at = parse_datetime(deadline)
                if timezone.is_naive(deadline_at):
                    deadline_at = timezone.make_aware(deadline_at, timezone.utc)
                if deadline_at and deadline_at <= timezone.now():
                    record.status = WorkflowCompletionOutbox.Status.STOPPED
                    record.next_retry_at = None
                    record.lease_token = None
                    record.lease_expires_at = None
                    record.last_error = "DEADLINE_EXCEEDED"
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
                    return None
            except Exception:
                pass
        now = timezone.now()
        if (
            record.status in (WorkflowCompletionOutbox.Status.PENDING, WorkflowCompletionOutbox.Status.FAILED)
            and record.next_retry_at
            and record.next_retry_at > now
        ):
            return None
        if record.status == WorkflowCompletionOutbox.Status.DELIVERING and record.lease_expires_at and record.lease_expires_at > now:
            return None
        if record.status == WorkflowCompletionOutbox.Status.FAILED:
            record.attempts = 0
        if record.attempts >= record.max_attempts:
            record.status = WorkflowCompletionOutbox.Status.FAILED
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
        record.status = WorkflowCompletionOutbox.Status.DELIVERING
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
        return record.payload, lease_token


def _mark_delivery_failed(record_id: int, lease_token, exc: Exception) -> None:
    with transaction.atomic():
        record = WorkflowCompletionOutbox.objects.select_for_update().filter(pk=record_id, lease_token=lease_token).first()
        if not record:
            return
        reason = str(exc)
        exhausted = record.attempts >= record.max_attempts
        stop = exhausted or reason.startswith("CALLBACK_REJECTED")
        if stop:
            record.status = WorkflowCompletionOutbox.Status.STOPPED
            record.next_retry_at = None
        else:
            record.status = WorkflowCompletionOutbox.Status.FAILED if exhausted else WorkflowCompletionOutbox.Status.PENDING
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


def deliver_outbox_record(record_id: int) -> bool:
    claim = _claim_delivery(record_id)
    if claim is None:
        return False
    payload, lease_token = claim
    try:
        deliver_gateway_callback(payload)
    except Exception as exc:
        _mark_delivery_failed(record_id, lease_token, exc)
        logger.exception(
            "event=workflow_async_callback_delivery_failed outbox_id=%s execution_id=%s",
            record_id,
            (payload or {}).get("execution_id"),
        )
        return False
    updated = WorkflowCompletionOutbox.objects.filter(
        pk=record_id,
        lease_token=lease_token,
        status=WorkflowCompletionOutbox.Status.DELIVERING,
    ).update(
        status=WorkflowCompletionOutbox.Status.DELIVERED,
        delivered_at=timezone.now(),
        next_retry_at=None,
        lease_token=None,
        lease_expires_at=None,
        last_error="",
        updated_at=timezone.now(),
    )
    return bool(updated)


def due_outbox_ids(now=None, batch_size: int = OUTBOX_DISPATCH_BATCH_SIZE) -> list[int]:
    now = now or timezone.now()
    due_retry = Q(status__in=[WorkflowCompletionOutbox.Status.PENDING, WorkflowCompletionOutbox.Status.FAILED]) & (
        Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now)
    )
    expired_delivery = Q(status=WorkflowCompletionOutbox.Status.DELIVERING) & (Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
    return list(WorkflowCompletionOutbox.objects.filter(due_retry | expired_delivery).order_by("pk").values_list("pk", flat=True)[:batch_size])


def dispatch_pending_async_callbacks() -> dict[str, int]:
    reconciled = reconcile_terminal_async_callbacks()
    delivered = 0
    failed = 0
    for record_id in due_outbox_ids():
        try:
            if deliver_outbox_record(record_id):
                delivered += 1
            else:
                failed += 1
        except Exception:
            failed += 1
            logger.exception("event=workflow_async_callback_dispatch_failed outbox_id=%s", record_id)
    return {"reconciled": reconciled, "delivered": delivered, "failed": failed}
