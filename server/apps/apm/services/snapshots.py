from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.apm.models import ApmEvent, ApmEventSnapshot, ApmEventSnapshotPayload, ApmPolicy
from apps.apm.services.contracts import PolicyQueryResult
from apps.apm.services.metric_snapshots import resolve_result_unit
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
            ApmPolicy.MetricType.SLOW_REQUEST_RATE: "ratio",
            ApmPolicy.MetricType.APDEX: "ratio",
            ApmPolicy.MetricType.ERROR_COUNT: "count",
            ApmPolicy.MetricType.SLOW_REQUEST_COUNT: "count",
            ApmPolicy.MetricType.P50: "ms",
            ApmPolicy.MetricType.P75: "ms",
            ApmPolicy.MetricType.P90: "ms",
            ApmPolicy.MetricType.P95: "ms",
            ApmPolicy.MetricType.P99: "ms",
            ApmPolicy.MetricType.LATENCY_AVG: "ms",
            ApmPolicy.MetricType.LATENCY_MAX: "ms",
            ApmPolicy.MetricType.THROUGHPUT: "req/s",
            ApmPolicy.MetricType.NO_TRAFFIC: "req/s",
        }[policy.metric_type]
        window_end = result.window_ended_at or event.occurred_at
        series = [
            {
                "timestamp": point.timestamp.isoformat(),
                "value": ApmEventSnapshotStore._point_value(policy.metric_type, point),
            }
            for point in result.series[-MAX_SNAPSHOT_POINTS:]
        ]
        baseline_series = [
            {
                "timestamp": point.timestamp.isoformat(),
                "value": ApmEventSnapshotStore._point_value(policy.metric_type, point),
            }
            for point in result.baseline_series[-MAX_SNAPSHOT_POINTS:]
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
                "no_data_alert_name": policy.no_data_alert_name,
                "compare_mode": policy.compare_mode,
                "compare_offset_amount": policy.compare_offset_amount,
                "compare_value_kind": policy.compare_value_kind,
                "min_request_count": policy.min_request_count,
                "slow_threshold_ms": policy.slow_threshold_ms,
                "apdex_threshold_ms": policy.apdex_threshold_ms,
                "trigger_window": policy.trigger_window,
                "recovery_threshold": dict(policy.recovery_threshold or {}),
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
                "current_value": str(result.current_value) if result.current_value is not None else None,
                "baseline_value": str(result.baseline_value) if result.baseline_value is not None else None,
                "result_unit": resolve_result_unit(policy),
            },
            "trace_context": {
                "service_namespace": policy.service.namespace,
                "service_name": policy.service.name,
                "endpoint": endpoint,
                "environment": policy.environment,
                "version": version,
                "started_at": (window_end - timedelta(minutes=policy.metric_window)).isoformat(),
                "ended_at": window_end.isoformat(),
            },
            "pending_payload": {
                "schema_version": 1,
                "event_id": event.event_id,
                "event_point": event.occurred_at.isoformat(),
                "threshold": threshold,
                "series": series,
                "baseline_series": baseline_series,
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
            pending_payload = snapshot.pending_payload
            snapshot.save(update_fields=("payload_attempts", "updated_at"))

        try:
            existing_path = ApmEventSnapshotPayload.objects.filter(snapshot_id=snapshot_id).values_list("data", flat=True).first()
            if not existing_path:
                field = ApmEventSnapshotPayload._meta.get_field("data")
                uploaded_path = field._upload_to_s3(
                    ApmEventSnapshotPayload(snapshot_id=snapshot_id),
                    pending_payload,
                )
                payload, _created = ApmEventSnapshotPayload.objects.get_or_create(
                    snapshot_id=snapshot_id,
                    defaults={"data": ""},
                )
                ApmEventSnapshotPayload.objects.filter(pk=payload.pk).update(data=uploaded_path)
        except IntegrityError:
            pass
        except Exception as exc:
            with transaction.atomic():
                snapshot = ApmEventSnapshot.objects.select_for_update().get(id=snapshot_id)
                if snapshot.payload_status in {
                    ApmEventSnapshot.PayloadStatus.AVAILABLE,
                    ApmEventSnapshot.PayloadStatus.EXPIRED,
                }:
                    return snapshot
                snapshot.payload_status = ApmEventSnapshot.PayloadStatus.UNAVAILABLE
                snapshot.payload_error_code = "object_storage_unavailable"
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
                "APM event snapshot payload upload failed",
                extra={"snapshot_id": str(snapshot.id), "error_type": type(exc).__name__},
            )
            return snapshot

        with transaction.atomic():
            snapshot = ApmEventSnapshot.objects.select_for_update().get(id=snapshot_id)
            if snapshot.payload_status == ApmEventSnapshot.PayloadStatus.EXPIRED:
                return snapshot
            snapshot.payload_status = ApmEventSnapshot.PayloadStatus.AVAILABLE
            snapshot.payload_error_code = ""
            snapshot.payload_error_message = ""
            snapshot.pending_payload = {}
            snapshot.save(
                update_fields=(
                    "payload_status",
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
                if snapshot.payload_status == ApmEventSnapshot.PayloadStatus.EXPIRED:
                    continue
                payload_path = ApmEventSnapshotPayload.objects.filter(snapshot=snapshot).values_list("data", flat=True).first()
            if payload_path:
                try:
                    ApmEventSnapshotStore._delete_payload_object(payload_path)
                except Exception as exc:
                    with transaction.atomic():
                        snapshot = ApmEventSnapshot.objects.select_for_update().get(id=snapshot_id)
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
            with transaction.atomic():
                snapshot = ApmEventSnapshot.objects.select_for_update().get(id=snapshot_id)
                if snapshot.retention_expires_at > now:
                    continue
                if snapshot.payload_status == ApmEventSnapshot.PayloadStatus.EXPIRED:
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
        if metric_type == ApmPolicy.MetricType.ERROR_COUNT:
            return None if point.error_count is None else float(point.error_count)
        if metric_type == ApmPolicy.MetricType.SLOW_REQUEST_COUNT:
            return None if point.slow_count is None else float(point.slow_count)
        if metric_type == ApmPolicy.MetricType.SLOW_REQUEST_RATE:
            if point.slow_count is None or not point.request_count:
                return None
            return float(point.slow_count) / float(point.request_count)
        if metric_type == ApmPolicy.MetricType.APDEX:
            if point.satisfied_count is None or point.tolerating_count is None or not point.request_count:
                return None
            return (point.satisfied_count + point.tolerating_count / 2) / point.request_count
        return {
            ApmPolicy.MetricType.ERROR_RATE: point.error_rate,
            ApmPolicy.MetricType.P50: point.p50_ms,
            ApmPolicy.MetricType.P75: point.p75_ms,
            ApmPolicy.MetricType.P90: point.p90_ms,
            ApmPolicy.MetricType.P95: point.p95_ms,
            ApmPolicy.MetricType.P99: point.p99_ms,
            ApmPolicy.MetricType.LATENCY_AVG: point.avg_ms,
            ApmPolicy.MetricType.LATENCY_MAX: point.max_ms,
            ApmPolicy.MetricType.THROUGHPUT: point.request_rate,
            ApmPolicy.MetricType.NO_TRAFFIC: point.request_rate,
        }[metric_type]
