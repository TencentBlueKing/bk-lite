from __future__ import annotations

from django.db import transaction

from apps.apm.models import ApmAlert, ApmAlertMetricSnapshot, ApmEvent, ApmPolicy
from apps.apm.services.contracts import MetricDataState, PolicyQueryResult

MAX_ALERT_METRIC_SNAPSHOTS = 1440


def _metric_unit(metric_type: str) -> str:
    if metric_type in ApmPolicy.RATIO_METRIC_TYPES:
        return "ratio"
    if metric_type in ApmPolicy.COUNT_METRIC_TYPES:
        return "count"
    if metric_type in ApmPolicy.LATENCY_METRIC_TYPES:
        return "ms"
    return {
        ApmPolicy.MetricType.THROUGHPUT: "req/s",
        ApmPolicy.MetricType.NO_TRAFFIC: "req/s",
    }[metric_type]


def resolve_result_unit(policy: ApmPolicy) -> str:
    """percent 用结果单位；delta 与 absolute 沿用指标单位。"""
    if (
        getattr(policy, "compare_mode", ApmPolicy.CompareMode.ABSOLUTE) != ApmPolicy.CompareMode.ABSOLUTE
        and getattr(policy, "compare_value_kind", "") == ApmPolicy.CompareValueKind.PERCENT
    ):
        return "percent"
    return _metric_unit(policy.metric_type)


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
                    "unit": resolve_result_unit(policy),
                    "aggregation": policy.aggregation,
                    "evaluation_interval": policy.evaluation_interval,
                    "metric_window": policy.metric_window,
                    "snapshots": [],
                },
            )
            if not created:
                snapshot = ApmAlertMetricSnapshot.objects.select_for_update().get(pk=snapshot.pk)

            snapshot_time = (result.window_ended_at or result.evaluated_at).isoformat()
            if any(item.get("snapshot_time") == snapshot_time for item in snapshot.snapshots):
                return snapshot

            snapshot_type = "no_data" if result.data_state == MetricDataState.NO_DATA else "event" if event is not None else "info"
            snapshot.snapshots.append(
                {
                    "type": snapshot_type,
                    "snapshot_time": snapshot_time,
                    "event_id": event.event_id if event is not None else None,
                    "event_time": event.occurred_at.isoformat() if event is not None else None,
                    "value": str(result.value) if result.value is not None else None,
                    "current_value": str(result.current_value) if result.current_value is not None else None,
                    "baseline_value": str(result.baseline_value) if result.baseline_value is not None else None,
                    "result_unit": resolve_result_unit(policy),
                    "threshold": threshold,
                    "data_state": str(result.data_state),
                }
            )
            if len(snapshot.snapshots) > MAX_ALERT_METRIC_SNAPSHOTS:
                snapshot.snapshots = snapshot.snapshots[-MAX_ALERT_METRIC_SNAPSHOTS:]
            snapshot.save(update_fields=("snapshots", "updated_at"))
            return snapshot

    @staticmethod
    def serialize(snapshot: ApmAlertMetricSnapshot) -> dict:
        items = list(snapshot.snapshots or [])
        truncated = len(items) >= MAX_ALERT_METRIC_SNAPSHOTS
        if len(items) > MAX_ALERT_METRIC_SNAPSHOTS:
            items = items[-MAX_ALERT_METRIC_SNAPSHOTS:]
        return {
            "unit": snapshot.unit,
            "aggregation": snapshot.aggregation,
            "evaluation_interval": snapshot.evaluation_interval,
            "metric_window": snapshot.metric_window,
            "snapshots": items,
            "truncated": truncated,
        }
