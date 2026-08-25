from __future__ import annotations

from django.db import transaction

from apps.apm.models import ApmAlert, ApmAlertMetricSnapshot, ApmEvent, ApmPolicy
from apps.apm.services.contracts import MetricDataState, PolicyQueryResult


def _metric_unit(metric_type: str) -> str:
    return {
        ApmPolicy.MetricType.ERROR_RATE: "ratio",
        ApmPolicy.MetricType.P95: "ms",
        ApmPolicy.MetricType.P99: "ms",
        ApmPolicy.MetricType.THROUGHPUT: "req/s",
        ApmPolicy.MetricType.NO_TRAFFIC: "req/s",
    }[metric_type]


class ApmAlertMetricSnapshotStore:
    """按 Monitor 的 Alert 一对一模型追加策略扫描结果。"""

    @staticmethod
    def record(
        *,
        alert: ApmAlert,
        event: ApmEvent | None,
        policy: ApmPolicy,
        result: PolicyQueryResult,
        threshold: dict[str, str] | None,
    ) -> ApmAlertMetricSnapshot:
        with transaction.atomic():
            snapshot, created = ApmAlertMetricSnapshot.objects.get_or_create(
                alert=alert,
                defaults={
                    "unit": _metric_unit(policy.metric_type),
                    "aggregation": policy.aggregation,
                    "evaluation_interval": policy.evaluation_interval,
                    "metric_window": policy.metric_window,
                    "snapshots": [],
                },
            )
            if not created:
                snapshot = ApmAlertMetricSnapshot.objects.select_for_update().get(pk=snapshot.pk)

            snapshot_time = result.evaluated_at.isoformat()
            if any(item.get("snapshot_time") == snapshot_time for item in snapshot.snapshots):
                return snapshot

            snapshot_type = (
                "no_data"
                if result.data_state == MetricDataState.NO_DATA
                else "event"
                if event is not None
                else "info"
            )
            snapshot.snapshots.append(
                {
                    "type": snapshot_type,
                    "snapshot_time": snapshot_time,
                    "event_id": event.event_id if event is not None else None,
                    "event_time": event.occurred_at.isoformat() if event is not None else None,
                    "value": str(result.value) if result.value is not None else None,
                    "threshold": threshold,
                    "data_state": str(result.data_state),
                }
            )
            snapshot.save(update_fields=("snapshots", "updated_at"))
            return snapshot

    @staticmethod
    def serialize(snapshot: ApmAlertMetricSnapshot) -> dict:
        return {
            "unit": snapshot.unit,
            "aggregation": snapshot.aggregation,
            "evaluation_interval": snapshot.evaluation_interval,
            "metric_window": snapshot.metric_window,
            "snapshots": list(snapshot.snapshots or []),
        }
