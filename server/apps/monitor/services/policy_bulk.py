from __future__ import annotations

from collections import Counter
from typing import Any

from apps.monitor.tasks.utils.policy_methods import LEGACY_ALGORITHM_MAPPING, POLICY_ALGORITHMS
from apps.monitor.utils.unit_converter import UnitConverter

LEGACY_METRIC_UNIT_MAPPING = {
    "%": "percent",
}


def normalize_template_algorithms(template: dict[str, Any]) -> tuple[str, str]:
    group_algorithm = template.get("group_algorithm")
    algorithm = str(template.get("algorithm") or "avg_over_time").lower()
    if group_algorithm:
        return str(group_algorithm).lower(), algorithm
    if algorithm in POLICY_ALGORITHMS and algorithm not in LEGACY_ALGORITHM_MAPPING:
        return "avg", algorithm
    return LEGACY_ALGORITHM_MAPPING.get(algorithm, ("avg", "avg_over_time"))


def normalize_default_calculation_unit(metric_unit: str) -> str:
    normalized_unit = LEGACY_METRIC_UNIT_MAPPING.get(metric_unit, metric_unit)
    return normalized_unit if UnitConverter.is_known_unit(normalized_unit) else ""


def normalize_stored_metric_unit(metric_unit: str, data_type: str = "") -> str:
    """策略表 metric_unit 只存短单位名；Enum/JSON 枚举定义留在 Metric.unit。"""
    unit = (metric_unit or "").strip()
    if not unit or unit in ("none", "short"):
        return ""
    if data_type == "Enum" or unit.startswith("["):
        return ""
    if len(unit) > 50:
        return ""
    return unit


def _dimension_names(dimensions) -> list[str]:
    names = []
    if not isinstance(dimensions, list):
        return names
    for item in dimensions:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = ""
        if name and name not in names:
            names.append(name)
    return names


def resolve_bulk_group_by(template: dict[str, Any], config: dict[str, Any], monitor_object_id: int) -> list[str]:
    group_by = config.get("group_by") or template.get("group_by")
    if isinstance(group_by, list):
        cleaned = [str(item).strip() for item in group_by if str(item).strip()]
        if cleaned:
            return cleaned
    names = ["instance_id"]
    dimensions = template.get("dimensions") or []
    dimension_names = _dimension_names(dimensions)
    if not dimension_names:
        metric_name = str(template.get("metric_name") or "").strip()
        query = template.get("query_condition") or {}
        if isinstance(query, dict):
            metric_name = metric_name or str(query.get("metric_name") or "").strip()
        if metric_name:
            from apps.monitor.models.monitor_metrics import Metric

            metric = (
                Metric.objects.filter(monitor_object_id=monitor_object_id, name=metric_name)
                .only("dimensions")
                .first()
            )
            if metric:
                dimension_names = _dimension_names(metric.dimensions)
    for name in dimension_names:
        if name not in names:
            names.append(name)
    return names


def _merge_asset_organizations(assets: list[dict[str, Any]]) -> list[Any]:
    organizations: list[Any] = []
    seen = set()
    for asset in assets:
        for organization in asset.get("organizations") or []:
            if organization in seen:
                continue
            seen.add(organization)
            organizations.append(organization)
    return organizations


def _template_source_id(template: dict[str, Any]) -> int | None:
    """批量下发时记录来源模板；无有效 id 时不写 FK。"""
    raw_id = template.get("id")
    try:
        template_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    return template_id if template_id > 0 else None


def _template_metric_name(template: dict[str, Any]) -> str:
    """与前端 getTemplateMetricName 对齐：优先顶层 metric_name，再回落到 query_condition。"""
    metric = str(template.get("metric_name") or "").strip()
    if metric:
        return metric
    query = template.get("query_condition") or {}
    if isinstance(query, dict):
        return str(query.get("metric_name") or "").strip()
    return ""


def build_distinct_policy_names(
    templates: list[dict[str, Any]],
    name_prefix: str = "",
) -> list[str]:
    prefix = (name_prefix or "").strip()
    bases: list[str] = []
    metrics: list[str] = []
    template_names: list[str] = []
    for template in templates:
        metric = _template_metric_name(template)
        template_name = str(template.get("name") or metric or "").strip()
        base = "-".join(part for part in [prefix, template_name] if part) or metric or "策略"
        bases.append(base)
        metrics.append(metric)
        template_names.append(template_name)

    base_counts = Counter(bases)
    used: set[str] = set()
    names: list[str] = []
    for index, base in enumerate(bases):
        name = base
        metric = metrics[index]
        if base_counts[base] > 1 and metric and metric != template_names[index]:
            name = f"{name}-{metric}"
        candidate = name
        suffix = 2
        while candidate in used:
            candidate = f"{name}-{suffix}"
            suffix += 1
        used.add(candidate)
        names.append(candidate)
    return names


def build_bulk_policy_payloads(
    *,
    monitor_object_id: int,
    templates: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    name_prefix = (config.get("name_prefix") or "").strip()
    instance_ids = [str(asset["instance_id"]) for asset in assets]
    organizations = _merge_asset_organizations(assets)
    policy_names = build_distinct_policy_names(templates, name_prefix)
    for template, policy_name in zip(templates, policy_names):
        group_algorithm, algorithm = normalize_template_algorithms(template)
        metric_unit = normalize_stored_metric_unit(
            template.get("metric_unit") or "",
            str(template.get("data_type") or ""),
        )
        default_calculation_unit = normalize_default_calculation_unit(metric_unit)
        group_by = resolve_bulk_group_by(template, config, monitor_object_id)
        template_name = template.get("name") or template.get("metric_name") or ""
        enable_alerts = config.get("enable_alerts") or ["threshold"]
        payload = {
            "name": policy_name,
            "alert_name": template.get("alert_name") or template_name,
            "monitor_object": monitor_object_id,
            "organizations": organizations,
            "collect_type": template.get("collect_type"),
            "query_condition": template.get("query_condition")
            or {
                "type": "metric",
                "metric_id": template.get("metric_id"),
                "filter": template.get("filter") or [],
            },
            "source": {
                "type": "instance",
                "values": instance_ids,
            },
            "schedule": config.get("schedule") or template.get("schedule") or {},
            "period": config.get("period") or template.get("period") or {},
            "group_algorithm": group_algorithm,
            "algorithm": algorithm,
            "group_by": group_by,
            "threshold": template.get("threshold") or [],
            "trigger_count": config.get("trigger_count", template.get("trigger_count", 1)),
            "recovery_condition": config.get("recovery_condition", template.get("recovery_condition", 5)),
            "metric_unit": metric_unit,
            "calculation_unit": template.get("calculation_unit") or default_calculation_unit,
            "threshold_unit": (template.get("threshold_unit") or template.get("calculation_unit") or default_calculation_unit or ""),
            "notice": bool(config.get("notice", False)),
            "notice_type_ids": config.get("notice_type_ids") or [],
            "notice_users": config.get("notice_users") or [],
            "enable": bool(config.get("enable", True)),
            "enable_alerts": enable_alerts,
            "compare_mode": template.get("compare_mode") or "absolute",
            "compare_value_kind": template.get("compare_value_kind") or "",
            "compare_offset_hours": template.get("compare_offset_hours"),
            "compare_offset_days": template.get("compare_offset_days"),
            "compare_baseline_weeks": template.get("compare_baseline_weeks"),
            "count_predicate": template.get("count_predicate") or {},
            "forecast_target": template.get("forecast_target"),
            "forecast_target_unit": template.get("forecast_target_unit") or "",
            "forecast_lookback": template.get("forecast_lookback") or {},
            "recovery_threshold": template.get("recovery_threshold") or {},
        }
        template_id = _template_source_id(template)
        if template_id is not None:
            payload["source_template"] = template_id
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
