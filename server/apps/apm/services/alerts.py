from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.db.models.functions import TruncHour

from apps.apm.models import ApmAlert, ApmAlertOutbox, ApmEvent, ApmEventSnapshot, ApmPolicyTargetState
from apps.apm.services.contracts import MetricDataState, PolicyQueryResult
from apps.apm.services.policies import DjangoApmPolicyService
from apps.core.utils.viewset_utils import build_json_membership_query


class DjangoApmAlertService:
    @staticmethod
    def queryset(*, organization_id: int | None = None, organization_ids: Sequence[int] | None = None) -> QuerySet[ApmAlert]:
        queryset = ApmAlert.objects.select_related("policy", "service").prefetch_related(
            "events",
            "events__outbox_entries",
            "snapshots",
        )
        ids = list(organization_ids) if organization_ids is not None else [organization_id]
        return queryset.filter(build_json_membership_query(queryset, "organizations", ids))

    def list(
        self,
        *,
        organization_id: int | None = None,
        organization_ids: Sequence[int] | None = None,
        started_at: datetime,
        ended_at: datetime,
        status: str | None = None,
        status_group: str | None = None,
        severity: str | None = None,
        metric_type: str | None = None,
        service_id=None,
        keyword: str = "",
        limit: int = 50,
    ) -> list[dict]:
        queryset = self.queryset(organization_id=organization_id, organization_ids=organization_ids).filter(
            last_event_at__gte=started_at,
            last_event_at__lte=ended_at,
        )
        if status:
            queryset = queryset.filter(status=status)
        if status_group == "active":
            queryset = queryset.filter(status=ApmAlert.Status.ACTIVE)
        elif status_group == "history":
            queryset = queryset.filter(
                status__in=(ApmAlert.Status.RECOVERED, ApmAlert.Status.CLOSED)
            )
        if severity:
            queryset = queryset.filter(severity=severity)
        if metric_type:
            queryset = queryset.filter(metric_type=metric_type)
        if service_id:
            queryset = queryset.filter(service_id=service_id)
        if keyword:
            queryset = queryset.filter(
                Q(policy_name__icontains=keyword)
                | Q(service_name__icontains=keyword)
                | Q(service_namespace__icontains=keyword)
                | Q(endpoint__icontains=keyword)
                | Q(environment__icontains=keyword)
            )
        return [self.serialize(alert) for alert in queryset.order_by("-last_event_at", "-id")[:limit]]

    def distribution(
        self,
        *,
        organization_id: int | None = None,
        organization_ids: Sequence[int] | None = None,
        started_at: datetime,
        ended_at: datetime,
        status_group: str | None = None,
    ) -> list[dict]:
        event_queryset = ApmEvent.objects.all()
        if status_group == "active":
            event_queryset = event_queryset.filter(alert__status=ApmAlert.Status.ACTIVE)
        elif status_group == "history":
            event_queryset = event_queryset.filter(
                alert__status__in=(ApmAlert.Status.RECOVERED, ApmAlert.Status.CLOSED)
            )
        ids = list(organization_ids) if organization_ids is not None else [organization_id]
        rows = (
            event_queryset.filter(build_json_membership_query(event_queryset, "organizations", ids))
            .filter(occurred_at__gte=started_at, occurred_at__lte=ended_at)
            .annotate(bucket=TruncHour("occurred_at"))
            .values("bucket", "severity")
            .annotate(count=Count("id"))
            .order_by("bucket", "severity")[:1000]
        )
        buckets = {}
        for row in rows:
            bucket = row["bucket"].isoformat()
            buckets.setdefault(bucket, {"time": bucket, "critical": 0, "error": 0, "warning": 0})
            buckets[bucket][row["severity"]] = row["count"]
        return list(buckets.values())

    @staticmethod
    def serialize(alert: ApmAlert) -> dict:
        events = list(alert.events.all())
        outboxes_prefetched = all("outbox_entries" in getattr(event, "_prefetched_objects_cache", {}) for event in events)
        if outboxes_prefetched:
            delivery_statuses = [delivery.delivery_status for event in events for delivery in event.outbox_entries.all()]
        else:
            delivery_statuses = list(
                ApmAlertOutbox.objects.filter(event__alert=alert).values_list("delivery_status", flat=True)
            )
        status_set = set(delivery_statuses)
        if not status_set:
            notification_status = "none"
        elif status_set == {ApmAlertOutbox.DeliveryStatus.DELIVERED}:
            notification_status = "delivered"
        elif ApmAlertOutbox.DeliveryStatus.DELIVERED in status_set:
            notification_status = "partial"
        elif ApmAlertOutbox.DeliveryStatus.PENDING in status_set:
            notification_status = "pending"
        else:
            notification_status = "failed"
        return {
            "id": alert.id,
            "external_id": alert.external_id,
            "title": alert.policy_name,
            "policy_id": alert.policy_id_snapshot,
            "policy_name": alert.policy_name,
            "service_id": alert.service_id,
            "service_namespace": alert.service_namespace,
            "service_name": alert.service_name,
            "environment": alert.environment,
            "endpoint": alert.endpoint,
            "version": alert.version,
            "metric_type": alert.metric_type,
            "severity": alert.severity,
            "status": alert.status,
            "notification_status": notification_status,
            "current_value": alert.current_value,
            "operator": alert.operator,
            "started_at": alert.started_at,
            "ended_at": alert.ended_at,
            "last_event_at": alert.last_event_at,
            "event_count": len(events),
            "events": [
                {
                    "id": event.id,
                    "event_id": event.event_id,
                    "action": event.action,
                    "severity": event.severity,
                    "value": event.value,
                    "occurred_at": event.occurred_at,
                    "title": event.title,
                    "description": event.description,
                }
                for event in sorted(events, key=lambda item: (item.occurred_at, str(item.id)))
            ],
        }

    @staticmethod
    def close(alert: ApmAlert, *, actor: str, occurred_at: datetime) -> ApmAlert:
        with transaction.atomic():
            locked = ApmAlert.objects.select_for_update().get(id=alert.id)
            if locked.status != ApmAlert.Status.ACTIVE:
                return locked
            state = (
                ApmPolicyTargetState.objects.select_for_update().filter(policy=locked.policy, active_alert_id=locked.external_id).first()
                if locked.policy_id
                else None
            )
            if locked.policy is not None and state is not None:
                result = PolicyQueryResult(
                    value=locked.current_value,
                    breached=False,
                    evaluated_at=occurred_at,
                    data_state=MetricDataState.AVAILABLE,
                )
                snapshot = DjangoApmPolicyService._record_event(
                    locked.policy,
                    state,
                    result,
                    occurred_at,
                    locked.external_id,
                    ApmEvent.Action.CLOSED,
                    {"severity": locked.severity, "comparator": "closed", "value": ""},
                )
                state.status = ApmPolicyTargetState.Status.NORMAL
                state.active_alert_id = ""
                state.current_severity = ""
                state.consecutive_hits = 0
                state.consecutive_recoveries = 0
                state.consecutive_no_data = 0
                state.save()
            else:
                event, _ = ApmEvent.objects.get_or_create(
                    event_id=f"{locked.external_id}:closed:{locked.severity}",
                    defaults={
                        "alert": locked,
                        "action": ApmEvent.Action.CLOSED,
                        "title": f"APM {locked.policy_name}人工关闭",
                        "description": f"由 {actor} 人工关闭",
                        "severity": locked.severity,
                        "service": locked.service_name,
                        "item": locked.metric_type,
                        "value": locked.current_value,
                        "resource_id": str(locked.service_id or ""),
                        "resource_name": f"{locked.service_namespace}/{locked.service_name}".lstrip("/"),
                        "policy_id": locked.policy_id_snapshot,
                        "environment": locked.environment,
                        "organizations": locked.organizations,
                        "occurred_at": occurred_at,
                        "ended_at": occurred_at,
                    },
                )
                previous = locked.snapshots.order_by("-occurred_at", "-id").first()
                snapshot = event.snapshot if hasattr(event, "snapshot") else None
                if snapshot is None:
                    snapshot = ApmEventSnapshot.objects.create(
                        alert=locked,
                        event=event,
                        source_event_id=event.event_id,
                        action=event.action,
                        occurred_at=occurred_at,
                        organizations=locked.organizations,
                        policy_snapshot=previous.policy_snapshot if previous else {"id": locked.policy_id_snapshot, "name": locked.policy_name},
                        object_snapshot=(
                            previous.object_snapshot
                            if previous
                            else {
                                "service_id": str(locked.service_id or ""),
                                "service_namespace": locked.service_namespace,
                                "service_name": locked.service_name,
                                "endpoint": locked.endpoint,
                                "environment": locked.environment,
                                "version": locked.version,
                            }
                        ),
                        evaluation_snapshot={
                            "value": str(locked.current_value) if locked.current_value is not None else None,
                            "severity": locked.severity,
                            "data_state": "available",
                            "comparator": "closed",
                            "threshold": None,
                        },
                        trace_context=previous.trace_context if previous else {},
                        pending_payload={"schema_version": 1, "event_id": event.event_id, "event_point": occurred_at.isoformat(), "series": []},
                        retention_expires_at=occurred_at + (previous.retention_expires_at - previous.occurred_at if previous else timedelta(days=90)),
                    )
                locked.status = ApmAlert.Status.CLOSED
                locked.ended_at = occurred_at
                locked.last_event_at = occurred_at
                locked.operator = actor
                locked.save(update_fields=("status", "ended_at", "last_event_at", "operator", "updated_at"))
            locked.operator = actor
            locked.status = ApmAlert.Status.CLOSED
            locked.ended_at = occurred_at
            locked.last_event_at = occurred_at
            locked.save(update_fields=("operator", "status", "ended_at", "last_event_at", "updated_at"))
        return ApmAlert.objects.get(id=alert.id)
