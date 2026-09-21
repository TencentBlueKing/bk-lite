from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from apps.rum.constants import SUBJECT_APPLICATION_LIST
from apps.rum.services.analytics import Analytics, get_analytics
from apps.rum.services.control import ControlError, ControlPlane, control_unavailable, get_control_plane
from apps.rum.services.errors import SourcemapStore, _sourcemap_meta, get_sourcemap_store
from apps.rum.services.query import empty_release_list, parse_range_params
from apps.rum.services.settings import load_rum_settings
from apps.rum.services.sourcemap import asset_fingerprint, new_sourcemap_token, validate_sourcemap, verify_sourcemap_token
from apps.rum.services.validation import ValidationError, valid_application

_MAX_UPLOAD = 8 << 20


class BaselineStore(Protocol):
    def list(self) -> list[dict]:
        ...

    def upsert(self, application: str, baseline_release: str, actor: str) -> dict:
        ...


class MemoryBaselineStore:
    def __init__(self):
        self._items: dict[str, dict] = {}

    def list(self) -> list[dict]:
        return [dict(item) for item in self._items.values()]

    def upsert(self, application: str, baseline_release: str, actor: str) -> dict:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        current = self._items.get(application)
        if current is None:
            item = {
                "id": f"baseline-{len(self._items) + 1}",
                "application": application,
                "baselineRelease": baseline_release,
                "createdBy": actor,
                "updatedBy": actor,
                "createdAt": now,
                "updatedAt": now,
            }
        else:
            item = {
                **current,
                "baselineRelease": baseline_release,
                "updatedBy": actor,
                "updatedAt": now,
            }
        self._items[application] = item
        return dict(item)


class DjangoBaselineStore:
    def list(self) -> list[dict]:
        from apps.rum.models import RumReleaseBaseline

        return [_serialize_baseline(item) for item in RumReleaseBaseline.objects.all()]

    def upsert(self, application: str, baseline_release: str, actor: str) -> dict:
        from apps.rum.models import RumReleaseBaseline

        item, created = RumReleaseBaseline.objects.get_or_create(
            application=application,
            defaults={
                "baseline_release": baseline_release,
                "created_by": actor,
                "updated_by": actor,
            },
        )
        if not created:
            item.baseline_release = baseline_release
            item.updated_by = actor
            item.save()
        return _serialize_baseline(item)


def _serialize_baseline(item) -> dict:
    return {
        "id": item.id,
        "application": item.application,
        "baselineRelease": item.baseline_release,
        "createdBy": item.created_by,
        "updatedBy": item.updated_by,
        "createdAt": item.created_at.isoformat().replace("+00:00", "Z") if item.created_at else None,
        "updatedAt": item.updated_at.isoformat().replace("+00:00", "Z") if item.updated_at else None,
    }


_baseline_store: BaselineStore | None = None


def get_baseline_store() -> BaselineStore:
    global _baseline_store
    if _baseline_store is None:
        _baseline_store = DjangoBaselineStore()
    return _baseline_store


def set_baseline_store(store: BaselineStore | None) -> None:
    """Test seam."""
    global _baseline_store
    _baseline_store = store


class CredentialStore(Protocol):
    def get(self, application: str) -> dict | None:
        ...

    def upsert(self, application: str, token_digest: str, actor: str) -> dict:
        ...


class MemoryCredentialStore:
    def __init__(self):
        self._items: dict[str, dict] = {}

    def get(self, application: str) -> dict | None:
        item = self._items.get(application)
        return dict(item) if item else None

    def upsert(self, application: str, token_digest: str, actor: str) -> dict:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        item = {
            "application": application,
            "tokenDigest": token_digest,
            "createdBy": actor,
            "createdAt": now,
            "updatedAt": now,
        }
        self._items[application] = item
        return dict(item)


class DjangoCredentialStore:
    def get(self, application: str) -> dict | None:
        from apps.rum.models import RumSourcemapCredential

        try:
            item = RumSourcemapCredential.objects.get(pk=application)
        except RumSourcemapCredential.DoesNotExist:
            return None
        return _serialize_credential(item)

    def upsert(self, application: str, token_digest: str, actor: str) -> dict:
        from apps.rum.models import RumSourcemapCredential

        item, created = RumSourcemapCredential.objects.get_or_create(
            application=application,
            defaults={"token_digest": token_digest, "created_by": actor},
        )
        if not created:
            item.token_digest = token_digest
            if actor and not item.created_by:
                item.created_by = actor
            item.save()
        return _serialize_credential(item)


def _serialize_credential(item) -> dict:
    return {
        "application": item.application,
        "tokenDigest": item.token_digest,
        "createdBy": item.created_by,
        "createdAt": item.created_at.isoformat().replace("+00:00", "Z") if item.created_at else None,
        "updatedAt": item.updated_at.isoformat().replace("+00:00", "Z") if item.updated_at else None,
    }


_credential_store: CredentialStore | None = None


def get_credential_store() -> CredentialStore:
    global _credential_store
    if _credential_store is None:
        _credential_store = DjangoCredentialStore()
    return _credential_store


def set_credential_store(store: CredentialStore | None) -> None:
    """Test seam."""
    global _credential_store
    _credential_store = store


class ReleasesService:
    def __init__(
        self,
        control: ControlPlane | None = None,
        analytics: Analytics | None = None,
        baselines: BaselineStore | None = None,
        sourcemaps: SourcemapStore | None = None,
        credentials: CredentialStore | None = None,
    ):
        self.control = control or get_control_plane()
        self.analytics = analytics or get_analytics()
        self.baselines = baselines or get_baseline_store()
        self.sourcemaps = sourcemaps or get_sourcemap_store()
        self.credentials = credentials or get_credential_store()
        self.settings = load_rum_settings()

    def _list_enabled_apps(self, actor: str) -> tuple[list[str], str | None]:
        try:
            _, data = self.control.request(SUBJECT_APPLICATION_LIST, actor, {})
        except ControlError as exc:
            if control_unavailable(exc):
                return [], "control"
            raise
        registry = data if isinstance(data, list) else []
        return [item.get("application") for item in registry if item.get("application") and item.get("enabled", True)], None

    def _requested_apps(self, params: dict[str, Any]) -> list[str]:
        apps: list[str] = []
        single = (params.get("application") or "").strip()
        if single:
            apps.append(single)
        multi = params.get("applications")
        if isinstance(multi, str) and multi.strip():
            apps.extend([part.strip() for part in multi.split(",") if part.strip()])
        elif isinstance(multi, list):
            apps.extend([str(part).strip() for part in multi if str(part).strip()])
        return apps

    def _require_application(self, actor: str, application: str) -> None:
        application = (application or "").strip()
        if not application or not valid_application(application):
            raise ValidationError("invalid application")
        enabled, reason = self._list_enabled_apps(actor)
        if reason == "control":
            raise ControlError("unavailable", "RUM controller is unavailable")
        if application not in enabled:
            raise ControlError("not_found", "application not found")

    def list_releases(self, actor: str, params: dict[str, Any]) -> dict:
        try:
            start, end = parse_range_params(params)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        enabled, reason = self._list_enabled_apps(actor)
        if reason == "control":
            return empty_release_list(reason="control")
        requested = self._requested_apps(params)
        apps = [name for name in requested if name in enabled] if requested else enabled
        if not self.analytics.available():
            return empty_release_list(reason="analytics")
        limit = int(params.get("limit") or 0)
        page = self.analytics.list_releases(
            self.settings.tenant_id,
            {
                "from": start,
                "to": end,
                "applications": apps,
                "traffic": params.get("traffic") or "visitors",
                "limit": limit,
            },
        )
        rows = list(page.get("releases") or [])
        if len(apps) == 1:
            baselines = {item["application"]: item["baselineRelease"] for item in self.baselines.list() if item.get("application") == apps[0]}
            baseline_release = baselines.get(apps[0])
            baseline_row = None
            if baseline_release:
                for row in rows:
                    if row.get("release") == baseline_release:
                        row["isBaseline"] = True
                        baseline_row = row
                        break
            if baseline_row is not None:
                for row in rows:
                    if row is baseline_row:
                        continue
                    error_delta = int(row.get("errorCount") or 0) - int(baseline_row.get("errorCount") or 0)
                    sessions_delta = int(row.get("affectedSessions") or 0) - int(baseline_row.get("affectedSessions") or 0)
                    users_delta = int(row.get("affectedUsers") or 0) - int(baseline_row.get("affectedUsers") or 0)
                    issues_delta = int(row.get("distinctIssues") or 0) - int(baseline_row.get("distinctIssues") or 0)
                    lcp_delta = float(row.get("lcpP75") or 0) - float(baseline_row.get("lcpP75") or 0)
                    inp_delta = float(row.get("inpP75") or 0) - float(baseline_row.get("inpP75") or 0)
                    row["errorDelta"] = error_delta
                    row["sessionsDelta"] = sessions_delta
                    row["usersDelta"] = users_delta
                    row["issuesDelta"] = issues_delta
                    row["lcpP75Delta"] = lcp_delta
                    row["inpP75Delta"] = inp_delta
                    row["suspectedRegression"] = error_delta > 0 or lcp_delta > 0 or inp_delta > 0
        return {**page, "releases": rows}

    def put_baseline(self, actor: str, application: str, body: dict) -> dict:
        application = (application or "").strip()
        baseline_release = (body.get("baselineRelease") or "").strip()
        if not baseline_release:
            raise ValidationError("baselineRelease is required")
        self._require_application(actor, application)
        return self.baselines.upsert(application, baseline_release, actor)

    def list_sourcemaps(self, actor: str, params: dict[str, Any]) -> list[dict]:
        application = (params.get("application") or "").strip()
        if not application:
            # Sourcemaps are listed per application only; no registry-wide dump.
            raise ValidationError("application is required")
        self._require_application(actor, application)
        return self.sourcemaps.list(application)

    def _save_sourcemap(self, application: str, release: str, asset: str, raw: bytes, actor: str) -> dict:
        if len(raw) > _MAX_UPLOAD:
            raise ValidationError("sourcemap exceeds upload size limit")
        try:
            content = validate_sourcemap(raw)
        except ValueError as exc:
            raise ValidationError("invalid sourcemap") from exc
        stored = self.sourcemaps.save(application, release, asset, content, created_by=actor)
        return _sourcemap_meta(stored)

    def upload_sourcemap(self, actor: str, form: dict[str, Any], raw: bytes) -> dict:
        application = (form.get("application") or "").strip()
        release = (form.get("release") or "").strip()
        asset = asset_fingerprint(form.get("asset") or "")
        if not application or not release or not asset:
            raise ValidationError("application, release, and asset are required")
        self._require_application(actor, application)
        return self._save_sourcemap(application, release, asset, raw, actor)

    def rotate_credential(self, actor: str, application: str) -> dict:
        application = (application or "").strip()
        self._require_application(actor, application)
        token, digest = new_sourcemap_token()
        credential = self.credentials.upsert(application, digest, actor)
        return {
            "application": application,
            "token": token,
            "createdAt": credential.get("updatedAt") or credential.get("createdAt"),
        }

    def ingest_sourcemap(self, authorization: str, params: dict[str, Any], raw: bytes) -> dict:
        application = (params.get("application") or "").strip()
        release = (params.get("release") or "").strip()
        asset = asset_fingerprint(params.get("asset") or "")
        auth = (authorization or "").strip()
        if not application or not release or not asset or not auth.lower().startswith("bearer "):
            raise ValidationError("application, release, asset, and Bearer token are required")
        token = auth[7:].strip()
        credential = self.credentials.get(application)
        if credential is None or not verify_sourcemap_token(token, credential.get("tokenDigest") or ""):
            raise ControlError("forbidden", "invalid sourcemap credential")
        return self._save_sourcemap(application, release, asset, raw, f"ci:{application}")
