from __future__ import annotations

import ast
from typing import Any


def _display_asset_id(instance_id: str) -> str:
    try:
        parsed = ast.literal_eval(instance_id)
    except (SyntaxError, ValueError):
        return instance_id.strip("'()")
    if isinstance(parsed, tuple) and parsed:
        return str(parsed[0])
    return str(parsed)


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
        for asset in assets:
            instance_id = str(asset["instance_id"])
            display_instance = _display_asset_id(instance_id)
            template_name = template.get("name") or template.get("metric_name") or ""
            policy_name = "-".join(part for part in [name_prefix, template_name, display_instance] if part)
            payloads.append(
                {
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
                    "algorithm": template.get("algorithm") or "avg",
                    "group_by": group_by,
                    "threshold": template.get("threshold") or [],
                    "recovery_condition": config.get("recovery_condition", 5),
                    "metric_unit": template.get("metric_unit") or "",
                    "calculation_unit": template.get("calculation_unit") or template.get("metric_unit") or "",
                    "no_data_period": config.get("no_data_period") or {},
                    "no_data_recovery_period": config.get("no_data_recovery_period") or {},
                    "no_data_level": config.get("no_data_level") or "",
                    "no_data_alert_name": config.get("no_data_alert_name") or "",
                    "notice": bool(config.get("notice", False)),
                    "notice_type": config.get("notice_type") or "",
                    "notice_type_ids": config.get("notice_type_ids") or [],
                    "notice_users": config.get("notice_users") or [],
                    "enable": bool(config.get("enable", True)),
                    "enable_alerts": config.get("enable_alerts") or ["threshold"],
                }
            )

    return payloads
