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
class EnabledApplications:
    """Enabled names for one read.

    ``applications`` is the controller registry when that list succeeds, otherwise
    the enabled Postgres catalog (and then the requested subset). ``catalog_empty``
    is about that full catalog, before the requested subset is applied.
    ``control_down`` is true only when the controller list failed as unavailable.
    """

    applications: list[str]
    control_down: bool = False
    catalog_empty: bool = False


@dataclass(frozen=True)
class ProductScope:
    applications: list[str]
    reason: str | None = None  # "control" | "analytics" | None
    control_down: bool = False

    @property
    def degraded(self) -> bool:
        return self.reason is not None or self.control_down


def postgres_enabled_application_names() -> list[str]:
    """Enabled application names from the Postgres catalog."""

    from apps.rum.models import RumApplication

    return list(RumApplication.objects.filter(enabled=True).order_by("-created_at", "name").values_list("name", flat=True))


def list_enabled_applications(
    control: ControlPlane,
    actor: str,
    requested: list[str] | None = None,
) -> EnabledApplications:
    """Resolve enabled application names for a read.

    A successful controller list is the registry. When that list fails as
    unavailable, the enabled Postgres ``RumApplication`` rows are the catalog.
    Disabled applications stay out of both paths.
    """

    try:
        _, data = control.request(SUBJECT_APPLICATION_LIST, actor, {})
    except ControlError as exc:
        if not control_unavailable(exc):
            raise
        catalog = postgres_enabled_application_names()
        control_down = True
    else:
        registry = data if isinstance(data, list) else []
        catalog = [item.get("application") for item in registry if item.get("application") and item.get("enabled", True)]
        control_down = False
    if requested:
        allowed = set(catalog)
        scoped = [name for name in requested if name in allowed]
    else:
        scoped = list(catalog)
    return EnabledApplications(applications=scoped, control_down=control_down, catalog_empty=not catalog)


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
    """Enabled names plus which plane is down.

    Controller failure still returns the Postgres enabled names and sets
    ``control_down``. ``reason`` stays a single string: ``control`` only when
    that fallback catalog is empty, ``analytics`` when the analytics plane is
    unavailable.
    """

    from apps.rum.services.analytics import get_analytics

    control = control or get_control_plane()
    analytics = analytics if analytics is not None else get_analytics()
    found = list_enabled_applications(control, actor)
    if found.control_down and found.catalog_empty:
        return ProductScope(applications=[], reason=REASON_CONTROL, control_down=True)
    if not analytics.available():
        return ProductScope(
            applications=list(found.applications),
            reason=REASON_ANALYTICS,
            control_down=found.control_down,
        )
    requested_names = [name.strip() for name in (requested or []) if str(name).strip()]
    if not requested_names:
        return ProductScope(
            applications=list(found.applications),
            reason=None,
            control_down=found.control_down,
        )
    allowed = set(found.applications)
    scoped = [name for name in requested_names if name in allowed]
    return ProductScope(applications=scoped, reason=None, control_down=found.control_down)
