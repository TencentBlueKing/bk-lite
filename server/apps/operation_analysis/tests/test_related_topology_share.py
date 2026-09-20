"""Share path for related topology must query CMDB as the sharer, not the visitor."""

import json
from types import SimpleNamespace

from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.views.share_view import DashboardShareAccessViewSet

CENTER_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_UUID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def _dashboard_view_sets(inst_uuid=CENTER_UUID):
    return [
        {
            "valueConfig": {
                "chartType": "relatedTopology",
                "sceneWidgetType": "relatedTopology",
                "relatedTopology": {"modelId": "host", "instUuid": inst_uuid},
            }
        }
    ]


def _principal(*, resource_type="dashboard", view_sets=None, sharer_name="sharer-alice"):
    sharer = SimpleNamespace(
        username=sharer_name,
        is_superuser=False,
        is_authenticated=True,
        pk=9,
        id=9,
    )
    return SimpleNamespace(
        resource_type=resource_type,
        resource=SimpleNamespace(view_sets=view_sets if view_sets is not None else _dashboard_view_sets()),
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


def _post_share(monkeypatch, *, principal, payload, captured):
    _patch_share(monkeypatch, principal)

    def fake_as_view(actions):
        assert actions == {"post": "related_topology"}

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
            captured["inst_uuid"] = data.get("inst_uuid")
            return Response({"ok": True})

        return view

    monkeypatch.setattr(
        "apps.operation_analysis.views.scene_widget_view.SceneWidgetViewSet.as_view",
        fake_as_view,
    )

    factory = APIRequestFactory()
    request = factory.post("/share/", payload, format="json")
    force_authenticate(request, user=_visitor())
    view = DashboardShareAccessViewSet.as_view({"post": "related_topology"})
    return view(request, session_id="session-1")


def test_share_related_topology_delegates_with_sharer_not_visitor(monkeypatch):
    captured = {}
    response = _post_share(
        monkeypatch,
        principal=_principal(),
        payload={"inst_uuid": CENTER_UUID},
        captured=captured,
    )

    assert response.status_code == 200
    assert captured["username"] == "sharer-alice"
    assert captured["team"] == "42"
    assert captured["inst_uuid"] == CENTER_UUID


def test_share_related_topology_allows_screen_canvas(monkeypatch):
    captured = {}
    response = _post_share(
        monkeypatch,
        principal=_principal(
            resource_type="screen",
            view_sets={"items": _dashboard_view_sets()},
        ),
        payload={"inst_uuid": CENTER_UUID},
        captured=captured,
    )

    assert response.status_code == 200
    assert captured["username"] == "sharer-alice"


def test_share_related_topology_rejects_when_widget_not_declared(monkeypatch):
    captured = {}
    response = _post_share(
        monkeypatch,
        principal=_principal(view_sets=[{"valueConfig": {"chartType": "line"}}]),
        payload={"inst_uuid": CENTER_UUID},
        captured=captured,
    )

    assert response.status_code == 403
    assert captured == {}


def test_share_related_topology_rejects_undeclared_inst_uuid(monkeypatch):
    captured = {}
    response = _post_share(
        monkeypatch,
        principal=_principal(),
        payload={"inst_uuid": OTHER_UUID},
        captured=captured,
    )

    assert response.status_code == 403
    assert captured == {}
