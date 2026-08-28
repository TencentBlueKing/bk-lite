"""Share path for application3D must reuse the same permission-aware QueryService.

These tests avoid full django_db migrate where possible, and assert:
- Share delegates with sharer identity (not visitor)
- application_detail field allowlist / CMDB show_fields / sensitive exclusion
  behave the same when that sharer identity is the request.user
"""

import json
from types import SimpleNamespace

from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.services.application3d.health import aggregate_application_health
from apps.operation_analysis.services.application3d.presenters import present_application_properties
from apps.operation_analysis.services.application3d.query_service import Application3DQueryService, _ApplicationScope
from apps.operation_analysis.views.share_view import DashboardShareAccessViewSet

APP_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _attrs():
    return [
        {"attr_id": "app_id", "attr_name": "ID", "attr_type": "str"},
        {"attr_id": "operator", "attr_name": "Operator", "attr_type": "str"},
        {"attr_id": "bak_operator", "attr_name": "Backup", "attr_type": "password"},
        {"attr_id": "comment", "attr_name": "Comment", "attr_type": "str"},
        {"attr_id": "secret_token", "attr_name": "Secret", "attr_type": "str"},
    ]


def _application_payload():
    return {
        "inst_uuid": APP_A,
        "inst_name": "app",
        "model_id": "application",
        "app_id": "A-1",
        "operator": "hidden-user",
        "bak_operator": "sensitive-user",
        "comment": "visible-comment",
        "secret_token": "must-not-leak",
    }


def test_presenter_omits_missing_field_permission_sensitive_and_secret_token():
    properties = present_application_properties(
        _application_payload(),
        _attrs(),
        visible_fields={"app_id", "bak_operator", "comment", "secret_token"},
    )
    assert [item["key"] for item in properties] == ["app_id", "comment"]


def test_share_application_detail_delegates_with_sharer_not_visitor(monkeypatch):
    captured = {}
    sharer = SimpleNamespace(
        username="sharer-alice",
        is_superuser=False,
        is_authenticated=True,
        pk=9,
        id=9,
    )
    visitor = SimpleNamespace(
        username="visitor-bob",
        is_superuser=False,
        is_authenticated=True,
        pk=2,
        id=2,
    )
    principal = SimpleNamespace(
        resource_type="screen",
        resource=SimpleNamespace(
            view_sets={
                "items": [
                    {
                        "valueConfig": {
                            "chartType": "application3D",
                            "sceneWidgetType": "application3D",
                        }
                    }
                ]
            }
        ),
        space_id=42,
        user=sharer,
    )

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

    def fake_as_view(actions):
        assert actions == {"post": "application3d_application_detail"}

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
            captured["application_id"] = data.get("applicationId")
            return Response({"ok": True})

        return view

    monkeypatch.setattr(
        "apps.operation_analysis.views.scene_widget_view.SceneWidgetViewSet.as_view",
        fake_as_view,
    )

    factory = APIRequestFactory()
    request = factory.post(
        "/share/",
        {"applicationId": APP_A},
        format="json",
    )
    force_authenticate(request, user=visitor)
    view = DashboardShareAccessViewSet.as_view({"post": "application3d_application_detail"})
    response = view(request, session_id="session-1")

    assert response.status_code == 200
    assert captured["username"] == "sharer-alice"
    assert captured["team"] == "42"
    assert captured["application_id"] == APP_A


def test_share_application_detail_rejects_when_widget_not_declared(monkeypatch):
    visitor = SimpleNamespace(
        username="visitor-bob",
        is_superuser=False,
        is_authenticated=True,
        pk=2,
        id=2,
    )
    principal = SimpleNamespace(
        resource_type="screen",
        resource=SimpleNamespace(view_sets={"items": [{"valueConfig": {"chartType": "line"}}]}),
        space_id=42,
        user=SimpleNamespace(username="sharer-alice"),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.views.share_view.resolve_session",
        lambda **kwargs: principal,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.views.share_view.log_share_access",
        lambda *args, **kwargs: None,
    )

    factory = APIRequestFactory()
    request = factory.post("/share/", {"applicationId": APP_A}, format="json")
    force_authenticate(request, user=visitor)
    view = DashboardShareAccessViewSet.as_view({"post": "application3d_application_detail"})
    response = view(request, session_id="session-1")

    assert response.status_code == 403


def test_application_detail_with_sharer_identity_applies_field_permissions(monkeypatch):
    """Same QueryService path Share delegates into: sharer show_fields gate properties."""
    application = _application_payload()
    request = SimpleNamespace(
        user=SimpleNamespace(username="sharer-alice", is_superuser=False),
        COOKIES={"current_team": "42", "include_children": "0"},
        data={},
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_application",
        classmethod(lambda cls, req, application_id: application),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(
            lambda cls, req, apps: _ApplicationScope(
                applications=apps,
                hosts_by_app={APP_A: []},
                policies={},
                complete_apps={APP_A},
            )
        ),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.ModelManage.search_model_attr",
        lambda model_id: _attrs(),
    )

    seen_users = []

    def show_fields(model_id, user):
        seen_users.append(user.username)
        return ["app_id", "bak_operator", "comment", "secret_token"]

    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.ApplicationResourceOverviewService._get_show_fields",
        show_fields,
    )

    result = Application3DQueryService.application_detail(request, APP_A)

    assert seen_users == ["sharer-alice"]
    assert [item["key"] for item in result["application"]["properties"]] == ["app_id", "comment"]
    assert "secret_token" not in {item["key"] for item in result["application"]["properties"]}
    assert "operator" not in {item["key"] for item in result["application"]["properties"]}
    assert "bak_operator" not in {item["key"] for item in result["application"]["properties"]}


def test_share_and_normal_no_data_critical_uses_same_alarming_health(monkeypatch):
    """Share and Normal both call Application3DQueryService; health aggregation is shared."""
    aggregated = aggregate_application_health([{"alert_type": "no_data", "level": "critical", "count": 1}])
    assert aggregated["state"] == "alarming"
    assert aggregated["highestSeverity"]["id"] == "critical"
    assert aggregated["noDataAlarmCount"] == 1
    assert aggregated["severityCounts"]["critical"] == 1

    applications = [{"inst_uuid": APP_A, "inst_name": "nodata", "model_id": "application"}]
    scope = _ApplicationScope(
        applications=applications,
        hosts_by_app={APP_A: [{"inst_uuid": "host-1", "monitor_id": "monitor-1"}]},
        policies={1: SimpleNamespace(id=1)},
        complete_apps={APP_A},
    )
    grouped = [{"monitor_instance_id": "monitor-1", "alert_type": "no_data", "level": "critical", "count": 1}]
    monkeypatch.setattr(
        Application3DQueryService,
        "_grouped_alert_counts_by_monitor",
        classmethod(lambda cls, scoped, monitor_ids: [row for row in grouped if row["monitor_instance_id"] in monitor_ids]),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_filter_definition",
        classmethod(lambda cls: ([], set())),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_applications",
        classmethod(lambda cls, request: applications),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(lambda cls, request, apps: scope),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_application",
        classmethod(lambda cls, request, application_id: applications[0]),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.ModelManage.search_model_attr",
        lambda model_id: [],
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.ApplicationResourceOverviewService._get_show_fields",
        lambda model_id, user: None,
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_paged_scoped_alerts",
        classmethod(lambda cls, scoped, app_id, *, cursor: ([], False)),
    )

    request = SimpleNamespace(
        user=SimpleNamespace(username="sharer-alice", is_superuser=False),
        COOKIES={"current_team": "42", "include_children": "0"},
        data={},
    )
    wall_health = Application3DQueryService.wall(request)["items"][0]["health"]
    detail_health = Application3DQueryService.application_detail(request, APP_A)["application"]["health"]
    for health in (wall_health, detail_health):
        assert health["state"] == aggregated["state"] == "alarming"
        assert health["highestSeverity"]["id"] == "critical"
        assert health["noDataAlarmCount"] == 1
        assert health["severityCounts"]["critical"] == 1
        assert health["reason"] != "unavailable"
