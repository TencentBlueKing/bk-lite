"""Current-value ranking for network devices.

CPU and memory reuse the existing detail capability for Switch, Router, Firewall,
Loadbalance and Wanopt, including each template's or / max / avg order. Categories
without that capability are left off the board. Total traffic reuses the public
IF-MIB catalog: per-interface HC or 32-bit rate over a fixed 5 minutes, summed,
then inbound plus outbound. That is a different window and aggregation shape from
the detail page's variable-duration sum-then-or query.

A raw series is fresh for two collection intervals. VictoriaMetrics lookback is
open at the far end, so gauge search uses two intervals plus one second and does
not read the aggregation timestamp. rate() ignores that lookback, so traffic also
keeps a counter only when timestamp() of the raw series is inside the same age.
sampled_at remains the timestamp on the instant-vector point.
"""

import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from apps.monitor.services.metric_query_contract import build_instance_matcher_groups, join_label_queries
from apps.monitor.services.metric_series import MAX_INSTANCE_IDS
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.query_deadline import past_deadline

SUPPORTED_METRIC_TYPES = ("cpu", "memory", "traffic")
NETWORK_DEVICE_TYPE_ID = "Network Device"
CPU_MEMORY_OBJECT_NAMES = frozenset({"Switch", "Router", "Firewall", "Loadbalance", "Wanopt"})
GAUGE_METRIC_NAMES = {"cpu": "device_cpu_usage", "memory": "device_memory_usage"}
TRAFFIC_METRIC_NAMES = ("device_total_incoming_traffic", "device_total_outgoing_traffic")
IFMIB_RATE_WINDOW_SECONDS = 300
DEFAULT_COLLECTION_INTERVAL_SECONDS = 300
DETAIL_QUERY_CHUNK_SIZE = MAX_INSTANCE_IDS
# Local margin under VictoriaMetrics' default -search.maxQueryLen of 16384.
# This is not read from VM and is not a protocol field.
QUERY_BYTE_BUDGET = 16128
DETAIL_METRIC_MANIFEST = Path(__file__).resolve().parent.parent / "support-files" / "network_device_detail_metrics.json"
_CATALOG_SELECTOR = "{instance_type='switch', __$labels__}"
_CATALOG_RATE = re.compile(r"rate\(([A-Za-z_:][A-Za-z0-9_:]*)\{([^{}]*)\}\[5m\]\)")


@dataclass(frozen=True)
class NetworkCandidate:
    instance_id: str
    value: Any
    sampled_at: datetime
    metric_type: str


@dataclass(frozen=True)
class NetworkDeviceDetailMetric:
    capability_id: str
    template: str


class _QueryBudgetExceeded(RuntimeError):
    def __init__(self, query_bytes: int):
        super().__init__("网络设备资源指标查询失败")
        self.query_bytes = query_bytes


def validate_metric_type(metric_type: str) -> str:
    normalized = str(metric_type or "").strip().lower()
    if normalized not in SUPPORTED_METRIC_TYPES:
        raise ValueError("metric_type 仅支持 cpu、memory、traffic")
    return normalized


def _aware(value):
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _monitor_object_type_id(monitor_object) -> str:
    if monitor_object is None:
        return ""
    if hasattr(monitor_object, "type_id"):
        type_id = monitor_object.type_id
        return "" if type_id in (None, "") else str(type_id)
    related_id = getattr(getattr(monitor_object, "type", None), "id", None)
    return "" if related_id in (None, "") else str(related_id)


def _instance_keys(instance) -> tuple[str, ...]:
    monitor_object = getattr(instance, "monitor_object", None)
    raw = getattr(monitor_object, "instance_id_keys", None) or ["instance_id"]
    keys = tuple(str(key).strip() for key in raw if str(key).strip())
    return keys or ("instance_id",)


def collection_interval_seconds(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_COLLECTION_INTERVAL_SECONDS
    return number if number > 0 else DEFAULT_COLLECTION_INTERVAL_SECONDS


def gauge_search_window_seconds(interval_seconds: int) -> int:
    """Search window that keeps a sample exactly two intervals old.

    VictoriaMetrics instant lookback is (time-step, time]. Two intervals alone
    drops that boundary sample.
    """
    return 2 * int(interval_seconds) + 1


def traffic_search_window_seconds(interval_seconds: int) -> int:
    return max(IFMIB_RATE_WINDOW_SECONDS, gauge_search_window_seconds(interval_seconds))


def freshness_cutoff_literal(reference: datetime, interval_seconds: int) -> str:
    cutoff = reference.timestamp() - 2 * interval_seconds
    if math.isfinite(cutoff) and float(cutoff).is_integer():
        return str(int(cutoff))
    return format(cutoff, ".6f").rstrip("0").rstrip(".")


def _single_instance_id(instance) -> str | None:
    if _instance_keys(instance) != ("instance_id",):
        return None
    parsed = parse_instance_id(getattr(instance, "id", None))
    if len(parsed) != 1 or parsed[0] in (None, ""):
        return None
    return str(parsed[0])


def _remaining_timeout(deadline):
    if deadline is None:
        return None
    return max(deadline - time.monotonic(), 0.001)


def _deadline_failure(metric_type, *, query_bytes, chunk_count, capability_id="", direction=""):
    try:
        raise RuntimeError("网络设备资源指标查询失败")
    except RuntimeError as exc:
        return _safe_query_error(
            exc,
            metric_type=metric_type,
            failed_stage="deadline",
            query_bytes=query_bytes,
            chunk_count=chunk_count,
            capability_id=capability_id,
            direction=direction,
            error_type="DeadlineExceeded",
        )


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _safe_query_error(exc, *, metric_type, failed_stage, query_bytes, chunk_count, capability_id="", direction="", error_type):
    """Return a safe error for the handler log. The original exception is left unchanged."""
    safe = RuntimeError("网络设备资源指标查询失败")
    safe.add_note(
        "metric_type=%s failed_stage=%s capability_id=%s direction=%s "
        "chunk_count=%s query_bytes=%s budget_bytes=%s error_type=%s"
        % (
            metric_type,
            failed_stage,
            capability_id,
            direction,
            chunk_count,
            query_bytes,
            QUERY_BYTE_BUDGET,
            error_type,
        )
    )
    return safe.with_traceback(exc.__traceback__)


def _pack_rendered(ids, render, measure):
    """Greedy batches. The stored render is the one whose size was measured."""
    ordered = sorted(set(ids))
    singles = []
    for instance_id in ordered:
        rendered = render([instance_id])
        size = measure(rendered)
        if size > QUERY_BYTE_BUDGET:
            raise _QueryBudgetExceeded(size)
        singles.append((instance_id, rendered))

    batches = []
    current_ids = []
    current_rendered = None
    for instance_id, single in singles:
        if not current_ids:
            current_ids = [instance_id]
            current_rendered = single
            continue
        if len(current_ids) >= DETAIL_QUERY_CHUNK_SIZE:
            batches.append((current_ids, current_rendered))
            current_ids = [instance_id]
            current_rendered = single
            continue
        trial_ids = current_ids + [instance_id]
        trial = render(trial_ids)
        if measure(trial) <= QUERY_BYTE_BUDGET:
            current_ids = trial_ids
            current_rendered = trial
            continue
        batches.append((current_ids, current_rendered))
        current_ids = [instance_id]
        current_rendered = single
    if current_ids:
        batches.append((current_ids, current_rendered))
    return batches


@lru_cache(maxsize=1)
def load_network_device_detail_metrics() -> dict[tuple[str, str], NetworkDeviceDetailMetric]:
    import json

    from apps.monitor.services.dashboard_query_capabilities import load_dashboard_query_capabilities

    payload = json.loads(DETAIL_METRIC_MANIFEST.read_text(encoding="utf-8"))
    bindings_payload = payload.get("bindings")
    if payload.get("version") != 1 or not isinstance(bindings_payload, list):
        raise RuntimeError("invalid network device detail metric manifest")

    capabilities = load_dashboard_query_capabilities()
    bindings = {}
    for item in bindings_payload:
        if not isinstance(item, dict):
            raise RuntimeError("invalid network device detail metric")
        object_name = str(item.get("object_name") or "").strip()
        metric_name = str(item.get("metric_name") or "").strip()
        if object_name not in CPU_MEMORY_OBJECT_NAMES or metric_name not in set(GAUGE_METRIC_NAMES.values()):
            continue
        capability_id = str(item.get("capability_id") or "").strip()
        capability = capabilities.get(capability_id)
        key = (object_name, metric_name)
        if capability is None or object_name not in capability.object_names or key in bindings:
            raise RuntimeError(f"invalid network device detail metric: {object_name}.{metric_name or '-'}")
        bindings[key] = NetworkDeviceDetailMetric(capability_id=capability_id, template=capability.template)
    return bindings


@lru_cache(maxsize=1)
def _device_total_catalog() -> dict[str, str]:
    from apps.monitor.management.services.plugin_migrate import _build_common_ifmib_metrics

    found = {}
    for item in _build_common_ifmib_metrics("switch", ""):
        name = str(item.get("name") or "")
        if name in TRAFFIC_METRIC_NAMES:
            found[name] = str(item["query"])
    if set(found) != set(TRAFFIC_METRIC_NAMES):
        raise RuntimeError("公共 IF-MIB 总流量定义缺失")
    return found


def build_device_total_rate_query(metric_name: str, matcher: str, cutoff: str) -> str:
    template = _device_total_catalog()[metric_name]
    if _CATALOG_SELECTOR not in template:
        raise RuntimeError("公共 IF-MIB 总流量定义无法套用到排行")
    scoped = template.replace(_CATALOG_SELECTOR, "{" + matcher + "}")

    def _gate(match):
        selector = f"{match.group(1)}{{{match.group(2)}}}"
        return f"(rate({selector}[5m]) and ignoring(__name__) (timestamp({selector}) >= {cutoff}))"

    gated, count = _CATALOG_RATE.subn(_gate, scoped)
    if count != 2:
        raise RuntimeError("公共 IF-MIB 总流量定义无法套用到排行")
    return gated


def build_ranked_rows(candidates, device_meta, *, limit=10):
    ordered = sorted(
        candidates,
        key=lambda item: (-float(item.value), str(device_meta[item.instance_id].get("name") or item.instance_id), item.instance_id),
    )[:limit]
    rows = []
    for rank, item in enumerate(ordered, 1):
        meta = device_meta[item.instance_id]
        rows.append(
            {
                "rank": rank,
                "display_name": meta.get("name") or meta.get("ip") or item.instance_id,
                "ip": meta.get("ip") or "",
                "instance_id": item.instance_id,
                "device_type": meta.get("object_name"),
                "value": round(float(item.value), 2),
                "unit": "byteps" if item.metric_type == "traffic" else "percent",
                "sampled_at": item.sampled_at.isoformat(),
            }
        )
    return rows


def _collect_devices(authorized_instances):
    meta = {}
    devices = []
    for instance in authorized_instances:
        object_type_id = _monitor_object_type_id(getattr(instance, "monitor_object", None))
        if object_type_id != NETWORK_DEVICE_TYPE_ID:
            continue
        instance_id = _single_instance_id(instance)
        if instance_id is None:
            continue
        monitor_object = getattr(instance, "monitor_object", None)
        item = {
            "name": getattr(instance, "name", ""),
            "ip": getattr(instance, "ip", ""),
            "object_name": getattr(monitor_object, "name", ""),
            "object_type_id": object_type_id,
            "interval": collection_interval_seconds(getattr(instance, "interval", None)),
        }
        meta[instance_id] = item
        devices.append({"instance_id": instance_id, "object_name": item["object_name"], "interval": item["interval"]})
    return devices, meta


class NetworkDeviceResourceTopService:
    def __init__(self, *, vm_api, now=None):
        self.vm_api = vm_api
        self.now = now

    def run(self, metric_type, authorized_instances, *, limit=10, deadline=None):
        metric_type = validate_metric_type(metric_type)
        if not 1 <= int(limit) <= 100:
            raise ValueError("limit 必须在 1 到 100 之间")
        reference = _aware(self.now) or datetime.now(timezone.utc)
        devices, meta = _collect_devices(authorized_instances)
        if not devices:
            return []
        if past_deadline(deadline):
            raise _deadline_failure(metric_type, query_bytes=0, chunk_count=0)
        if metric_type == "traffic":
            candidates = self._traffic_candidates(devices, reference, deadline)
        else:
            candidates = self._gauge_candidates(metric_type, devices, reference, deadline)
        return build_ranked_rows(candidates, meta, limit=int(limit))

    def _query_instant(self, query: str, window: str, reference: datetime, *, timeout=None):
        kwargs = {"step": window, "lookback_delta": window, "time": reference.timestamp()}
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = self.vm_api.query(query, **kwargs)
        if not isinstance(response, dict) or response.get("status") != "success":
            raise RuntimeError("网络设备资源指标查询失败")
        result = response.get("data", {}).get("result", [])
        samples = []
        for series in result if isinstance(result, list) else []:
            labels = series.get("metric") or {}
            point = series.get("value")
            instance_id = str(labels.get("instance_id") or "")
            if not instance_id or not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                sampled_at = datetime.fromtimestamp(float(point[0]), tz=timezone.utc)
                value = float(point[1])
            except (TypeError, ValueError, OSError, OverflowError):
                continue
            if not math.isfinite(value):
                continue
            samples.append((instance_id, value, sampled_at))
        return samples

    def _remember(self, found: dict, instance_id: str, value: float, sampled_at: datetime, allowed: set[str]):
        if instance_id not in allowed:
            return
        current = found.get(instance_id)
        if current is None or sampled_at >= current[1]:
            found[instance_id] = (value, sampled_at)

    def _gauge_candidates(self, metric_type: str, devices: list[dict], reference: datetime, deadline):
        metric_name = GAUGE_METRIC_NAMES[metric_type]
        bindings = load_network_device_detail_metrics()
        groups = {}
        for device in devices:
            if device["object_name"] not in CPU_MEMORY_OBJECT_NAMES:
                continue
            binding = bindings.get((device["object_name"], metric_name))
            if binding is None:
                continue
            group = groups.setdefault(
                (binding.capability_id, device["interval"]),
                {"template": binding.template, "capability_id": binding.capability_id, "interval": device["interval"], "ids": []},
            )
            group["ids"].append(device["instance_id"])

        plans = []
        for group in groups.values():
            window = f"{gauge_search_window_seconds(group['interval'])}s"
            template = group["template"]

            def render(chunk_ids, template=template):
                query = join_label_queries(template, build_instance_matcher_groups(tuple(chunk_ids), ["instance_id"]))
                if "__$" in query:
                    raise RuntimeError("网络设备详情查询模板参数不完整")
                return query

            failure = None
            try:
                batches = _pack_rendered(group["ids"], render, _utf8_len)
            except _QueryBudgetExceeded as exc:
                failure = _safe_query_error(
                    exc,
                    metric_type=metric_type,
                    failed_stage="single_query_over_budget",
                    query_bytes=exc.query_bytes,
                    chunk_count=0,
                    capability_id=group["capability_id"],
                    error_type="QueryBudgetExceeded",
                )
            if failure is not None:
                raise failure
            plans.append((group["capability_id"], window, batches))

        found = {}
        for capability_id, window, batches in plans:
            for chunk_ids, query in batches:
                if past_deadline(deadline):
                    raise _deadline_failure(
                        metric_type,
                        query_bytes=_utf8_len(query),
                        chunk_count=len(batches),
                        capability_id=capability_id,
                    )
                failure = None
                try:
                    samples = self._query_instant(query, window, reference, timeout=_remaining_timeout(deadline))
                except TypeError:
                    raise
                except Exception as exc:
                    failure = _safe_query_error(
                        exc,
                        metric_type=metric_type,
                        failed_stage="query_chunk",
                        query_bytes=_utf8_len(query),
                        chunk_count=len(batches),
                        capability_id=capability_id,
                        error_type=type(exc).__name__,
                    )
                if failure is not None:
                    raise failure
                allowed = set(chunk_ids)
                for instance_id, value, sampled_at in samples:
                    self._remember(found, instance_id, value, sampled_at, allowed)
        return [NetworkCandidate(instance_id, value, sampled_at, metric_type) for instance_id, (value, sampled_at) in found.items()]

    def _traffic_candidates(self, devices: list[dict], reference: datetime, deadline):
        by_interval = {}
        for device in devices:
            by_interval.setdefault(device["interval"], []).append(device["instance_id"])
        plans = []
        for interval, instance_ids in by_interval.items():
            cutoff = freshness_cutoff_literal(reference, interval)
            window = f"{traffic_search_window_seconds(interval)}s"

            def render(chunk_ids, cutoff=cutoff):
                matcher = build_instance_matcher_groups(tuple(chunk_ids), ["instance_id"])[0][0]
                return tuple(build_device_total_rate_query(name, matcher, cutoff) for name in TRAFFIC_METRIC_NAMES)

            failure = None
            try:
                batches = _pack_rendered(instance_ids, render, lambda pair: max(_utf8_len(query) for query in pair))
            except _QueryBudgetExceeded as exc:
                failure = _safe_query_error(
                    exc,
                    metric_type="traffic",
                    failed_stage="single_query_over_budget",
                    query_bytes=exc.query_bytes,
                    chunk_count=0,
                    direction="+".join(TRAFFIC_METRIC_NAMES),
                    error_type="QueryBudgetExceeded",
                )
            if failure is not None:
                raise failure
            plans.append((window, batches))

        totals = {}
        for window, batches in plans:
            for chunk_ids, queries in batches:
                allowed = set(chunk_ids)
                for direction, query in zip(TRAFFIC_METRIC_NAMES, queries):
                    if past_deadline(deadline):
                        raise _deadline_failure(
                            "traffic",
                            query_bytes=_utf8_len(query),
                            chunk_count=len(batches),
                            direction=direction,
                        )
                    failure = None
                    try:
                        samples = self._query_instant(query, window, reference, timeout=_remaining_timeout(deadline))
                    except TypeError:
                        raise
                    except Exception as exc:
                        failure = _safe_query_error(
                            exc,
                            metric_type="traffic",
                            failed_stage="query_chunk",
                            query_bytes=_utf8_len(query),
                            chunk_count=len(batches),
                            direction=direction,
                            error_type=type(exc).__name__,
                        )
                    if failure is not None:
                        raise failure
                    for instance_id, value, sampled_at in samples:
                        if instance_id not in allowed:
                            continue
                        current = totals.get(instance_id)
                        if current is None:
                            totals[instance_id] = [value, sampled_at]
                        else:
                            current[0] += value
                            if sampled_at > current[1]:
                                current[1] = sampled_at
        return [NetworkCandidate(instance_id, value, sampled_at, "traffic") for instance_id, (value, sampled_at) in totals.items()]
