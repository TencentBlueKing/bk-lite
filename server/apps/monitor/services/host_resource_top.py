"""Pure host resource Top10 normalization helpers.

The NATS adapter and persistence lookups are intentionally kept out of this
module so ranking behavior can be tested without a Django database.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import math
from typing import Any

from apps.monitor.utils.dimension import parse_instance_id


SUPPORTED_METRIC_TYPES = ("cpu", "memory", "disk")
DEFAULT_INTERVAL_SECONDS = 300


@dataclass(frozen=True)
class HostCandidate:
    instance_id: str
    value: Any
    sampled_at: datetime
    metric_type: str
    labels: dict[str, Any] = field(default_factory=dict)


def validate_metric_type(metric_type: str) -> str:
    normalized = str(metric_type or "").strip().lower()
    if normalized not in SUPPORTED_METRIC_TYPES:
        raise ValueError("metric_type 仅支持 cpu、memory、disk")
    return normalized


def _as_finite_percentage(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0 or number > 100:
        return None
    return number


def _as_aware_datetime(value: datetime) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _interval_seconds(meta: dict[str, Any]) -> int:
    try:
        interval = int(meta.get("interval", DEFAULT_INTERVAL_SECONDS))
    except (TypeError, ValueError):
        interval = DEFAULT_INTERVAL_SECONDS
    return interval if interval > 0 else DEFAULT_INTERVAL_SECONDS


def _candidate_key(item: HostCandidate) -> tuple[str, str, str, str]:
    labels = item.labels
    return (
        str(labels.get("mount") or ""),
        str(labels.get("path") or ""),
        str(labels.get("fstype") or ""),
        str(labels.get("device") or ""),
    )


def normalize_metric_candidates(
    candidates: list[HostCandidate],
    host_meta: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[HostCandidate]:
    reference_now = _as_aware_datetime(now or datetime.now(timezone.utc))
    valid: list[HostCandidate] = []
    for item in candidates:
        instance_id = str(item.instance_id or "")
        if not instance_id or item.metric_type not in SUPPORTED_METRIC_TYPES:
            continue
        sampled_at = _as_aware_datetime(item.sampled_at)
        value = _as_finite_percentage(item.value)
        if sampled_at is None or value is None:
            continue
        meta = host_meta.get(instance_id)
        if meta is None:
            continue
        if reference_now - sampled_at > timedelta(seconds=2 * _interval_seconds(meta)):
            continue
        valid.append(
            HostCandidate(
                instance_id=instance_id,
                value=value,
                sampled_at=sampled_at,
                metric_type=item.metric_type,
                labels=dict(item.labels or {}),
            )
        )

    by_instance: dict[str, HostCandidate] = {}
    for item in valid:
        current = by_instance.get(item.instance_id)
        if current is None or item.sampled_at > current.sampled_at:
            by_instance[item.instance_id] = item

    if not valid or valid[0].metric_type != "disk":
        return list(by_instance.values())

    disk_by_instance: dict[str, HostCandidate] = {}
    for item in valid:
        current = disk_by_instance.get(item.instance_id)
        if current is None or item.value > current.value or (
            item.value == current.value and _candidate_key(item) < _candidate_key(current)
        ):
            disk_by_instance[item.instance_id] = item
    return list(disk_by_instance.values())


def _display_name(meta: dict[str, Any], instance_id: str) -> str:
    host_name = str(meta.get("host_name") or "").strip()
    ip = str(meta.get("ip") or "").strip()
    if host_name and ip:
        return f"{host_name} ({ip})"
    return host_name or ip or instance_id


def build_ranked_rows(
    candidates: list[HostCandidate],
    host_meta: dict[str, dict[str, Any]],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    ordered = sorted(
        candidates,
        key=lambda item: (
            -float(item.value),
            _display_name(host_meta.get(item.instance_id, {}), item.instance_id),
            item.instance_id,
        ),
    )[:limit]
    rows = []
    for rank, item in enumerate(ordered, start=1):
        meta = host_meta.get(item.instance_id, {})
        labels = item.labels
        rows.append(
            {
                "rank": rank,
                "display_name": _display_name(meta, item.instance_id),
                "usage_percent": round(float(item.value), 2),
                "instance_id": item.instance_id,
                "host_name": meta.get("host_name") or None,
                "ip": meta.get("ip") or None,
                "metric_type": item.metric_type,
                "mount": labels.get("mount") if item.metric_type == "disk" else None,
                "path": labels.get("path") if item.metric_type == "disk" else None,
                "fstype": labels.get("fstype") if item.metric_type == "disk" else None,
                "sampled_at": item.sampled_at.isoformat(),
            }
        )
    return rows


class HostResourceTopService:
    """Query and rank the latest resource values for authorized hosts."""

    METRIC_NAMES = {
        "cpu": ("host_cpu_usage_percent", "host_cpu_usage_percent_gauge"),
        "memory": ("host_mem_used_percent", "host_mem_used_percent_gauge"),
        "disk": ("host_disk_used_percent", "host_disk_used_percent_gauge"),
    }

    def __init__(self, *, vm_api, now: datetime | None = None):
        self.vm_api = vm_api
        self.now = now

    def _query(self, metric_type: str, lookback_seconds: int) -> list[HostCandidate]:
        metric_names = self.METRIC_NAMES[metric_type]
        query = '__name__=~"' + "|".join(metric_names) + '"'
        try:
            response = self.vm_api.query(f"{{{query}}}", lookback_delta=f"{lookback_seconds}s")
        except TypeError:
            response = self.vm_api.query(f"{{{query}}}")
        if not isinstance(response, dict) or response.get("status") != "success":
            message = response.get("error") if isinstance(response, dict) else None
            raise RuntimeError(message or "主机资源指标查询失败")

        result = response.get("data", {}).get("result", [])
        if not isinstance(result, list):
            return []
        candidates: list[HostCandidate] = []
        for series in result:
            if not isinstance(series, dict):
                continue
            labels = series.get("metric") or {}
            instance_id = labels.get("instance_id")
            value = series.get("value")
            if not instance_id or not isinstance(value, (list, tuple)) or len(value) < 2:
                continue
            try:
                sampled_at = datetime.fromtimestamp(float(value[0]), tz=timezone.utc)
            except (TypeError, ValueError, OSError, OverflowError):
                continue
            candidate_labels = {
                "mount": labels.get("mount") or labels.get("path"),
                "path": labels.get("path") or labels.get("device"),
                "fstype": labels.get("fstype"),
                "device": labels.get("device"),
            }
            candidates.append(
                HostCandidate(
                    instance_id=str(instance_id),
                    value=value[1],
                    sampled_at=sampled_at,
                    metric_type=metric_type,
                    labels=candidate_labels,
                )
            )
        return candidates

    def run(self, metric_type: str, authorized_instances: list[Any]) -> list[dict[str, Any]]:
        normalized_type = validate_metric_type(metric_type)
        host_meta = {
            str(parse_instance_id(instance.id)[0]): {
                "host_name": getattr(instance, "name", "") or "",
                "ip": getattr(instance, "ip", "") or "",
                "interval": getattr(instance, "interval", DEFAULT_INTERVAL_SECONDS),
            }
            for instance in authorized_instances
            if getattr(instance, "id", None)
        }
        if not host_meta:
            return []
        max_lookback = max(
            2 * _interval_seconds(meta)
            for meta in host_meta.values()
        )
        candidates = self._query(normalized_type, max_lookback)
        normalized = normalize_metric_candidates(candidates, host_meta, now=self.now)
        return build_ranked_rows(normalized, host_meta)
