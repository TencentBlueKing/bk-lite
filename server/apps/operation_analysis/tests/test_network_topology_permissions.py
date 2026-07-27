import uuid

import pytest
from rest_framework.test import APIClient

from apps.base.models import User
from apps.operation_analysis.models.models import Directory, NetworkTopology


def _make_user(*, username: str, groups: list[int], permissions: set[str]):
    user = User.objects.create_user(
        username=username,
        password="testpass123",
        domain="domain.com",
        locale="en",
        group_list=[{"id": group_id, "name": f"Team {group_id}"} for group_id in groups],
        roles=[],
    )
    user.permission = {"ops-analysis": permissions}
    user.is_superuser = False
    return user


def _make_topology():
    directory = Directory.objects.create(
        name=f"nt-auth-dir-{uuid.uuid4()}",
        groups=[1],
        domain="domain.com",
    )
    return NetworkTopology.objects.create(
        name=f"nt-auth-{uuid.uuid4()}",
        directory=directory,
        groups=[1],
        domain="domain.com",
        created_by="owner",
        updated_by="owner",
        base_url="https://weops.example.com",
        token="service-token",
        view_sets={"nodes": [], "links": []},
    )


def _client_for(user, *, current_team: int):
    client = APIClient()
    client.force_authenticate(user=user)
    client.cookies["current_team"] = str(current_team)
    client.cookies["include_children"] = "0"
    return client


def _grant_instance(monkeypatch, topology, *permissions):
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *args, **kwargs: {
            "team": [],
            "instance": [
                {
                    "id": topology.id,
                    "permission": list(permissions),
                }
            ],
        },
    )


@pytest.mark.django_db
def test_non_space_member_cannot_read_config_or_call_metric_values(monkeypatch):
    topology = _make_topology()
    visitor = _make_user(
        username=f"nt-foreign-{uuid.uuid4()}",
        groups=[99],
        permissions={"view-View"},
    )
    client = _client_for(visitor, current_team=99)
    adapter_called = False

    class FakeAdapter:
        def batch_metric_values(self, items):
            nonlocal adapter_called
            adapter_called = True
            return {"items": []}

    monkeypatch.setattr(
        "apps.operation_analysis.views.network_topology_view._adapter_for",
        lambda _: FakeAdapter(),
    )

    config_response = client.get(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/config/"
    )
    metric_response = client.post(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/weops/metric_values/",
        {"items": []},
        format="json",
    )

    assert config_response.status_code == 403
    assert metric_response.status_code == 403
    assert adapter_called is False


@pytest.mark.django_db
def test_space_member_without_view_rule_cannot_read_topology_config(monkeypatch):
    topology = _make_topology()
    member = _make_user(
        username=f"nt-member-no-view-{uuid.uuid4()}",
        groups=[1],
        permissions={"view-View"},
    )
    client = _client_for(member, current_team=1)
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *args, **kwargs: {"team": [], "instance": []},
    )

    response = client.get(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/config/"
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_space_member_with_view_rule_can_read_topology_and_config(monkeypatch):
    topology = _make_topology()
    viewer = _make_user(
        username=f"nt-viewer-{uuid.uuid4()}",
        groups=[1],
        permissions={"view-View"},
    )
    client = _client_for(viewer, current_team=1)
    _grant_instance(monkeypatch, topology, "View")

    detail_response = client.get(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/"
    )
    config_response = client.get(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/config/"
    )

    assert detail_response.status_code == 200
    assert config_response.status_code == 200


@pytest.mark.django_db
def test_space_member_with_edit_rule_can_update_topology(monkeypatch):
    topology = _make_topology()
    editor = _make_user(
        username="nt-editor",
        groups=[1],
        permissions={"view-EditChart"},
    )
    client = _client_for(editor, current_team=1)
    _grant_instance(monkeypatch, topology, "Operate")

    response = client.patch(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/",
        {"name": "updated-by-editor"},
        format="json",
    )

    assert response.status_code == 200
    topology.refresh_from_db()
    assert topology.name == "updated-by-editor"


@pytest.mark.django_db
def test_update_and_delete_require_their_feature_permissions(monkeypatch):
    topology = _make_topology()
    viewer = _make_user(
        username=f"nt-view-only-{uuid.uuid4()}",
        groups=[1],
        permissions={"view-View"},
    )
    client = _client_for(viewer, current_team=1)
    _grant_instance(monkeypatch, topology, "View", "Operate")

    update_response = client.patch(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/",
        {"name": "must-not-change"},
        format="json",
    )
    delete_response = client.delete(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/"
    )

    assert update_response.status_code == 403
    assert delete_response.status_code == 403
    topology.refresh_from_db()
    assert topology.name != "must-not-change"


@pytest.mark.django_db
def test_space_member_with_delete_permission_can_delete_topology(monkeypatch):
    topology = _make_topology()
    topology_id = topology.id
    deleter = _make_user(
        username="nt-deleter",
        groups=[1],
        permissions={"view-DeleteChart"},
    )
    client = _client_for(deleter, current_team=1)
    _grant_instance(monkeypatch, topology, "Operate")

    response = client.delete(
        f"/api/v1/operation_analysis/api/network_topology/{topology_id}/"
    )

    assert response.status_code == 200
    assert NetworkTopology.objects.filter(id=topology_id).exists() is False
