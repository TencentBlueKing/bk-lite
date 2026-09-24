from __future__ import annotations

from typing import Any, Protocol

from apps.rum.constants import SUBJECT_APPLICATION_LIST
from apps.rum.services.analytics import Analytics, get_analytics
from apps.rum.services.control import ControlError, ControlPlane, control_unavailable, get_control_plane
from apps.rum.services.query import empty_view_list, parse_range_params
from apps.rum.services.settings import load_rum_settings
from apps.rum.services.validation import ValidationError


class SavedViewStore(Protocol):
    def list(self, actor: str, screen: str | None) -> list[dict]:
        ...

    def create(self, actor: str, body: dict) -> dict:
        ...

    def delete(self, actor: str, view_id: str) -> None:
        ...


class MemorySavedViewStore:
    def __init__(self):
        self._items: dict[str, dict] = {}
        self._seq = 0

    def list(self, actor: str, screen: str | None) -> list[dict]:
        out = []
        for item in self._items.values():
            if screen and item["screen"] != screen:
                continue
            if item["owner"] == actor or item["shared"]:
                out.append(dict(item))
        return sorted(out, key=lambda row: row.get("updatedAt") or "", reverse=True)

    def create(self, actor: str, body: dict) -> dict:
        screen = (body.get("screen") or "").strip()
        name = (body.get("name") or "").strip()
        if not screen or not name:
            raise ValidationError("screen and name are required")
        if len(name) > 128 or len(screen) > 64:
            raise ValidationError("screen or name is too long")
        self._seq += 1
        item = {
            "id": f"sv-{self._seq}",
            "screen": screen,
            "name": name,
            "contextJson": body.get("contextJson") or body.get("context_json") or "",
            "shared": bool(body.get("shared")),
            "owner": actor,
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
        self._items[item["id"]] = item
        return dict(item)

    def delete(self, actor: str, view_id: str) -> None:
        item = self._items.get(view_id)
        if item is None:
            raise ControlError("not_found", "saved view not found")
        if item["owner"].lower() != actor.lower():
            raise ControlError("forbidden", "only the owner can delete this saved view")
        del self._items[view_id]


class DjangoSavedViewStore:
    def list(self, actor: str, screen: str | None) -> list[dict]:
        from django.db.models import Q

        from apps.rum.models import RumSavedView

        qs = RumSavedView.objects.all()
        if screen:
            qs = qs.filter(screen=screen.strip())
        qs = qs.filter(Q(owner=actor) | Q(shared=True)).order_by("-updated_at")
        return [_serialize(item) for item in qs]

    def create(self, actor: str, body: dict) -> dict:
        from apps.rum.models import RumSavedView

        screen = (body.get("screen") or "").strip()
        name = (body.get("name") or "").strip()
        if not screen or not name:
            raise ValidationError("screen and name are required")
        if len(name) > 128 or len(screen) > 64:
            raise ValidationError("screen or name is too long")
        item = RumSavedView.objects.create(
            screen=screen,
            name=name,
            context_json=body.get("contextJson") or body.get("context_json") or "",
            shared=bool(body.get("shared")),
            owner=actor,
        )
        return _serialize(item)

    def delete(self, actor: str, view_id: str) -> None:
        from apps.rum.models import RumSavedView

        try:
            item = RumSavedView.objects.get(pk=view_id)
        except RumSavedView.DoesNotExist as exc:
            raise ControlError("not_found", "saved view not found") from exc
        if item.owner.lower() != actor.lower():
            raise ControlError("forbidden", "only the owner can delete this saved view")
        item.delete()


def _serialize(item) -> dict:
    return {
        "id": item.id,
        "screen": item.screen,
        "name": item.name,
        "contextJson": item.context_json,
        "shared": item.shared,
        "owner": item.owner,
        "createdAt": item.created_at.isoformat().replace("+00:00", "Z") if item.created_at else None,
        "updatedAt": item.updated_at.isoformat().replace("+00:00", "Z") if item.updated_at else None,
    }


class ViewsService:
    def __init__(
        self,
        control: ControlPlane | None = None,
        analytics: Analytics | None = None,
        saved_views: SavedViewStore | None = None,
    ):
        self.control = control or get_control_plane()
        self.analytics = analytics or get_analytics()
        self.saved_views = saved_views or DjangoSavedViewStore()
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

    def list_views(self, actor: str, params: dict[str, Any]) -> dict:
        mode = (params.get("mode") or "route").strip() or "route"
        if mode not in {"route", "release"}:
            raise ValidationError("mode must be route or release")
        try:
            start, end = parse_range_params(params)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        enabled, reason = self._list_enabled_apps(actor)
        if reason == "control":
            return empty_view_list(mode=mode, reason="control")
        requested = self._requested_apps(params)
        apps = [name for name in requested if name in enabled] if requested else enabled
        if not self.analytics.available():
            return empty_view_list(mode=mode, reason="analytics")
        return self.analytics.list_views(
            self.settings.tenant_id,
            {
                "from": start,
                "to": end,
                "applications": apps,
                "mode": mode,
                "traffic": params.get("traffic") or "visitors",
                "release": params.get("release") or "",
                "limit": int(params.get("limit") or 0),
            },
        )

    def list_saved_views(self, actor: str, screen: str | None) -> list[dict]:
        return self.saved_views.list(actor, screen)

    def create_saved_view(self, actor: str, body: dict) -> dict:
        return self.saved_views.create(actor, body)

    def delete_saved_view(self, actor: str, view_id: str) -> None:
        self.saved_views.delete(actor, view_id)
