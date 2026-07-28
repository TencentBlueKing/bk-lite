import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, Report, Screen, Topology
from apps.operation_analysis.models.share_models import DashboardShareLink
from apps.operation_analysis.services.share_service import create_or_get_share, exchange_share
from apps.system_mgmt.models.user import User


@pytest.fixture
def sharer(db):
    User.objects.create(
        username="canvas-sharer",
        domain="domain.com",
        display_name="Sharer",
        email="canvas-sharer@example.com",
        password="x",
        group_list=[{"id": 1}],
    )
    return SimpleNamespace(
        id=1,
        pk=1,
        username="canvas-sharer",
        domain="domain.com",
        disabled=False,
        is_superuser=True,
        is_authenticated=True,
        locale="zh-Hans",
        group_list=[{"id": 1}],
    )


@pytest.fixture
def visitor(db):
    User.objects.create(
        username="canvas-visitor",
        domain="other.com",
        display_name="Visitor",
        email="canvas-visitor@example.com",
        password="x",
        group_list=[{"id": 99}],
    )
    return SimpleNamespace(
        id=2,
        pk=2,
        username="canvas-visitor",
        domain="other.com",
        disabled=False,
        is_superuser=False,
        is_authenticated=True,
        locale="zh-Hans",
        group_list=[{"id": 99}],
    )


def _make_directory():
    return Directory.objects.create(name=f"canvas-dir-{uuid.uuid4()}", groups=[1], created_by="alice")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "model,resource_type,endpoint",
    [
        (Screen, DashboardShareLink.ResourceType.SCREEN, "screen"),
        (Topology, DashboardShareLink.ResourceType.TOPOLOGY, "topology"),
        (Architecture, DashboardShareLink.ResourceType.ARCHITECTURE, "architecture"),
    ],
)
def test_create_share_for_canvas_types(
    settings, sharer, visitor, monkeypatch, model, resource_type, endpoint
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    directory = _make_directory()
    resource = model.objects.create(
        name=f"share-{resource_type}-{uuid.uuid4()}",
        directory=directory,
        groups=[1],
        created_by="alice",
        domain="domain.com",
        view_sets=[],
    )

    result = create_or_get_share(
        resource_type=resource_type,
        resource=resource,
        sharer=sharer,
        tenant_domain=resource.domain,
        space_id=1,
    )
    assert result.link.resource_type == resource_type
    assert result.link.dashboard_instance_id == resource.pk
    assert result.link.dashboard_id is None

    session = exchange_share(token=result.token, visitor=visitor)
    assert session.share_link.resource_type == resource_type

    client = APIClient()
    client.force_authenticate(visitor)
    detail = client.get(f"/api/v1/operation_analysis/api/dashboard_share/session/{session.session_id}/")
    assert detail.status_code == 200
    assert detail.data["resource_type"] == resource_type
    assert detail.data["id"] == resource.id


@pytest.mark.django_db
def test_detail_only_architecture_rejects_datasource_query(settings, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    directory = _make_directory()
    resource = Architecture.objects.create(
        name=f"share-query-architecture-{uuid.uuid4()}",
        directory=directory,
        groups=[1],
        created_by="alice",
        domain="domain.com",
        view_sets=[],
    )
    result = create_or_get_share(
        resource_type=DashboardShareLink.ResourceType.ARCHITECTURE,
        resource=resource,
        sharer=sharer,
        tenant_domain=resource.domain,
        space_id=1,
    )
    session = exchange_share(token=result.token, visitor=visitor)

    client = APIClient()
    client.force_authenticate(visitor)
    response = client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/{session.session_id}/query/1/",
        {},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_report_share_api_is_not_open(settings, sharer, monkeypatch):
    """第一阶段不开放报表分享入口，但 resource_type 仍保留。"""
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    directory = _make_directory()
    report = Report.objects.create(
        name=f"share-report-api-{uuid.uuid4()}",
        directory=directory,
        groups=[1],
        created_by="alice",
        domain="domain.com",
        view_sets={},
    )
    client = APIClient()
    client.force_authenticate(sharer)
    client.cookies["current_team"] = "1"
    response = client.post(
        f"/api/v1/operation_analysis/api/report/{report.id}/share/",
        {},
        format="json",
    )
    assert response.status_code == 405
    assert not DashboardShareLink.objects.filter(
        resource_type=DashboardShareLink.ResourceType.REPORT,
        dashboard_instance_id=report.pk,
    ).exists()


@pytest.mark.django_db
def test_report_resource_type_still_supported_by_service(settings, sharer, visitor, monkeypatch):
    """service 层仍支持 report resource_type，便于后续阶段接入。"""
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    directory = _make_directory()
    report = Report.objects.create(
        name=f"share-report-service-{uuid.uuid4()}",
        directory=directory,
        groups=[1],
        created_by="alice",
        domain="domain.com",
        view_sets={},
    )
    result = create_or_get_share(
        resource_type=DashboardShareLink.ResourceType.REPORT,
        resource=report,
        sharer=sharer,
        tenant_domain=report.domain,
        space_id=1,
    )
    assert result.link.resource_type == DashboardShareLink.ResourceType.REPORT
    session = exchange_share(token=result.token, visitor=visitor)
    client = APIClient()
    client.force_authenticate(visitor)
    detail = client.get(f"/api/v1/operation_analysis/api/dashboard_share/session/{session.session_id}/")
    assert detail.status_code == 200
    assert detail.data["resource_type"] == DashboardShareLink.ResourceType.REPORT
    query = client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/{session.session_id}/query/1/",
        {},
        format="json",
    )
    assert query.status_code == 403


@pytest.mark.django_db
def test_screen_share_api_endpoint(settings, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    directory = _make_directory()
    screen = Screen.objects.create(
        name=f"share-screen-api-{uuid.uuid4()}",
        directory=directory,
        groups=[1],
        created_by="alice",
        domain="domain.com",
        view_sets={},
    )
    client = APIClient()
    client.force_authenticate(sharer)
    client.cookies["current_team"] = "1"
    response = client.post(
        f"/api/v1/operation_analysis/api/screen/{screen.id}/share/",
        {},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["resource_type"] == DashboardShareLink.ResourceType.SCREEN
    assert "/ops-analysis/share/" in response.data["url"]
