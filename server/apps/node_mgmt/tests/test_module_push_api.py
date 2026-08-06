"""节点创建/详情模块推送 API 入口。"""

from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.utils import current_team_scope
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Node, NodeOrganization
from apps.node_mgmt.views import installer as installer_view
from apps.node_mgmt.views import node as node_view

pytestmark = pytest.mark.django_db

NODE_URL = "/api/v1/node_mgmt/api/node"
INSTALL_URL = "/api/v1/node_mgmt/api/installer/controller/install/"


class _ScopedSystemMgmt:
    def get_authorized_groups_scoped(self, actor_context, include_children=False):
        return {"result": True, "data": [1]}

    def get_assignable_groups(self, actor_context):
        return {"result": True, "data": [1]}


@pytest.fixture
def node(db):
    region = CloudRegion.objects.create(name="push-api-region")
    n = Node.objects.create(
        id="n-push-api-1",
        name="push-api-node",
        ip="10.0.0.21",
        operating_system="linux",
        collector_configuration_directory="/tmp",
        cloud_region=region,
    )
    NodeOrganization.objects.create(node=n, organization=1)
    return n


def _auth_request(method, path, data, *, permissions=("cloud_region_node-Edit",)):
    factory = APIRequestFactory()
    request = getattr(factory, method)(path, data, format="json")
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


def test_detail_push_action(mocker, node, monkeypatch):
    push = mocker.patch("apps.node_mgmt.services.module_push.ModulePushService.push_node")
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        node_view,
        "authorize_node_ids",
        lambda request, node_ids, required_permission="View": ([node], None),
    )

    response = node_view.NodeViewSet.as_view({"post": "module_push"})(
        _auth_request("post", f"{NODE_URL}/{node.id}/module_push/", {"targets": ["cmdb"]}),
        pk=node.id,
    )

    assert response.status_code == 200
    push.assert_called_once()
    args, kwargs = push.call_args
    assert args[0] == node.id
    assert kwargs["targets"] == ["cmdb"]
    assert kwargs["actor_scope"]["operator"] == "alice"
    assert 1 in kwargs["actor_scope"]["allowed_org_ids"]


def test_create_node_with_push_targets_cmdb_calls_push(mocker, node, monkeypatch):
    push = mocker.patch("apps.node_mgmt.services.module_push.ModulePushService.push_node")
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        installer_view.InstallerService,
        "install_controller",
        lambda *args, **kwargs: 99,
    )
    monkeypatch.setattr(installer_view, "install_controller", SimpleNamespace(delay=lambda *a, **k: None))
    monkeypatch.setattr(
        installer_view,
        "_authorize_existing_install_nodes",
        lambda request, node_ids: None,
    )

    payload = {
        "cloud_region_id": node.cloud_region_id,
        "work_node": "worker-1",
        "package_id": 1,
        "cpu_architecture": "x86_64",
        "push_targets": ["cmdb"],
        "nodes": [
            {
                "ip": node.ip,
                "node_id": node.id,
                "node_name": node.name,
                "os": "linux",
                "organizations": [1],
                "port": 22,
                "username": "root",
                "password": "secret",
            }
        ],
    }

    response = installer_view.InstallerViewSet.as_view({"post": "controller_install"})(
        _auth_request("post", INSTALL_URL, payload)
    )

    assert response.status_code == 200
    push.assert_called_once()
    args, kwargs = push.call_args
    assert args[0] == node.id
    assert kwargs["targets"] == ["cmdb"]
    assert kwargs["actor_scope"]["operator"] == "alice"


def test_create_succeeds_when_push_raises(mocker, node, monkeypatch):
    mocker.patch(
        "apps.node_mgmt.services.module_push.ModulePushService.push_node",
        side_effect=RuntimeError("rpc down"),
    )
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        installer_view.InstallerService,
        "install_controller",
        lambda *args, **kwargs: 100,
    )
    monkeypatch.setattr(installer_view, "install_controller", SimpleNamespace(delay=lambda *a, **k: None))
    monkeypatch.setattr(
        installer_view,
        "_authorize_existing_install_nodes",
        lambda request, node_ids: None,
    )

    payload = {
        "cloud_region_id": node.cloud_region_id,
        "work_node": "worker-1",
        "package_id": 1,
        "cpu_architecture": "x86_64",
        "push_targets": ["cmdb"],
        "nodes": [
            {
                "ip": node.ip,
                "node_id": node.id,
                "node_name": node.name,
                "os": "linux",
                "organizations": [1],
                "port": 22,
                "username": "root",
                "password": "secret",
            }
        ],
    }

    response = installer_view.InstallerViewSet.as_view({"post": "controller_install"})(
        _auth_request("post", INSTALL_URL, payload)
    )

    assert response.status_code == 200
