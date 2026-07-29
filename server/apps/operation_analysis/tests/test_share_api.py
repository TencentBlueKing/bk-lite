import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
from apps.system_mgmt.models.menu import Menu
from apps.system_mgmt.models.role import Role
from apps.system_mgmt.models.user import User


@pytest.fixture
def dashboard(db):
    directory = Directory.objects.create(name=f"share-api-dir-{uuid.uuid4()}", groups=[1], created_by="alice")
    return Dashboard.objects.create(
        name=f"share-api-dashboard-{uuid.uuid4()}",
        directory=directory,
        groups=[1],
        created_by="alice",
        domain="domain.com",
        view_sets=[],
    )


@pytest.fixture
def sharer(db):
    User.objects.create(
        username="alice",
        domain="domain.com",
        display_name="Alice",
        email="alice@example.com",
        password="x",
        group_list=[{"id": 1}],
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


@pytest.fixture
def visitor(db):
    User.objects.create(
        username="bob",
        domain="other.com",
        display_name="Bob",
        email="bob@example.com",
        password="x",
        group_list=[{"id": 99}],
    )
    return SimpleNamespace(
        id=2,
        pk=2,
        username="bob",
        domain="other.com",
        disabled=False,
        is_superuser=False,
        is_authenticated=True,
        locale="zh-Hans",
        group_list=[{"id": 99}],
    )


@pytest.mark.django_db
def test_prepare_is_login_exempt_for_auth_middleware():
    """未登录 prepare 不带 Bearer；必须绕过 AuthMiddleware，否则登录后会被误判为会话过期。"""
    from apps.core.middlewares.auth_middleware import AuthMiddleware
    from apps.operation_analysis.views.share_view import DashboardShareAccessViewSet
    from django.test import RequestFactory

    view = DashboardShareAccessViewSet.as_view({"post": "prepare"})
    assert getattr(view, "login_exempt", False) is True

    mw = AuthMiddleware(get_response=lambda request: None)
    request = RequestFactory().post(
        "/api/v1/operation_analysis/api/dashboard_share/prepare/",
        data='{"token":"x"}',
        content_type="application/json",
    )
    assert mw.process_view(request, view, [], {}) is None


@pytest.mark.django_db
def test_anonymous_prepare_returns_state_without_bearer(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    sharer_client = APIClient()
    sharer_client.force_authenticate(sharer)
    sharer_client.cookies["current_team"] = "1"
    created = sharer_client.post(
        f"/api/v1/operation_analysis/api/dashboard/{dashboard.id}/share/",
        {},
        format="json",
    )
    token = created.data["url"].rsplit("/", 1)[-1]

    anonymous = APIClient()
    response = anonymous.post(
        "/api/v1/operation_analysis/api/dashboard_share/prepare/",
        {"token": token},
        format="json",
    )
    assert response.status_code == 200
    assert "state" in response.data
    assert response.data["state"]
    assert "bk_dashboard_share_prep" in response.cookies


@pytest.mark.django_db
def test_prepare_then_exchange_with_nonce_cookie(settings, dashboard, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    # 全局测试用 DummyCache，这里换成可读写内存缓存，否则 prepare state 无法跨请求
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

    sharer_client = APIClient()
    sharer_client.force_authenticate(sharer)
    sharer_client.cookies["current_team"] = "1"
    created = sharer_client.post(
        f"/api/v1/operation_analysis/api/dashboard/{dashboard.id}/share/",
        {},
        format="json",
    )
    token = created.data["url"].rsplit("/", 1)[-1]

    browser = APIClient()
    prepared = browser.post(
        "/api/v1/operation_analysis/api/dashboard_share/prepare/",
        {"token": token},
        format="json",
    )
    assert prepared.status_code == 200
    assert "bk_dashboard_share_prep" in prepared.cookies
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
    assert exchanged.data["session_id"]


@pytest.mark.django_db
def test_share_api_is_idempotent_and_post_only(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    client = APIClient()
    client.force_authenticate(sharer)
    client.cookies["current_team"] = "1"
    path = f"/api/v1/operation_analysis/api/dashboard/{dashboard.id}/share/"

    first = client.post(path, {}, format="json")
    second = client.post(path, {}, format="json")

    assert first.status_code == second.status_code == 200
    assert first.data["url"] == second.data["url"]
    assert set(first.data) == {"id", "url", "status", "sharer_username", "resource_type"}
    assert client.get(path).status_code == 405
    assert client.delete(f"{path}{first.data['id']}/").status_code == 404


@pytest.mark.django_db
def test_cross_tenant_visitor_can_exchange_and_read_dashboard(settings, dashboard, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-key"
    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_canvas", lambda **_: True)
    sharer_client = APIClient()
    sharer_client.force_authenticate(sharer)
    sharer_client.cookies["current_team"] = "1"
    created = sharer_client.post(
        f"/api/v1/operation_analysis/api/dashboard/{dashboard.id}/share/",
        {},
        format="json",
    )
    token = created.data["url"].rsplit("/", 1)[-1]

    visitor_client = APIClient()
    visitor_client.force_authenticate(visitor)
    exchanged = visitor_client.post(
        "/api/v1/operation_analysis/api/dashboard_share/exchange/",
        {"token": token},
        format="json",
    )
    assert exchanged.status_code == 200

    detail = visitor_client.get(
        f"/api/v1/operation_analysis/api/dashboard_share/session/{exchanged.data['session_id']}/",
    )
    assert detail.status_code == 200
    assert detail.data["id"] == dashboard.id
    assert "groups" not in detail.data
    assert "created_by" not in detail.data


@pytest.mark.django_db
def test_share_query_rejects_datasource_not_declared_by_dashboard(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-key"
    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_canvas", lambda **_: True)
    datasource = DataSourceAPIModel.objects.create(
        name=f"unrelated-{uuid.uuid4()}",
        rest_api="monitor/test",
        groups=[1],
        created_by="alice",
        updated_by="alice",
    )
    sharer_client = APIClient()
    sharer_client.force_authenticate(sharer)
    sharer_client.cookies["current_team"] = "1"
    created = sharer_client.post(
        f"/api/v1/operation_analysis/api/dashboard/{dashboard.id}/share/",
        {},
        format="json",
    )
    token = created.data["url"].rsplit("/", 1)[-1]
    visitor_client = APIClient()
    visitor_client.force_authenticate(visitor)
    exchanged = visitor_client.post(
        "/api/v1/operation_analysis/api/dashboard_share/exchange/",
        {"token": token},
        format="json",
    )

    response = visitor_client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/"
        f"{exchanged.data['session_id']}/query/{datasource.id}/",
        {},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_share_datasource_metadata_is_scoped_and_secret_free(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-key"
    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_canvas", lambda **_: True)
    datasource = DataSourceAPIModel.objects.create(
        name=f"shared-{uuid.uuid4()}",
        rest_api="monitor/test",
        groups=[1],
        params=[{"name": "host", "type": "string"}],
        connection_config={"password": "secret"},
        created_by="alice",
        updated_by="alice",
    )
    dashboard.view_sets = [{"valueConfig": {"dataSource": datasource.id}}]
    dashboard.save(update_fields=["view_sets"])
    sharer_client = APIClient()
    sharer_client.force_authenticate(sharer)
    sharer_client.cookies["current_team"] = "1"
    created = sharer_client.post(
        f"/api/v1/operation_analysis/api/dashboard/{dashboard.id}/share/",
        {},
        format="json",
    )
    visitor_client = APIClient()
    visitor_client.force_authenticate(visitor)
    exchanged = visitor_client.post(
        "/api/v1/operation_analysis/api/dashboard_share/exchange/",
        {"token": created.data["url"].rsplit("/", 1)[-1]},
        format="json",
    )

    response = visitor_client.get(
        f"/api/v1/operation_analysis/api/dashboard_share/session/"
        f"{exchanged.data['session_id']}/data_sources/",
    )

    assert response.status_code == 200
    assert response.data[0]["id"] == datasource.id
    assert "connection_config" not in response.data[0]
    assert "query_config" not in response.data[0]
    assert "rest_api" not in response.data[0]
    assert "tag" not in response.data[0]


@pytest.mark.django_db
def test_share_query_uses_sharer_runtime_authorization_context(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-key"
    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_canvas", lambda **_: True)
    namespace = NameSpace.objects.create(
        name=f"shared-query-{uuid.uuid4()}",
        account="test",
        password="test",
        domain="localhost:4222",
    )
    datasource = DataSourceAPIModel.objects.create(
        name=f"shared-query-{uuid.uuid4()}",
        rest_api="monitor/test",
        groups=[1],
        params=[{"name": "region", "value": "east"}],
        created_by="alice",
        updated_by="alice",
    )
    datasource.namespaces.add(namespace)
    dashboard.view_sets = [
        {
            "valueConfig": {
                "dataSource": datasource.id,
                "dataSourceParams": [{"name": "region", "filterType": "filter"}],
            }
        }
    ]
    dashboard.save(update_fields=["view_sets"])
    data_source_menu = Menu.objects.create(
        name="data_source-View",
        display_name="View data source",
        url="",
        app="ops-analysis",
    )
    role = Role.objects.create(
        name=f"shared-query-role-{uuid.uuid4()}",
        app="ops-analysis",
        menu_list=[data_source_menu.id],
    )
    persisted_sharer = User.objects.get(username="alice", domain="domain.com")
    persisted_sharer.role_list = [role.id]
    persisted_sharer.group_list = []
    persisted_sharer.save(update_fields=["role_list", "group_list"])

    def fake_get_data(self):
        if not self.params["user_info"]["permission"]:
            raise RuntimeError("missing sharer runtime authorization")
        return {"result": True, "data": [{"region": "east", "count": 1}]}

    monkeypatch.setattr(
        "apps.operation_analysis.common.get_nats_source_data.GetNatsData.get_data",
        fake_get_data,
    )
    sharer_client = APIClient()
    sharer_client.force_authenticate(sharer)
    sharer_client.cookies["current_team"] = "1"
    created = sharer_client.post(
        f"/api/v1/operation_analysis/api/dashboard/{dashboard.id}/share/",
        {},
        format="json",
    )
    visitor_client = APIClient()
    visitor_client.force_authenticate(visitor)
    exchanged = visitor_client.post(
        "/api/v1/operation_analysis/api/dashboard_share/exchange/",
        {"token": created.data["url"].rsplit("/", 1)[-1]},
        format="json",
    )

    response = visitor_client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/"
        f"{exchanged.data['session_id']}/query/{datasource.id}/",
        {"region": "east"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data == [{"region": "east", "count": 1}]
