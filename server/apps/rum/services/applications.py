from __future__ import annotations

from typing import Any

from apps.rum.constants import DEFAULT_BUDGETS, SUBJECT_APPLICATION_APPLY, SUBJECT_APPLICATION_GET, SUBJECT_APPLICATION_LIST
from apps.rum.services.analytics import Analytics, get_analytics
from apps.rum.services.control import ControlError, ControlPlane, control_unavailable
from apps.rum.services.health import probe_pipeline_health
from apps.rum.services.settings import RumRuntimeSettings, load_rum_settings
from apps.rum.services.snippets import build_snippet, parse_analytics_range
from apps.rum.services.status import build_status
from apps.rum.services.validation import ValidationError, canonical_origins, new_browser_key, valid_application, valid_budgets


def strip_browser_keys(view: Any) -> Any:
    """Drop plaintext browser keys from a registry view; digests stay for display."""
    if not isinstance(view, dict):
        return view
    return {key: value for key, value in view.items() if key != "browserKeys"}


class ApplicationsService:
    def __init__(
        self,
        control: ControlPlane,
        settings: RumRuntimeSettings | None = None,
        analytics: Analytics | None = None,
    ):
        self.control = control
        self.settings = settings or load_rum_settings()
        self.analytics = analytics if analytics is not None else get_analytics()

    def _load_registry(self, actor: str) -> list[dict]:
        _, data = self.control.request(SUBJECT_APPLICATION_LIST, actor, {})
        if data is None:
            return []
        if not isinstance(data, list):
            raise ControlError("internal_error", "controller list payload must be an array")
        # The list is a registry overview; browser keys are only handed out
        # per application (get / keys) so one call cannot dump every key.
        return [strip_browser_keys(item) for item in data]

    def list_applications(self, actor: str) -> list[dict]:
        try:
            return self._load_registry(actor)
        except ControlError as exc:
            if control_unavailable(exc):
                return []
            raise

    def get_application(self, actor: str, name: str) -> dict:
        if not valid_application(name):
            raise ValidationError("invalid application")
        _, data = self.control.request(SUBJECT_APPLICATION_GET, actor, {"application": name})
        if not isinstance(data, dict):
            raise ControlError("internal_error", "controller get payload must be an object")
        return data

    def create_application(self, actor: str, body: dict) -> tuple[int, dict]:
        name = (body.get("application") or "").strip()
        if not valid_application(name):
            raise ValidationError("invalid application")
        origins = canonical_origins(body.get("origins"))
        budgets = body.get("budgets") or dict(DEFAULT_BUDGETS)
        if not valid_budgets(budgets):
            raise ValidationError("invalid budgets")
        key = new_browser_key()
        payload = {
            "application": name,
            # Organization is derived from the deployment, never from the caller.
            "orgId": self.settings.tenant_id,
            "enabled": True,
            "browserKeys": [key],
            "origins": origins,
            "budgets": budgets,
        }
        revision, data = self.control.request(SUBJECT_APPLICATION_APPLY, actor, payload, expected_revision=0)
        return revision, data

    def update_application(self, actor: str, name: str, body: dict) -> tuple[int, dict]:
        current = self.get_application(actor, name)
        origins = current.get("origins") or []
        if "origins" in body and body["origins"] is not None:
            origins = canonical_origins(body["origins"])
        enabled = current.get("enabled", True)
        if "enabled" in body and body["enabled"] is not None:
            enabled = bool(body["enabled"])
        budgets = current.get("budgets") or dict(DEFAULT_BUDGETS)
        if body.get("budgets") is not None:
            budgets = body["budgets"]
            if not valid_budgets(budgets):
                raise ValidationError("invalid budgets")
        payload = {
            "application": name,
            "orgId": current.get("orgId") or "",
            "enabled": enabled,
            "browserKeys": list(current.get("browserKeys") or []),
            "origins": origins,
            "budgets": budgets,
        }
        revision, data = self.control.request(
            SUBJECT_APPLICATION_APPLY,
            actor,
            payload,
            expected_revision=int(current.get("revision") or 0),
        )
        return revision, data

    def reissue_key(self, actor: str, name: str) -> tuple[int, dict]:
        current = self.get_application(actor, name)
        keys = list(current.get("browserKeys") or [])
        keys.append(new_browser_key())
        payload = {
            "application": name,
            "orgId": current.get("orgId") or "",
            "enabled": bool(current.get("enabled", True)),
            "browserKeys": keys,
            "origins": list(current.get("origins") or []),
            "budgets": current.get("budgets") or dict(DEFAULT_BUDGETS),
        }
        revision, data = self.control.request(
            SUBJECT_APPLICATION_APPLY,
            actor,
            payload,
            expected_revision=int(current.get("revision") or 0),
        )
        return revision, data

    def disable_application(self, actor: str, name: str) -> tuple[int, dict]:
        current = self.get_application(actor, name)
        payload = {
            "application": name,
            "orgId": current.get("orgId") or "",
            "enabled": False,
            "browserKeys": list(current.get("browserKeys") or []),
            "origins": list(current.get("origins") or []),
            "budgets": current.get("budgets") or dict(DEFAULT_BUDGETS),
        }
        revision, data = self.control.request(
            SUBJECT_APPLICATION_APPLY,
            actor,
            payload,
            expected_revision=int(current.get("revision") or 0),
        )
        return revision, data

    def status(self, actor: str, name: str) -> dict:
        if not valid_application(name):
            raise ValidationError("invalid application")
        try:
            view = self.get_application(actor, name)
        except ControlError as exc:
            if control_unavailable(exc):
                return build_status(None, application=name, controller_unreachable=True)
            raise
        return build_status(view, application=name)

    def overview(self, actor: str, name: str, range_key: str | None) -> dict:
        from datetime import datetime, timedelta, timezone

        key, ok = parse_analytics_range(range_key)
        if not ok:
            raise ValidationError("invalid range")
        if not valid_application(name):
            raise ValidationError("invalid application")
        try:
            view = self.get_application(actor, name)
            enabled = bool(view.get("enabled"))
            control_down = False
        except ControlError as exc:
            if not control_unavailable(exc):
                raise
            enabled = False
            control_down = True
        payload: dict[str, Any] = {
            "application": name,
            "enabled": enabled,
            "range": key,
            "kpi": {
                "application": name,
                "sessions": 0,
                "views": 0,
                "errors": 0,
                "lcpP75": 0,
                "inpP75": 0,
                "errorRate": 0,
            },
            "sparkline": [],
            "trend": [],
            "countries": [],
            "devices": {"mobile": 0, "desktop": 0},
            "environments": [],
            "releases": [],
        }
        if control_down:
            payload["controlUnavailable"] = True
        if not self.analytics.available():
            payload["analyticsUnavailable"] = True
            return payload
        end = datetime.now(timezone.utc)
        windows = {"1h": timedelta(hours=1), "24h": timedelta(hours=24), "7d": timedelta(days=7)}
        start = end - windows[key]
        overview = self.analytics.application_overview(self.settings.tenant_id, name, start, end)  # type: ignore[attr-defined]
        payload.update(
            {
                "kpi": overview.get("kpi") or payload["kpi"],
                "sparkline": overview.get("sparkline") or [],
                "trend": overview.get("trend") or [],
                "countries": overview.get("countries") or [],
                "devices": overview.get("devices") or payload["devices"],
                "environments": overview.get("environments") or [],
                "releases": overview.get("releases") or [],
            }
        )
        return payload

    def analytics_catalog(self, actor: str, range_key: str | None) -> dict:
        from datetime import datetime, timedelta, timezone

        key, ok = parse_analytics_range(range_key)
        if not ok:
            raise ValidationError("invalid range")
        try:
            registry = self._load_registry(actor)
            control_down = False
        except ControlError as exc:
            if not control_unavailable(exc):
                raise
            registry = []
            control_down = True
        enabled_apps = [item.get("application") for item in registry if item.get("application") and item.get("enabled", True)]
        applications = [
            {
                "application": item.get("application"),
                "enabled": bool(item.get("enabled")),
                "sessions": 0,
                "views": 0,
                "errors": 0,
                "lcpP75": 0,
                "inpP75": 0,
                "errorRate": 0,
            }
            for item in registry
        ]
        page = {
            "configured": bool(registry) and not control_down,
            "range": key,
            "applications": applications,
            "sparklines": {},
            "kpi": {
                "poorApps": 0,
                "sessions": 0,
                "views": 0,
                "errors": 0,
                "worstLcp": 0,
                "worstInp": 0,
            },
        }
        if control_down:
            page["configured"] = False
            page["controlUnavailable"] = True
        if not self.analytics.available():
            page["configured"] = False
            page["analyticsUnavailable"] = True
            return page
        end = datetime.now(timezone.utc)
        windows = {"1h": timedelta(hours=1), "24h": timedelta(hours=24), "7d": timedelta(days=7)}
        start = end - windows[key]
        rows, sparks = self.analytics.applications_page(self.settings.tenant_id, start, end, enabled_apps)  # type: ignore[attr-defined]
        by_app = {row["application"]: row for row in rows}
        for item in page["applications"]:
            health = by_app.get(item["application"])
            if not health:
                continue
            item.update(
                {
                    "sessions": health.get("sessions") or 0,
                    "views": health.get("views") or 0,
                    "errors": health.get("errors") or 0,
                    "lcpP75": health.get("lcpP75") or 0,
                    "inpP75": health.get("inpP75") or 0,
                    "errorRate": health.get("errorRate") or 0,
                    "environment": health.get("environment") or "",
                    "release": health.get("release") or "",
                    "sdkVersion": health.get("sdkVersion") or "",
                    "lastSeenMs": health.get("lastSeenMs") or 0,
                }
            )
        page["sparklines"] = sparks
        if not control_down:
            page["configured"] = True
        kpi = page["kpi"]
        for item in page["applications"]:
            if not item.get("enabled"):
                continue
            kpi["sessions"] += int(item.get("sessions") or 0)
            kpi["views"] += int(item.get("views") or 0)
            kpi["errors"] += int(item.get("errors") or 0)
            kpi["worstLcp"] = max(kpi["worstLcp"], float(item.get("lcpP75") or 0))
            kpi["worstInp"] = max(kpi["worstInp"], float(item.get("inpP75") or 0))
        return page

    def meta(self) -> dict:
        health = probe_pipeline_health(
            control=self.control,
            analytics=self.analytics,
            settings=self.settings,
        )
        return {
            "collectUrl": self.settings.collect_url,
            "replayUrl": self.settings.replay_url,
            "sdkCdnUrl": self.settings.sdk_cdn_url,
            **health.as_dict(),
        }

    def health(self, actor: str = "system") -> dict:
        """Pipeline probe used by UI banners and ops checks."""

        return probe_pipeline_health(
            control=self.control,
            analytics=self.analytics,
            settings=self.settings,
            actor=actor,
        ).as_dict()

    def snippets(self, body: dict) -> dict:
        return build_snippet(body, self.settings.sdk_cdn_url)
