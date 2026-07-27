"""Network-device resource Top10 query and ranking helpers."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any

from apps.monitor.utils.dimension import parse_instance_id

SUPPORTED_METRIC_TYPES = ("cpu", "memory", "traffic")
NETWORK_DEVICE_OBJECT_NAMES = ("Switch", "Router", "Firewall", "Loadbalance")
DEFAULT_INTERVAL_SECONDS = 300


@dataclass(frozen=True)
class NetworkCandidate:
    instance_id: str
    value: Any
    sampled_at: datetime
    metric_type: str


def validate_metric_type(metric_type: str) -> str:
    normalized = str(metric_type or "").strip().lower()
    if normalized not in SUPPORTED_METRIC_TYPES:
        raise ValueError("metric_type 仅支持 cpu、memory、traffic")
    return normalized


def _aware(value):
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _interval(meta):
    try:
        value = int(meta.get("interval", DEFAULT_INTERVAL_SECONDS))
    except (TypeError, ValueError):
        value = DEFAULT_INTERVAL_SECONDS
    return value if value > 0 else DEFAULT_INTERVAL_SECONDS


def _valid_value(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def normalize_candidates(candidates, device_meta, *, now=None):
    reference = _aware(now) or datetime.now(timezone.utc)
    fresh = []
    for item in candidates:
        instance_id = str(item.instance_id or "")
        meta = device_meta.get(instance_id)
        sampled_at = _aware(item.sampled_at)
        value = _valid_value(item.value)
        if not instance_id or not meta or meta.get("object_name") not in NETWORK_DEVICE_OBJECT_NAMES:
            continue
        if sampled_at is None or value is None:
            continue
        if reference - sampled_at > timedelta(seconds=2 * _interval(meta)):
            continue
        fresh.append(NetworkCandidate(instance_id, value, sampled_at, item.metric_type))
    return fresh


def build_ranked_rows(candidates, device_meta, *, limit=10):
    ordered = sorted(
        candidates,
        key=lambda item: (-float(item.value), str(device_meta[item.instance_id].get("name") or item.instance_id), item.instance_id),
    )[:limit]
    rows = []
    for rank, item in enumerate(ordered, 1):
        meta = device_meta[item.instance_id]
        rows.append({
            "rank": rank,
            "display_name": meta.get("name") or meta.get("ip") or item.instance_id,
            "ip": meta.get("ip") or "",
            "instance_id": item.instance_id,
            "device_type": meta.get("object_name"),
            "value": round(float(item.value), 2),
            "unit": "byteps" if item.metric_type == "traffic" else "percent",
            "sampled_at": item.sampled_at.isoformat(),
        })
    return rows


class NetworkDeviceResourceTopService:
    METRIC_NAMES = {
        "cpu": ("device_cpu_usage",),
        "memory": ("device_memory_usage", "device_memory_used", "device_memory_free", "device_memory_total"),
        "traffic": ("device_total_incoming_traffic", "device_total_outgoing_traffic"),
    }

    def __init__(self, *, vm_api, now=None):
        self.vm_api = vm_api
        self.now = now

    def _query_metric(self, metric_name, lookback_seconds):
        query = f'{{__name__="{metric_name}"}}'
        try:
            response = self.vm_api.query(query, lookback_delta=f"{lookback_seconds}s")
        except TypeError:
            response = self.vm_api.query(query)
        if not isinstance(response, dict) or response.get("status") != "success":
            raise RuntimeError((response or {}).get("error", "网络设备资源指标查询失败"))
        result = response.get("data", {}).get("result", [])
        samples = []
        for series in result if isinstance(result, list) else []:
            labels = series.get("metric") or {}
            point = series.get("value")
            if not labels.get("instance_id") or not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                sampled_at = datetime.fromtimestamp(float(point[0]), tz=timezone.utc)
            except (TypeError, ValueError, OSError, OverflowError):
                continue
            samples.append((str(labels["instance_id"]), point[1], sampled_at))
        return samples

    def run(self, metric_type, authorized_instances, *, limit=10):
        metric_type = validate_metric_type(metric_type)
        if not 1 <= int(limit) <= 100:
            raise ValueError("limit 必须在 1 到 100 之间")
        meta = {
            str(parse_instance_id(instance.id)[0]): {
                "name": getattr(instance, "name", ""),
                "ip": getattr(instance, "ip", ""),
                "interval": getattr(instance, "interval", DEFAULT_INTERVAL_SECONDS),
                "object_name": getattr(getattr(instance, "monitor_object", None), "name", ""),
            }
            for instance in authorized_instances if getattr(instance, "id", None)
        }
        meta = {key: value for key, value in meta.items() if value["object_name"] in NETWORK_DEVICE_OBJECT_NAMES}
        if not meta:
            return []
        lookback = max(2 * _interval(value) for value in meta.values())
        raw = []
        for metric_name in self.METRIC_NAMES[metric_type]:
            raw.extend((instance_id, metric_name, value, sampled_at) for instance_id, value, sampled_at in self._query_metric(metric_name, lookback))
        valid = []
        for instance_id, metric_name, value, sampled_at in raw:
            if instance_id in meta:
                valid.append(NetworkCandidate(instance_id, value, sampled_at, metric_name))
        valid = normalize_candidates(valid, meta, now=self.now)
        grouped = {}
        for item in valid:
            grouped.setdefault(item.instance_id, {}).setdefault(item.metric_type, []).append(item)
        aggregate = []
        for instance_id, by_metric in grouped.items():
            samples = by_metric
            if metric_type == "cpu":
                values = [item.value for key, items in samples.items() if key == "device_cpu_usage" for item in items]
                if not values:
                    continue
                value = sum(values) / len(values)
                used = [item for key, items in samples.items() if key == "device_cpu_usage" for item in items]
            elif metric_type == "traffic":
                values = [item.value for items in samples.values() for item in items]
                if not values:
                    continue
                value = sum(values)
                used = [item for items in samples.values() for item in items]
            else:
                usage = [item for key, items in samples.items() if key == "device_memory_usage" for item in items]
                used = [item for key, items in samples.items() if key == "device_memory_used" for item in items]
                free = [item for key, items in samples.items() if key == "device_memory_free" for item in items]
                total = [item for key, items in samples.items() if key == "device_memory_total" for item in items]
                if usage:
                    value = sum(item.value for item in usage) / len(usage)
                    used = usage
                elif used and total and sum(item.value for item in total) > 0:
                    value = sum(item.value for item in used) / sum(item.value for item in total) * 100
                elif total and free and sum(item.value for item in total) > 0:
                    value = (sum(item.value for item in total) - sum(item.value for item in free)) / sum(item.value for item in total) * 100
                elif used and free and sum(item.value for item in used) + sum(item.value for item in free) > 0:
                    value = sum(item.value for item in used) / (sum(item.value for item in used) + sum(item.value for item in free)) * 100
                else:
                    continue
                if not 0 <= value <= 100:
                    continue
            aggregate.append(NetworkCandidate(instance_id, value, max(item.sampled_at for item in used), metric_type))
        return build_ranked_rows(aggregate, meta, limit=int(limit))
