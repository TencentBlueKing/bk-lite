from __future__ import annotations

import os
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


def pending_catalog_health() -> dict[str, str]:
    return {"status": "pending"}


def _origin_health_url(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, "/health", "", ""))


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

    @staticmethod
    def _dependencies() -> dict[str, tuple[str, tuple[str, str] | None]]:
        traces_endpoint = os.getenv("APM_VICTORIATRACES_QUERY_ENDPOINT", "http://127.0.0.1:10428")
        metrics_endpoint = os.getenv("APM_VICTORIAMETRICS_QUERY_ENDPOINT") or os.getenv("VICTORIAMETRICS_HOST", "")
        trace_user = os.getenv("APM_VICTORIATRACES_USER", "")
        trace_password = os.getenv("APM_VICTORIATRACES_PASSWORD", "")
        metrics_user = os.getenv("VICTORIAMETRICS_USER", "")
        metrics_password = os.getenv("VICTORIAMETRICS_PWD", "")
        return {
            "collector": (os.getenv("APM_COLLECTOR_HEALTH_ENDPOINT", ""), None),
            "trace_store": (
                os.getenv("APM_VICTORIATRACES_HEALTH_ENDPOINT") or _origin_health_url(traces_endpoint),
                (trace_user, trace_password) if trace_user else None,
            ),
            "metric_store": (
                os.getenv("APM_VICTORIAMETRICS_HEALTH_ENDPOINT") or _origin_health_url(metrics_endpoint),
                (metrics_user, metrics_password) if metrics_user else None,
            ),
        }

    def probe(self) -> dict[str, dict[str, str]]:
        checked_at = timezone.now().isoformat()
        result = {}
        for name, (endpoint, auth) in self._dependencies().items():
            if not endpoint:
                result[name] = {"status": "pending", "last_checked_at": checked_at}
                continue
            try:
                response = self.session.get(endpoint, auth=auth, timeout=(1, 2))
                response.raise_for_status()
            except requests.RequestException:
                result[name] = {
                    "status": "degraded",
                    "last_failed_at": checked_at,
                    "error_code": f"{name}_unavailable",
                }
            else:
                result[name] = {"status": "ok", "last_succeeded_at": checked_at}
        result["notification_responder"] = self._probe_notification_responder(checked_at)
        return result


def pending_runtime_dependencies_health() -> dict[str, dict[str, str]]:
    return {
        "collector": {"status": "pending"},
        "trace_store": {"status": "pending"},
        "metric_store": {"status": "pending"},
        "notification_responder": {"status": "pending"},
    }
