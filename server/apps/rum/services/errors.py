from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from apps.rum.constants import SUBJECT_APPLICATION_LIST
from apps.rum.services.analytics import Analytics, get_analytics
from apps.rum.services.control import ControlError, ControlPlane, control_unavailable, get_control_plane
from apps.rum.services.query import empty_error_detail, empty_error_list, parse_range_params
from apps.rum.services.settings import load_rum_settings
from apps.rum.services.sourcemap import (
    OUTCOME_INVALID,
    OUTCOME_MISSING_ARTIFACT,
    OUTCOME_MISSING_RELEASE,
    OUTCOME_RESOLVED,
    OUTCOME_UNMAPPED,
    parse_frames,
    restore_frames,
)
from apps.rum.services.validation import ValidationError, valid_application


def match_issue_status(status: str, filter_value: str | None) -> bool:
    filter_value = (filter_value or "").strip()
    if filter_value in {"", "all"}:
        return True
    if filter_value == "active":
        return status not in {"resolved", "ignored"}
    return status == filter_value


class IssueStore(Protocol):
    def get(self, fingerprint: str) -> dict | None:
        ...

    def upsert(self, issue: dict) -> dict:
        ...


class MemoryIssueStore:
    def __init__(self):
        self._items: dict[str, dict] = {}

    def get(self, fingerprint: str) -> dict | None:
        item = self._items.get(fingerprint)
        return dict(item) if item else None

    def upsert(self, issue: dict) -> dict:
        current = self._items.get(issue["fingerprint"], {})
        merged = {**current, **issue}
        if "id" not in merged:
            merged["id"] = f"issue-{len(self._items) + 1}"
        if "createdAt" not in merged:
            merged["createdAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        merged["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._items[merged["fingerprint"]] = merged
        return dict(merged)


class DjangoIssueStore:
    def get(self, fingerprint: str) -> dict | None:
        from apps.rum.models import RumIssue

        try:
            item = RumIssue.objects.get(fingerprint=fingerprint)
        except RumIssue.DoesNotExist:
            return None
        return _serialize_issue(item)

    def upsert(self, issue: dict) -> dict:
        from apps.rum.models import RumIssue

        item, _ = RumIssue.objects.get_or_create(
            fingerprint=issue["fingerprint"],
            defaults={"status": issue.get("status") or "open"},
        )
        if issue.get("status"):
            item.status = issue["status"]
        if "note" in issue and issue["note"] is not None:
            item.note = issue["note"]
        if issue.get("resolvedVersion"):
            item.resolved_version = issue["resolvedVersion"]
        if item.status == "resolved" and item.resolved_at is None:
            item.resolved_at = datetime.now(timezone.utc)
        if issue.get("updatedBy"):
            item.updated_by = issue["updatedBy"]
        item.save()
        return _serialize_issue(item)


_issue_store: IssueStore | None = None


def get_issue_store() -> IssueStore:
    global _issue_store
    if _issue_store is None:
        _issue_store = DjangoIssueStore()
    return _issue_store


def set_issue_store(store: IssueStore | None) -> None:
    """Test seam."""
    global _issue_store
    _issue_store = store


def _serialize_issue(item) -> dict:
    return {
        "id": item.id,
        "fingerprint": item.fingerprint,
        "status": item.status,
        "note": item.note,
        "resolvedAt": item.resolved_at.isoformat().replace("+00:00", "Z") if item.resolved_at else None,
        "resolvedVersion": item.resolved_version,
        "ignoredUntil": item.ignored_until.isoformat().replace("+00:00", "Z") if item.ignored_until else None,
        "updatedBy": item.updated_by,
        "createdAt": item.created_at.isoformat().replace("+00:00", "Z") if item.created_at else None,
        "updatedAt": item.updated_at.isoformat().replace("+00:00", "Z") if item.updated_at else None,
    }


class SourcemapStore(Protocol):
    def find(self, application: str, release: str, file_name: str) -> dict | None:
        ...

    def list(self, application: str = "") -> list[dict]:
        ...

    def save(self, application: str, release: str, file_name: str, content: bytes, created_by: str = "") -> dict:
        ...


def _sourcemap_meta(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "application": item.get("application"),
        "release": item.get("release"),
        "fileName": item.get("fileName"),
        "createdBy": item.get("createdBy") or "",
        "createdAt": item.get("createdAt"),
    }


class MemorySourcemapStore:
    def __init__(self):
        self._items: dict[tuple[str, str, str], dict] = {}
        self._seq = 0

    def find(self, application: str, release: str, file_name: str) -> dict | None:
        item = self._items.get((application, release, file_name))
        return dict(item) if item else None

    def list(self, application: str = "") -> list[dict]:
        rows = []
        for item in self._items.values():
            if application and item.get("application") != application:
                continue
            rows.append(_sourcemap_meta(item))
        return rows

    def save(self, application: str, release: str, file_name: str, content: bytes, created_by: str = "") -> dict:
        from datetime import datetime, timezone

        self._seq += 1
        item = {
            "id": f"map-{self._seq}",
            "application": application,
            "release": release,
            "fileName": file_name,
            "content": content,
            "createdBy": created_by,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        self._items[(application, release, file_name)] = item
        return dict(item)


class DjangoSourcemapStore:
    def find(self, application: str, release: str, file_name: str) -> dict | None:
        from apps.rum.models import RumSourcemap

        qs = RumSourcemap.objects.filter(application=application)
        if release:
            qs = qs.filter(release=release)
        if file_name:
            qs = qs.filter(file_name=file_name)
        item = qs.order_by("-created_at").first()
        return _serialize_sourcemap(item, with_content=True) if item else None

    def list(self, application: str = "") -> list[dict]:
        from apps.rum.models import RumSourcemap

        qs = RumSourcemap.objects.all().order_by("-created_at")
        if application:
            qs = qs.filter(application=application)
        return [_serialize_sourcemap(item, with_content=False) for item in qs]

    def save(self, application: str, release: str, file_name: str, content: bytes, created_by: str = "") -> dict:
        from apps.rum.models import RumSourcemap

        item = RumSourcemap(
            application=application,
            release=release,
            file_name=file_name,
            content=content,
            created_by=created_by,
        )
        item.save()
        return _serialize_sourcemap(item, with_content=True)


def _serialize_sourcemap(item, *, with_content: bool) -> dict:
    row = {
        "id": item.id,
        "application": item.application,
        "release": item.release,
        "fileName": item.file_name,
        "createdBy": item.created_by,
        "createdAt": item.created_at.isoformat().replace("+00:00", "Z") if item.created_at else None,
    }
    if with_content:
        row["content"] = bytes(item.content)
    return row


_sourcemap_store: SourcemapStore | None = None


def get_sourcemap_store() -> SourcemapStore:
    global _sourcemap_store
    if _sourcemap_store is None:
        _sourcemap_store = DjangoSourcemapStore()
    return _sourcemap_store


def set_sourcemap_store(store: SourcemapStore | None) -> None:
    """Test seam."""
    global _sourcemap_store
    _sourcemap_store = store


class ErrorsService:
    def __init__(
        self,
        control: ControlPlane | None = None,
        analytics: Analytics | None = None,
        issues: IssueStore | None = None,
        sourcemaps: SourcemapStore | None = None,
    ):
        self.control = control or get_control_plane()
        self.analytics = analytics or get_analytics()
        self.issues = issues or get_issue_store()
        self.sourcemaps = sourcemaps or get_sourcemap_store()
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

    def list_errors(self, actor: str, params: dict[str, Any]) -> dict:
        try:
            start, end = parse_range_params(params)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        enabled, reason = self._list_enabled_apps(actor)
        if reason == "control":
            return empty_error_list(reason="control")
        requested = self._requested_apps(params)
        apps = [name for name in requested if name in enabled] if requested else enabled
        if not self.analytics.available():
            return empty_error_list(reason="analytics")
        display_limit = int(params.get("limit") or 100)
        if display_limit <= 0:
            display_limit = 100
        display_limit = min(display_limit, 500)
        status_filter = params.get("status")
        query_limit = 500 if status_filter and status_filter != "all" else display_limit
        page = self.analytics.list_error_issues(
            self.settings.tenant_id,
            {
                "from": start,
                "to": end,
                "applications": apps,
                "userId": params.get("userId") or "",
                "release": params.get("release") or "",
                "traffic": params.get("traffic") or "visitors",
                "orderBy": params.get("orderBy") or "count",
                "limit": query_limit,
            },
        )
        rows = page.get("issues") or []
        kept = []
        for row in rows:
            fingerprint = row.get("fingerprint") or ""
            status = "open"
            stored = self.issues.get(fingerprint) if fingerprint else None
            if stored:
                status = stored.get("status") or "open"
            row = {**row, "status": status}
            if not match_issue_status(status, status_filter):
                continue
            kept.append(row)
        return {"issues": kept[:display_limit]}

    def error_detail(self, actor: str, fingerprint: str, params: dict[str, Any]) -> dict:
        fingerprint = (fingerprint or "").strip()
        if not fingerprint:
            raise ValidationError("fingerprint is required")
        try:
            start, end = parse_range_params(params)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        enabled, reason = self._list_enabled_apps(actor)
        if reason == "control":
            return empty_error_detail(reason="control")
        requested = self._requested_apps(params)
        apps = [name for name in requested if name in enabled] if requested else enabled
        if not self.analytics.available():
            return empty_error_detail(reason="analytics")
        detail = self.analytics.error_detail(
            self.settings.tenant_id,
            fingerprint,
            {
                "from": start,
                "to": end,
                "applications": apps,
                "traffic": params.get("traffic") or "visitors",
                "limit": int(params.get("limit") or 0),
            },
        )
        if not detail.get("fingerprint"):
            raise ControlError("not_found", "error issue not found")
        stored = self.issues.get(fingerprint)
        if stored:
            detail["status"] = stored.get("status") or detail.get("status") or "open"
            detail["note"] = stored.get("note") or ""
            detail["resolvedAt"] = stored.get("resolvedAt")
            detail["resolvedVersion"] = stored.get("resolvedVersion") or ""
            detail["ignoredUntil"] = stored.get("ignoredUntil")
        detail.setdefault("signals", [])
        detail.setdefault("occurrences", [])
        return detail

    def patch_issue(self, actor: str, fingerprint: str, body: dict) -> dict:
        fingerprint = (fingerprint or "").strip()
        if not fingerprint:
            raise ValidationError("fingerprint is required")
        issue = self.issues.get(fingerprint) or {"fingerprint": fingerprint, "status": "open"}
        status = (body.get("status") or "").strip()
        if status:
            if status not in {"open", "reviewed", "resolved", "ignored"}:
                raise ValidationError("invalid status")
            issue["status"] = status
        if "note" in body:
            issue["note"] = body.get("note") or ""
        if body.get("resolvedVersion"):
            issue["resolvedVersion"] = body["resolvedVersion"]
        if issue.get("status") == "resolved":
            issue["resolvedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        issue["updatedBy"] = actor
        return self.issues.upsert(issue)

    def restore_sourcemap(self, actor: str, body: dict) -> dict:
        application = (body.get("application") or "").strip()
        release = (body.get("release") or "").strip()
        if not application or not valid_application(application):
            raise ValidationError("application is required")
        enabled, reason = self._list_enabled_apps(actor)
        if reason == "control":
            raise ControlError("unavailable", "RUM controller is unavailable")
        if application not in enabled:
            raise ControlError("not_found", "application not found")
        try:
            frames = parse_frames(body.get("frames") or [])
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        result = {
            "frames": frames,
            "anyResolved": False,
            "outcome": OUTCOME_MISSING_ARTIFACT,
        }
        if not release:
            result["outcome"] = OUTCOME_MISSING_RELEASE
            return result
        saw_map = False
        saw_invalid = False
        for index, frame in enumerate(frames):
            file_name = frame.get("file") or ""
            if not file_name.startswith("asset:"):
                continue
            stored = self.sourcemaps.find(application, release, file_name)
            if stored is None:
                continue
            saw_map = True
            restored = restore_frames([frame], stored["content"], stored.get("id") or "")
            if restored["outcome"] == OUTCOME_INVALID:
                saw_invalid = True
            if restored["anyResolved"]:
                result["frames"][index] = restored["frames"][0]
                result["anyResolved"] = True
                result["sourcemapId"] = restored.get("sourcemapId")
        if result["anyResolved"]:
            result["outcome"] = OUTCOME_RESOLVED
        elif saw_invalid:
            result["outcome"] = OUTCOME_INVALID
        elif saw_map:
            result["outcome"] = OUTCOME_UNMAPPED
        return result
