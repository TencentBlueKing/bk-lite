from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.node_mgmt.models import Collector
from apps.node_mgmt.views.collector import CollectorViewSet


pytestmark = pytest.mark.django_db


def _collector_payload(collector_id: str) -> dict:
    return {
        "id": collector_id,
        "name": "Issue 4071 Collector",
        "service_type": "svc",
        "node_operating_system": "linux",
        "cpu_architecture": "x86_64",
        "executable_path": "/opt/collector/bin/collector",
        "execute_parameters": "--config %s",
    }


def _request(method: str, path: str, data=None, permissions=()):
    request = getattr(APIRequestFactory(), method)(path, data=data, format="json")
    user = SimpleNamespace(
        is_authenticated=True,
        is_superuser=False,
        locale="en",
        permission={"node": set(permissions)},
    )
    force_authenticate(request, user=user)
    return request


def test_collector_create_requires_add_permission():
    view = CollectorViewSet.as_view({"post": "create"})
    payload = _collector_payload("issue-4071-create")

    denied = view(_request("post", "/node_mgmt/api/collector/", payload))

    assert denied.status_code == 403
    assert not Collector.objects.filter(id=payload["id"]).exists()

    allowed = view(
        _request(
            "post",
            "/node_mgmt/api/collector/",
            payload,
            permissions=("collector_list-Add",),
        )
    )

    assert allowed.status_code == 201
    assert Collector.objects.filter(id=payload["id"], is_pre=False).exists()


def test_collector_partial_update_requires_edit_permission():
    collector = Collector.objects.create(**_collector_payload("issue-4071-update"))
    view = CollectorViewSet.as_view({"patch": "partial_update"})

    denied = view(
        _request(
            "patch",
            f"/node_mgmt/api/collector/{collector.id}/",
            {"executable_path": "/tmp/denied"},
        ),
        pk=collector.id,
    )

    assert denied.status_code == 403
    collector.refresh_from_db()
    assert collector.executable_path == "/opt/collector/bin/collector"

    allowed = view(
        _request(
            "patch",
            f"/node_mgmt/api/collector/{collector.id}/",
            {"executable_path": "/opt/collector/bin/updated"},
            permissions=("collector_list-Edit",),
        ),
        pk=collector.id,
    )

    assert allowed.status_code == 200
    collector.refresh_from_db()
    assert collector.executable_path == "/opt/collector/bin/updated"


def test_collector_destroy_requires_delete_permission():
    collector = Collector.objects.create(**_collector_payload("issue-4071-delete"))
    view = CollectorViewSet.as_view({"delete": "destroy"})

    denied = view(
        _request("delete", f"/node_mgmt/api/collector/{collector.id}/"),
        pk=collector.id,
    )

    assert denied.status_code == 403
    assert Collector.objects.filter(id=collector.id).exists()

    allowed = view(
        _request(
            "delete",
            f"/node_mgmt/api/collector/{collector.id}/",
            permissions=("collector_list-Delete",),
        ),
        pk=collector.id,
    )

    assert allowed.status_code == 204
    assert not Collector.objects.filter(id=collector.id).exists()
