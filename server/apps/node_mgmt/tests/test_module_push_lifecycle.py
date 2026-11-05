"""节点删除时可选 retire_linked → lifecycle 退役已关联模块对象。"""

import logging
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.logger import SafeLogException, safe_log_value
from apps.core.utils import current_team_scope
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Node, NodeOrganization
from apps.node_mgmt.services.module_push import ModulePushService, parse_retire_linked_flag
from apps.node_mgmt.services.module_push_contract import EVENT_LIFECYCLE
from apps.node_mgmt.services.node_collection_exit import EXIT_FAILED_LOG
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


def test_best_effort_unlink_cmdb_even_without_cmdb_id(mocker, linked_node):
    linked_node.cmdb_id = ""
    linked_node.save(update_fields=["cmdb_id"])
    cmdb = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.return_value = {"id": None, "updated": True}
    monitor = mocker.patch("apps.node_mgmt.services.module_push.MonitorLinkage")

    ModulePushService.best_effort_unlink_cmdb(
        linked_node,
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
        max_attempts=1,
    )

    cmdb.return_value.ingest_from_source.assert_called_once()
    kwargs = cmdb.return_value.ingest_from_source.call_args.kwargs
    assert kwargs["event_type"] == EVENT_LIFECYCLE
    assert kwargs["link_ids"]["node_id"] == linked_node.id
    assert "cmdb_id" not in kwargs["link_ids"]
    assert monitor.call_count == 0


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


def test_destroy_always_exits_collection_and_ignores_retire_linked(mocker, linked_node, monkeypatch):
    unlink = mocker.patch("apps.node_mgmt.views.node.ModulePushService.best_effort_unlink_cmdb")
    retire = mocker.patch("apps.node_mgmt.views.node.ModulePushService.best_effort_retire_linked")
    exit_collection = mocker.patch("apps.node_mgmt.views.node.NodeCollectionExitService.apply")
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
    unlink.assert_called_once()
    retire.assert_not_called()
    exit_collection.assert_called_once()
    destroy.assert_called_once_with(linked_node)


def test_destroy_always_unlinks_cmdb_even_without_retire_linked(mocker, linked_node, monkeypatch):
    unlink = mocker.patch("apps.node_mgmt.views.node.ModulePushService.best_effort_unlink_cmdb")
    exit_collection = mocker.patch("apps.node_mgmt.views.node.NodeCollectionExitService.apply")
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
    unlink.assert_called_once()
    exit_collection.assert_called_once()
    destroy.assert_called_once_with(linked_node)


def test_destroy_proceeds_when_unlink_or_exit_fails(mocker, linked_node, monkeypatch, caplog):
    secret = "APPLY-SECRET-MUST-NOT-ENTER-LOGS"

    def _raise(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        node_view,
        "authorize_node_ids",
        lambda request, node_ids, required_permission="View": ([linked_node], None),
    )
    destroy = mocker.patch.object(node_view.NodeViewSet, "perform_destroy")
    mocker.patch("apps.node_mgmt.views.node.NodeCollectionExitService.apply", side_effect=_raise)

    caplog.set_level(logging.ERROR, logger="node")
    response = node_view.NodeViewSet.as_view({"delete": "destroy"})(
        _auth_delete(f"{NODE_URL}/{linked_node.id}/", query="retire_linked=1"),
        pk=linked_node.id,
    )

    assert response.status_code == 200
    destroy.assert_called_once()
    errors = [record for record in caplog.records if record.msg == EXIT_FAILED_LOG and record.exc_info]
    assert len(errors) == 1
    error_record = errors[0]
    assert error_record.levelno == logging.ERROR
    assert error_record.args == (safe_log_value(linked_node.id), "apply", "RuntimeError")
    assert error_record.getMessage() == EXIT_FAILED_LOG % error_record.args
    assert error_record.exc_info[0] is SafeLogException
    assert error_record.exc_info[1].args == ("RuntimeError",)
    traceback_frame = error_record.exc_info[2]
    while traceback_frame.tb_next is not None:
        traceback_frame = traceback_frame.tb_next
    assert traceback_frame.tb_frame.f_code.co_name == "_raise"
    formatted = logging.Formatter().format(error_record)
    assert secret not in formatted
    assert secret not in caplog.text
