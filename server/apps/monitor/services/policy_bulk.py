from __future__ import annotations

import ast
from typing import Any

from apps.monitor.utils.unit_converter import UnitConverter

LEGACY_ALGORITHM_MAPPING = {
    "avg": ("avg", "avg_over_time"),
    "avg_over_time": ("avg", "avg_over_time"),
    "max": ("max", "max_over_time"),
    "max_over_time": ("max", "max_over_time"),
    "min": ("min", "min_over_time"),
    "min_over_time": ("min", "min_over_time"),
    "sum": ("sum", "sum_over_time"),
    "sum_over_time": ("sum", "sum_over_time"),
    "count": ("count", "last_over_time"),
    "count_over_time": ("count", "count_over_time"),
    "last_over_time": ("avg", "last_over_time"),
}

LEGACY_METRIC_UNIT_MAPPING = {
    "%": "percent",
}


def _display_asset_id(instance_id: str) -> str:
    try:
        parsed = ast.literal_eval(instance_id)
    except (SyntaxError, ValueError):
        return instance_id.strip("'()")
    if isinstance(parsed, tuple) and parsed:
        return str(parsed[0])
    return str(parsed)


def normalize_template_algorithms(template: dict[str, Any]) -> tuple[str, str]:
    group_algorithm = template.get("group_algorithm")
    algorithm = template.get("algorithm") or "avg_over_time"
    if group_algorithm:
        return str(group_algorithm).lower(), str(algorithm).lower()
    return LEGACY_ALGORITHM_MAPPING.get(str(algorithm).lower(), ("avg", "avg_over_time"))


def normalize_default_calculation_unit(metric_unit: str) -> str:
    normalized_unit = LEGACY_METRIC_UNIT_MAPPING.get(metric_unit, metric_unit)
    return normalized_unit if UnitConverter.is_known_unit(normalized_unit) else ""


def build_bulk_policy_payloads(
    *,
    monitor_object_id: int,
    templates: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    name_prefix = (config.get("name_prefix") or "").strip()
    group_by = config.get("group_by") or ["instance_id"]

    for template in templates:
        group_algorithm, algorithm = normalize_template_algorithms(template)
        metric_unit = template.get("metric_unit") or ""
        default_calculation_unit = normalize_default_calculation_unit(metric_unit)
        for asset in assets:
            instance_id = str(asset["instance_id"])
            display_instance = _display_asset_id(instance_id)
            template_name = template.get("name") or template.get("metric_name") or ""
            policy_name = "-".join(part for part in [name_prefix, template_name, display_instance] if part)
            enable_alerts = config.get("enable_alerts") or ["threshold"]
            payload = {
                "name": policy_name,
                "alert_name": template.get("alert_name") or template_name,
                "monitor_object": monitor_object_id,
                "organizations": asset.get("organizations") or [],
                "collect_type": template.get("collect_type"),
                "query_condition": {
                    "type": "metric",
                    "metric_id": template.get("metric_id"),
                    "filter": template.get("filter") or [],
                },
                "source": {
                    "type": "instance",
                    "values": [instance_id],
                },
                "schedule": config.get("schedule") or {},
                "period": config.get("period") or {},
                "group_algorithm": group_algorithm,
                "algorithm": algorithm,
                "group_by": group_by,
                "threshold": template.get("threshold") or [],
                "trigger_count": config.get("trigger_count", template.get("trigger_count", 1)),
                "recovery_condition": config.get("recovery_condition", 5),
                "metric_unit": metric_unit,
                "calculation_unit": template.get("calculation_unit") or default_calculation_unit,
                "threshold_unit": (template.get("threshold_unit") or template.get("calculation_unit") or default_calculation_unit or ""),
                "notice": bool(config.get("notice", False)),
                "notice_type_ids": config.get("notice_type_ids") or [],
                "notice_users": config.get("notice_users") or [],
                "enable": bool(config.get("enable", True)),
                "enable_alerts": enable_alerts,
            }
            if config.get("notice_type"):
                payload["notice_type"] = config["notice_type"]
            if "no_data" in enable_alerts:
                payload["no_data_period"] = config.get("no_data_period") or {}
                payload["no_data_recovery_period"] = config.get("no_data_recovery_period") or {}
                if config.get("no_data_level"):
                    payload["no_data_level"] = config["no_data_level"]
                if config.get("no_data_alert_name"):
                    payload["no_data_alert_name"] = config["no_data_alert_name"]
            payloads.append(payload)

    return payloads
