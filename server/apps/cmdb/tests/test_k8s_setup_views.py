from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.services.k8s_setup import K8sSetupService
from apps.cmdb.views.k8s_setup import K8sSetupViewSet

pytestmark = pytest.mark.unit


def _user(permission=None):
    return SimpleNamespace(
        username="bob",
        is_superuser=False,
        is_authenticated=True,
        is_active=True,
        permission={"cmdb": set(permission or [])},
        group_list=[{"id": 1, "name": "Default Team"}],
        group_tree=[],
        roles=[],
        locale="en",
    )


def _call(action, user, data):
    request = APIRequestFactory().post(
        f"/api/v1/cmdb/api/k8s_setup/{action}/",
        data=data,
        format="json",
    )
    force_authenticate(request, user=user)
    return K8sSetupViewSet.as_view({"post": action})(request)


@pytest.mark.parametrize(
    ("action", "service_method", "payload"),
    [
        (
            "install_token",
            "generate_install_token",
            {"collector_cluster_id": "c1", "cloud_region_id": 1},
        ),
        (
            "install_command",
            "generate_install_command",
            {"collector_cluster_id": "c1", "cloud_region_id": 1},
        ),
        (
            "verify",
            "verify_collector_reporting",
            {"collector_cluster_id": "c1"},
        ),
    ],
)
def test_k8s_setup_internal_actions_reject_users_without_permission(
    action, service_method, payload
):
    with patch.object(K8sSetupService, service_method, return_value={}) as service:
        response = _call(action, _user(), payload)

    assert response.status_code == 403
    service.assert_not_called()


@pytest.mark.parametrize(
    ("action", "required_permission", "service_method", "payload", "result"),
    [
        (
            "install_token",
            "auto_collection-Execute",
            "generate_install_token",
            {"collector_cluster_id": "c1", "cloud_region_id": 1},
            {"token": "masked-token"},
        ),
        (
            "install_command",
            "auto_collection-Execute",
            "generate_install_command",
            {"collector_cluster_id": "c1", "cloud_region_id": 1},
            {"command": "kubectl apply"},
        ),
        (
            "verify",
            "auto_collection-View",
            "verify_collector_reporting",
            {"collector_cluster_id": "c1"},
            {"reporting": True},
        ),
    ],
)
def test_k8s_setup_internal_actions_allow_required_permission(
    action, required_permission, service_method, payload, result
):
    with patch.object(
        K8sSetupService, service_method, return_value=result
    ) as service:
        response = _call(action, _user({required_permission}), payload)

    assert response.status_code == 200
    service.assert_called_once()
