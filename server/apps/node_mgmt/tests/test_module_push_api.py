"""节点创建/详情模块推送 API 入口。"""

from types import SimpleNamespace

import pytest
from django.core.cache import cache
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.utils import current_team_scope
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Node, NodeOrganization
from apps.node_mgmt.views import installer as installer_view
from apps.node_mgmt.views import node as node_view

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "node-mgmt-module-push-api-tests",
        }
    }
    cache.clear()
    yield
    cache.clear()


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
    monkeypatch.setattr(
        "apps.node_mgmt.serializers.installer.assert_cloud_ips_available",
        lambda *args, **kwargs: None,
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

    response = installer_view.InstallerViewSet.as_view({"post": "controller_install"})(_auth_request("post", INSTALL_URL, payload))

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
    monkeypatch.setattr(
        "apps.node_mgmt.serializers.installer.assert_cloud_ips_available",
        lambda *args, **kwargs: None,
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

    response = installer_view.InstallerViewSet.as_view({"post": "controller_install"})(_auth_request("post", INSTALL_URL, payload))

    assert response.status_code == 200
    from django.core.cache import cache

    from apps.node_mgmt.constants.installer import InstallerConstants

    prefix = InstallerConstants.MODULE_PUSH_INTENT_CACHE_PREFIX
    assert cache.get(f"{prefix}:node:{node.id}") is None


def test_install_new_node_remembers_deferred_push_and_does_not_push_now(mocker, monkeypatch):
    region = CloudRegion.objects.create(name="push-api-new")
    push = mocker.patch("apps.node_mgmt.services.module_push.ModulePushService.push_node")
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        installer_view.InstallerService,
        "install_controller",
        lambda *args, **kwargs: 101,
    )
    monkeypatch.setattr(installer_view, "install_controller", SimpleNamespace(delay=lambda *a, **k: None))

    payload = {
        "cloud_region_id": region.id,
        "work_node": "worker-1",
        "package_id": 1,
        "cpu_architecture": "x86_64",
        "push_targets": ["cmdb", "monitor"],
        "nodes": [
            {
                "ip": "10.0.0.88",
                "node_name": "new-host",
                "os": "linux",
                "organizations": [1],
                "port": 22,
                "username": "root",
                "password": "secret",
            }
        ],
    }

    response = installer_view.InstallerViewSet.as_view({"post": "controller_install"})(_auth_request("post", INSTALL_URL, payload))

    assert response.status_code == 200
    push.assert_not_called()
    from django.core.cache import cache

    from apps.node_mgmt.constants.installer import InstallerConstants

    intent = cache.get(f"{InstallerConstants.MODULE_PUSH_INTENT_CACHE_PREFIX}:ip:{region.id}:10.0.0.88")
    assert intent["targets"] == ["cmdb", "monitor"]
    assert intent["operator"] == "alice"


def test_manual_install_remembers_deferred_push(monkeypatch):
    region = CloudRegion.objects.create(name="push-api-manual")
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        installer_view,
        "_validate_install_target_organizations",
        lambda request, nodes: None,
    )

    payload = {
        "cloud_region_id": region.id,
        "os": "linux",
        "cpu_architecture": "x86_64",
        "package_id": 1,
        "push_targets": ["cmdb", "monitor"],
        "nodes": [
            {
                "ip": "10.0.0.89",
                "node_id": "manual-node-89",
                "node_name": "manual-host",
                "organizations": [1],
            }
        ],
    }

    response = installer_view.InstallerViewSet.as_view({"post": "controller_manual_install"})(
        _auth_request("post", "/api/v1/node_mgmt/api/installer/controller/manual_install/", payload)
    )

    assert response.status_code == 200
    from django.core.cache import cache

    from apps.node_mgmt.constants.installer import InstallerConstants

    intent = cache.get(f"{InstallerConstants.MODULE_PUSH_INTENT_CACHE_PREFIX}:node:manual-node-89")
    assert intent["targets"] == ["cmdb", "monitor"]
    assert cache.get(f"{InstallerConstants.MODULE_PUSH_INTENT_CACHE_PREFIX}:ip:{region.id}:10.0.0.89")["targets"] == [
        "cmdb",
        "monitor",
    ]


def test_sidecar_first_register_consumes_deferred_push(mocker, monkeypatch):
    region = CloudRegion.objects.create(name="push-api-sidecar")
    from django.core.cache import cache

    from apps.node_mgmt.constants.controller import ControllerConstants
    from apps.node_mgmt.constants.installer import InstallerConstants
    from apps.node_mgmt.services.module_push import ModulePushService
    from apps.node_mgmt.services.sidecar import Sidecar

    ModulePushService.remember_deferred_push(
        cloud_region_id=region.id,
        nodes=[{"ip": "10.0.0.90", "node_id": "sidecar-new-90"}],
        targets=["cmdb", "monitor"],
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
    )
    push = mocker.patch("apps.node_mgmt.services.module_push.ModulePushService.push_node")
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    request = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "sidecar-host",
            "node_details": {
                "ip": "10.0.0.90",
                "operating_system": "Linux",
                "cpu_architecture": "x86_64",
                "collector_configuration_directory": "/opt/fusion-collectors/generated",
                "metrics": {},
                "status": {"status": 0},
                "tags": [
                    f"zone:{region.id}",
                    "group:1",
                    f"{ControllerConstants.INSTALL_METHOD_TAG}:{ControllerConstants.AUTO}",
                    f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_HOST}",
                ],
                "log_file_list": [],
            },
        },
    )
    response = Sidecar.update_node_client(request, "sidecar-new-90")

    assert response.status_code == 202
    push.assert_called_once()
    args, kwargs = push.call_args
    assert args[0] == "sidecar-new-90"
    assert kwargs["targets"] == ["cmdb", "monitor"]
    assert kwargs["actor_scope"]["operator"] == "alice"
    assert cache.get(f"{InstallerConstants.MODULE_PUSH_INTENT_CACHE_PREFIX}:node:sidecar-new-90") is None

    Sidecar.update_node_client(request, "sidecar-new-90")
    assert push.call_count == 1


def test_sidecar_deferred_consume_failure_does_not_block_heartbeat(mocker, monkeypatch, caplog):
    import logging

    region = CloudRegion.objects.create(name="push-api-sidecar-fail")
    from apps.node_mgmt.constants.controller import ControllerConstants
    from apps.node_mgmt.services.module_push import ModulePushService
    from apps.node_mgmt.services.sidecar import Sidecar

    ModulePushService.remember_deferred_push(
        cloud_region_id=region.id,
        nodes=[{"ip": "10.0.0.91", "node_id": "sidecar-fail-91"}],
        targets=["monitor"],
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
    )
    mocker.patch(
        "apps.node_mgmt.services.module_push.ModulePushService.consume_deferred_push_for_node",
        side_effect=RuntimeError("ingest down"),
    )
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)
    caplog.set_level(logging.ERROR, logger="node")

    request = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "sidecar-fail",
            "node_details": {
                "ip": "10.0.0.91",
                "operating_system": "Linux",
                "cpu_architecture": "x86_64",
                "collector_configuration_directory": "/opt/fusion-collectors/generated",
                "metrics": {},
                "status": {"status": 0},
                "tags": [
                    f"zone:{region.id}",
                    "group:1",
                    f"{ControllerConstants.INSTALL_METHOD_TAG}:{ControllerConstants.AUTO}",
                    f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_HOST}",
                ],
                "log_file_list": [],
            },
        },
    )
    response = Sidecar.update_node_client(request, "sidecar-fail-91")

    assert response.status_code == 202
    records = [r for r in caplog.records if r.name == "node" and "deferred consume failed" in (r.msg or "")]
    assert len(records) == 1
    record = records[0]
    assert record.exc_info is not None
    assert record.args == ("sidecar-fail-91", "RuntimeError")
    formatted = record.msg % record.args
    assert "sidecar-fail-91" in formatted
    assert "failed_stage=deferred_consume" in formatted
    assert "error_type=RuntimeError" in formatted
    assert "ingest down" not in formatted
