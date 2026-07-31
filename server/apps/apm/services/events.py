from __future__ import annotations

from datetime import datetime

from apps.apm.constants import APM_ALERT_PUSHER


class AlertsUnavailable(RuntimeError):
    pass


class DjangoApmEventReader:
    """只读取 Alerts 中 APM 来源事件，不复制生命周期数据。"""

    def list(
        self,
        *,
        organization_id: int,
        started_at: datetime,
        ended_at: datetime,
        action: str | None = None,
        severity: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        try:
            from apps.alerts.models.models import Event
            from apps.core.utils.viewset_utils import build_json_membership_query
        except (ImportError, RuntimeError) as exc:
            raise AlertsUnavailable("Alerts 模块不可用") from exc

        queryset = Event.objects.select_related("source").filter(
            push_source_id=APM_ALERT_PUSHER,
            received_at__gte=started_at,
            received_at__lte=ended_at,
        )
        queryset = queryset.filter(build_json_membership_query(queryset, "team", [organization_id]))
        if action:
            queryset = queryset.filter(action=action)
        level_by_severity = {"critical": "0", "error": "1", "warning": "2"}
        if severity:
            queryset = queryset.filter(level=level_by_severity[severity])
        return [self._serialize(event) for event in queryset.order_by("-received_at", "-id")[:limit]]

    @staticmethod
    def _serialize(event) -> dict:
        labels = event.labels if isinstance(event.labels, dict) else {}
        return {
            "id": event.id,
            "event_id": event.event_id,
            "external_id": event.external_id,
            "title": event.title,
            "description": event.description,
            "severity": {"0": "critical", "1": "error", "2": "warning"}.get(event.level, "info"),
            "action": event.action,
            "status": event.status,
            "service": event.service,
            "item": event.item,
            "value": event.value,
            "resource_id": event.resource_id,
            "resource_name": event.resource_name,
            "start_time": event.start_time,
            "end_time": event.end_time,
            "received_at": event.received_at,
            "policy_id": labels.get("policy_id"),
            "environment": labels.get("environment", ""),
        }
