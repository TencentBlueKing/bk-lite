from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.rum.constants import SUBJECT_APPLICATION_LIST
from apps.rum.services.control import ControlError, ControlPlane, control_unavailable, get_control_plane
from apps.rum.services.settings import RumRuntimeSettings, load_rum_settings

REASON_CONTROL = "control"
REASON_ANALYTICS = "analytics"


@dataclass(frozen=True)
class PipelineHealth:
    control_configured: bool
    analytics_configured: bool
    control_available: bool
    analytics_available: bool

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
        }
        if self.control_unavailable:
            payload["controlUnavailable"] = True
        if self.analytics_unavailable:
            payload["analyticsUnavailable"] = True
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
) -> PipelineHealth:
    """Probe control + analytics availability for /meta and /health."""

    from apps.rum.services.analytics import get_analytics

    settings = settings or load_rum_settings()
    control = control or get_control_plane()
    analytics = analytics if analytics is not None else get_analytics()

    control_configured = bool(settings.nats_url) or control.available()
    analytics_configured = bool(settings.victoria_logs_url and settings.victoria_traces_url)

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
    )


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
