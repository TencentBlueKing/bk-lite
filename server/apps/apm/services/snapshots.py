from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.apm.models import ApmEvent, ApmEventSnapshot, ApmEventSnapshotPayload, ApmPolicy
from apps.apm.services.contracts import PolicyQueryResult
from apps.core.logger import apm_logger as logger

SNAPSHOT_RETENTION_DAYS = 90
MAX_SNAPSHOT_POINTS = 240
MAX_SNAPSHOT_RETRIES = 8


class ApmEventSnapshotStore:
    """以 event 为幂等键保存不可变语义快照，并补偿对象载荷写入。"""

    @staticmethod
    def stage(
        *,
        event: ApmEvent,
        policy: ApmPolicy,
        result: PolicyQueryResult,
        endpoint: str,
        version: str,
        threshold: dict[str, str] | None,
    ) -> ApmEventSnapshot:
        unit = {
            ApmPolicy.MetricType.ERROR_RATE: "ratio",
            ApmPolicy.MetricType.P95: "ms",
            ApmPolicy.MetricType.P99: "ms",
            ApmPolicy.MetricType.THROUGHPUT: "req/s",
            ApmPolicy.MetricType.NO_TRAFFIC: "req/s",
        }[policy.metric_type]
        series = [
            {
                "timestamp": point.timestamp.isoformat(),
                "value": ApmEventSnapshotStore._point_value(policy.metric_type, point),
            }
            for point in result.series[-MAX_SNAPSHOT_POINTS:]
        ]
        defaults = {
            "alert": event.alert,
            "event": event,
            "schema_version": 1,
            "action": event.action,
            "occurred_at": event.occurred_at,
            "organizations": list(event.organizations),
            "policy_snapshot": {
                "id": str(policy.id),
                "name": policy.name,
                "alert_name": policy.alert_name,
                "metric_type": policy.metric_type,
                "evaluation_interval": policy.evaluation_interval,
                "metric_window": policy.metric_window,
                "aggregation": policy.aggregation,
                "thresholds": list(policy.thresholds),
                "trigger_after": policy.trigger_after,
                "recover_after": policy.recover_after,
                "no_data_after": policy.no_data_after,
                "no_data_severity": policy.no_data_severity,
            },
            "object_snapshot": {
                "service_id": str(policy.service_id),
                "service_namespace": policy.service.namespace,
                "service_name": policy.service.name,
                "endpoint": endpoint,
                "environment": policy.environment,
                "version": version,
            },
            "evaluation_snapshot": {
                "value": str(result.value) if result.value is not None else None,
                "unit": unit,
                "comparator": threshold.get("comparator") if threshold else None,
                "threshold": threshold.get("value") if threshold else None,
                "severity": threshold.get("severity") if threshold else event.severity,
                "data_state": str(result.data_state),
            },
            "trace_context": {
                "service_namespace": policy.service.namespace,
                "service_name": policy.service.name,
                "endpoint": endpoint,
                "environment": policy.environment,
                "version": version,
                "started_at": (event.occurred_at - timedelta(minutes=policy.metric_window)).isoformat(),
                "ended_at": event.occurred_at.isoformat(),
            },
            "pending_payload": {
                "schema_version": 1,
                "event_id": event.event_id,
                "event_point": event.occurred_at.isoformat(),
                "threshold": threshold,
                "series": series,
            },
            "retention_expires_at": event.occurred_at + timedelta(days=SNAPSHOT_RETENTION_DAYS),
        }
        snapshot, _ = ApmEventSnapshot.objects.get_or_create(source_event_id=event.event_id, defaults=defaults)
        return snapshot

    @staticmethod
    def persist(snapshot_id: UUID) -> ApmEventSnapshot:
        with transaction.atomic():
            snapshot = ApmEventSnapshot.objects.select_for_update().get(id=snapshot_id)
            if snapshot.payload_status in {
                ApmEventSnapshot.PayloadStatus.AVAILABLE,
                ApmEventSnapshot.PayloadStatus.EXPIRED,
            }:
                return snapshot
            if snapshot.payload_attempts >= MAX_SNAPSHOT_RETRIES:
                return snapshot
            snapshot.payload_attempts += 1
            try:
                ApmEventSnapshotPayload.objects.get_or_create(
                    snapshot=snapshot,
                    defaults={"data": snapshot.pending_payload},
                )
            except Exception as exc:
                snapshot.payload_status = ApmEventSnapshot.PayloadStatus.UNAVAILABLE
                snapshot.payload_error_code = "object_storage_unavailable"
                snapshot.payload_error_message = str(exc)[:512]
                snapshot.save(
                    update_fields=(
                        "payload_status",
                        "payload_attempts",
                        "payload_error_code",
                        "payload_error_message",
                        "updated_at",
                    )
                )
                logger.warning(
                    "APM event snapshot payload upload failed",
                    extra={"snapshot_id": str(snapshot.id), "error_type": type(exc).__name__},
                )
                return snapshot
            snapshot.payload_status = ApmEventSnapshot.PayloadStatus.AVAILABLE
            snapshot.payload_error_code = ""
            snapshot.payload_error_message = ""
            snapshot.pending_payload = {}
            snapshot.save(
                update_fields=(
                    "payload_status",
                    "payload_attempts",
                    "payload_error_code",
                    "payload_error_message",
                    "pending_payload",
                    "updated_at",
                )
            )
            return snapshot

    @staticmethod
    def expire_due(*, now=None, limit: int = 100) -> int:
        now = now or timezone.now()
        ids = list(
            ApmEventSnapshot.objects.filter(retention_expires_at__lte=now)
            .exclude(payload_status=ApmEventSnapshot.PayloadStatus.EXPIRED)
            .order_by("id")
            .values_list("id", flat=True)[: max(0, min(limit, 1000))]
        )
        expired = 0
        for snapshot_id in ids:
            with transaction.atomic():
                snapshot = ApmEventSnapshot.objects.select_for_update().get(id=snapshot_id)
                if snapshot.retention_expires_at > now:
                    continue
                payload_path = ApmEventSnapshotPayload.objects.filter(snapshot=snapshot).values_list("data", flat=True).first()
                if payload_path:
                    try:
                        ApmEventSnapshotStore._delete_payload_object(payload_path)
                    except Exception as exc:
                        snapshot.payload_status = ApmEventSnapshot.PayloadStatus.UNAVAILABLE
                        snapshot.payload_error_code = "retention_delete_failed"
                        snapshot.payload_error_message = str(exc)[:512]
                        snapshot.save(
                            update_fields=(
                                "payload_status",
                                "payload_error_code",
                                "payload_error_message",
                                "updated_at",
                            )
                        )
                        logger.warning(
                            "APM event snapshot payload retention delete failed",
                            extra={"snapshot_id": str(snapshot.id), "error_type": type(exc).__name__},
                        )
                        continue
                ApmEventSnapshotPayload.objects.filter(snapshot=snapshot).delete()
                snapshot.payload_status = ApmEventSnapshot.PayloadStatus.EXPIRED
                snapshot.pending_payload = {}
                snapshot.payload_error_code = ""
                snapshot.payload_error_message = ""
                snapshot.save(
                    update_fields=(
                        "payload_status",
                        "pending_payload",
                        "payload_error_code",
                        "payload_error_message",
                        "updated_at",
                    )
                )
                expired += 1
        return expired

    @staticmethod
    def _delete_payload_object(payload_path: str) -> None:
        field = ApmEventSnapshotPayload._meta.get_field("data")
        field.storage.delete(payload_path)

    @staticmethod
    def serialize(snapshot: ApmEventSnapshot) -> dict:
        payload = None
        payload_status = snapshot.payload_status
        payload_error_code = snapshot.payload_error_code
        if snapshot.payload_status == ApmEventSnapshot.PayloadStatus.AVAILABLE:
            try:
                payload = snapshot.payload.data
            except Exception as exc:
                payload_status = ApmEventSnapshot.PayloadStatus.UNAVAILABLE
                payload_error_code = "object_storage_read_failed"
                logger.warning(
                    "APM event snapshot payload read failed",
                    extra={"snapshot_id": str(snapshot.id), "error_type": type(exc).__name__},
                )
        return {
            "id": snapshot.id,
            "event_id": snapshot.source_event_id,
            "schema_version": snapshot.schema_version,
            "action": snapshot.action,
            "occurred_at": snapshot.occurred_at,
            "policy_snapshot": snapshot.policy_snapshot,
            "object_snapshot": snapshot.object_snapshot,
            "evaluation_snapshot": snapshot.evaluation_snapshot,
            "trace_context": snapshot.trace_context,
            "payload_status": payload_status,
            "payload_error_code": payload_error_code,
            "payload": payload,
            "retention_expires_at": snapshot.retention_expires_at,
        }

    @staticmethod
    def _point_value(metric_type: str, point) -> float | None:
        return {
            ApmPolicy.MetricType.ERROR_RATE: point.error_rate,
            ApmPolicy.MetricType.P95: point.p95_ms,
            ApmPolicy.MetricType.P99: point.p99_ms,
            ApmPolicy.MetricType.THROUGHPUT: point.request_rate,
            ApmPolicy.MetricType.NO_TRAFFIC: point.request_rate,
        }[metric_type]
