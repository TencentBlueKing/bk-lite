"""分享态应用拓扑按分享者身份取数。画布声明了组件后，可查询分享者有权的应用系统。"""

import json
from types import SimpleNamespace

from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.views.share_view import DashboardShareAccessViewSet

CENTER_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_UUID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def _view_sets(inst_uuid=CENTER_UUID):
    return [
        {
            "valueConfig": {
                "chartType": "applicationTopology",
                "sceneWidgetType": "applicationTopology",
                "applicationTopology": {"modelId": "system", "instUuid": inst_uuid, "depth": 3},
            }
        }
    ]


def _principal(*, resource_type="dashboard", view_sets=None):
    sharer = SimpleNamespace(username="sharer-alice", is_superuser=False, is_authenticated=True, pk=9, id=9)
    return SimpleNamespace(
        resource_type=resource_type,
        resource=SimpleNamespace(view_sets=view_sets if view_sets is not None else _view_sets()),
        space_id=42,
        user=sharer,
    )


def _post(monkeypatch, *, principal, payload, captured):
    monkeypatch.setattr("apps.operation_analysis.views.share_view.resolve_session", lambda **kwargs: principal)
    monkeypatch.setattr("apps.operation_analysis.views.share_view._delegated_sharer_user", lambda user: user)
    monkeypatch.setattr("apps.operation_analysis.views.share_view.log_share_access", lambda *args, **kwargs: None)

    def fake_as_view(actions):
        assert actions == {"post": "application_topology"}

        def view(request):
            user = getattr(request, "user", None) or getattr(request, "_force_auth_user", None)
            captured["username"] = getattr(user, "username", None)
            captured["team"] = request.COOKIES.get("current_team")
            data = getattr(request, "data", None)
            if not isinstance(data, dict):
                data = json.loads(request.body.decode() or "{}")
            captured["inst_uuid"] = data.get("inst_uuid")
            captured["depth"] = data.get("depth")
            return Response({"ok": True})

        return view

    monkeypatch.setattr("apps.operation_analysis.views.scene_widget_view.SceneWidgetViewSet.as_view", fake_as_view)
    request = APIRequestFactory().post("/share/", payload, format="json")
    force_authenticate(request, user=SimpleNamespace(username="visitor-bob", is_authenticated=True, is_superuser=False, pk=2, id=2))
    return DashboardShareAccessViewSet.as_view({"post": "application_topology"})(request, session_id="session-1")


def test_share_application_topology_delegates_declared_instance(monkeypatch):
    captured = {}
    response = _post(monkeypatch, principal=_principal(), payload={"inst_uuid": CENTER_UUID, "depth": 3}, captured=captured)
    assert response.status_code == 200
    assert captured["username"] == "sharer-alice"
    assert captured["team"] == "42"
    assert captured["inst_uuid"] == CENTER_UUID


def test_share_application_topology_allows_another_system_on_the_canvas(monkeypatch):
    captured = {}
    response = _post(monkeypatch, principal=_principal(), payload={"inst_uuid": OTHER_UUID, "depth": 3}, captured=captured)
    assert response.status_code == 200
    assert captured["inst_uuid"] == OTHER_UUID


def test_share_application_topology_rejects_when_widget_not_declared(monkeypatch):
    captured = {}
    response = _post(
        monkeypatch,
        principal=_principal(view_sets=[{"valueConfig": {"chartType": "line"}}]),
        payload={"inst_uuid": CENTER_UUID, "depth": 3},
        captured=captured,
    )
    assert response.status_code == 403
    assert captured == {}
