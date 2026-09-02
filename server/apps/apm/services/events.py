from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from apps.apm.models import ApmEvent
from apps.apm.services.deliveries import DjangoNotificationDeliveryService
from apps.core.utils.viewset_utils import build_json_membership_query


class DjangoApmEventReader:
    """查询 APM 自己持久化的领域告警事件。"""

    def list(
        self,
        *,
        organization_id: int | None = None,
        organization_ids: Sequence[int] | None = None,
        started_at: datetime,
        ended_at: datetime,
        action: str | None = None,
        severity: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        queryset = (
            ApmEvent.objects.select_related("alert", "snapshot")
            .prefetch_related("outbox_entries")
            .filter(
                occurred_at__gte=started_at,
                occurred_at__lte=ended_at,
            )
        )
        ids = list(organization_ids) if organization_ids is not None else [organization_id]
        queryset = queryset.filter(build_json_membership_query(queryset, "organizations", ids))
        if action:
            queryset = queryset.filter(action=action)
        if severity:
            queryset = queryset.filter(severity=severity)
        return [self._serialize(event) for event in queryset.order_by("-occurred_at", "-id")[:limit]]

    @staticmethod
    def _serialize(event: ApmEvent) -> dict:
        return {
            "id": event.id,
            "event_id": event.event_id,
            "external_id": event.alert.external_id,
            "title": event.title,
            "description": event.description,
            "severity": event.severity,
            "action": event.action,
            "status": event.alert.status,
            "service": event.service,
            "item": event.item,
            "value": event.value,
            "resource_id": event.resource_id,
            "resource_name": event.resource_name,
            "start_time": event.alert.started_at,
            "end_time": event.ended_at,
            "received_at": event.occurred_at,
            "policy_id": event.policy_id,
            "environment": event.environment,
            "endpoint": event.alert.endpoint,
            "version": event.alert.version,
            "snapshot_status": event.snapshot.payload_status if hasattr(event, "snapshot") else "unavailable",
            "notification_deliveries": [DjangoNotificationDeliveryService.serialize(delivery) for delivery in event.outbox_entries.all()],
        }
