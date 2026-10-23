from __future__ import annotations

import hashlib
from typing import Any

from cryptography.fernet import InvalidToken
from django.db import transaction

from apps.core.mixinx import EncryptMixin
from apps.rum.constants import DEFAULT_BUDGETS, MAX_ORIGINS, SUBJECT_APPLICATION_GET
from apps.rum.services.analytics import Analytics, get_analytics
from apps.rum.services.control import ControlError, ControlPlane, control_unavailable
from apps.rum.services.health import probe_pipeline_health
from apps.rum.services.projection import PublishService
from apps.rum.services.settings import RumRuntimeSettings, load_rum_settings
from apps.rum.services.snippets import build_snippet, parse_analytics_range
from apps.rum.services.status import build_status
from apps.rum.services.validation import ValidationError, canonical_origins, new_browser_key, valid_application, valid_budgets

MAX_ACTIVE_KEYS = 2


def key_digest(value: str) -> str:
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


def encrypt_browser_key(value: str) -> str:
    suite = EncryptMixin.get_cipher_suite()
    return suite.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_browser_key(cipher: str) -> str:
    try:
        suite = EncryptMixin.get_cipher_suite()
        return suite.decrypt(cipher.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return ""


def _budget_columns(budgets: dict) -> dict:
    return {
        "requests_per_minute": int(budgets["requestsPerMinute"]),
        "compressed_bytes_per_minute": int(budgets["compressedBytesPerMinute"]),
        "decompressed_bytes_per_minute": int(budgets["decompressedBytesPerMinute"]),
        "events_per_minute": int(budgets["eventsPerMinute"]),
    }


def _budgets_json(app) -> dict:
    return {
        "requestsPerMinute": int(app.requests_per_minute),
        "compressedBytesPerMinute": int(app.compressed_bytes_per_minute),
        "decompressedBytesPerMinute": int(app.decompressed_bytes_per_minute),
        "eventsPerMinute": int(app.events_per_minute),
    }


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
        return self.list_applications(actor)

    def list_applications(self, actor: str) -> list[dict]:
        from apps.rum.models import RumApplication

        unavailable = not self.control.available()
        return [
            strip_browser_keys(self._view(app.name, include_keys=False, control_down=unavailable))
            for app in RumApplication.objects.all().order_by("-created_at", "name")
        ]

    def get_application(self, actor: str, name: str) -> dict:
        if not valid_application(name):
            raise ValidationError("invalid application")
        from apps.rum.models import RumApplication

        if not RumApplication.objects.filter(name=name).exists():
            raise ControlError("not_found", "application not found")
        return self._view(name, include_keys=True, control_down=not self.control.available())

    def create_application(self, actor: str, body: dict) -> tuple[int, dict]:
        name = (body.get("application") or "").strip()
        if not valid_application(name):
            raise ValidationError("invalid application")
        origins = canonical_origins(body.get("origins"))
        budgets = body.get("budgets") or dict(DEFAULT_BUDGETS)
        if not valid_budgets(budgets):
            raise ValidationError("invalid budgets")
        return self._commit(
            actor,
            name,
            origins=origins,
            enabled=True,
            budgets=budgets,
            extra_keys=[new_browser_key()],
            create=True,
        )

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
        return self._commit(actor, name, origins=origins, enabled=enabled, budgets=budgets, extra_keys=[], create=False)

    def reissue_key(self, actor: str, name: str) -> tuple[int, dict]:
        current = self.get_application(actor, name)
        return self._commit(
            actor,
            name,
            origins=list(current.get("origins") or []),
            enabled=bool(current.get("enabled", True)),
            budgets=current.get("budgets") or dict(DEFAULT_BUDGETS),
            extra_keys=[new_browser_key()],
            create=False,
        )

    def disable_application(self, actor: str, name: str) -> tuple[int, dict]:
        current = self.get_application(actor, name)
        return self._commit(
            actor,
            name,
            origins=list(current.get("origins") or []),
            enabled=False,
            budgets=current.get("budgets") or dict(DEFAULT_BUDGETS),
            extra_keys=[],
            create=False,
        )

    def _commit(
        self,
        actor: str,
        name: str,
        *,
        origins: list[str],
        enabled: bool,
        budgets: dict,
        extra_keys: list[str],
        create: bool,
    ) -> tuple[int, dict]:
        from apps.rum.models import RumApplication, RumApplicationKey, RumApplicationOrigin, RumProjectionOutbox

        if len(origins) > MAX_ORIGINS:
            raise ValidationError("too many origins")
        with transaction.atomic():
            if create:
                if RumApplication.objects.filter(name=name).exists():
                    raise ValidationError("application already exists")
                app = RumApplication.objects.create(
                    name=name,
                    tenant_id=self.settings.tenant_id,
                    org_id=self.settings.tenant_id,
                    enabled=enabled,
                    revision=0,
                    created_by=actor,
                    **_budget_columns(budgets),
                )
            else:
                app = RumApplication.objects.filter(name=name).first()
                if app is None:
                    raise ControlError("not_found", "application not found")
                app.enabled = enabled
                app.org_id = app.org_id or self.settings.tenant_id
                for column, value in _budget_columns(budgets).items():
                    setattr(app, column, value)
            active = RumApplicationKey.objects.filter(application=name, status="active").count()
            if active + len(extra_keys) > MAX_ACTIVE_KEYS:
                raise ValidationError("at most 2 active browser keys; retire one before issuing another")
            for plain in extra_keys:
                RumApplicationKey.objects.create(
                    application=name,
                    key_cipher=encrypt_browser_key(plain),
                    key_digest=key_digest(plain),
                    status="active",
                )
            app.revision = int(app.revision or 0) + 1
            app.save()
            RumApplicationOrigin.objects.filter(application=name).delete()
            RumApplicationOrigin.objects.bulk_create(
                [RumApplicationOrigin(application=name, origin=origin) for origin in origins]
            )
            digests = list(
                RumApplicationKey.objects.filter(application=name, status="active")
                .order_by("created_at")
                .values_list("key_digest", flat=True)
            )
            payload = {
                "application": name,
                "tenantId": app.tenant_id,
                "orgId": app.org_id,
                "enabled": app.enabled,
                "revision": int(app.revision),
                "budgets": _budgets_json(app),
                "origins": list(origins),
                "browserKeyDigests": digests,
            }
            outbox = RumProjectionOutbox.objects.create(
                kind="application",
                application=name,
                revision=int(app.revision),
                payload_json=payload,
                status="pending",
            )
            revision = int(app.revision)
            outbox_id = outbox.id
        published, _data = PublishService(self.control).publish(outbox_id)
        view = self._view(name, include_keys=True, control_down=not self.control.available())
        if not published:
            view["projectionPending"] = True
        return revision, view

    def _view(self, name: str, *, include_keys: bool, control_down: bool) -> dict:
        from apps.rum.models import RumApplication, RumApplicationKey, RumApplicationOrigin

        app = RumApplication.objects.get(name=name)
        origins = list(
            RumApplicationOrigin.objects.filter(application=name).order_by("origin").values_list("origin", flat=True)
        )
        key_rows = list(RumApplicationKey.objects.filter(application=name, status="active").order_by("created_at"))
        plain: list[str] = []
        if include_keys:
            for row in key_rows:
                value = decrypt_browser_key(row.key_cipher)
                if value:
                    plain.append(value)
        accepted, stored, unavailable = self._timestamps(name, control_down)
        view = {
            "application": app.name,
            "tenantId": app.tenant_id,
            "orgId": app.org_id,
            "enabled": app.enabled,
            "revision": int(app.revision),
            "browserKeys": plain,
            "browserKeyDigests": [row.key_digest for row in key_rows],
            "origins": origins,
            "budgets": _budgets_json(app),
            "lastAcceptedAt": accepted,
            "lastStoredAt": stored,
        }
        if unavailable:
            view["controlUnavailable"] = True
        if not include_keys:
            view.pop("browserKeys", None)
        return view

    def _timestamps(self, name: str, control_down: bool) -> tuple[int, int, bool]:
        if control_down or not self.control.available():
            return 0, 0, True
        try:
            _, data = self.control.request(SUBJECT_APPLICATION_GET, "system", {"application": name})
        except ControlError as exc:
            if control_unavailable(exc):
                return 0, 0, True
            return 0, 0, False
        if not isinstance(data, dict):
            return 0, 0, False
        return int(data.get("lastAcceptedAt") or 0), int(data.get("lastStoredAt") or 0), False

    def status(self, actor: str, name: str) -> dict:
        if not valid_application(name):
            raise ValidationError("invalid application")
        try:
            view = self.get_application(actor, name)
        except ControlError as exc:
            if control_unavailable(exc):
                return build_status(None, application=name, controller_unreachable=True)
            raise
        return build_status(
            view,
            application=name,
            controller_unreachable=bool(view.get("controlUnavailable")),
        )

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
            control_down = bool(view.get("controlUnavailable"))
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
        registry = self._load_registry(actor)
        control_down = not self.control.available()
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
            "publicOrigin": self.settings.public_origin,
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
