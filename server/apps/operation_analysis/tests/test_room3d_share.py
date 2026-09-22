"""Share path for room3D must query CMDB as the sharer, not the visitor."""

import json
from types import SimpleNamespace

from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.views.share_view import DashboardShareAccessViewSet

ROOM_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ROOM_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _screen_view_sets():
    return {
        "items": [
            {
                "valueConfig": {
                    "chartType": "room3D",
                    "sceneWidgetType": "room3D",
                    "room3D": {"serverRoomId": ROOM_A},
                }
            }
        ]
    }


def _principal(*, resource_type="screen", view_sets=None, sharer_name="sharer-alice"):
    sharer = SimpleNamespace(
        username=sharer_name,
        is_superuser=False,
        is_authenticated=True,
        pk=9,
        id=9,
    )
    return SimpleNamespace(
        resource_type=resource_type,
        resource=SimpleNamespace(view_sets=view_sets if view_sets is not None else _screen_view_sets()),
        space_id=42,
        user=sharer,
    )


def _visitor():
    return SimpleNamespace(
        username="visitor-bob",
        is_superuser=False,
        is_authenticated=True,
        pk=2,
        id=2,
    )


def _patch_share(monkeypatch, principal):
    monkeypatch.setattr(
        "apps.operation_analysis.views.share_view.resolve_session",
        lambda **kwargs: principal,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.views.share_view._delegated_sharer_user",
        lambda user: user,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.views.share_view.log_share_access",
        lambda *args, **kwargs: None,
    )


def _post_share(monkeypatch, *, principal, action, payload, captured):
    _patch_share(monkeypatch, principal)

    def fake_as_view(actions):
        assert actions == {"post": action}

        def view(request):
            user = getattr(request, "user", None) or getattr(request, "_force_auth_user", None)
            captured["username"] = getattr(user, "username", None)
            captured["team"] = request.COOKIES.get("current_team")
            data = getattr(request, "data", None)
            if not isinstance(data, dict):
                try:
                    data = json.loads(request.body.decode() or "{}")
                except (TypeError, ValueError, UnicodeDecodeError):
                    data = {}
            captured["payload"] = data
            return Response({"ok": True})

        return view

    monkeypatch.setattr(
        "apps.operation_analysis.views.scene_widget_view.SceneWidgetViewSet.as_view",
        fake_as_view,
    )

    factory = APIRequestFactory()
    request = factory.post("/share/", payload, format="json")
    force_authenticate(request, user=_visitor())
    view = DashboardShareAccessViewSet.as_view({"post": action})
    return view(request, session_id="session-1")


def test_share_room3d_rooms_delegates_with_sharer_not_visitor(monkeypatch):
    captured = {}
    response = _post_share(
        monkeypatch,
        principal=_principal(),
        action="room3d_rooms",
        payload={},
        captured=captured,
    )

    assert response.status_code == 200
    assert captured["username"] == "sharer-alice"
    assert captured["team"] == "42"


def test_share_room3d_layout_allows_undeclared_room_in_sharer_scope(monkeypatch):
    captured = {}
    response = _post_share(
        monkeypatch,
        principal=_principal(),
        action="room3d_layout",
        payload={"server_room_id": ROOM_B},
        captured=captured,
    )

    assert response.status_code == 200
    assert captured["payload"]["server_room_id"] == ROOM_B
    assert captured["username"] == "sharer-alice"


def test_share_room3d_rejects_when_widget_not_declared(monkeypatch):
    captured = {}
    response = _post_share(
        monkeypatch,
        principal=_principal(view_sets={"items": [{"valueConfig": {"chartType": "line"}}]}),
        action="room3d_layout",
        payload={"server_room_id": ROOM_A},
        captured=captured,
    )

    assert response.status_code == 403
    assert captured == {}


def test_share_room3d_rejects_dashboard_canvas(monkeypatch):
    captured = {}
    response = _post_share(
        monkeypatch,
        principal=_principal(resource_type="dashboard", view_sets=[{"valueConfig": {"chartType": "room3D"}}]),
        action="room3d_rooms",
        payload={},
        captured=captured,
    )

    assert response.status_code == 403
    assert captured == {}
