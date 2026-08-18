import json
from types import SimpleNamespace

import pytest
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.models.sidecar import CloudRegion, Node, NodeOrganization
from apps.node_mgmt.tasks import sidecar_config as sidecar_config_tasks
from apps.node_mgmt.views import node as node_view
from rest_framework.test import APIRequestFactory, force_authenticate


def _request(data, permissions=("cloud_region_node-Edit",)):
    request = APIRequestFactory().post("/node_mgmt/api/node/batch_update_organizations/", data, format="json")
    user = SimpleNamespace(
        username="operator",
        domain="domain.com",
        locale="zh-Hans",
        is_superuser=False,
        is_authenticated=True,
        permission={"node": set(permissions)},
    )
    force_authenticate(request, user=user)
    request.user = user
    return request


def _node(region, node_id, organization):
    node = Node.objects.create(
        id=node_id,
        name=node_id,
        ip=f"10.0.0.{organization}",
        operating_system="linux",
        cpu_architecture="x86_64",
        collector_configuration_directory="/etc/collector",
        cloud_region=region,
        created_by="tester",
        updated_by="tester",
    )
    NodeOrganization.objects.create(node=node, organization=organization)
    return node


def test_batch_update_organizations_requires_edit_permission(monkeypatch):
    authorized = []
    monkeypatch.setattr(
        node_view,
        "authorize_node_ids",
        lambda request, node_ids: authorized.append(node_ids),
    )

    response = node_view.NodeViewSet.as_view({"post": "batch_update_organizations"})(
        _request(
            {"node_ids": ["node-1"], "organizations": [1]},
            permissions=(),
        )
    )

    assert response.status_code == 403
    assert authorized == []


@pytest.mark.django_db
def test_batch_update_organizations_replaces_assignments_for_all_selected_nodes(monkeypatch):
    region = CloudRegion.objects.create(name="batch-org-region", created_by="tester", updated_by="tester")
    first_node = _node(region, "batch-org-node-1", 1)
    second_node = _node(region, "batch-org-node-2", 2)
    monkeypatch.setattr(
        node_view,
        "authorize_node_ids",
        lambda request, node_ids: ([first_node, second_node], None),
    )
    monkeypatch.setattr(node_view, "authorize_target_organizations", lambda request, node, organizations: None)

    response = node_view.NodeViewSet.as_view({"post": "batch_update_organizations"})(
        _request(
            {
                "node_ids": [first_node.id, second_node.id],
                "organizations": [7, 8],
            }
        )
    )

    assert response.status_code == 200
    assert json.loads(response.content)["data"]["updated_count"] == 2
    assert set(NodeOrganization.objects.filter(node=first_node).values_list("organization", flat=True)) == {7, 8}
    assert set(NodeOrganization.objects.filter(node=second_node).values_list("organization", flat=True)) == {7, 8}


@pytest.mark.django_db
def test_batch_update_organizations_queues_one_sidecar_sync_after_commit(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    region = CloudRegion.objects.create(name="batch-org-sync-region", created_by="tester", updated_by="tester")
    first_node = _node(region, "batch-org-sync-node-1", 1)
    second_node = _node(region, "batch-org-sync-node-2", 1)
    monkeypatch.setattr(
        node_view,
        "authorize_node_ids",
        lambda request, node_ids: ([first_node, second_node], None),
    )
    monkeypatch.setattr(node_view, "authorize_target_organizations", lambda request, node, organizations: None)
    queued = []
    monkeypatch.setattr(
        node_view.sync_nodes_organizations_to_sidecar,
        "delay",
        lambda **kwargs: queued.append(kwargs),
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = node_view.NodeViewSet.as_view({"post": "batch_update_organizations"})(
            _request(
                {
                    "node_ids": [first_node.id, second_node.id],
                    "organizations": [9],
                }
            )
        )

    assert response.status_code == 200
    assert queued == [
        {
            "node_ids": [first_node.id, second_node.id],
            "organizations": [9],
        }
    ]


@pytest.mark.django_db
def test_batch_update_organizations_stays_successful_when_sidecar_queue_is_unavailable(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    region = CloudRegion.objects.create(name="batch-org-queue-failure-region", created_by="tester", updated_by="tester")
    node = _node(region, "batch-org-queue-failure-node", 1)
    monkeypatch.setattr(node_view, "authorize_node_ids", lambda request, node_ids: ([node], None))
    monkeypatch.setattr(node_view, "authorize_target_organizations", lambda request, target, organizations: None)

    def raise_queue_error(**kwargs):
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(node_view.sync_nodes_organizations_to_sidecar, "delay", raise_queue_error)

    with django_capture_on_commit_callbacks(execute=True):
        response = node_view.NodeViewSet.as_view({"post": "batch_update_organizations"})(_request({"node_ids": [node.id], "organizations": [7]}))

    assert response.status_code == 200
    assert list(NodeOrganization.objects.filter(node=node).values_list("organization", flat=True)) == [7]


@pytest.mark.django_db
def test_batch_update_organizations_rejects_duplicate_node_ids_without_changes(monkeypatch):
    region = CloudRegion.objects.create(name="batch-org-duplicate-region", created_by="tester", updated_by="tester")
    node = _node(region, "batch-org-duplicate-node", 1)
    monkeypatch.setattr(node_view, "authorize_node_ids", lambda request, node_ids: ([node, node], None))
    monkeypatch.setattr(node_view, "authorize_target_organizations", lambda request, target, organizations: None)

    response = node_view.NodeViewSet.as_view({"post": "batch_update_organizations"})(
        _request(
            {
                "node_ids": [node.id, node.id],
                "organizations": [7],
            }
        )
    )

    assert response.status_code == 400
    assert list(NodeOrganization.objects.filter(node=node).values_list("organization", flat=True)) == [1]


@pytest.mark.django_db
def test_batch_update_organizations_rejects_duplicate_organizations_without_changes(monkeypatch):
    region = CloudRegion.objects.create(name="batch-org-duplicate-org-region", created_by="tester", updated_by="tester")
    node = _node(region, "batch-org-duplicate-org-node", 1)
    monkeypatch.setattr(node_view, "authorize_node_ids", lambda request, node_ids: ([node], None))
    monkeypatch.setattr(node_view, "authorize_target_organizations", lambda request, target, organizations: None)

    response = node_view.NodeViewSet.as_view({"post": "batch_update_organizations"})(
        _request(
            {
                "node_ids": [node.id],
                "organizations": [7, 7],
            }
        )
    )

    assert response.status_code == 400
    assert list(NodeOrganization.objects.filter(node=node).values_list("organization", flat=True)) == [1]


@pytest.mark.django_db
def test_batch_update_organizations_rejects_unauthorized_nodes_without_changes(monkeypatch):
    region = CloudRegion.objects.create(name="batch-org-denied-region", created_by="tester", updated_by="tester")
    node = _node(region, "batch-org-denied-node", 1)
    monkeypatch.setattr(
        node_view,
        "authorize_node_ids",
        lambda request, node_ids: (None, WebUtils.response_403("denied")),
    )
    queued = []
    monkeypatch.setattr(
        node_view.sync_nodes_organizations_to_sidecar,
        "delay",
        lambda **kwargs: queued.append(kwargs),
    )

    response = node_view.NodeViewSet.as_view({"post": "batch_update_organizations"})(
        _request(
            {
                "node_ids": [node.id],
                "organizations": [7],
            }
        )
    )

    assert response.status_code == 403
    assert list(NodeOrganization.objects.filter(node=node).values_list("organization", flat=True)) == [1]
    assert queued == []


@pytest.mark.django_db
def test_batch_sidecar_sync_continues_after_one_node_fails(monkeypatch):
    region = CloudRegion.objects.create(name="batch-org-partial-sync-region", created_by="tester", updated_by="tester")
    first_node = _node(region, "batch-org-partial-sync-node-1", 1)
    second_node = _node(region, "batch-org-partial-sync-node-2", 1)
    synced = []

    def sync(node, *, name=None, organizations=None):
        synced.append((node.id, organizations))
        if node.id == first_node.id:
            raise ValueError("node offline")

    monkeypatch.setattr(sidecar_config_tasks.SidecarConfigService, "sync_node_properties", sync)

    result = sidecar_config_tasks.sync_nodes_organizations_to_sidecar.run(
        [first_node.id, second_node.id],
        [7, 8],
    )

    assert result == {"success": 1, "failed": 1}
    assert synced == [
        (first_node.id, ["7", "8"]),
        (second_node.id, ["7", "8"]),
    ]
