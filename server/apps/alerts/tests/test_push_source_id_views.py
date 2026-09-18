"""监控源目录 options 接口：按当前组织返回候选，权限对齐告警源 options。"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.service.push_source_catalog import MemoryCatalogStore, PushSourceCatalog
from apps.alerts.views.push_source_id import PushSourceIdViewSet


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


@pytest.fixture
def permission_user(authenticated_user):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {}
    return authenticated_user


@pytest.fixture(autouse=True)
def memory_catalog(monkeypatch):
    from apps.alerts.service import push_source_catalog as catalog_mod

    catalog = PushSourceCatalog(store=MemoryCatalogStore(), now=lambda: 1_700_000_000, min_interval=0)
    monkeypatch.setattr(catalog_mod, "_default_catalog", catalog)
    return catalog


def _request(method, path, user, team=None):
    factory = APIRequestFactory()
    request = getattr(factory, method)(path)
    force_authenticate(request, user=user)
    if team is not None:
        request.COOKIES["current_team"] = str(team)
    return request


def _render(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _items(response):
    payload = _render(response)
    data = payload["data"]
    return data["items"] if isinstance(data, dict) else data


def _seed_catalog(cat):
    cat.observe([1], ["prod", "001"])
    cat.observe([2], ["other"])
    cat.store.set(cat.READY_KEY.format(team_id=1), 1)
    cat.store.set(cat.READY_KEY.format(team_id=2), 1)


@pytest.mark.django_db
def test_push_source_options_returns_current_team_catalog(superuser, memory_catalog):
    _seed_catalog(memory_catalog)
    request = _request("get", "/push_source_ids/options/", superuser, team=1)
    response = PushSourceIdViewSet.as_view({"get": "options"})(request)
    assert response.status_code == status.HTTP_200_OK
    assert _items(response) == ["001", "prod"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "permission",
    [
        "Integration-View",
        "Alarms-View",
        "alert_assign-View",
        "shield_strategy-View",
        "alert_enrichment-View",
        "correlation_rules-View",
        "action_rules-View",
    ],
)
def test_push_source_options_allow_rule_pages(permission_user, permission, memory_catalog):
    permission_user.permission = {"alarm": {permission}}
    _seed_catalog(memory_catalog)
    request = _request("get", "/push_source_ids/options/", permission_user, team=1)
    response = PushSourceIdViewSet.as_view({"get": "options"})(request)
    assert response.status_code == status.HTTP_200_OK
    assert _items(response) == ["001", "prod"]


@pytest.mark.django_db
def test_push_source_options_reject_without_permission(permission_user):
    request = _request("get", "/push_source_ids/options/", permission_user, team=1)
    response = PushSourceIdViewSet.as_view({"get": "options"})(request)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_push_source_options_missing_current_team_returns_empty(superuser, memory_catalog):
    _seed_catalog(memory_catalog)
    request = _request("get", "/push_source_ids/options/", superuser)
    response = PushSourceIdViewSet.as_view({"get": "options"})(request)
    assert response.status_code == status.HTTP_200_OK
    assert _items(response) == []
