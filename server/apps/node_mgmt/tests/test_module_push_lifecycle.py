"""节点删除时可选 retire_linked → lifecycle 退役已关联模块对象。"""

from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.utils import current_team_scope
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Node, NodeOrganization
from apps.node_mgmt.services.module_push import ModulePushService, parse_retire_linked_flag
from apps.node_mgmt.services.module_push_contract import EVENT_LIFECYCLE
from apps.node_mgmt.views import node as node_view

pytestmark = pytest.mark.django_db

NODE_URL = "/api/v1/node_mgmt/api/node"


class _ScopedSystemMgmt:
    def get_authorized_groups_scoped(self, actor_context, include_children=False):
        return {"result": True, "data": [1]}

    def get_assignable_groups(self, actor_context):
        return {"result": True, "data": [1]}


@pytest.fixture
def linked_node(db):
    region = CloudRegion.objects.create(name="lifecycle-region")
    n = Node.objects.create(
        id="n-lifecycle-1",
        name="lifecycle-node",
        ip="10.0.0.88",
        operating_system="linux",
        collector_configuration_directory="/tmp",
        cloud_region=region,
        cmdb_id="42",
        monitor_id="mon-42",
    )
    NodeOrganization.objects.create(node=n, organization=1)
    return n


def _auth_delete(path, *, query=None, data=None, permissions=("cloud_region_node-Delete",)):
    factory = APIRequestFactory()
    if query:
        path = f"{path}?{query}"
    request = factory.delete(path, data or {}, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    user = SimpleNamespace(
        username="alice",
        domain="domain.com",
        locale="en",
        is_superuser=False,
        is_authenticated=True,
        group_list=[{"id": 1, "name": "Team"}],
        permission={"node": set(permissions)},
    )
    force_authenticate(request, user=user)
    request.user = user
    return request


def test_parse_retire_linked_defaults_false():
    req = SimpleNamespace(query_params={}, data={})
    assert parse_retire_linked_flag(req) is False


def test_parse_retire_linked_from_query():
    req = SimpleNamespace(query_params={"retire_linked": "true"}, data={})
    assert parse_retire_linked_flag(req) is True


def test_parse_retire_linked_from_body():
    req = SimpleNamespace(query_params={}, data={"retire_linked": True})
    assert parse_retire_linked_flag(req) is True


def test_retire_linked_pushes_lifecycle_to_cmdb_and_monitor(mocker, linked_node):
    cmdb = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.return_value = {
        "id": 42,
        "updated": True,
        "ignored": False,
    }
    monitor = mocker.patch("apps.node_mgmt.services.module_push.MonitorLinkage")
    monitor.return_value.ingest_from_source.return_value = {
        "id": "mon-42",
        "updated": True,
        "ignored": False,
    }

    results = ModulePushService.retire_linked(
        linked_node,
        targets=["cmdb", "monitor"],
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
        max_attempts=1,
    )

    assert results["cmdb"].state == "ok"
    assert results["monitor"].state == "ok"
    cmdb_kwargs = cmdb.return_value.ingest_from_source.call_args.kwargs
    assert cmdb_kwargs["event_type"] == EVENT_LIFECYCLE
    assert cmdb_kwargs["raw"] == {"action": "retire"}
    assert cmdb_kwargs["link_ids"]["node_id"] == linked_node.id
    assert cmdb_kwargs["link_ids"]["cmdb_id"] == "42"
    assert cmdb_kwargs["link_ids"]["monitor_id"] == "mon-42"
    mon_kwargs = monitor.return_value.ingest_from_source.call_args.kwargs
    assert mon_kwargs["event_type"] == EVENT_LIFECYCLE
    assert mon_kwargs["raw"]["action"] == "retire"


def test_best_effort_retire_only_targets_with_ids(mocker, linked_node):
    linked_node.monitor_id = ""
    linked_node.save(update_fields=["monitor_id"])
    cmdb = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.return_value = {"id": 42, "updated": True}
    monitor = mocker.patch("apps.node_mgmt.services.module_push.MonitorLinkage")

    ModulePushService.best_effort_retire_linked(
        linked_node,
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
        max_attempts=1,
    )

    cmdb.return_value.ingest_from_source.assert_called_once()
    assert monitor.call_count == 0


def test_destroy_retire_linked_true_calls_lifecycle(mocker, linked_node, monkeypatch):
    retire = mocker.patch(
        "apps.node_mgmt.views.node.ModulePushService.best_effort_retire_linked"
    )
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        node_view,
        "authorize_node_ids",
        lambda request, node_ids, required_permission="View": ([linked_node], None),
    )
    destroy = mocker.patch.object(node_view.NodeViewSet, "perform_destroy")

    response = node_view.NodeViewSet.as_view({"delete": "destroy"})(
        _auth_delete(f"{NODE_URL}/{linked_node.id}/", query="retire_linked=true"),
        pk=linked_node.id,
    )

    assert response.status_code == 200
    retire.assert_called_once()
    destroy.assert_called_once_with(linked_node)


def test_destroy_retire_linked_false_skips_lifecycle(mocker, linked_node, monkeypatch):
    retire = mocker.patch(
        "apps.node_mgmt.views.node.ModulePushService.best_effort_retire_linked"
    )
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        node_view,
        "authorize_node_ids",
        lambda request, node_ids, required_permission="View": ([linked_node], None),
    )
    destroy = mocker.patch.object(node_view.NodeViewSet, "perform_destroy")

    response = node_view.NodeViewSet.as_view({"delete": "destroy"})(
        _auth_delete(f"{NODE_URL}/{linked_node.id}/"),
        pk=linked_node.id,
    )

    assert response.status_code == 200
    retire.assert_not_called()
    destroy.assert_called_once_with(linked_node)


def test_destroy_proceeds_when_retire_fails(mocker, linked_node, monkeypatch):
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        node_view,
        "authorize_node_ids",
        lambda request, node_ids, required_permission="View": ([linked_node], None),
    )
    destroy = mocker.patch.object(node_view.NodeViewSet, "perform_destroy")
    mocker.patch(
        "apps.node_mgmt.services.module_push.ModulePushService.retire_linked",
        side_effect=RuntimeError("peer down"),
    )

    response = node_view.NodeViewSet.as_view({"delete": "destroy"})(
        _auth_delete(f"{NODE_URL}/{linked_node.id}/", query="retire_linked=1"),
        pk=linked_node.id,
    )

    assert response.status_code == 200
    destroy.assert_called_once()
