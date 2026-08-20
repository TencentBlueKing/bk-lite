# -*- coding: utf-8 -*-
"""Batch latest IF-MIB interface metrics for network status topology links."""

from __future__ import annotations

import re
from typing import Any

from apps.core.logger import monitor_logger as logger
from apps.monitor.utils.dimension import parse_instance_id

MAX_INTERFACE_METRIC_INSTANCE_IDS = 200

# (metric key, PromQL template with {selector}, is_rate_counter)
INTERFACE_METRIC_QUERIES: tuple[tuple[str, str, bool], ...] = (
    ("interface_ifOperStatus", "interface_ifOperStatus{{{selector}}}", False),
    ("interface_ifHighSpeed", "interface_ifHighSpeed{{{selector}}}", False),
    ("interface_ifSpeed", "interface_ifSpeed{{{selector}}}", False),
    ("interface_ifHCInOctets", "rate(interface_ifHCInOctets{{{selector}}}[5m])", True),
    ("interface_ifHCOutOctets", "rate(interface_ifHCOutOctets{{{selector}}}[5m])", True),
    ("interface_ifInOctets", "rate(interface_ifInOctets{{{selector}}}[5m])", True),
    ("interface_ifOutOctets", "rate(interface_ifOutOctets{{{selector}}}[5m])", True),
    ("interface_ifInErrors", "rate(interface_ifInErrors{{{selector}}}[5m])", True),
    ("interface_ifOutErrors", "rate(interface_ifOutErrors{{{selector}}}[5m])", True),
    ("interface_ifInDiscards", "rate(interface_ifInDiscards{{{selector}}}[5m])", True),
    ("interface_ifOutDiscards", "rate(interface_ifOutDiscards{{{selector}}}[5m])", True),
)


class InterfaceMetricsQueryError(ValueError):
    """Caller-facing validation error for the interface metrics NATS."""


def normalize_instance_ids(raw: Any) -> list[str]:
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        values = [part.strip() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, (list, tuple)):
        values = [str(item).strip() for item in raw if str(item).strip()]
    else:
        raise InterfaceMetricsQueryError("instance_ids 必须是字符串或数组")

    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    if len(unique) > MAX_INTERFACE_METRIC_INSTANCE_IDS:
        raise InterfaceMetricsQueryError(f"instance_ids 不能超过 {MAX_INTERFACE_METRIC_INSTANCE_IDS}")
    return unique


def vm_instance_id_labels(instance_ids: list[str]) -> list[str]:
    """Map stored monitor instance IDs to VictoriaMetrics instance_id labels."""
    labels: list[str] = []
    seen: set[str] = set()
    for instance_id in instance_ids:
        parsed = parse_instance_id(instance_id)
        if not parsed:
            continue
        label = str(parsed[0] or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


def map_vm_instance_id(vm_instance_id: str, instance_ids: list[str]) -> str | None:
    """Map a VM label back to the first requested monitor instance id."""
    vm_id = str(vm_instance_id or "").strip()
    if not vm_id:
        return None
    if vm_id in instance_ids:
        return vm_id
    for instance_id in instance_ids:
        parsed = parse_instance_id(instance_id)
        if parsed and str(parsed[0] or "").strip() == vm_id:
            return instance_id
    return None


def build_instance_id_selector(instance_ids: list[str]) -> str:
    escaped = "|".join(re.escape(item) for item in instance_ids)
    escaped = escaped.replace("\\", "\\\\").replace('"', '\\"')
    return f'instance_id=~"^(?:{escaped})$"'


def parse_instant_vector(payload: Any, metric_name: str) -> list[dict[str, Any]]:
    result = []
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return result
    data = payload.get("data") or {}
    series = data.get("result") or []
    if not isinstance(series, list):
        return result
    for item in series:
        if not isinstance(item, dict):
            continue
        labels = item.get("metric") or {}
        if not isinstance(labels, dict):
            continue
        instance_id = str(labels.get("instance_id") or "").strip()
        if_descr = str(labels.get("ifDescr") or "").strip()
        if not instance_id or not if_descr:
            continue
        value_pair = item.get("value") or []
        if not isinstance(value_pair, (list, tuple)) or len(value_pair) < 2:
            continue
        try:
            numeric = float(value_pair[1])
        except (TypeError, ValueError):
            continue
        if numeric != numeric:  # NaN
            continue
        result.append(
            {
                "instance_id": instance_id,
                "ifDescr": if_descr,
                "metric": metric_name,
                "value": numeric,
            }
        )
    return result


def merge_interface_metric_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["instance_id"], row["ifDescr"])
        item = grouped.setdefault(
            key,
            {"instance_id": row["instance_id"], "ifDescr": row["ifDescr"], "metrics": {}},
        )
        item["metrics"][row["metric"]] = row["value"]
    return list(grouped.values())


def query_interface_metric_items(vm_api, instance_ids: list[str]) -> list[dict[str, Any]]:
    if not instance_ids:
        return []
    labels = vm_instance_id_labels(instance_ids)
    if not labels:
        return []
    selector = build_instance_id_selector(labels)
    rows: list[dict[str, Any]] = []
    for metric_name, template, _is_rate in INTERFACE_METRIC_QUERIES:
        query = template.format(selector=selector)
        try:
            payload = vm_api.query(query, step="5m")
        except Exception:
            logger.exception("interface metric query failed metric=%s", metric_name)
            raise
        for row in parse_instant_vector(payload, metric_name):
            requested_id = map_vm_instance_id(row["instance_id"], instance_ids)
            if not requested_id:
                continue
            rows.append({**row, "instance_id": requested_id})
    return merge_interface_metric_rows(rows)
