import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.models.models import Directory, Screen
from apps.operation_analysis.models.share_models import ScreenDisplayGrant, ScreenDisplaySession
from apps.operation_analysis.services.display_token import InvalidDisplayToken, build_display_token, parse_display_token
from apps.operation_analysis.services.network_status_topology import NetworkStatusTopologyService
from apps.operation_analysis.services.share_token import InvalidShareToken, build_share_token, parse_share_token
from apps.operation_analysis.views.datasource_view import DataSourceAPIModelViewSet
from apps.system_mgmt.models.user import User

SIGNING_KEY = "test-signing-key-at-least-32-bytes"


def _directory():
    return Directory.objects.create(name=f"display-dir-{uuid.uuid4()}", groups=[1], created_by="alice")


def _screen(**overrides):
    payload = {
        "name": f"display-screen-{uuid.uuid4()}",
        "directory": _directory(),
        "groups": [1],
        "created_by": "alice",
        "domain": "domain.com",
        "view_sets": {},
    }
    payload.update(overrides)
    return Screen.objects.create(**payload)


def _sharer():
    User.objects.get_or_create(
        username="alice",
        domain="domain.com",
        defaults={
            "display_name": "Alice",
            "email": "alice@example.com",
            "password": "x",
            "group_list": [1],
        },
    )
    return SimpleNamespace(
        id=1,
        pk=1,
        username="alice",
        domain="domain.com",
        disabled=False,
        is_superuser=True,
        is_authenticated=True,
        locale="zh-Hans",
        group_list=[{"id": 1}],
    )


def _admin(client, user):
    client.force_authenticate(user)
    client.cookies["current_team"] = "1"
    return client


def _create(client, screen, days=30):
    return client.post(
        f"/api/v1/operation_analysis/api/screen/{screen.id}/display_grant/",
        {"duration_days": days},
        format="json",
    )


def _token(url):
    return url.rsplit("/", 1)[-1]


@pytest.mark.django_db
def test_display_and_share_tokens_reject_each_other(settings):
    settings.DASHBOARD_SHARE_SIGNING_KEY = SIGNING_KEY
    public_id = uuid.uuid4()
    display_token = build_display_token(public_id)
    share_token = build_share_token(public_id)
    with pytest.raises(InvalidShareToken):
        parse_share_token(display_token)
    with pytest.raises(InvalidDisplayToken):
        parse_display_token(share_token)


@pytest.mark.django_db
def test_one_grant_per_screen_and_duration_is_closed(settings):
    settings.DASHBOARD_SHARE_SIGNING_KEY = SIGNING_KEY
    screen = _screen()
    admin = _admin(APIClient(), _sharer())
    created = _create(admin, screen, 30)
    assert created.status_code == 200
    assert created.data["state"] == "active"
    assert created.data["duration_days"] == 30
    assert created.data["url"].startswith("/ops-analysis/display/t/")
    first_expiry = created.data["expires_at"]

    again = _create(admin, screen, 90)
    assert again.status_code == 409
    assert ScreenDisplayGrant.objects.filter(screen=screen).count() == 1
    stored = ScreenDisplayGrant.objects.get(screen=screen)
    assert stored.expires_at.isoformat() == first_expiry or str(stored.expires_at)[:19] == str(first_expiry)[:19]

    rejected = admin.post(
        f"/api/v1/operation_analysis/api/screen/{screen.id}/display_grant/regenerate/",
        {"duration_days": 39},
        format="json",
    )
    assert rejected.status_code == 400
    stored.refresh_from_db()
    assert stored.duration_days == 30


@pytest.mark.django_db
def test_display_session_reads_declared_data_and_rejects_other_sources(settings, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = SIGNING_KEY
    screen = _screen(view_sets=[{"valueConfig": {"dataSource": 42}}])
    admin = _admin(APIClient(), _sharer())
    created = _create(admin, screen, 1)
    token = _token(created.data["url"])

    monkeypatch.setattr(
        DataSourceAPIModelViewSet,
        "get_source_data",
        lambda self, request, pk=None: __import__("rest_framework.response", fromlist=["Response"]).Response({"rows": [1]}),
    )

    television = APIClient()
    activated = television.post(
        "/api/v1/operation_analysis/api/screen_display/activate/",
        {"token": token},
        format="json",
    )
    assert activated.status_code == 200
    cookie = activated.cookies["bk_screen_display"]
    assert cookie["httponly"]
    assert cookie["path"] == "/"
    assert "bk_screen_display" not in activated.data

    canvas = television.get("/api/v1/operation_analysis/api/screen_display/current/")
    assert canvas.status_code == 200
    assert canvas.data["name"] == screen.name
    assert canvas.data["resource_type"] == "screen"

    allowed = television.post("/api/v1/operation_analysis/api/screen_display/current/query/42/", {}, format="json")
    assert allowed.status_code == 200
    assert allowed.data["rows"] == [1]

    denied = television.post("/api/v1/operation_analysis/api/screen_display/current/query/99/", {}, format="json")
    assert denied.status_code == 403

    mismatch = APIClient()
    mismatch.cookies["bk_screen_display"] = str(uuid.uuid4())
    assert mismatch.get("/api/v1/operation_analysis/api/screen_display/current/").status_code == 404


@pytest.mark.django_db
def test_display_data_sources_include_rest_api_for_filter_lookup(settings):
    settings.DASHBOARD_SHARE_SIGNING_KEY = SIGNING_KEY
    datasource = DataSourceAPIModel.objects.create(
        name=f"room-list-{uuid.uuid4()}",
        rest_api="cmdb/get_room_list",
        groups=[1],
        created_by="alice",
        updated_by="alice",
    )
    screen = _screen(view_sets=[{"valueConfig": {"dataSource": datasource.id}}])
    admin = _admin(APIClient(), _sharer())
    created = _create(admin, screen, 1)
    television = APIClient()
    activated = television.post(
        "/api/v1/operation_analysis/api/screen_display/activate/",
        {"token": _token(created.data["url"])},
        format="json",
    )
    assert activated.status_code == 200

    response = television.get("/api/v1/operation_analysis/api/screen_display/current/data_sources/")
    assert response.status_code == 200
    assert response.data[0]["id"] == datasource.id
    assert response.data[0]["rest_api"] == "cmdb/get_room_list"
    assert "connection_config" not in response.data[0]


@pytest.mark.django_db
def test_expiry_pause_and_regenerate_take_effect_without_waiting(settings, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = SIGNING_KEY
    screen = _screen()
    admin = _admin(APIClient(), _sharer())
    created = _create(admin, screen, 1)
    token = _token(created.data["url"])
    grant = ScreenDisplayGrant.objects.get(screen=screen)
    original_expiry = grant.expires_at

    television = APIClient()
    assert television.post("/api/v1/operation_analysis/api/screen_display/activate/", {"token": token}, format="json").status_code == 200
    assert television.get("/api/v1/operation_analysis/api/screen_display/current/").status_code == 200
    grant.refresh_from_db()
    assert grant.expires_at == original_expiry

    paused = admin.post(f"/api/v1/operation_analysis/api/screen/{screen.id}/display_grant/pause/", {}, format="json")
    assert paused.status_code == 200
    assert paused.data["state"] == "paused"
    assert television.get("/api/v1/operation_analysis/api/screen_display/current/").status_code == 404
    paused_activate = television.post("/api/v1/operation_analysis/api/screen_display/activate/", {"token": token}, format="json")
    assert paused_activate.status_code == 403
    assert paused_activate.data["reason"] == "paused"

    resumed = admin.post(f"/api/v1/operation_analysis/api/screen/{screen.id}/display_grant/resume/", {}, format="json")
    assert resumed.status_code == 200
    reopened = APIClient()
    assert reopened.post("/api/v1/operation_analysis/api/screen_display/activate/", {"token": token}, format="json").status_code == 200

    future = original_expiry + timedelta(seconds=5)
    monkeypatch.setattr(
        "apps.operation_analysis.services.display_service.timezone.now",
        lambda: future,
    )
    expired = reopened.get("/api/v1/operation_analysis/api/screen_display/current/")
    assert expired.status_code == 404
    expired_activate = APIClient().post(
        "/api/v1/operation_analysis/api/screen_display/activate/",
        {"token": token},
        format="json",
    )
    assert expired_activate.status_code == 403
    assert expired_activate.data["reason"] == "expired"
    refused_resume = admin.post(f"/api/v1/operation_analysis/api/screen/{screen.id}/display_grant/resume/", {}, format="json")
    assert refused_resume.status_code == 409
    grant.refresh_from_db()
    assert grant.expires_at == original_expiry

    monkeypatch.undo()
    renewed = admin.post(
        f"/api/v1/operation_analysis/api/screen/{screen.id}/display_grant/regenerate/",
        {"duration_days": 7},
        format="json",
    )
    assert renewed.status_code == 200
    assert renewed.data["duration_days"] == 7
    new_token = _token(renewed.data["url"])
    assert new_token != token
    assert APIClient().post("/api/v1/operation_analysis/api/screen_display/activate/", {"token": token}, format="json").status_code == 404
    assert reopened.get("/api/v1/operation_analysis/api/screen_display/current/").status_code == 404
    fresh = APIClient()
    assert fresh.post("/api/v1/operation_analysis/api/screen_display/activate/", {"token": new_token}, format="json").status_code == 200
    assert fresh.get("/api/v1/operation_analysis/api/screen_display/current/").status_code == 200
    assert ScreenDisplaySession.objects.filter(grant=grant).count() == 1


@pytest.mark.django_db
def test_sharer_loss_stops_the_next_display_request(settings):
    settings.DASHBOARD_SHARE_SIGNING_KEY = SIGNING_KEY
    screen = _screen()
    admin = _admin(APIClient(), _sharer())
    created = _create(admin, screen, 30)
    television = APIClient()
    assert (
        television.post(
            "/api/v1/operation_analysis/api/screen_display/activate/",
            {"token": _token(created.data["url"])},
            format="json",
        ).status_code
        == 200
    )

    User.objects.filter(username="alice", domain="domain.com").update(group_list=[])
    assert television.get("/api/v1/operation_analysis/api/screen_display/current/").status_code == 404

    User.objects.filter(username="alice", domain="domain.com").update(group_list=[{"id": 1}], disabled=True)
    assert (
        APIClient()
        .post(
            "/api/v1/operation_analysis/api/screen_display/activate/",
            {"token": _token(created.data["url"])},
            format="json",
        )
        .status_code
        == 404
    )


@pytest.mark.django_db
def test_display_credential_cannot_enter_login_or_colleague_share(settings, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = SIGNING_KEY
    summaries = []
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_audit.log_ops_analysis_operation",
        lambda request, action_type, summary: summaries.append(summary),
    )
    screen = _screen()
    admin = _admin(APIClient(), _sharer())
    created = _create(admin, screen, 30)
    token = _token(created.data["url"])
    share = admin.post(f"/api/v1/operation_analysis/api/screen/{screen.id}/share/", {}, format="json")
    assert share.status_code == 200
    share_token = _token(share.data["url"])

    anonymous = APIClient()
    assert anonymous.post("/api/v1/operation_analysis/api/dashboard_share/prepare/", {"token": token}, format="json").status_code != 200
    assert anonymous.post("/api/v1/operation_analysis/api/screen_display/activate/", {"token": share_token}, format="json").status_code == 404
    assert anonymous.post("/api/v1/operation_analysis/api/dashboard_share/exchange/", {"token": token, "state": "x"}, format="json").status_code in {
        401,
        403,
    }

    activated = anonymous.post("/api/v1/operation_analysis/api/screen_display/activate/", {"token": token}, format="json")
    assert activated.status_code == 200
    bare = APIClient()
    bare.cookies["bk_screen_display"] = activated.cookies["bk_screen_display"].value
    screen_api = bare.get(f"/api/v1/operation_analysis/api/screen/{screen.id}/")
    assert screen_api.status_code in {401, 403}
    assert token not in "\n".join(summaries)


@pytest.mark.django_db
def test_display_activate_is_login_exempt():
    from django.test import RequestFactory

    from apps.core.middlewares.auth_middleware import AuthMiddleware
    from apps.operation_analysis.views.display_view import ScreenDisplayAccessViewSet

    view = ScreenDisplayAccessViewSet.as_view({"post": "activate"})
    assert getattr(view, "login_exempt", False) is True
    middleware = AuthMiddleware(get_response=lambda request: None)
    request = RequestFactory().post(
        "/api/v1/operation_analysis/api/screen_display/activate/",
        data='{"token":"x"}',
        content_type="application/json",
    )
    assert middleware.process_view(request, view, [], {}) is None


DEVICE_A = "11111111-1111-4111-8111-111111111111"
DEVICE_B = "22222222-2222-4222-8222-222222222222"


def _network_status_screen(*, inst_uuids, node_limit=20, one_hop=False):
    return _screen(
        view_sets={
            "items": [
                {
                    "chartType": "networkStatusTopology",
                    "valueConfig": {
                        "chartType": "networkStatusTopology",
                        "sceneWidgetType": "networkStatusTopology",
                        "networkStatusTopology": {
                            "instUuids": inst_uuids,
                            "nodeLimit": node_limit,
                            "oneHop": one_hop,
                        },
                    },
                }
            ],
        }
    )


def _activate_display(screen):
    admin = _admin(APIClient(), _sharer())
    created = _create(admin, screen, 1)
    television = APIClient()
    activated = television.post(
        "/api/v1/operation_analysis/api/screen_display/activate/",
        {"token": _token(created.data["url"])},
        format="json",
    )
    assert activated.status_code == 200
    return television


def _allow_sharer_scene_permission(monkeypatch):
    monkeypatch.setattr(
        "apps.operation_analysis.views.share_view.build_user_authorization_context",
        lambda user: {"is_superuser": True, "permission": {}, "group_tree": [], "timezone": "UTC"},
    )


@pytest.mark.django_db
def test_display_network_status_topology_only_allows_devices_saved_on_the_screen(settings, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = SIGNING_KEY
    _allow_sharer_scene_permission(monkeypatch)
    seen = {}

    def fake_build(cls, request, inst_uuids, node_limit=None, depth=None):
        seen["inst_uuids"] = list(inst_uuids)
        seen["node_limit"] = node_limit
        seen["depth"] = depth
        return {"nodes": [], "links": [], "truncated": False, "node_limit": node_limit}

    monkeypatch.setattr(NetworkStatusTopologyService, "build", classmethod(fake_build))
    television = _activate_display(_network_status_screen(inst_uuids=[DEVICE_A], node_limit=20))

    allowed = television.post(
        "/api/v1/operation_analysis/api/screen_display/current/network_status_topology/",
        {"inst_uuids": [DEVICE_A], "node_limit": 20},
        format="json",
    )
    assert allowed.status_code == 200
    assert seen["inst_uuids"] == [DEVICE_A]
    assert seen["depth"] is None

    other_device = television.post(
        "/api/v1/operation_analysis/api/screen_display/current/network_status_topology/",
        {"inst_uuids": [DEVICE_B], "node_limit": 20},
        format="json",
    )
    assert other_device.status_code == 403

    too_many_nodes = television.post(
        "/api/v1/operation_analysis/api/screen_display/current/network_status_topology/",
        {"inst_uuids": [DEVICE_A], "node_limit": 21},
        format="json",
    )
    assert too_many_nodes.status_code == 403

    one_hop = television.post(
        "/api/v1/operation_analysis/api/screen_display/current/network_status_topology/",
        {"inst_uuids": [DEVICE_A], "node_limit": 20, "depth": 1},
        format="json",
    )
    assert one_hop.status_code == 403


@pytest.mark.django_db
def test_display_network_status_topology_allows_one_hop_only_when_the_widget_saved_it(settings, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = SIGNING_KEY
    _allow_sharer_scene_permission(monkeypatch)
    monkeypatch.setattr(
        NetworkStatusTopologyService,
        "build",
        classmethod(lambda cls, request, inst_uuids, node_limit=None, depth=None: {"nodes": [], "links": []}),
    )
    television = _activate_display(_network_status_screen(inst_uuids=[DEVICE_A], node_limit=20, one_hop=True))
    allowed = television.post(
        "/api/v1/operation_analysis/api/screen_display/current/network_status_topology/",
        {"inst_uuids": [DEVICE_A], "node_limit": 20, "depth": 1},
        format="json",
    )
    assert allowed.status_code == 200

    plain = _activate_display(_screen(view_sets={"items": []}))
    missing = plain.post(
        "/api/v1/operation_analysis/api/screen_display/current/network_status_topology/",
        {"inst_uuids": [DEVICE_A], "node_limit": 20},
        format="json",
    )
    assert missing.status_code == 403
