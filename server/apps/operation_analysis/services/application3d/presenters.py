from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone

from apps.cmdb.services.application_resource_overview import ApplicationResourceOverviewService
from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.services.application3d.constants import PROPERTY_ALLOWLIST
from apps.operation_analysis.services.application3d.metric_fields import resolve_policy_metric_display_name
from apps.operation_analysis.services.application3d.severity import severity_from_monitor_level

_SENSITIVE_ATTR_TYPES = {"password", "secret"}


def present_application_properties(
    instance: dict[str, Any],
    attrs: list[dict[str, Any]],
    *,
    visible_fields: set[str] | None,
) -> list[dict[str, str]]:
    attr_map = {str(attr.get("attr_id")): attr for attr in attrs if attr.get("attr_id")}
    properties: list[dict[str, str]] = []
    for key in PROPERTY_ALLOWLIST:
        if visible_fields is not None and key not in visible_fields:
            continue
        attr = attr_map.get(key)
        raw_value = instance.get(key)
        if not attr or raw_value in (None, "", [], {}):
            continue
        attr_type = str(attr.get("attr_type") or "").lower()
        if attr_type in _SENSITIVE_ATTR_TYPES or any(token in key.lower() for token in ("password", "secret", "token")):
            continue
        display_instance = dict(instance)
        try:
            display_value = ApplicationResourceOverviewService._get_display_value(display_instance, key, attr_map)
        except (KeyError, TypeError, ValueError):
            continue
        except Exception:
            logger.exception("application3D property display conversion failed for field %s", key)
            continue
        if display_value in (None, ""):
            continue
        properties.append(
            {
                "key": key,
                "label": str(attr.get("attr_name") or key),
                "displayValue": str(display_value),
            }
        )
    return properties


def iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def alert_duration_seconds(alert: Any) -> int:
    started = getattr(alert, "start_event_time", None)
    if not started:
        return 0
    ended = getattr(alert, "end_event_time", None) or timezone.now()
    return max(0, int((ended - started).total_seconds()))


def present_alarm_list_item(
    alert: Any,
    *,
    host: dict[str, Any],
    policy: Any,
    metrics_by_id: dict | None = None,
) -> dict[str, Any]:
    is_no_data = str(getattr(alert, "alert_type", "")).lower() == "no_data"
    alert_type = "no_data" if is_no_data else "alert"
    return {
        "id": str(alert.id),
        "content": alert.content or "",
        "severity": severity_from_monitor_level(alert.level),
        "alertType": alert_type,
        "isNoData": is_no_data,
        "occurredAt": iso_datetime(alert.start_event_time),
        "resource": {
            "id": str(host.get("inst_uuid") or ""),
            "name": str(host.get("inst_name") or host.get("inst_uuid") or ""),
        },
        "metricName": resolve_policy_metric_display_name(policy, metrics_by_id=metrics_by_id),
        "durationSeconds": alert_duration_seconds(alert),
        "policyName": getattr(policy, "name", "") or "",
    }
