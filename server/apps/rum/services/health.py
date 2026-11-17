from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.core.logger import rum_logger as logger
from apps.rum.constants import SUBJECT_APPLICATION_LIST
from apps.rum.services.control import ControlError, ControlPlane, control_unavailable, get_control_plane
from apps.rum.services.settings import RumRuntimeSettings, load_rum_settings
from apps.rum.services.victoria_client import ping_health

REASON_CONTROL = "control"
REASON_ANALYTICS = "analytics"
_TRACES_PROBE_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class PipelineHealth:
    control_configured: bool
    analytics_configured: bool
    control_available: bool
    analytics_available: bool
    traces_configured: bool
    traces_available: bool | None = None

    @property
    def control_unavailable(self) -> bool:
        return not self.control_available

    @property
    def analytics_unavailable(self) -> bool:
        return not self.analytics_available

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "controlConfigured": self.control_configured,
            "analyticsConfigured": self.analytics_configured,
            "controlAvailable": self.control_available,
            "analyticsAvailable": self.analytics_available,
            "tracesConfigured": self.traces_configured,
        }
        if self.control_unavailable:
            payload["controlUnavailable"] = True
        if self.analytics_unavailable:
            payload["analyticsUnavailable"] = True
        if self.traces_available is not None:
            payload["tracesAvailable"] = self.traces_available
            if not self.traces_available:
                payload["tracesUnavailable"] = True
        return payload


@dataclass(frozen=True)
class ProductScope:
    applications: list[str]
    reason: str | None = None  # "control" | "analytics" | None

    @property
    def degraded(self) -> bool:
        return self.reason is not None


def probe_pipeline_health(
    *,
    control: ControlPlane | None = None,
    analytics=None,
    settings: RumRuntimeSettings | None = None,
    actor: str = "system",
    probe_traces: bool = False,
) -> PipelineHealth:
    """Probe control + analytics availability for /meta and /health.

    VictoriaTraces is only probed when ``probe_traces`` is set (the /health check), so page loads
    such as /meta never wait on it.
    """

    from apps.rum.services.analytics import get_analytics

    settings = settings or load_rum_settings()
    control = control or get_control_plane()
    analytics = analytics if analytics is not None else get_analytics()

    control_configured = bool(settings.nats_url) or control.available()
    analytics_configured = bool(settings.victoria_logs_url)
    traces_configured = bool(settings.victoria_traces_url)
    traces_available = _traces_available(settings) if probe_traces else None

    control_available = False
    if control.available():
        try:
            control.request(SUBJECT_APPLICATION_LIST, actor, {})
            control_available = True
        except ControlError as exc:
            control_available = not control_unavailable(exc)
        except Exception:  # noqa: BLE001
            control_available = False

    analytics_available = bool(analytics.available())
    return PipelineHealth(
        control_configured=control_configured,
        analytics_configured=analytics_configured,
        control_available=control_available,
        analytics_available=analytics_available,
        traces_configured=traces_configured,
        traces_available=traces_available,
    )


def _traces_available(settings: RumRuntimeSettings) -> bool:
    """VictoriaTraces reachability. Empty or failed probes stay independent of analytics."""

    if not settings.victoria_traces_url:
        return False
    try:
        ping_health(
            settings.victoria_traces_url,
            timeout_seconds=min(settings.victoria_timeout_seconds or _TRACES_PROBE_TIMEOUT_SECONDS, _TRACES_PROBE_TIMEOUT_SECONDS),
            label="VictoriaTraces",
        )
    except Exception as exc:  # noqa: BLE001 — traces health is reported; analytics stays independent
        logger.warning(
            "rum traces health unavailable failed_stage=%s error_type=%s",
            "traces_health",
            type(exc).__name__,
        )
        return False
    return True


def resolve_product_scope(
    actor: str,
    requested: list[str] | None = None,
    *,
    control: ControlPlane | None = None,
    analytics=None,
) -> ProductScope:
    """Empty page + reason when the control/analytics pipeline is down."""

    from apps.rum.services.analytics import get_analytics

    control = control or get_control_plane()
    analytics = analytics if analytics is not None else get_analytics()
    try:
        _, data = control.request(SUBJECT_APPLICATION_LIST, actor, {})
    except ControlError as exc:
        if control_unavailable(exc):
            return ProductScope(applications=[], reason=REASON_CONTROL)
        raise
    registry = data if isinstance(data, list) else []
    enabled = [item.get("application") for item in registry if item.get("application") and item.get("enabled", True)]
    if not analytics.available():
        return ProductScope(applications=enabled, reason=REASON_ANALYTICS)
    requested = [name.strip() for name in (requested or []) if str(name).strip()]
    if not requested:
        return ProductScope(applications=enabled, reason=None)
    enabled_set = set(enabled)
    scoped = [name for name in requested if name in enabled_set]
    return ProductScope(applications=scoped, reason=None)
