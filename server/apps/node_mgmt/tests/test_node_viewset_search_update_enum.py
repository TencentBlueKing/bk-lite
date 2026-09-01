"""NodeViewSet.search / update / enum / 批量绑定与采集动作节点。"""
import json
import uuid
from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, Collector, Node
from apps.node_mgmt.models.action import CollectorActionTask, CollectorActionTaskNode
from apps.node_mgmt.models.sidecar import NodeOrganization
from apps.node_mgmt.views import node as node_view

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()


def _user():
    user = UserFactory(username=f"node-vs-{uuid.uuid4().hex[:8]}", domain="domain.com", is_superuser=True)
    user.permission = {
        "node": {
            "cloud_region_node-View",
            "cloud_region_node-Edit",
            "cloud_region_node-EditMainConfiguration",
            "cloud_region_node-OperateCollector",
        }
    }
    user.locale = "en"
    return user


def _auth(request, user=None):
    user = user or _user()
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = "1"
    return user


def _region_and_nodes():
    region = CloudRegion.objects.create(name=f"nv-{uuid.uuid4().hex[:8]}")
    keep = Node.objects.create(
        id=f"keep-{uuid.uuid4().hex[:8]}",
        name="keep-node",
        ip="10.0.0.1",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/tmp",
        cloud_region=region,
        status={},
    )
    other = Node.objects.create(
        id=f"other-{uuid.uuid4().hex[:8]}",
        name="other-node",
        ip="10.0.0.2",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/tmp",
        cloud_region=region,
        status={},
    )
    NodeOrganization.objects.create(node=keep, organization=7)
    NodeOrganization.objects.create(node=other, organization=8)
    return region, keep, other


def test_search_filters_by_name_org_and_cloud_region(monkeypatch):
    region, keep, other = _region_and_nodes()
    monkeypatch.setattr(node_view, "get_node_permission", lambda request: {"team": [1], "instance": []})
    monkeypatch.setattr(
        node_view,
        "get_authorized_node_queryset",
        lambda request, permission=None: Node.objects.filter(id__in=[keep.id, other.id]),
    )
    monkeypatch.setattr(node_view.NodeService, "process_node_data", staticmethod(lambda data: data))

    request = factory.post(
        "/node/search/",
        {
            "filters": {"name": [{"lookup_expr": "icontains", "value": "keep"}]},
            "organization_ids": "7",
            "cloud_region_id": region.id,
        },
        format="json",
    )
    _auth(request)
    resp = node_view.NodeViewSet.as_view({"post": "search"})(request)
    body = json.loads(resp.content)
    assert body["result"] is True
    ids = [item["id"] for item in body["data"]]
    assert ids == [keep.id]
    assert body["data"][0]["organization"] == [7]


def test_search_paginates_when_page_size_set(monkeypatch):
    _, keep, other = _region_and_nodes()
    monkeypatch.setattr(node_view, "get_node_permission", lambda request: {})
    monkeypatch.setattr(
        node_view,
        "get_authorized_node_queryset",
        lambda request, permission=None: Node.objects.filter(id__in=[keep.id, other.id]),
    )
    monkeypatch.setattr(node_view.NodeService, "process_node_data", staticmethod(lambda data: data))
    request = factory.post("/node/search/?page=1&page_size=1", {}, format="json")
    _auth(request)
    resp = node_view.NodeViewSet.as_view({"post": "search"})(request)
    resp.render()
    body = json.loads(resp.content)
    assert body["result"] is True
    assert body["code"] == "20000"
    assert body["data"]["count"] == 2
    assert len(body["data"]["items"]) == 1
    assert body["data"]["items"][0]["id"] in {keep.id, other.id}


def test_update_node_renames_replaces_orgs_and_syncs(monkeypatch):
    _, node, _ = _region_and_nodes()
    delay = MagicMock()
    monkeypatch.setattr(node_view, "authorize_node_ids", lambda request, node_ids: ([node], None))
    monkeypatch.setattr(node_view, "authorize_target_organizations", lambda request, node, orgs: None)
    monkeypatch.setattr(node_view.sync_node_properties_to_sidecar, "delay", delay)
    request = factory.patch(f"/node/{node.id}/update/", {"name": "renamed", "organizations": [11, 12]}, format="json")
    _auth(request)
    resp = node_view.NodeViewSet.as_view({"patch": "update_node"})(request, pk=node.id)
    body = json.loads(resp.content)
    assert body["result"] is True
    node.refresh_from_db()
    assert node.name == "renamed"
    assert set(NodeOrganization.objects.filter(node=node).values_list("organization", flat=True)) == {11, 12}
    delay.assert_called_once_with(node_id=node.id, name="renamed", organizations=[11, 12])


def test_enum_falls_back_to_constant_labels(monkeypatch):
    monkeypatch.setattr(node_view.LanguageLoader, "get", lambda self, key, default=None: "")
    request = factory.get("/node/enum/")
    _auth(request)
    resp = node_view.NodeViewSet.as_view({"get": "enum"})(request)
    body = json.loads(resp.content)
    data = body["data"]
    assert data["sidecar_status"][ControllerConstants.NORMAL] == ControllerConstants.SIDECAR_STATUS_ENUM[ControllerConstants.NORMAL]
    assert data["install_method"][ControllerConstants.AUTO] == ControllerConstants.INSTALL_METHOD_ENUM[ControllerConstants.AUTO]
    assert data["os"][NodeConstants.LINUX_OS] == NodeConstants.LINUX_OS_DISPLAY
    assert data["tag"]["monitor"]["is_app"] is True
    assert data["tag"]["monitor"]["name"] == CollectorConstants.TAG_ENUM["monitor"]["name"]
    assert data["node_type"] == ControllerConstants.NODE_TYPE_ENUM


def test_batch_binding_success_and_error(monkeypatch):
    monkeypatch.setattr(node_view, "authorize_node_ids", lambda request, node_ids: (node_ids, None))
    monkeypatch.setattr(node_view, "authorize_mutable_collector_configuration_ids", lambda request, ids: (ids, None))
    monkeypatch.setattr(
        node_view.NodeService,
        "batch_binding_node_configuration",
        staticmethod(lambda node_ids, cfg_id: (True, "bound")),
    )
    request = factory.post(
        "/node/batch_binding_configuration/",
        {"node_ids": ["n1"], "collector_configuration_id": "cfg-1"},
        format="json",
    )
    _auth(request)
    ok = node_view.NodeViewSet.as_view({"post": "batch_binding_node_configuration"})(request)
    body = json.loads(ok.content)
    assert body["result"] is True
    assert body["data"] == "bound"

    monkeypatch.setattr(
        node_view.NodeService,
        "batch_binding_node_configuration",
        staticmethod(lambda node_ids, cfg_id: (False, "conflict")),
    )
    request = factory.post(
        "/node/batch_binding_configuration/",
        {"node_ids": ["n1"], "collector_configuration_id": "cfg-1"},
        format="json",
    )
    _auth(request)
    err = node_view.NodeViewSet.as_view({"post": "batch_binding_node_configuration"})(request)
    body = json.loads(err.content)
    assert body["result"] is False
    assert body["message"] == "conflict"


def test_batch_operate_returns_task_id(monkeypatch):
    called = {}

    def _operate(node_ids, collector_id, operation, created_by="", domain="domain.com", updated_by_domain="domain.com"):
        called["node_ids"] = node_ids
        called["collector_id"] = collector_id
        called["operation"] = operation
        called["created_by"] = created_by
        return "task-88"

    monkeypatch.setattr(node_view, "authorize_node_ids", lambda request, node_ids: (node_ids, None))
    monkeypatch.setattr(node_view.NodeService, "batch_operate_node_collector", staticmethod(_operate))
    request = factory.post(
        "/node/batch_operate_collector/",
        {"node_ids": ["n1"], "collector_id": "c1", "operation": "restart"},
        format="json",
    )
    user = _auth(request)
    resp = node_view.NodeViewSet.as_view({"post": "batch_operate_node_collector"})(request)
    body = json.loads(resp.content)
    assert body["result"] is True
    assert body["data"] == {"task_id": "task-88"}
    assert called == {
        "node_ids": ["n1"],
        "collector_id": "c1",
        "operation": "restart",
        "created_by": user.username,
    }


def test_collector_action_nodes_filters_status_and_summarizes(monkeypatch):
    region, node, _ = _region_and_nodes()
    collector = Collector.objects.create(
        id=f"col-{uuid.uuid4().hex[:8]}",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
    )
    task = CollectorActionTask.objects.create(
        collector=collector,
        cloud_region=region,
        action="restart",
        status="running",
        total_count=1,
    )
    CollectorActionTaskNode.objects.create(
        task=task,
        node=node,
        status="success",
        result={"overall_status": "success"},
    )
    waiting_node = Node.objects.create(
        id=f"wait-{uuid.uuid4().hex[:8]}",
        name="wait-node",
        ip="10.0.0.9",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/tmp",
        cloud_region=region,
        status={},
    )
    CollectorActionTaskNode.objects.create(task=task, node=waiting_node, status="waiting", result={})
    monkeypatch.setattr(
        node_view,
        "get_authorized_node_queryset",
        lambda request: Node.objects.filter(id__in=[node.id, waiting_node.id]),
    )
    request = factory.post(
        f"/node/collector/action/{task.id}/nodes/",
        {"status": ["success"], "page": 1, "page_size": 10},
        format="json",
    )
    _auth(request)
    resp = node_view.NodeViewSet.as_view({"post": "collector_action_nodes"})(request, task_id=task.id)
    body = json.loads(resp.content)
    data = body["data"]
    assert data["task_id"] == task.id
    assert data["status"] == "running"
    assert data["count"] == 1
    assert data["items"][0]["node_id"] == node.id
    assert data["items"][0]["status"] == "success"
    assert data["items"][0]["ip"] == node.ip
    assert data["summary"]["total"] == 2
    assert data["summary"]["success"] == 1
    assert data["summary"]["waiting"] == 1


def test_destroy_deletes_authorized_node(monkeypatch):
    _, node, _ = _region_and_nodes()
    monkeypatch.setattr(node_view, "authorize_node_ids", lambda request, node_ids: ([node], None))
    request = factory.delete(f"/node/{node.id}/")
    _auth(request)
    resp = node_view.NodeViewSet.as_view({"delete": "destroy"})(request, pk=node.id)
    body = json.loads(resp.content)
    assert body["result"] is True
    assert not Node.objects.filter(id=node.id).exists()
