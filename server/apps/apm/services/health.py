from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

import requests
from django.utils import timezone

from apps.apm.models import ApmPolicyNotificationTarget
from apps.rpc.system_mgmt import SystemMgmt


CATALOG_RECONCILE_HEALTH_KEY = "apm:catalog:reconcile:health"
RUNTIME_DEPENDENCIES_HEALTH_KEY = "apm:runtime:dependencies:health"
POLICY_EVALUATION_HEALTH_KEY = "apm:policy:evaluation:health"
NOTIFICATION_DELIVERY_HEALTH_KEY = "apm:notification:delivery:health"
HEALTH_COMPONENT_KEYS = {
    "catalog_reconcile": CATALOG_RECONCILE_HEALTH_KEY,
    "policy_evaluation": POLICY_EVALUATION_HEALTH_KEY,
    "notification_delivery": NOTIFICATION_DELIVERY_HEALTH_KEY,
}
RUNTIME_COMPONENTS = (
    "regional_collector",
    "nats_publish",
    "jetstream",
    "system_collector",
    "victoria_traces",
    "victoria_traces_retention",
    "notification_responder",
)
MINIMUM_TRACE_RETENTION_DAYS = 35
_DURATION_RE = re.compile(r"^(?P<amount>[1-9]\d*)(?P<unit>[dh])$")
_PROMETHEUS_SAMPLE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>[^\n]*)\})?\s+(?P<value>-?(?:\d+(?:\.\d*)?|\.\d+))$",
    re.MULTILINE,
)


def pending_catalog_health() -> dict[str, str]:
    return {"status": "pending"}


def _origin_health_url(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, "/health", "", ""))


def _retention_days(value: str) -> float | None:
    match = _DURATION_RE.fullmatch(value.strip())
    if match is None:
        return None
    amount = int(match.group("amount"))
    return float(amount) if match.group("unit") == "d" else amount / 24


class RuntimeDependencyHealthProbe:
    """只在运行期执行的有界健康探测，不参与 Server 启动。"""

    def __init__(self, *, session=None, notification_client=None):
        self.session = session or requests.Session()
        self.notification_client = notification_client or SystemMgmt()

    @staticmethod
    def _alert_copy_channel_ids() -> list[int]:
        return list(
            ApmPolicyNotificationTarget.objects.filter(
                delivery_mode=ApmPolicyNotificationTarget.DeliveryMode.ALERT_EVENT_COPY,
                policy__is_enabled=True,
            )
            .order_by("channel_id")
            .values_list("channel_id", flat=True)
            .distinct()[:20]
        )

    def _probe_notification_responder(self, checked_at: str) -> dict[str, str]:
        channel_ids = self._alert_copy_channel_ids()
        if not channel_ids:
            return {"status": "pending", "last_checked_at": checked_at}
        try:
            responses = [self.notification_client.probe_notification_channel(channel_id) for channel_id in channel_ids]
        except Exception:
            return {
                "status": "degraded",
                "last_failed_at": checked_at,
                "error_code": "notification_responder_unavailable",
            }
        if not all(isinstance(response, dict) and response.get("result") is True for response in responses):
            return {
                "status": "degraded",
                "last_failed_at": checked_at,
                "error_code": "notification_responder_unavailable",
            }
        return {"status": "ok", "last_succeeded_at": checked_at}

    def _probe_http(
        self,
        name: str,
        endpoint: str,
        checked_at: str,
        *,
        auth: tuple[str, str] | None = None,
    ) -> dict[str, str]:
        if not endpoint:
            return {"status": "pending", "last_checked_at": checked_at}
        try:
            response = self.session.get(endpoint, auth=auth, timeout=(1, 2))
            response.raise_for_status()
        except requests.RequestException:
            return {
                "status": "degraded",
                "last_failed_at": checked_at,
                "error_code": f"{name}_unavailable",
            }
        return {"status": "ok", "last_succeeded_at": checked_at}

    def _probe_nats_publish(self, checked_at: str) -> dict[str, object]:
        endpoint = os.getenv("APM_REGIONAL_COLLECTOR_METRICS_ENDPOINT", "")
        if not endpoint:
            return {"status": "pending", "last_checked_at": checked_at}
        try:
            response = self.session.get(endpoint, auth=None, timeout=(1, 2))
            response.raise_for_status()
            samples = list(_PROMETHEUS_SAMPLE_RE.finditer(response.text))
        except (requests.RequestException, ValueError):
            return {
                "status": "degraded",
                "last_failed_at": checked_at,
                "error_code": "nats_publish_metrics_invalid",
            }
        def sample(name: str, *, exporter: bool = False) -> float | None:
            for match in samples:
                labels = match.group("labels") or ""
                if match.group("name") == name and (not exporter or 'exporter="nats_jetstream"' in labels):
                    return float(match.group("value"))
            return None

        ack_count = sample("bklite_apm_nats_publish_acks_total")
        if ack_count is None:
            ack_count = sample("bklite_apm_nats_publish_acks")
        if ack_count is None:
            return {
                "status": "degraded",
                "last_failed_at": checked_at,
                "error_code": "nats_publish_metrics_missing",
            }
        result: dict[str, object] = {"status": "ok", "last_succeeded_at": checked_at}
        result["publish_acks"] = int(ack_count)
        last_ack = sample("bklite_apm_nats_last_publish_ack_unixtime")
        if last_ack and last_ack > 0:
            result["last_publish_ack_at"] = datetime.fromtimestamp(last_ack, tz=UTC).isoformat()
        queue_size = sample("otelcol_exporter_queue_size", exporter=True)
        queue_capacity = sample("otelcol_exporter_queue_capacity", exporter=True)
        if queue_size is not None and queue_capacity is not None and queue_capacity > 0:
            queue_utilization = queue_size / queue_capacity
            result.update(
                queue_size=int(queue_size),
                queue_capacity=int(queue_capacity),
                queue_capacity_percent=round(queue_utilization * 100, 2),
            )
            if queue_utilization >= 0.85:
                result["status"] = "degraded"
                result["error_code"] = "regional_queue_capacity_critical"
        return result

    @staticmethod
    def _stream_detail(payload: object) -> Mapping[str, object] | None:
        if isinstance(payload, Mapping):
            if payload.get("name") == os.getenv("APM_NATS_STREAM", "APM_TRACES") and isinstance(payload.get("state"), Mapping):
                return payload
            for value in payload.values():
                found = RuntimeDependencyHealthProbe._stream_detail(value)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for value in payload:
                found = RuntimeDependencyHealthProbe._stream_detail(value)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _consumer_detail(payload: object) -> Mapping[str, object] | None:
        if isinstance(payload, Mapping):
            if payload.get("name") == os.getenv("APM_NATS_CONSUMER", "BKLITE_APM_SYSTEM") and "num_pending" in payload:
                return payload
            for value in payload.values():
                found = RuntimeDependencyHealthProbe._consumer_detail(value)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for value in payload:
                found = RuntimeDependencyHealthProbe._consumer_detail(value)
                if found is not None:
                    return found
        return None

    def _probe_jetstream(self, checked_at: str) -> dict[str, object]:
        endpoint = os.getenv("APM_NATS_MONITOR_ENDPOINT", "").rstrip("/")
        if not endpoint:
            return {"status": "pending", "last_checked_at": checked_at}
        username = os.getenv("APM_NATS_MONITOR_USER", "")
        password = os.getenv("APM_NATS_MONITOR_PASSWORD", "")
        try:
            response = self.session.get(
                f"{endpoint}/jsz",
                params={"streams": "true", "consumers": "true"},
                auth=(username, password) if username else None,
                timeout=(1, 2),
            )
            response.raise_for_status()
            payload = response.json()
            detail = self._stream_detail(payload)
            consumer = self._consumer_detail(payload)
        except (requests.RequestException, ValueError):
            detail = None
        if detail is None:
            return {
                "status": "degraded",
                "last_failed_at": checked_at,
                "error_code": "jetstream_unavailable_or_stream_missing",
            }
        state = detail["state"]
        stream_bytes = int(state.get("bytes", 0))
        messages = int(state.get("messages", 0))
        max_bytes = int(os.getenv("APM_NATS_STREAM_MAX_BYTES", "268435456"))
        utilization = stream_bytes / max_bytes if max_bytes > 0 else 1.0
        result: dict[str, object] = {
            "status": "degraded" if utilization >= 0.85 else "ok",
            "last_succeeded_at": checked_at,
            "stream_bytes": stream_bytes,
            "stream_messages": messages,
            "capacity_percent": round(utilization * 100, 2),
            "consumer_pending": int(consumer.get("num_pending", 0)) if consumer else 0,
            "consumer_ack_pending": int(consumer.get("num_ack_pending", 0)) if consumer else 0,
            "consumer_redelivered": int(consumer.get("num_redelivered", 0)) if consumer else 0,
        }
        if utilization >= 0.85:
            result["error_code"] = "jetstream_capacity_critical"
        return result

    @staticmethod
    def _retention_health(checked_at: str) -> dict[str, object]:
        configured = os.getenv("APM_TRACE_RETENTION", "35d")
        days = _retention_days(configured)
        if days is None:
            return {
                "status": "degraded",
                "last_failed_at": checked_at,
                "error_code": "victoria_traces_retention_invalid",
            }
        result: dict[str, object] = {
            "status": "ok" if days >= MINIMUM_TRACE_RETENTION_DAYS else "degraded",
            "last_checked_at": checked_at,
            "configured_days": days,
            "required_days": MINIMUM_TRACE_RETENTION_DAYS,
        }
        if days < MINIMUM_TRACE_RETENTION_DAYS:
            result["error_code"] = "victoria_traces_retention_too_short"
        return result

    def probe(self) -> dict[str, dict[str, object]]:
        checked_at = timezone.now().isoformat()
        traces_endpoint = (
            os.getenv("VICTORIATRACES_HOST")
            or os.getenv("APM_VICTORIATRACES_QUERY_ENDPOINT")
            or "http://127.0.0.1:10428"
        )
        trace_user = os.getenv("APM_VICTORIATRACES_USER", "")
        trace_password = os.getenv("APM_VICTORIATRACES_PASSWORD", "")
        result = {
            "regional_collector": self._probe_http(
                "regional_collector",
                os.getenv("APM_REGIONAL_COLLECTOR_HEALTH_ENDPOINT", ""),
                checked_at,
            ),
            "nats_publish": self._probe_nats_publish(checked_at),
            "jetstream": self._probe_jetstream(checked_at),
            "system_collector": self._probe_http(
                "system_collector",
                os.getenv("APM_SYSTEM_COLLECTOR_HEALTH_ENDPOINT", ""),
                checked_at,
            ),
            "victoria_traces": self._probe_http(
                "victoria_traces",
                os.getenv("APM_VICTORIATRACES_HEALTH_ENDPOINT") or _origin_health_url(traces_endpoint),
                checked_at,
                auth=(trace_user, trace_password) if trace_user else None,
            ),
            "victoria_traces_retention": self._retention_health(checked_at),
            "notification_responder": self._probe_notification_responder(checked_at),
        }
        return result


def pending_runtime_dependencies_health() -> dict[str, dict[str, str]]:
    return {component: {"status": "pending"} for component in RUNTIME_COMPONENTS}
