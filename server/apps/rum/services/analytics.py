from __future__ import annotations

from typing import Protocol

from apps.core.logger import rum_logger as logger
from apps.rum.services.query import (
    empty_error_detail,
    empty_error_list,
    empty_release_list,
    empty_session_journey,
    empty_session_list,
    empty_session_trend,
    empty_view_list,
)


class Analytics(Protocol):
    def available(self) -> bool:
        ...

    def list_sessions(self, tenant_id: str, opts: dict) -> dict:
        ...

    def session_trend(self, tenant_id: str, opts: dict) -> dict:
        ...

    def session_journey(self, tenant_id: str, application: str, session_id: str, opts: dict) -> dict:
        ...

    def list_views(self, tenant_id: str, opts: dict) -> dict:
        ...

    def list_error_issues(self, tenant_id: str, opts: dict) -> dict:
        ...

    def error_detail(self, tenant_id: str, fingerprint: str, opts: dict) -> dict:
        ...

    def funnel_reach(self, tenant_id: str, steps: list[str], opts: dict) -> dict:
        ...

    def list_releases(self, tenant_id: str, opts: dict) -> dict:
        ...

    def monitor_metric(self, tenant_id: str, opts: dict) -> float:
        ...

    def metric_series(self, tenant_id: str, opts: dict) -> list[dict]:
        ...


class UnavailableAnalytics:
    """Fallback when VictoriaLogs is not configured or unreachable."""

    def available(self) -> bool:
        return False

    def list_sessions(self, tenant_id: str, opts: dict) -> dict:
        return empty_session_list(reason="analytics")

    def session_trend(self, tenant_id: str, opts: dict) -> dict:
        return empty_session_trend(reason="analytics")

    def session_journey(self, tenant_id: str, application: str, session_id: str, opts: dict) -> dict:
        return empty_session_journey(reason="analytics")

    def list_views(self, tenant_id: str, opts: dict) -> dict:
        return empty_view_list(mode=opts.get("mode") or "route", reason="analytics")

    def list_error_issues(self, tenant_id: str, opts: dict) -> dict:
        return empty_error_list(reason="analytics")

    def error_detail(self, tenant_id: str, fingerprint: str, opts: dict) -> dict:
        return empty_error_detail(reason="analytics")

    def funnel_reach(self, tenant_id: str, steps: list[str], opts: dict) -> dict:
        return {"steps": list(steps), "reached": [], "analyticsUnavailable": True}

    def list_releases(self, tenant_id: str, opts: dict) -> dict:
        return empty_release_list(reason="analytics")

    def monitor_metric(self, tenant_id: str, opts: dict) -> float:
        raise RuntimeError("analytics unavailable")

    def metric_series(self, tenant_id: str, opts: dict) -> list[dict]:
        return []


_analytics: Analytics | None = None


def _build_analytics() -> Analytics:
    from apps.rum.services.settings import load_rum_settings
    from apps.rum.services.victoria_analytics import VictoriaAnalytics

    settings = load_rum_settings()
    if not settings.victoria_logs_url or not settings.victoria_traces_url:
        return UnavailableAnalytics()
    try:
        return VictoriaAnalytics.open(
            logs_endpoint=settings.victoria_logs_url,
            traces_endpoint=settings.victoria_traces_url,
            account_id=settings.victoria_account_id,
            project_id=settings.victoria_project_id,
            timeout_seconds=settings.victoria_timeout_seconds,
            ping=True,
        )
    except Exception as exc:  # noqa: BLE001 — degrade when VL is down
        logger.warning("rum victoria analytics unavailable: %s", exc)
        return UnavailableAnalytics()


def get_analytics() -> Analytics:
    global _analytics
    if _analytics is None:
        _analytics = _build_analytics()
    return _analytics


def set_analytics(analytics: Analytics | None) -> None:
    global _analytics
    _analytics = analytics
