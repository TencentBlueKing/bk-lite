import json
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.utils import current_team_scope
from apps.node_mgmt.models.installer import CollectorTask, CollectorTaskNode, ControllerTask, ControllerTaskNode
from apps.node_mgmt.models.sidecar import CloudRegion, Collector, CollectorConfiguration, Node, NodeOrganization
from apps.node_mgmt.services import node as node_service
from apps.node_mgmt.utils import permission as node_permission
from apps.node_mgmt.views import installer as installer_view


class _ScopedSystemMgmt:
    data_team_ids = [1]
    assignable_team_ids = [1]

    def __init__(self, *args, **kwargs):
        pass

    def get_authorized_groups_scoped(self, actor_context, include_children=False):
        return {"result": True, "data": self.data_team_ids}

    def get_assignable_groups(self, actor_context):
        return {"result": True, "data": self.assignable_team_ids}


def _request(data=None, *, permissions=()):
    request = APIRequestFactory().post("/node-mgmt/test", data or {}, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    user = SimpleNamespace(
        username="admin",
        domain="domain.com",
        locale="en",
        is_superuser=True,
        is_authenticated=True,
        group_list=[1, 2],
        permission={"node": set(permissions)},
    )
    force_authenticate(request, user=user)
    request.user = user
    return request


def _response_data(response):
    return json.loads(response.content)["data"]


def _region(name):
    return CloudRegion.objects.create(
        name=name,
        created_by="tester",
        updated_by="tester",
    )


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


def _patch_broad_permission(monkeypatch):
    monkeypatch.setattr(node_permission, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        node_permission,
        "get_permission_rules",
        lambda *args, **kwargs: {"team": [1, 2], "instance": []},
    )


@pytest.mark.django_db
def test_superuser_node_queryset_excludes_sibling_team(monkeypatch):
    region = _region("node-current-team")
    current_node = _node(region, "node-current", 1)
    _node(region, "node-sibling", 2)
    _patch_broad_permission(monkeypatch)

    result_ids = set(node_permission.get_authorized_node_queryset(_request()).values_list("id", flat=True))

    assert result_ids == {current_node.id}


@pytest.mark.django_db
def test_node_service_superuser_scope_intersects_object_permission(monkeypatch):
    region = _region("node-service-current-team")
    current_node = _node(region, "service-node-current", 1)
    _node(region, "service-node-sibling", 2)
    monkeypatch.setattr(node_service, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        node_service,
        "get_permission_rules",
        lambda *args, **kwargs: {"team": [1, 2], "instance": []},
    )

    result = node_service.NodeService.get_authorized_nodes_by_ids(
        ["service-node-current", "service-node-sibling"],
        permission_data={
            "username": "admin",
            "domain": "domain.com",
            "current_team": 1,
            "include_children": False,
            "is_superuser": True,
        },
    )

    assert [item["id"] for item in result] == [current_node.id]


@pytest.mark.django_db
def test_shared_configuration_write_requires_all_impacted_orgs(monkeypatch):
    region = _region("shared-configuration")
    current_node = _node(region, "shared-node-current", 1)
    sibling_node = _node(region, "shared-node-sibling", 2)
    collector = Collector.objects.create(
        id="shared-collector",
        name="shared-collector",
        service_type="exec",
        node_operating_system="linux",
        executable_path="/bin/collector",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
    )
    shared_config = CollectorConfiguration.objects.create(
        id="shared-config",
        name="shared-config",
        collector=collector,
        config_template="template",
        cloud_region=region,
        created_by="admin",
        updated_by="admin",
    )
    shared_config.nodes.add(current_node, sibling_node)
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        node_permission,
        "get_authorized_collector_configuration_queryset",
        lambda request, permission=None: CollectorConfiguration.objects.filter(id=shared_config.id),
    )
    monkeypatch.setattr(
        node_permission,
        "get_authorized_node_queryset",
        lambda request, permission=None: Node.objects.filter(id__in=[current_node.id, sibling_node.id]),
    )

    writable = node_permission.get_mutable_collector_configuration_queryset(_request())

    assert not writable.filter(id=shared_config.id).exists()


def test_superuser_target_organizations_must_be_assignable(monkeypatch):
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)

    response = node_permission.authorize_target_organizations(_request(), SimpleNamespace(), [2])

    assert response.status_code == 403


@pytest.mark.django_db
def test_collector_task_summary_counts_only_current_team_nodes(monkeypatch):
    region = _region("collector-task-current-team")
    current_node = _node(region, "collector-task-current", 1)
    sibling_node = _node(region, "collector-task-sibling", 2)
    task = CollectorTask.objects.create(
        type="install",
        status="running",
        package_version_id=1,
    )
    CollectorTaskNode.objects.create(
        task=task,
        node=current_node,
        status="success",
        result={},
    )
    CollectorTaskNode.objects.create(
        task=task,
        node=sibling_node,
        status="error",
        result={},
    )
    _patch_broad_permission(monkeypatch)

    response = installer_view.InstallerViewSet.as_view({"post": "collector_install_nodes"})(
        _request(permissions=("cloud_region_node-OperateCollector",)),
        task_id=str(task.id),
    )
    data = _response_data(response)

    assert {item["node_id"] for item in data["items"]} == {current_node.id}
    assert data["summary"]["total"] == 1
    assert data["summary"]["success"] == 1


@pytest.mark.django_db
def test_controller_task_nodes_follow_current_node_org_and_legacy_snapshot(
    monkeypatch,
):
    region = _region("controller-task-current-team")
    current_node = _node(region, "controller-task-current", 1)
    sibling_node = _node(region, "controller-task-sibling", 2)
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="running",
        work_node="worker",
        package_version_id=1,
        created_by="other-user",
        updated_by="other-user",
    )

    def create_task_node(node_id, ip, organizations):
        return ControllerTaskNode.objects.create(
            task=task,
            node_id=node_id,
            ip=ip,
            node_name=node_id or f"legacy-{ip}",
            os="linux",
            organizations=organizations,
            port=22,
            username="root",
            password="",
            status="waiting",
        )

    linked_current = create_task_node(current_node.id, current_node.ip, [2])
    create_task_node(sibling_node.id, sibling_node.ip, [1])
    legacy_current = create_task_node("", "10.0.1.1", [1])
    create_task_node("", "10.0.1.2", [2])
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        installer_view,
        "get_authorized_node_queryset",
        lambda request: Node.objects.filter(id=current_node.id),
    )

    response = installer_view.InstallerViewSet.as_view({"post": "controller_install_nodes"})(
        _request(permissions=("cloud_region_node-Edit",)),
        task_id=str(task.id),
    )
    data = _response_data(response)

    assert [item["task_node_id"] for item in data] == [
        linked_current.id,
        legacy_current.id,
    ]


@pytest.mark.django_db
def test_controller_retry_rejects_task_node_outside_current_team(monkeypatch):
    region = _region("controller-retry-current-team")
    current_node = _node(region, "controller-retry-current", 1)
    sibling_node = _node(region, "controller-retry-sibling", 2)
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="error",
        work_node="worker",
        package_version_id=1,
        created_by="admin",
        updated_by="admin",
    )
    sibling_task_node = ControllerTaskNode.objects.create(
        task=task,
        node_id=sibling_node.id,
        ip=sibling_node.ip,
        node_name=sibling_node.name,
        os="linux",
        organizations=[1],
        port=22,
        username="root",
        password="",
        status="error",
    )
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        installer_view,
        "get_authorized_node_queryset",
        lambda request: Node.objects.filter(id=current_node.id),
    )
    delayed = []
    monkeypatch.setattr(
        installer_view.retry_controller,
        "delay",
        lambda *args, **kwargs: delayed.append((args, kwargs)),
    )

    response = installer_view.InstallerViewSet.as_view({"post": "controller_retry"})(
        _request(
            {
                "task_id": task.id,
                "task_node_ids": [sibling_task_node.id],
            },
            permissions=("cloud_region_node-Edit",),
        )
    )

    assert response.status_code == 403
    assert delayed == []
