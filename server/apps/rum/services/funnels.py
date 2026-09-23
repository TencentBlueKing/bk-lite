from __future__ import annotations

from typing import Any, Protocol

from apps.rum.constants import SUBJECT_APPLICATION_LIST
from apps.rum.services.analytics import Analytics, get_analytics
from apps.rum.services.control import ControlError, ControlPlane, control_unavailable, get_control_plane
from apps.rum.services.query import parse_range_params
from apps.rum.services.settings import load_rum_settings
from apps.rum.services.validation import ValidationError, valid_application


def normalize_funnel(body: dict) -> dict:
    name = (body.get("name") or "").strip()
    application = (body.get("application") or "").strip()
    steps = body.get("steps") or body.get("stepList") or []
    if not isinstance(steps, list):
        raise ValidationError("steps must be an array")
    normalized_steps: list[str] = []
    for step in steps:
        value = str(step).strip()
        if not value or len(value) > 256 or not value.startswith("/"):
            raise ValidationError("each step must be a path starting with /")
        normalized_steps.append(value)
    if not name or len(name) > 120 or len(normalized_steps) < 2 or len(normalized_steps) > 8:
        raise ValidationError("funnel requires name and 2-8 route steps")
    if application and application != "*" and not valid_application(application):
        raise ValidationError("invalid application")
    return {
        "name": name,
        "application": application,
        "steps": normalized_steps,
        "defaultPreset": (body.get("defaultPreset") or body.get("default_preset") or "").strip(),
    }


class FunnelStore(Protocol):
    def list(self) -> list[dict]:
        ...

    def get(self, funnel_id: str) -> dict | None:
        ...

    def save(self, funnel: dict) -> dict:
        ...

    def delete(self, funnel_id: str) -> None:
        ...


class MemoryFunnelStore:
    def __init__(self):
        self._items: dict[str, dict] = {}
        self._seq = 0

    def list(self) -> list[dict]:
        return [dict(item) for item in self._items.values()]

    def get(self, funnel_id: str) -> dict | None:
        item = self._items.get(funnel_id)
        return dict(item) if item else None

    def save(self, funnel: dict) -> dict:
        item = dict(funnel)
        if not item.get("id"):
            self._seq += 1
            item["id"] = f"funnel-{self._seq}"
        self._items[item["id"]] = item
        return dict(item)

    def delete(self, funnel_id: str) -> None:
        if funnel_id not in self._items:
            raise ControlError("not_found", "funnel not found")
        del self._items[funnel_id]


_funnel_store: FunnelStore | None = None


def get_funnel_store() -> FunnelStore:
    global _funnel_store
    if _funnel_store is None:
        _funnel_store = DjangoFunnelStore()
    return _funnel_store


def set_funnel_store(store: FunnelStore | None) -> None:
    """Test seam."""
    global _funnel_store
    _funnel_store = store


class DjangoFunnelStore:
    def list(self) -> list[dict]:
        from apps.rum.models import RumFunnel

        return [_serialize(item) for item in RumFunnel.objects.all().order_by("-updated_at")]

    def get(self, funnel_id: str) -> dict | None:
        from apps.rum.models import RumFunnel

        try:
            return _serialize(RumFunnel.objects.get(pk=funnel_id))
        except RumFunnel.DoesNotExist:
            return None

    def save(self, funnel: dict) -> dict:
        from apps.rum.models import RumFunnel

        if funnel.get("id"):
            try:
                item = RumFunnel.objects.get(pk=funnel["id"])
            except RumFunnel.DoesNotExist as exc:
                raise ControlError("not_found", "funnel not found") from exc
        else:
            item = RumFunnel(created_by=funnel.get("createdBy") or "")
        item.name = funnel["name"]
        item.steps = list(funnel["steps"])
        item.application = funnel.get("application") or ""
        item.default_preset = funnel.get("defaultPreset") or ""
        if funnel.get("createdBy") and not item.created_by:
            item.created_by = funnel["createdBy"]
        item.save()
        return _serialize(item)

    def delete(self, funnel_id: str) -> None:
        from apps.rum.models import RumFunnel

        deleted, _ = RumFunnel.objects.filter(pk=funnel_id).delete()
        if not deleted:
            raise ControlError("not_found", "funnel not found")


def _serialize(item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "steps": list(item.steps or []),
        "application": item.application,
        "defaultPreset": item.default_preset,
        "createdBy": item.created_by,
        "createdAt": item.created_at.isoformat().replace("+00:00", "Z") if item.created_at else None,
        "updatedAt": item.updated_at.isoformat().replace("+00:00", "Z") if item.updated_at else None,
    }


class FunnelsService:
    def __init__(
        self,
        control: ControlPlane | None = None,
        analytics: Analytics | None = None,
        store: FunnelStore | None = None,
    ):
        self.control = control or get_control_plane()
        self.analytics = analytics or get_analytics()
        self.store = store or get_funnel_store()
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

    def list_funnels(self) -> list[dict]:
        return self.store.list()

    def create_funnel(self, actor: str, body: dict) -> dict:
        normalized = normalize_funnel(body)
        application = normalized["application"]
        if application and application != "*":
            enabled, reason = self._list_enabled_apps(actor)
            if reason == "control":
                raise ControlError("unavailable", "RUM controller is unavailable")
            if application not in enabled:
                raise ControlError("not_found", "application not found")
        return self.store.save({**normalized, "createdBy": actor})

    def update_funnel(self, actor: str, funnel_id: str, body: dict) -> dict:
        existing = self.store.get(funnel_id)
        if existing is None:
            raise ControlError("not_found", "funnel not found")
        normalized = normalize_funnel(body)
        application = normalized["application"]
        if application and application != "*":
            enabled, reason = self._list_enabled_apps(actor)
            if reason == "control":
                raise ControlError("unavailable", "RUM controller is unavailable")
            if application not in enabled:
                raise ControlError("not_found", "application not found")
        return self.store.save({**existing, **normalized, "id": funnel_id})

    def delete_funnel(self, funnel_id: str) -> None:
        self.store.delete(funnel_id)

    def funnel_reach(self, actor: str, funnel_id: str, params: dict[str, Any]) -> dict:
        funnel = self.store.get(funnel_id)
        if funnel is None:
            raise ControlError("not_found", "funnel not found")
        try:
            start, end = parse_range_params(params)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        steps = list(funnel.get("steps") or [])
        enabled, reason = self._list_enabled_apps(actor)
        if reason == "control":
            return {
                "steps": steps,
                "reached": [],
                "controlUnavailable": True,
            }
        requested: list[str] = []
        app = (funnel.get("application") or "").strip()
        if app and app != "*":
            requested = [app]
        else:
            multi = params.get("applications") or params.get("application")
            if isinstance(multi, str) and multi.strip():
                requested = [part.strip() for part in multi.split(",") if part.strip()]
            elif isinstance(multi, list):
                requested = [str(part).strip() for part in multi if str(part).strip()]
        apps = [name for name in requested if name in enabled] if requested else enabled
        if not self.analytics.available():
            return {
                "steps": steps,
                "reached": [],
                "analyticsUnavailable": True,
            }
        return self.analytics.funnel_reach(
            self.settings.tenant_id,
            steps,
            {
                "from": start,
                "to": end,
                "applications": apps,
                "windowSeconds": int(params.get("windowSeconds") or 0),
                "traffic": params.get("traffic") or "visitors",
            },
        )
