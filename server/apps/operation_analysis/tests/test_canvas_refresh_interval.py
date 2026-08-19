"""分析画布 refresh_interval 读写、PUT 不覆盖、非法值拒绝。"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.constants.canvas_refresh import DEFAULT_CANVAS_REFRESH_INTERVAL_MS, normalize_canvas_refresh_interval
from apps.operation_analysis.constants.import_export import ObjectType
from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, NetworkTopology, Report, Screen, Topology
from apps.operation_analysis.schemas.import_export_schema import DashboardItem, NetworkTopologyItem
from apps.operation_analysis.services.import_export.export_service import ExportService
from apps.operation_analysis.views import view as view_module
from apps.operation_analysis.views.network_topology_view import NetworkTopologyViewSet
from apps.operation_analysis.views.share_view import _serialize_shared_resource


def _request(method, path, user, data=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path) if data is None else fn(path, data=data, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


def _directory():
    return Directory.objects.create(name="refresh-dir", groups=[1], created_by="testuser")


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, 0),
        ("", 0),
        (60, 0),
        (1, 0),
        (0, 0),
        (60000, 60000),
        (300000, 300000),
        (600000, 600000),
    ],
)
def test_normalize_canvas_refresh_interval(raw, expected):
    assert normalize_canvas_refresh_interval(raw) == expected


@pytest.mark.django_db
def test_new_dashboard_defaults_refresh_interval_off(authenticated_user):
    user = _superuser(authenticated_user)
    directory = _directory()
    request = _request(
        "post",
        "/dashboard/",
        user,
        data={"name": "周期盘", "groups": [1], "directory": directory.id},
    )
    response = view_module.DashboardModelViewSet.as_view({"post": "create"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_201_CREATED
    assert payload["data"]["refresh_interval"] == DEFAULT_CANVAS_REFRESH_INTERVAL_MS
    dashboard = Dashboard.objects.get(name="周期盘")
    assert dashboard.refresh_interval == 0


@pytest.mark.django_db
def test_patch_dashboard_refresh_interval_and_put_layout_keeps_it(authenticated_user):
    user = _superuser(authenticated_user)
    directory = _directory()
    dashboard = Dashboard.objects.create(
        name="保存覆盖盘",
        groups=[1],
        directory=directory,
        created_by="testuser",
        refresh_interval=0,
    )

    patch_request = _request(
        "patch",
        f"/dashboard/{dashboard.id}/",
        user,
        data={"refresh_interval": 60000},
    )
    patch_response = view_module.DashboardModelViewSet.as_view({"patch": "partial_update"})(
        patch_request,
        pk=str(dashboard.id),
    )
    patch_payload = _render(patch_response)
    assert patch_response.status_code == status.HTTP_200_OK
    assert patch_payload["data"]["refresh_interval"] == 60000

    put_request = _request(
        "put",
        f"/dashboard/{dashboard.id}/",
        user,
        data={
            "name": dashboard.name,
            "desc": "",
            "filters": [],
            "other": {},
            "view_sets": [],
        },
    )
    put_response = view_module.DashboardModelViewSet.as_view({"put": "update"})(
        put_request,
        pk=str(dashboard.id),
    )
    _render(put_response)
    assert put_response.status_code == status.HTTP_200_OK
    dashboard.refresh_from_db()
    assert dashboard.refresh_interval == 60000


@pytest.mark.django_db
@pytest.mark.parametrize("invalid", [60, 1, 15000, -1])
def test_patch_dashboard_rejects_illegal_refresh_interval(authenticated_user, invalid):
    user = _superuser(authenticated_user)
    directory = _directory()
    dashboard = Dashboard.objects.create(
        name=f"非法间隔-{invalid}",
        groups=[1],
        directory=directory,
        created_by="testuser",
    )
    request = _request(
        "patch",
        f"/dashboard/{dashboard.id}/",
        user,
        data={"refresh_interval": invalid},
    )
    response = view_module.DashboardModelViewSet.as_view({"patch": "partial_update"})(
        request,
        pk=str(dashboard.id),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    dashboard.refresh_from_db()
    assert dashboard.refresh_interval == 0


@pytest.mark.django_db
def test_screen_and_topology_accept_refresh_interval(authenticated_user):
    user = _superuser(authenticated_user)
    directory = _directory()
    screen = Screen.objects.create(
        name="周期大屏",
        groups=[1],
        directory=directory,
        created_by="testuser",
        view_sets={"viewport": {"width": 1920, "height": 1080}, "items": [], "decorations": {}},
    )
    topology = Topology.objects.create(
        name="周期拓扑",
        groups=[1],
        directory=directory,
        created_by="testuser",
    )

    for viewset, instance, path in (
        (view_module.ScreenModelViewSet, screen, f"/screen/{screen.id}/"),
        (view_module.TopologyModelViewSet, topology, f"/topology/{topology.id}/"),
    ):
        request = _request("patch", path, user, data={"refresh_interval": 300000})
        response = viewset.as_view({"patch": "partial_update"})(request, pk=str(instance.id))
        payload = _render(response)
        assert response.status_code == status.HTTP_200_OK
        assert payload["data"]["refresh_interval"] == 300000


@pytest.mark.django_db
def test_report_accepts_refresh_interval_without_view_sets(authenticated_user):
    user = _superuser(authenticated_user)
    directory = _directory()
    report = Report.objects.create(
        name="周期报表",
        groups=[1],
        directory=directory,
        created_by="testuser",
        view_sets={"schema_version": 1, "filters": [], "sections": []},
    )
    request = _request(
        "patch",
        f"/report/{report.id}/",
        user,
        data={"refresh_interval": 60000},
    )
    response = view_module.ReportModelViewSet.as_view({"patch": "partial_update"})(
        request,
        pk=str(report.id),
    )
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["refresh_interval"] == 60000
    report.refresh_from_db()
    assert report.refresh_interval == 60000


@pytest.mark.django_db
def test_network_topology_put_config_does_not_reset_refresh_interval(authenticated_user):
    user = _superuser(authenticated_user)
    directory = _directory()
    topology = NetworkTopology.objects.create(
        name="nt-refresh",
        groups=[1],
        directory=directory,
        created_by="testuser",
        base_url="https://weops.example.com",
        token="encrypted-token",
        refresh_interval=60000,
    )
    request = _request(
        "put",
        f"/network_topology/{topology.id}/config/",
        user,
        data={"nodes": [], "links": []},
    )
    response = NetworkTopologyViewSet.as_view({"put": "config"})(request, pk=str(topology.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    topology.refresh_from_db()
    assert topology.refresh_interval == 60000


@pytest.mark.django_db
def test_export_dashboard_yaml_includes_refresh_interval():
    directory = _directory()
    dashboard = Dashboard.objects.create(
        name="导出间隔盘",
        groups=[1],
        directory=directory,
        created_by="testuser",
        refresh_interval=60000,
    )
    yaml_obj = ExportService.convert_canvas_to_yaml(dashboard, ObjectType.DASHBOARD, {}, {})
    assert yaml_obj["refresh_interval"] == 60000


@pytest.mark.django_db
def test_export_report_yaml_includes_refresh_interval():
    directory = _directory()
    report = Report.objects.create(
        name="导出间隔报表",
        groups=[1],
        directory=directory,
        created_by="testuser",
        refresh_interval=60000,
        view_sets={"schema_version": 1, "filters": [], "sections": []},
    )
    yaml_obj = ExportService.convert_canvas_to_yaml(report, ObjectType.REPORT, {}, {})
    assert yaml_obj["refresh_interval"] == 60000


@pytest.mark.django_db
def test_export_architecture_yaml_omits_refresh_interval():
    directory = _directory()
    architecture = Architecture.objects.create(
        name="架构无间隔",
        groups=[1],
        directory=directory,
        created_by="testuser",
    )
    yaml_obj = ExportService.convert_canvas_to_yaml(architecture, ObjectType.ARCHITECTURE, {}, {})
    assert "refresh_interval" not in yaml_obj


@pytest.mark.parametrize("raw, expected", [(None, 0), (60, 0), (1, 0), (300000, 300000)])
def test_yaml_item_normalizes_illegal_refresh_interval(raw, expected):
    payload = {"key": "dashboard::yaml-refresh", "name": "yaml-refresh"}
    if raw is not None:
        payload["refresh_interval"] = raw
    item = DashboardItem(**payload)
    assert item.refresh_interval == expected


def test_yaml_network_topology_legacy_60_imports_as_off():
    item = NetworkTopologyItem(
        key="networkTopology::nt-a",
        name="nt-a",
        base_url="https://weops.example.com",
        refresh_interval=60,
    )
    assert item.refresh_interval == 0


@pytest.mark.django_db
def test_share_payload_includes_refresh_interval_for_runtime_canvases():
    directory = _directory()
    dashboard = Dashboard.objects.create(
        name="分享间隔盘",
        groups=[1],
        directory=directory,
        created_by="testuser",
        refresh_interval=300000,
    )
    report = Report.objects.create(
        name="分享间隔报表",
        groups=[1],
        directory=directory,
        created_by="testuser",
        refresh_interval=60000,
        view_sets={"schema_version": 1, "filters": [], "sections": []},
    )
    architecture = Architecture.objects.create(
        name="分享架构",
        groups=[1],
        directory=directory,
        created_by="testuser",
    )
    network = NetworkTopology.objects.create(
        name="分享网络拓扑",
        groups=[1],
        directory=directory,
        created_by="testuser",
        base_url="https://weops.example.com",
        token="encrypted-token",
        refresh_interval=600000,
    )

    dashboard_payload = _serialize_shared_resource(type("Principal", (), {"resource_type": "dashboard", "resource": dashboard})())
    report_payload = _serialize_shared_resource(type("Principal", (), {"resource_type": "report", "resource": report})())
    architecture_payload = _serialize_shared_resource(type("Principal", (), {"resource_type": "architecture", "resource": architecture})())
    network_payload = _serialize_shared_resource(type("Principal", (), {"resource_type": "networkTopology", "resource": network})())

    assert dashboard_payload["refresh_interval"] == 300000
    assert report_payload["refresh_interval"] == 60000
    assert "refresh_interval" not in architecture_payload
    assert network_payload["refresh_interval"] == 600000
