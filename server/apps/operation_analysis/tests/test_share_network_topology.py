import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.operation_analysis.models.models import Directory, NetworkTopology
from apps.operation_analysis.models.share_models import DashboardShareLink
from apps.operation_analysis.services.share_service import (
    create_or_get_share,
    exchange_share,
)
from apps.system_mgmt.models.user import User


@pytest.fixture
def sharer(db):
    User.objects.create(
        username="nt-sharer",
        domain="domain.com",
        display_name="Sharer",
        email="nt-sharer@example.com",
        password="x",
        group_list=[{"id": 1}],
    )
    return SimpleNamespace(
        id=1,
        pk=1,
        username="nt-sharer",
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
        username="nt-visitor",
        domain="other.com",
        display_name="Visitor",
        email="nt-visitor@example.com",
        password="x",
        group_list=[{"id": 99}],
    )
    return SimpleNamespace(
        id=2,
        pk=2,
        username="nt-visitor",
        domain="other.com",
        disabled=False,
        is_superuser=False,
        is_authenticated=True,
        locale="zh-Hans",
        group_list=[{"id": 99}],
    )


def _make_network_topology(**overrides):
    directory = Directory.objects.create(
        name=f"nt-dir-{uuid.uuid4()}",
        groups=[1],
        created_by="alice",
    )
    defaults = {
        "name": f"nt-share-{uuid.uuid4()}",
        "directory": directory,
        "groups": [1],
        "domain": "domain.com",
        "created_by": "alice",
        "base_url": "https://weops.example.com",
        "token": "super-secret-weops-token",
        "view_sets": {
            "nodes": [],
            "links": [],
        },
    }
    defaults.update(overrides)
    return NetworkTopology.objects.create(**defaults)


@pytest.mark.django_db
def test_create_network_topology_share_success(settings, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    topology = _make_network_topology()
    client = APIClient()
    client.force_authenticate(sharer)
    client.cookies["current_team"] = "1"
    response = client.post(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/share/",
        {},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["resource_type"] == DashboardShareLink.ResourceType.NETWORK_TOPOLOGY
    assert "/ops-analysis/share/" in response.data["url"]
    link = DashboardShareLink.objects.get(id=response.data["id"])
    assert link.resource_type == DashboardShareLink.ResourceType.NETWORK_TOPOLOGY
    assert link.dashboard_instance_id == topology.pk
    assert link.dashboard_id is None


@pytest.mark.django_db
def test_network_topology_prepare_exchange_session_detail_without_token(
    settings, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    store = {}

    def cache_add(key, value, timeout=None):
        if key in store:
            return False
        store[key] = value
        return True

    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.set",
        lambda key, value, timeout=None: store.__setitem__(key, value),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.get",
        lambda key, default=None: store.get(key, default),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.delete",
        lambda key: store.pop(key, None) is not None,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.add",
        cache_add,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.incr",
        lambda key: store.__setitem__(key, int(store.get(key, 0)) + 1) or store[key],
    )

    topology = _make_network_topology()
    sharer_client = APIClient()
    sharer_client.force_authenticate(sharer)
    sharer_client.cookies["current_team"] = "1"
    created = sharer_client.post(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/share/",
        {},
        format="json",
    )
    assert created.status_code == 200
    token = created.data["url"].rsplit("/", 1)[-1]

    browser = APIClient()
    prepared = browser.post(
        "/api/v1/operation_analysis/api/dashboard_share/prepare/",
        {"token": token},
        format="json",
    )
    assert prepared.status_code == 200
    nonce = prepared.cookies["bk_dashboard_share_prep"].value
    state = prepared.data["state"]

    browser.force_authenticate(visitor)
    exchanged = browser.post(
        "/api/v1/operation_analysis/api/dashboard_share/exchange/",
        {"state": state},
        format="json",
        HTTP_COOKIE=f"bk_dashboard_share_prep={nonce}",
    )
    assert exchanged.status_code == 200, exchanged.data
    session_id = exchanged.data["session_id"]

    detail = browser.get(f"/api/v1/operation_analysis/api/dashboard_share/session/{session_id}/")
    assert detail.status_code == 200
    assert detail.data["resource_type"] == DashboardShareLink.ResourceType.NETWORK_TOPOLOGY
    assert detail.data["id"] == topology.id
    assert detail.data["view_sets"] == {"nodes": [], "links": []}
    assert "token" not in detail.data
    assert "base_url" not in detail.data
    assert "last_runtime_cache" not in detail.data
    assert "token_set" not in detail.data
    serialized = str(detail.data)
    assert "super-secret-weops-token" not in serialized
    assert "weops.example.com" not in serialized


@pytest.mark.django_db
def test_network_topology_share_rejects_without_view_permission(settings, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: False,
    )
    topology = _make_network_topology()
    client = APIClient()
    client.force_authenticate(sharer)
    client.cookies["current_team"] = "1"
    response = client.post(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/share/",
        {},
        format="json",
    )
    assert response.status_code == 403
    assert not DashboardShareLink.objects.filter(
        resource_type=DashboardShareLink.ResourceType.NETWORK_TOPOLOGY,
        dashboard_instance_id=topology.pk,
        status=DashboardShareLink.Status.ACTIVE,
    ).exists()


@pytest.mark.django_db
def test_network_topology_session_rejects_datasource_query(
    settings, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    topology = _make_network_topology()
    result = create_or_get_share(
        resource_type=DashboardShareLink.ResourceType.NETWORK_TOPOLOGY,
        resource=topology,
        sharer=sharer,
        tenant_domain=topology.domain,
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
