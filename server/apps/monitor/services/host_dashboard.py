"""Host dashboard query helpers for ops-analysis charts.

NATS adapters stay thin: permission and instance visibility live in the handler,
while folding, ranking-adjacent snapshot math, and series shaping stay here so
they can be unit-tested without Django.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from apps.core.utils.time_util import parse_rfc3339_range_utc, rfc3339_to_timestamp
from apps.monitor.services.host_metric_queries import (
    cpu_usage_query,
    disk_used_percent_query,
    disk_read_latency_query,
    disk_write_latency_query,
    diskio_io_util_query,
    diskio_read_bytes_query,
    diskio_write_bytes_query,
    load5_query,
    mem_used_percent_query,
    net_bytes_recv_query,
    net_bytes_sent_query,
    processes_blocked_query,
    processes_zombies_query,
)
from apps.monitor.services.host_resource_top import (
    DEFAULT_INTERVAL_SECONDS,
    HostCandidate,
    HostResourceTopService,
    host_display_name,
    normalize_metric_candidates,
)
from apps.monitor.utils.alert_name_variables import resolve_resource_ip
from apps.monitor.utils.dimension import parse_instance_id

HOST_OBJECT_NAME = "Host"
DEFAULT_RANGE_STEP = "5m"

DENIED_MONITOR_INSTANCE_MESSAGE = "没有权限访问指定的实例"
CMDB_LOCATOR_USED_AS_MONITOR_INSTANCE_MESSAGE = (
    "这些 instance_ids 是 CMDB 实例标识（inst_uuid 或数字 inst_id），不能直接查询监控。"
    "请改用 CMDB 实例的 monitor_id，或调用 cmdb_get_monitor_ids；"
    "未联动则用 monitor_list_object_instances 按主机名或 IP 获取监控 instance_id。"
)
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CMDB_NUMERIC_INST_ID_RE = re.compile(r"^[1-9]\d{9,15}$")

RANGE_METRIC_FOLD_SUM = "sum"
RANGE_METRIC_FOLD_MAX = "max"
RANGE_METRIC_FOLD_IDENTITY = "identity"

SUPPORTED_RANGE_METRIC_TYPES = (
    "cpu",
    "memory",
    "disk",
    "load5",
    "net_in",
    "net_out",
    "disk_io",
    "disk_write_latency",
    "disk_read_latency",
    "disk_read_rate",
    "disk_write_rate",
    "processes_blocked",
    "processes_zombies",
)


RANGE_METRIC_SPECS: dict[str, dict[str, Any]] = {
    "cpu": {
        "query": cpu_usage_query(),
        "fold": RANGE_METRIC_FOLD_IDENTITY,
    },
    "memory": {
        "query": mem_used_percent_query(),
        "fold": RANGE_METRIC_FOLD_IDENTITY,
    },
    "disk": {
        "query": disk_used_percent_query(),
        "fold": RANGE_METRIC_FOLD_MAX,
    },
    "load5": {
        "query": load5_query(),
        "fold": RANGE_METRIC_FOLD_IDENTITY,
    },
    "net_in": {
        "query": net_bytes_recv_query(),
        "fold": RANGE_METRIC_FOLD_SUM,
    },
    "net_out": {
        "query": net_bytes_sent_query(),
        "fold": RANGE_METRIC_FOLD_SUM,
    },
    "disk_io": {
        "query": diskio_io_util_query(),
        "fold": RANGE_METRIC_FOLD_MAX,
    },
    "disk_write_latency": {
        "query": disk_write_latency_query(),
        "fold": RANGE_METRIC_FOLD_MAX,
    },
    "disk_read_latency": {
        "query": disk_read_latency_query(),
        "fold": RANGE_METRIC_FOLD_MAX,
    },
    "disk_read_rate": {
        "query": diskio_read_bytes_query(),
        "fold": RANGE_METRIC_FOLD_SUM,
    },
    "disk_write_rate": {
        "query": diskio_write_bytes_query(),
        "fold": RANGE_METRIC_FOLD_SUM,
    },
    "processes_blocked": {
        "query": processes_blocked_query(),
        "fold": RANGE_METRIC_FOLD_IDENTITY,
    },
    "processes_zombies": {
        "query": processes_zombies_query(),
        "fold": RANGE_METRIC_FOLD_IDENTITY,
    },
}


EMPTY_SNAPSHOT = {
    "host_count": 0,
    "avg_cpu": None,
    "avg_memory": None,
    "avg_disk": None,
    "max_cpu": None,
    "max_cpu_host": None,
    "max_memory": None,
    "max_memory_host": None,
}


def validate_range_metric_type(metric_type: str) -> str:
    normalized = str(metric_type or "").strip().lower()
    if normalized not in SUPPORTED_RANGE_METRIC_TYPES:
        raise ValueError("metric_type 不支持")
    return normalized


def build_host_instance_rows(instances: Iterable[Any]) -> list[dict[str, str]]:
    rows = []
    for instance in instances:
        instance_id = str(getattr(instance, "id", "") or "")
        if not instance_id:
            continue
        rows.append(
            {
                "instance_id": instance_id,
                "display_name": host_display_name(
                    {
                        "host_name": getattr(instance, "name", "") or "",
                        "ip": getattr(instance, "ip", "") or "",
                    },
                    instance_id,
                ),
            }
        )
    rows.sort(key=lambda item: (item["display_name"], item["instance_id"]))
    return rows


def _as_finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _series_instance_id(labels: dict[str, Any]) -> str:
    raw = labels.get("instance_id")
    if raw in (None, ""):
        return ""
    parsed = parse_instance_id(raw)
    return str(parsed[0]) if parsed else str(raw)


def fold_host_range_series(
    series: list[dict[str, Any]],
    host_meta: dict[str, dict[str, Any]],
    *,
    fold: str,
    transform: Callable[[float], float] | None = None,
) -> dict[str, list[list[float]]]:
    """Collapse sub-dimension series into one line per authorized host."""
    grouped: dict[str, dict[float, list[float]]] = {}
    for item in series:
        if not isinstance(item, dict):
            continue
        labels = item.get("metric") or {}
        instance_id = _series_instance_id(labels if isinstance(labels, dict) else {})
        if not instance_id or instance_id not in host_meta:
            continue
        values = item.get("values")
        if not isinstance(values, list):
            continue
        bucket = grouped.setdefault(instance_id, {})
        for point in values:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                timestamp = float(point[0])
            except (TypeError, ValueError):
                continue
            number = _as_finite_number(point[1])
            if number is None:
                continue
            if transform is not None:
                number = transform(number)
            bucket.setdefault(timestamp, []).append(number)

    result: dict[str, list[list[float]]] = {}
    used_names: dict[str, int] = {}
    for instance_id, points in grouped.items():
        folded: list[list[float]] = []
        for timestamp in sorted(points):
            samples = points[timestamp]
            if fold == RANGE_METRIC_FOLD_SUM:
                value = sum(samples)
            elif fold == RANGE_METRIC_FOLD_MAX:
                value = max(samples)
            else:
                value = samples[-1]
            folded.append([timestamp, round(value, 4)])
        if not folded:
            continue
        name = host_display_name(host_meta.get(instance_id, {}), instance_id)
        if name in used_names:
            used_names[name] += 1
            name = f"{name} ({instance_id})"
        else:
            used_names[name] = 1
        result[name] = folded
    return result


def build_host_meta(instances: Iterable[Any]) -> dict[str, dict[str, Any]]:
    host_meta: dict[str, dict[str, Any]] = {}
    for instance in instances:
        instance_id = str(getattr(instance, "id", "") or "")
        if not instance_id:
            continue
        key = str(parse_instance_id(instance_id)[0])
        meta = {
            "host_name": getattr(instance, "name", "") or "",
            "ip": getattr(instance, "ip", "") or "",
            "interval": getattr(instance, "interval", DEFAULT_INTERVAL_SECONDS),
            "storage_id": instance_id,
        }
        host_meta[key] = meta
        host_meta[instance_id] = meta
    return host_meta


def _alias_token(value: Any) -> str:
    return str(value or "").strip()


def _instance_identity(instance: Any, fallback: str = "") -> str:
    return str(getattr(instance, "id", "") or fallback)


def _add_instance_alias(aliases: dict[str, list[Any]], token: str, instance: Any) -> None:
    if not token:
        return
    bucket = aliases.setdefault(token, [])
    ident = _instance_identity(instance)
    if ident and any(_instance_identity(item) == ident for item in bucket):
        return
    bucket.append(instance)


def _alias_tokens_for_instance(storage_id: str, instance: Any) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()

    def collect(value: Any) -> None:
        token = _alias_token(value)
        if not token or token in seen:
            return
        seen.add(token)
        tokens.append(token)
        lowered = token.lower()
        if lowered not in seen:
            seen.add(lowered)
            tokens.append(lowered)

    collect(storage_id)
    parsed = parse_instance_id(storage_id)
    if parsed:
        collect(parsed[0])
    collect(getattr(instance, "id", ""))
    parsed_pk = parse_instance_id(getattr(instance, "id", ""))
    if parsed_pk:
        collect(parsed_pk[0])
    collect(getattr(instance, "name", ""))
    collect(getattr(instance, "ip", ""))
    collect(resolve_resource_ip(getattr(instance, "summary_facts", None), getattr(instance, "ip", None)))
    collect(getattr(instance, "cmdb_id", ""))
    return tokens


def looks_like_cmdb_instance_locator(token: Any) -> bool:
    text = str(token or "").strip()
    if not text:
        return False
    return bool(_UUID_RE.fullmatch(text) or _CMDB_NUMERIC_INST_ID_RE.fullmatch(text))


def unresolved_monitor_instance_message(unresolved: Iterable[Any]) -> str:
    tokens = [str(item).strip() for item in unresolved if item not in (None, "")]
    if tokens and all(looks_like_cmdb_instance_locator(item) for item in tokens):
        return CMDB_LOCATOR_USED_AS_MONITOR_INSTANCE_MESSAGE
    return DENIED_MONITOR_INSTANCE_MESSAGE


def _instance_id_aliases(authorized_instances: dict[str, Any]) -> dict[str, list[Any]]:
    aliases: dict[str, list[Any]] = {}
    for storage_id, instance in (authorized_instances or {}).items():
        for token in _alias_tokens_for_instance(str(storage_id), instance):
            _add_instance_alias(aliases, token, instance)
    return aliases


def resolve_instance_storage_ids(
    authorized_instances: dict[str, Any],
    instance_ids: Iterable[Any],
) -> tuple[list[str], list[str]]:
    """Map requested IDs/names/IPs to storage keys; leftover tokens are unauthorized/unknown."""
    aliases = _instance_id_aliases(authorized_instances)
    storage_ids: list[str] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    for item in instance_ids or []:
        key = _alias_token(item)
        matches = aliases.get(key) or aliases.get(key.lower())
        if not matches:
            unresolved.append(str(item))
            continue
        for instance in matches:
            ident = _instance_identity(instance, fallback=key)
            if ident not in seen:
                seen.add(ident)
                storage_ids.append(ident)
    return storage_ids, unresolved


def select_instances_by_ids(authorized_instances: dict[str, Any], instance_ids: Iterable[Any]) -> list[Any]:
    """Resolve storage keys like ('abc',) and the logical first component abc."""
    storage_ids, _unresolved = resolve_instance_storage_ids(authorized_instances, instance_ids)
    return [authorized_instances[storage_id] for storage_id in storage_ids if storage_id in authorized_instances]


def empty_host_snapshot(*, host_count: int = 0) -> dict[str, Any]:
    snapshot = dict(EMPTY_SNAPSHOT)
    snapshot["host_count"] = host_count
    return snapshot


def build_host_resource_snapshot(
    *,
    host_meta: dict[str, dict[str, Any]],
    cpu_candidates: list[HostCandidate],
    memory_candidates: list[HostCandidate],
    disk_candidates: list[HostCandidate],
    now: datetime | None = None,
    host_count: int,
) -> dict[str, Any]:
    cpu_rows = normalize_metric_candidates(cpu_candidates, host_meta, now=now)
    memory_rows = normalize_metric_candidates(memory_candidates, host_meta, now=now)
    disk_rows = normalize_metric_candidates(disk_candidates, host_meta, now=now)

    def _average(rows: list[HostCandidate]) -> float | None:
        if not rows:
            return None
        return round(sum(float(item.value) for item in rows) / len(rows), 2)

    def _max_row(rows: list[HostCandidate]) -> tuple[float | None, str | None]:
        if not rows:
            return None, None
        winner = max(rows, key=lambda item: float(item.value))
        return round(float(winner.value), 2), host_display_name(
            host_meta.get(winner.instance_id, {}),
            winner.instance_id,
        )

    max_cpu, max_cpu_host = _max_row(cpu_rows)
    max_memory, max_memory_host = _max_row(memory_rows)
    return {
        "host_count": host_count,
        "avg_cpu": _average(cpu_rows),
        "avg_memory": _average(memory_rows),
        "avg_disk": _average(disk_rows),
        "max_cpu": max_cpu,
        "max_cpu_host": max_cpu_host,
        "max_memory": max_memory,
        "max_memory_host": max_memory_host,
    }


@dataclass
class HostMetricRangeService:
    vm_api: Any

    def run(
        self,
        *,
        metric_type: str,
        time_range: list | tuple,
        instances: list[Any],
        step: str = DEFAULT_RANGE_STEP,
    ) -> dict[str, list[list[float]]]:
        if not instances:
            return {}
        normalized_type = validate_range_metric_type(metric_type)
        spec = RANGE_METRIC_SPECS[normalized_type]
        start, end = parse_rfc3339_range_utc(time_range)
        host_meta = build_host_meta(instances)
        response = self.vm_api.query_range(
            spec["query"],
            rfc3339_to_timestamp(start),
            rfc3339_to_timestamp(end),
            step or DEFAULT_RANGE_STEP,
        )
        if not isinstance(response, dict) or response.get("status") != "success":
            message = response.get("error") if isinstance(response, dict) else None
            raise RuntimeError(message or "主机指标查询失败")
        result = response.get("data", {}).get("result", [])
        if not isinstance(result, list):
            return {}
        return fold_host_range_series(
            result,
            host_meta,
            fold=spec["fold"],
            transform=spec.get("transform"),
        )


class HostResourceSnapshotService:
    def __init__(self, *, vm_api, now: datetime | None = None):
        self.top = HostResourceTopService(vm_api=vm_api, now=now)
        self.now = now

    def run(self, instances: list[Any]) -> dict[str, Any]:
        host_count = len([item for item in instances if getattr(item, "id", None)])
        if not host_count:
            return empty_host_snapshot()
        lookback = self._lookback(instances)
        cpu = self.top._query("cpu", lookback)
        memory = self.top._query("memory", lookback)
        disk = self.top._query("disk", lookback)
        return build_host_resource_snapshot(
            host_meta=build_host_meta(instances),
            cpu_candidates=cpu,
            memory_candidates=memory,
            disk_candidates=disk,
            now=self.now or datetime.now(timezone.utc),
            host_count=host_count,
        )

    def _lookback(self, instances: list[Any]) -> int:
        host_meta = build_host_meta(instances)
        return max(2 * int(meta.get("interval") or DEFAULT_INTERVAL_SECONDS) for meta in host_meta.values())
