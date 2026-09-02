from __future__ import annotations

from collections.abc import Sequence

from django.db import transaction
from django.db.models import QuerySet

from apps.apm.models import ApmAlertOutbox, ApmNotificationDeliveryRetry
from apps.core.utils.viewset_utils import build_json_membership_query


class DeliveryStateConflict(RuntimeError):
    pass


class DjangoNotificationDeliveryService:
    def queryset(self, *, organization_id: int | None = None, organization_ids: Sequence[int] | None = None) -> QuerySet[ApmAlertOutbox]:
        queryset = ApmAlertOutbox.objects.select_related("event", "event__alert")
        ids = list(organization_ids) if organization_ids is not None else [organization_id]
        return queryset.filter(
            build_json_membership_query(queryset, "event__organizations", ids)
        )

    @staticmethod
    def serialize(delivery: ApmAlertOutbox) -> dict:
        return {
            "id": delivery.id,
            "event_id": delivery.event.event_id if delivery.event else None,
            "channel_id": delivery.channel_id,
            "channel_name": delivery.channel_name,
            "channel_type": delivery.channel_type,
            "delivery_mode": delivery.delivery_mode,
            "recipients": delivery.recipients,
            "status": delivery.delivery_status,
            "attempts": delivery.attempts,
            "next_retry_at": delivery.next_retry_at,
            "last_error_code": delivery.last_error_code,
            "last_error_message": delivery.last_error_message,
            "delivered_at": delivery.delivered_at,
            "failed_at": delivery.failed_at,
        }

    @staticmethod
    def retry(delivery: ApmAlertOutbox, *, actor: str, recipients: list[str] | None = None) -> ApmAlertOutbox:
        with transaction.atomic():
            locked = ApmAlertOutbox.objects.select_for_update().get(id=delivery.id)
            if locked.delivery_status != ApmAlertOutbox.DeliveryStatus.FAILED:
                raise DeliveryStateConflict("只有终止失败的通知可以人工重投。")
            if recipients is not None:
                if locked.delivery_mode == "alert_event_copy" and recipients:
                    raise DeliveryStateConflict("告警中心事件副本不接受接收人。")
                locked.recipients = recipients
                locked.receivers = recipients
            ApmNotificationDeliveryRetry.objects.create(
                delivery=locked,
                requested_by=actor,
                previous_attempts=locked.attempts,
                previous_error_code=locked.last_error_code,
                previous_error_message=locked.last_error_message,
                created_by=actor,
                updated_by=actor,
            )
            locked.delivery_status = ApmAlertOutbox.DeliveryStatus.PENDING
            locked.attempts = 0
            locked.next_retry_at = None
            locked.claimed_at = None
            locked.last_error_code = ""
            locked.last_error_message = ""
            locked.delivered_at = None
            locked.failed_at = None
            locked.save()
            return locked
