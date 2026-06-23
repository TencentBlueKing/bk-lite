"""NetworkWhiteListViewSet：CRUD + 权限门 + 缓存失效。

复用仓库既有 system_mgmt viewset 测试范式：APIRequestFactory + force_authenticate(SimpleNamespace)。
"""
import types

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.viewset.network_white_list_viewset import NetworkWhiteListViewSet

factory = APIRequestFactory()


def _user(perms, is_superuser=True):
    return types.SimpleNamespace(
        username="nwl-admin",
        domain="domain.com",
        locale="en",
        is_superuser=is_superuser,
        is_authenticated=True,
        permission={"system-manager": set(perms)},
    )


@pytest.mark.django_db
def test_create_normalizes_and_invalidates_cache(mocker):
    inval = mocker.patch("apps.system_mgmt.viewset.network_white_list_viewset.invalidate_network_whitelist_cache")
    view = NetworkWhiteListViewSet.as_view({"post": "create"})
    request = factory.post(
        "/system_mgmt/network_white_list/",
        {"network": "10.11.73.15", "remark": "mcp"},
        format="json",
    )
    force_authenticate(request, user=_user({"network_white_list-Add"}))

    response = view(request)

    assert response.status_code == 201
    assert response.data["network"] == "10.11.73.15/32"
    assert response.data["created_by"] == "nwl-admin"
    inval.assert_called_once()


@pytest.mark.django_db
def test_create_rejects_invalid_cidr():
    view = NetworkWhiteListViewSet.as_view({"post": "create"})
    request = factory.post("/system_mgmt/network_white_list/", {"network": "bad-cidr"}, format="json")
    force_authenticate(request, user=_user({"network_white_list-Add"}))

    response = view(request)

    assert response.status_code == 400


@pytest.mark.django_db
def test_create_denied_without_permission():
    view = NetworkWhiteListViewSet.as_view({"post": "create"})
    request = factory.post("/system_mgmt/network_white_list/", {"network": "10.11.73.0/24"}, format="json")
    force_authenticate(request, user=_user(set(), is_superuser=False))

    response = view(request)

    assert response.status_code == 403


@pytest.mark.django_db
def test_list_returns_rows():
    from apps.system_mgmt.models import NetworkWhiteList

    NetworkWhiteList.objects.create(network="10.11.73.0/24")
    view = NetworkWhiteListViewSet.as_view({"get": "list"})
    request = factory.get("/system_mgmt/network_white_list/")
    force_authenticate(request, user=_user({"network_white_list-View"}))

    response = view(request)

    assert response.status_code == 200
    rows = response.data["results"] if isinstance(response.data, dict) else response.data
    networks = [item["network"] for item in rows]
    assert "10.11.73.0/24" in networks
