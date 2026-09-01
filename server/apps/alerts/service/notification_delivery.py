"""Alerts 通知 Outbox 的渠道级投递状态机。"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from apps.alerts.constants.constants import NotifyResultStatus
from apps.alerts.models.outbox import AlertNotificationDelivery, AlertOutbox
from apps.alerts.service.notify_service import NotifyResultService
from apps.core.logger import alert_logger as logger

DELIVERY_LEASE_TIMEOUT = timedelta(minutes=5)
DELIVERY_DISPATCH_BATCH_SIZE = 500


def _delivery_key(outbox_key: str, position: int, parameter: dict) -> str:
    identity = "\0".join(
        (
            outbox_key,
            str(position),
            str(parameter.get("channel_type") or ""),
            str(parameter.get("channel_id") or ""),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def ensure_notification_deliveries(record_id: int) -> list[int]:
    """幂等地把旧多渠道 payload 物化为每渠道一条持久意图。"""
    with transaction.atomic():
        record = AlertOutbox.objects.select_for_update().get(pk=record_id)
        params = record.payload.get("params") if isinstance(record.payload, dict) else []
        params = params if isinstance(params, list) else []
        existing_positions = set(record.notification_deliveries.values_list("position", flat=True))
        new_deliveries = []
        for position, raw_parameter in enumerate(params):
            if position in existing_positions:
                continue
            parameter = dict(raw_parameter) if isinstance(raw_parameter, dict) else {}
            new_deliveries.append(
                AlertNotificationDelivery(
                    outbox=record,
                    position=position,
                    delivery_key=_delivery_key(
                        record.idempotency_key,
                        position,
                        parameter,
                    ),
                    parameter=parameter,
                    channel_id=str(parameter.get("channel_id") or ""),
                    channel_type=str(parameter.get("channel_type") or ""),
                    max_attempts=record.max_attempts,
                )
            )
        if new_deliveries:
            AlertNotificationDelivery.objects.bulk_create(
                new_deliveries,
                ignore_conflicts=True,
            )
        return list(
            record.notification_deliveries.order_by("position").values_list(
                "pk",
                flat=True,
            )
        )


def schedule_notification_delivery(delivery_id: int) -> None:
    """提交渠道任务；Broker 故障时持久意图仍由周期补偿捞起。"""
    try:
        from apps.alerts.tasks import deliver_alert_notification_channel

        deliver_alert_notification_channel.delay(delivery_id)
    except Exception:
        logger.exception(
            "alert notification broker enqueue failed: delivery_id=%s",
            delivery_id,
        )


def schedule_notification_deliveries(delivery_ids: list[int]) -> None:
    for delivery_id in delivery_ids:
        schedule_notification_delivery(delivery_id)


def _failure_reason(parameter: dict, result) -> str:
    notify_result = result if isinstance(result, dict) else {"result": False}
    service = NotifyResultService(
        notify_users=list(parameter.get("username_list") or []),
        channel=str(parameter.get("channel_type") or ""),
        notify_result=notify_result,
        notify_object=parameter.get("object_id") or "",
        notify_action_object=parameter.get("notify_action_object") or "alert",
    )
    return service.format_failure_reason() or NotifyResultService.DEFAULT_FAILURE_REASON


def _failure_is_retryable(result) -> bool:
    if isinstance(result, dict) and isinstance(result.get("retryable"), bool):
        return result["retryable"]
    return True


def deliver_notification_channel(delivery_id: int, *, notify_func) -> bool:
    """领取并投递单个渠道；仅当前 claim 可以提交结果。"""
    claim_token = uuid4().hex
    now = timezone.now()
    with transaction.atomic():
        delivery = AlertNotificationDelivery.objects.select_for_update().filter(pk=delivery_id).first()
        if delivery is None or delivery.status in {
            AlertNotificationDelivery.Status.DELIVERED,
            AlertNotificationDelivery.Status.FAILED,
        }:
            return False
        if delivery.next_retry_at and delivery.next_retry_at > now:
            return False
        if delivery.status == AlertNotificationDelivery.Status.DELIVERING and delivery.updated_at > now - DELIVERY_LEASE_TIMEOUT:
            return False
        if delivery.attempts >= delivery.max_attempts:
            delivery.status = AlertNotificationDelivery.Status.FAILED
            delivery.next_retry_at = None
            delivery.last_error = delivery.last_error or "通知渠道重试次数已耗尽"
            delivery.save(
                update_fields=[
                    "status",
                    "next_retry_at",
                    "last_error",
                    "updated_at",
                ]
            )
            return False

        delivery.status = AlertNotificationDelivery.Status.DELIVERING
        delivery.attempts += 1
        delivery.claim_token = claim_token
        delivery.last_error = ""
        delivery.save(
            update_fields=[
                "status",
                "attempts",
                "claim_token",
                "last_error",
                "updated_at",
            ]
        )
        parameter = dict(delivery.parameter or {})
        attempt = delivery.attempts
        max_attempts = delivery.max_attempts

    try:
        results = notify_func([parameter])
        result = results[0] if isinstance(results, list) and len(results) == 1 else None
        succeeded = NotifyResultService.classify_notify_result(result) == NotifyResultStatus.SUCCESS
    except Exception:
        logger.exception(
            "alert notification channel execution failed: delivery_id=%s key=%s",
            delivery_id,
            delivery.delivery_key,
        )
        result = None
        succeeded = False

    finalized_at = timezone.now()
    if succeeded:
        finalized = bool(
            AlertNotificationDelivery.objects.filter(
                pk=delivery_id,
                status=AlertNotificationDelivery.Status.DELIVERING,
                claim_token=claim_token,
            ).update(
                status=AlertNotificationDelivery.Status.DELIVERED,
                delivered_at=finalized_at,
                next_retry_at=None,
                last_error="",
                updated_at=finalized_at,
            )
        )
        if finalized:
            logger.info(
                "alert notification channel delivered: delivery_id=%s key=%s channel=%s attempts=%s",
                delivery_id,
                delivery.delivery_key,
                delivery.channel_type,
                attempt,
            )
        return finalized

    exhausted = attempt >= max_attempts or not _failure_is_retryable(result)
    delay_seconds = min(3600, 2 ** min(attempt, 10) * 15)
    reason = _failure_reason(parameter, result)
    finalized = AlertNotificationDelivery.objects.filter(
        pk=delivery_id,
        status=AlertNotificationDelivery.Status.DELIVERING,
        claim_token=claim_token,
    ).update(
        status=(AlertNotificationDelivery.Status.FAILED if exhausted else AlertNotificationDelivery.Status.PENDING),
        next_retry_at=(None if exhausted else finalized_at + timedelta(seconds=delay_seconds)),
        last_error=reason[:2000],
        updated_at=finalized_at,
    )
    if finalized:
        logger.warning(
            "alert notification channel failed: delivery_id=%s key=%s channel=%s attempts=%s/%s terminal=%s error=%s",
            delivery_id,
            delivery.delivery_key,
            delivery.channel_type,
            attempt,
            max_attempts,
            exhausted,
            reason,
        )
    return False
