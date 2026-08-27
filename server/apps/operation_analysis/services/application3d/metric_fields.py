from __future__ import annotations

from typing import Any

from apps.monitor.models import Metric


def _query_condition(policy: Any) -> dict[str, Any]:
    raw = getattr(policy, "query_condition", None)
    return raw if isinstance(raw, dict) else {}


def resolve_policy_metric_id(policy: Any) -> str | None:
    """Metric definition id from MonitorPolicy.query_condition (not metric_instance_id)."""
    condition = _query_condition(policy)
    if condition.get("type") != "metric":
        return None
    metric_id = condition.get("metric_id")
    if metric_id is None or metric_id == "":
        return None
    return str(metric_id)


def resolve_policy_metric_display_name(
    policy: Any,
    *,
    metrics_by_id: dict[int, Metric] | None = None,
) -> str | None:
    """
    Resolve the user-facing metric label the same way Monitor Alert Detail does.

    - type=metric → Metric.display_name (fallback Metric.name)
    - type=formula → query_condition.result_name
    - otherwise → None

    Never uses MonitorPolicy.alert_name (that field is the alert title template).
    """
    condition = _query_condition(policy)
    query_type = condition.get("type")
    if query_type == "formula":
        result_name = str(condition.get("result_name") or "").strip()
        return result_name or None
    if query_type != "metric":
        return None

    metric_id = condition.get("metric_id")
    try:
        numeric_id = int(metric_id)
    except (TypeError, ValueError):
        return None

    metric = None
    if metrics_by_id is not None:
        metric = metrics_by_id.get(numeric_id)
    else:
        metric = Metric.objects.filter(id=numeric_id).only("id", "display_name", "name").first()
    if metric is None:
        return None
    return (metric.display_name or metric.name or "").strip() or None


def present_alarm_metric_fields(
    alert: Any,
    policy: Any,
    *,
    unit: str | None,
    metrics_by_id: dict[int, Metric] | None = None,
) -> dict[str, str | None]:
    value = getattr(alert, "value", None)
    return {
        "id": resolve_policy_metric_id(policy),
        "name": resolve_policy_metric_display_name(policy, metrics_by_id=metrics_by_id),
        "value": None if value is None else str(value),
        "unit": unit or None,
    }


def load_metrics_by_ids(metric_ids: set[int]) -> dict[int, Metric]:
    if not metric_ids:
        return {}
    return {metric.id: metric for metric in Metric.objects.filter(id__in=metric_ids).only("id", "display_name", "name")}


def collect_policy_metric_ids(policies: list[Any]) -> set[int]:
    ids: set[int] = set()
    for policy in policies:
        if policy is None:
            continue
        raw = resolve_policy_metric_id(policy)
        if raw is None:
            continue
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    return ids
