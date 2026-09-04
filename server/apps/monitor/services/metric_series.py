"""Generic authorized metric series helpers for ops-analysis charts.

NATS adapters stay thin: permission and instance visibility live in the handler.
Folding, protocol labels, conversation names, and chart shapes stay here so they
can be unit-tested without Django or VictoriaMetrics.
"""

from __future__ import annotations

import math
import re
from typing import Any, Callable, Iterable

from apps.monitor.services.host_resource_top import host_display_name
from apps.monitor.utils.vm_query_batch import run_unique_vm_queries

DEFAULT_OBJECT_NAMES = ("Switch", "Router", "Firewall", "Loadbalance")
SUPPORTED_MODES = frozenset({"range", "instant"})
SUPPORTED_COLLECT_TYPES = frozenset({"netflow", "sflow"})
DEFAULT_LIMIT = 10
MAX_LIMIT = 100
MAX_INSTANCE_IDS = 200
DEFAULT_RANGE_STEP = "5m"

_LIMITING_PREFIX = re.compile(r"^(topk|bottomk|limitk)\s*\(\s*\d+\s*,", re.IGNORECASE)

PROTOCOL_SHORT_NAMES = {
    "0": "HOPOPT",
    "1": "ICMP",
    "2": "IGMP",
    "4": "IPv4",
    "6": "TCP",
    "8": "EGP",
    "17": "UDP",
    "27": "RDP",
    "41": "IPv6",
    "47": "GRE",
    "50": "ESP",
    "51": "AH",
    "58": "ICMPv6",
    "88": "EIGRP",
    "89": "OSPF",
    "103": "PIM",
    "115": "L2TP",
    "118": "STP",
    "132": "SCTP",
    "136": "UDPLite",
}

_SRC_KEYS = ("src", "src_ip")
_DST_KEYS = ("dst", "dst_ip")
_PROTOCOL_KEYS = ("protocol", "header_protocol")
_DIMENSION_ALIASES = {
    "src_ip": "src",
    "dst_ip": "dst",
    "header_protocol": "protocol",
}


def validate_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized not in SUPPORTED_MODES:
        raise ValueError("mode 仅支持 range、instant")
    return normalized


def validate_collect_type(value) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    if normalized not in SUPPORTED_COLLECT_TYPES:
        raise ValueError("collect_type 仅支持 netflow、sflow")
    return normalized


def validate_metric_name(value) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError("metric 不能为空")
    return name


def validate_instance_id_count(instance_ids: list[str]) -> None:
    if len(instance_ids) > MAX_INSTANCE_IDS:
        raise ValueError("instance_ids 最多 200 个")


def validate_limit(value) -> int:
    if value in (None, ""):
        return DEFAULT_LIMIT
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit 必须是 1-100 的整数") from exc
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError("limit 必须是 1-100 的整数")
    return limit


def unwrap_limiting_query(query: str) -> str:
    text = str(query or "").strip()
    match = _LIMITING_PREFIX.match(text)
    if not match:
        return text
    start = text.find("(", match.start())
    depth = 0
    for index, char in enumerate(text[start:], start):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[match.end() : index].strip()
    return text


def window_selector(start_ts: float, end_ts: float) -> str:
    duration = max(1, int(end_ts - start_ts))
    return f"{duration}s"


def wrap_avg_over_time(query: str, window: str) -> str:
    return f"avg_over_time(({query})[{window}])"


def format_protocol_short_name(value) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return "--"
    mapped = PROTOCOL_SHORT_NAMES.get(normalized)
    if mapped:
        return mapped
    upper = normalized.upper()
    if re.fullmatch(r"[A-Z][A-Z0-9-]*", upper) and not normalized.isdigit():
        return upper
    if normalized.isdigit():
        return f"Proto-{normalized}"
    return upper


def _first_label(labels: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = labels.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def conversation_display_name(labels: dict[str, Any]) -> str:
    src = _first_label(labels, _SRC_KEYS)
    dst = _first_label(labels, _DST_KEYS)
    port = str(labels.get("dst_port") or "").strip()
    if not src or not dst:
        return ""
    if port and port != "0":
        return f"{src} → {dst}:{port}"
    return f"{src} → {dst}"


def endpoint_display_name(labels: dict[str, Any], *, ip_keys: tuple[str, ...], port_key: str) -> str:
    ip = _first_label(labels, ip_keys)
    port = str(labels.get(port_key) or "").strip()
    if not ip:
        return ""
    if port and port != "0":
        return f"{ip}:{port}"
    return ip


def instance_matches_protocol(instance: Any, protocol: str | None) -> bool:
    enabled = list(getattr(instance, "enabled_protocols", None) or [])
    if not enabled:
        return False
    if protocol is None:
        return True
    return protocol in enabled


def build_monitor_instance_rows(instances: Iterable[Any], *, protocol: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for instance in instances:
        if not instance_matches_protocol(instance, protocol):
            continue
        instance_id = str(getattr(instance, "id", "") or "")
        if not instance_id:
            continue
        ip = str(getattr(instance, "ip", "") or "")
        monitor_object = getattr(instance, "monitor_object", None)
        object_name = str(getattr(monitor_object, "name", "") or "")
        enabled = [str(item) for item in (getattr(instance, "enabled_protocols", None) or [])]
        rows.append(
            {
                "instance_id": instance_id,
                "display_name": host_display_name(
                    {
                        "host_name": getattr(instance, "name", "") or "",
                        "ip": ip,
                    },
                    instance_id,
                ),
                "ip": ip,
                "object_name": object_name,
                "enabled_protocols": enabled,
            }
        )
    rows.sort(key=lambda item: (item["display_name"], item["instance_id"]))
    return rows


def dimension_names(raw_dimensions) -> list[str]:
    names = []
    for item in raw_dimensions or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(item or "").strip()
        if name and name != "instance_id" and name not in names:
            names.append(name)
    return names


def canonical_dimension_names(raw_dimensions) -> list[str]:
    names = []
    for name in dimension_names(raw_dimensions):
        canonical = _DIMENSION_ALIASES.get(name, name)
        if canonical not in names:
            names.append(canonical)
    return names


class MetricSeriesQueryError(RuntimeError):
    """VictoriaMetrics 查询失败，不含 PromQL。"""


class MetricSeriesQueryService:
    def __init__(self, *, vm_api, build_label_query: Callable[..., str]):
        self.vm_api = vm_api
        self.build_label_query = build_label_query

    def run(
        self,
        *,
        mode: str,
        items: list[dict[str, Any]],
        start_ts: float,
        end_ts: float,
        step: str,
        limit: int,
    ):
        if not items:
            return [] if mode == "instant" else {}

        queries = []
        dimensions: list[str] = []
        for item in items:
            labeled = self.build_label_query(
                unwrap_limiting_query(item["query"]),
                instance_ids=item.get("instance_ids") or [],
                instance_id_keys=item.get("instance_id_keys") or ["instance_id"],
            )
            if mode == "instant":
                labeled = wrap_avg_over_time(labeled, window_selector(start_ts, end_ts))
            queries.append(labeled)
            for name in item.get("dimensions") or []:
                if name not in dimensions:
                    dimensions.append(name)

        if mode == "instant":
            results, errors = run_unique_vm_queries(
                queries,
                lambda query: self.vm_api.query(query, step=step, time=str(int(end_ts))),
            )
        else:
            results, errors = run_unique_vm_queries(
                queries,
                lambda query: self.vm_api.query_range(
                    query,
                    str(int(start_ts)),
                    str(int(end_ts)),
                    step,
                ),
            )
        if errors:
            raise MetricSeriesQueryError("指标查询失败")

        series = []
        for resp in results.values():
            if not isinstance(resp, dict) or resp.get("status") != "success":
                raise MetricSeriesQueryError("指标查询失败")
            series.extend((resp.get("data") or {}).get("result") or [])

        if mode == "instant":
            return fold_instant_rows(series, dimensions, limit)
        return fold_range_series(series, dimensions)


def _as_finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _series_value(item: dict[str, Any]) -> float | None:
    if "value" in item and isinstance(item.get("value"), (list, tuple)) and len(item["value"]) >= 2:
        return _as_finite_number(item["value"][1])
    values = item.get("values") or []
    if values:
        last = values[-1]
        if isinstance(last, (list, tuple)) and len(last) >= 2:
            return _as_finite_number(last[1])
    return None


def _normalize_labels(labels: dict[str, Any], dimensions: list[str]) -> dict[str, str]:
    normalized = {}
    for name in dimensions:
        raw = labels.get(name)
        if raw in (None, "") and name == "protocol":
            raw = labels.get("header_protocol")
        if raw in (None, "") and name == "src":
            raw = labels.get("src_ip")
        if raw in (None, "") and name == "dst":
            raw = labels.get("dst_ip")
        text = "" if raw in (None, "") else str(raw).strip()
        if name in _PROTOCOL_KEYS or name == "protocol":
            text = format_protocol_short_name(text)
        normalized[name] = text
    return normalized


def _row_name(labels: dict[str, str], dimensions: list[str]) -> str:
    if not dimensions:
        return "total"
    dimset = set(dimensions)
    if {"src", "dst"}.issubset(dimset) or {"src_ip", "dst_ip"}.issubset(dimset):
        display = conversation_display_name(labels)
        if display:
            return display
    if dimset in ({"src", "src_port"}, {"src_ip", "src_port"}):
        display = endpoint_display_name(labels, ip_keys=_SRC_KEYS, port_key="src_port")
        if display:
            return display
    if dimset in ({"dst", "dst_port"}, {"dst_ip", "dst_port"}):
        display = endpoint_display_name(labels, ip_keys=_DST_KEYS, port_key="dst_port")
        if display:
            return display
    if dimensions == ["protocol"] or dimensions == ["header_protocol"]:
        return labels.get("protocol") or labels.get("header_protocol") or "--"
    parts = [labels[name] for name in dimensions if labels.get(name)]
    return " / ".join(parts) if parts else "--"


def fold_instant_rows(series: list[dict[str, Any]], dimensions: list[str], limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for item in series:
        labels = _normalize_labels(item.get("metric") or {}, dimensions)
        value = _series_value(item)
        if value is None:
            continue
        key = tuple(labels.get(name, "") for name in dimensions)
        current = grouped.get(key)
        if current is None:
            grouped[key] = {"labels": labels, "value": value}
        else:
            current["value"] += value

    ranked = sorted(grouped.values(), key=lambda item: (-float(item["value"]), item["labels"]))
    rows = []
    for rank, item in enumerate(ranked[:limit], 1):
        row = dict(item["labels"])
        row["rank"] = rank
        row["name"] = _row_name(item["labels"], dimensions)
        row["value"] = float(item["value"])
        rows.append(row)
    return rows


def fold_range_series(series: list[dict[str, Any]], dimensions: list[str]) -> dict[str, list[list[float]]]:
    grouped: dict[str, dict[float, float]] = {}
    for item in series:
        labels = _normalize_labels(item.get("metric") or {}, dimensions)
        name = _row_name(labels, dimensions)
        points = grouped.setdefault(name, {})
        for pair in item.get("values") or []:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            ts = _as_finite_number(pair[0])
            value = _as_finite_number(pair[1])
            if ts is None or value is None:
                continue
            points[ts] = points.get(ts, 0.0) + value
    return {name: [[ts, points[ts]] for ts in sorted(points)] for name, points in grouped.items()}
