import json
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.utils import current_team_scope
from apps.node_mgmt.models.action import CollectorActionTask, CollectorActionTaskNode
from apps.node_mgmt.models.installer import CollectorTask, CollectorTaskNode, ControllerTask, ControllerTaskNode
from apps.node_mgmt.models.sidecar import CloudRegion, Collector, CollectorConfiguration, Node, NodeOrganization, SidecarApiToken
from apps.node_mgmt.services import node as node_service
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.utils import permission as node_permission
from apps.node_mgmt.utils.task_result_schema import project_task_status_from_summary
from apps.node_mgmt.utils.token_auth import generate_node_token
from apps.node_mgmt.views import collector_configuration as collector_configuration_view
from apps.node_mgmt.views import installer as installer_view
from apps.node_mgmt.views import node as node_view


class _ScopedSystemMgmt:
    data_team_ids = [1]
    assignable_team_ids = [1]

    def __init__(self, *args, **kwargs):
        pass

    def get_authorized_groups_scoped(self, actor_context, include_children=False):
        return {"result": True, "data": self.data_team_ids}

    def get_assignable_groups(self, actor_context):
        return {"result": True, "data": self.assignable_team_ids}


def _request(data=None, *, permissions=(), method="post"):
    request = getattr(APIRequestFactory(), method)("/node-mgmt/test", data or {}, format="json")
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
def test_authorize_node_ids_rejects_sibling_team_even_with_broad_operate_permission(
    monkeypatch,
):
    region = _region("authorize-node-current-team")
    _node(region, "authorize-node-current", 1)
    sibling_node = _node(region, "authorize-node-sibling", 2)
    _patch_broad_permission(monkeypatch)

    nodes, response = node_permission.authorize_node_ids(
        _request(),
        [sibling_node.id],
        required_permission="Operate",
    )

    assert nodes is None
    assert response.status_code == 403


@pytest.mark.django_db
def test_controller_uninstall_rejects_sibling_team_before_task_creation(
    monkeypatch,
):
    region = _region("uninstall-node-current-team")
    sibling_node = _node(region, "uninstall-node-sibling", 2)
    _patch_broad_permission(monkeypatch)
    uninstalled = []
    delayed = []
    monkeypatch.setattr(
        installer_view.InstallerService,
        "uninstall_controller",
        lambda *args, **kwargs: uninstalled.append((args, kwargs)) or 1,
    )
    monkeypatch.setattr(
        installer_view.uninstall_controller,
        "delay",
        lambda *args, **kwargs: delayed.append((args, kwargs)),
    )

    response = installer_view.InstallerViewSet.as_view({"post": "controller_uninstall"})(
        _request(
            {
                "cloud_region_id": region.id,
                "work_node": "worker",
                "nodes": [
                    {
                        "node_id": sibling_node.id,
                        "ip": sibling_node.ip,
                        "node_name": sibling_node.name,
                        "os": "linux",
                        "organizations": [2],
                    }
                ],
            },
            permissions=("cloud_region_node-Delete",),
        )
    )

    assert response.status_code == 403
    assert uninstalled == []
    assert delayed == []


def test_get_node_permission_rejects_noncanonical_current_team(monkeypatch):
    class _UnexpectedSystemMgmt:
        def __init__(self, *args, **kwargs):
            raise AssertionError("非规范 current_team 不应发起范围 RPC")

    monkeypatch.setattr(node_permission, "SystemMgmt", _UnexpectedSystemMgmt)
    request = _request()
    request.COOKIES["current_team"] = "01"

    assert node_permission.get_node_permission(request) == {}


@pytest.mark.parametrize("authorized_groups", [[True], [1.0], [1, "02"]])
def test_get_node_permission_rejects_noncanonical_authorized_group_range(
    monkeypatch,
    authorized_groups,
):
    class _NoncanonicalScopedSystemMgmt:
        def __init__(self, *args, **kwargs):
            pass

        def get_authorized_groups_scoped(self, actor_context, include_children=False):
            return {"result": True, "data": authorized_groups}

    monkeypatch.setattr(
        node_permission,
        "SystemMgmt",
        _NoncanonicalScopedSystemMgmt,
    )
    monkeypatch.setattr(
        node_permission,
        "get_permission_rules",
        lambda *args, **kwargs: pytest.fail("非规范授权组织范围不得进入对象权限查询"),
    )

    assert node_permission.get_node_permission(_request()) == {}


@pytest.mark.django_db
@pytest.mark.parametrize("permission_data", [None, {}])
def test_get_authorized_nodes_by_ids_without_permission_context_returns_nothing(
    permission_data,
):
    region = _region("node-service-empty-permission")
    _node(region, "service-node-empty-permission", 1)

    result = node_service.NodeService.get_authorized_nodes_by_ids(
        ["service-node-empty-permission"],
        permission_data=permission_data,
    )

    assert result == []


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


@pytest.mark.django_db
def test_shared_configuration_with_unassigned_node_is_not_mutable(monkeypatch):
    region = _region("shared-configuration-unassigned")
    assigned_node = _node(region, "shared-node-assigned", 1)
    unassigned_node = Node.objects.create(
        id="shared-node-unassigned",
        name="shared-node-unassigned",
        ip="10.0.1.2",
        operating_system="linux",
        cpu_architecture="x86_64",
        collector_configuration_directory="/etc/collector",
        cloud_region=region,
        created_by="tester",
        updated_by="tester",
    )
    collector = Collector.objects.create(
        id="shared-collector-unassigned",
        name="shared-collector-unassigned",
        service_type="exec",
        node_operating_system="linux",
        executable_path="/bin/collector",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
    )
    shared_config = CollectorConfiguration.objects.create(
        id="shared-config-unassigned",
        name="shared-config-unassigned",
        collector=collector,
        config_template="template",
        cloud_region=region,
        created_by="admin",
        updated_by="admin",
    )
    shared_config.nodes.add(assigned_node, unassigned_node)
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(
        node_permission,
        "get_authorized_collector_configuration_queryset",
        lambda request, permission=None: CollectorConfiguration.objects.filter(id=shared_config.id),
    )

    writable = node_permission.get_mutable_collector_configuration_queryset(_request())

    assert not writable.filter(id=shared_config.id).exists()


@pytest.mark.django_db
def test_shared_configuration_list_projects_nodes_to_current_team(monkeypatch):
    region = _region("shared-configuration-list-projection")
    current_node = _node(region, "shared-list-node-current", 1)
    sibling_node = _node(region, "shared-list-node-sibling", 2)
    collector = Collector.objects.create(
        id="shared-list-collector",
        name="shared-list-collector",
        service_type="exec",
        node_operating_system="linux",
        executable_path="/bin/collector",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
    )
    shared_config = CollectorConfiguration.objects.create(
        id="shared-list-config",
        name="shared-list-config",
        collector=collector,
        config_template="template",
        cloud_region=region,
        created_by="admin",
        updated_by="admin",
    )
    shared_config.nodes.add(current_node, sibling_node)
    for node in (current_node, sibling_node):
        node.status = {"collectors": [{"configuration_id": [shared_config.id]}]}
        node.save(update_fields=["status"])
    _patch_broad_permission(monkeypatch)

    response = collector_configuration_view.CollectorConfigurationViewSet.as_view({"get": "list"})(_request(method="get"))
    items = response.data.get("items", []) if isinstance(response.data, dict) else response.data
    serialized = next(item for item in items if item["id"] == shared_config.id)

    assert response.status_code == 200
    assert serialized["nodes"] == [current_node.id]
    assert sibling_node.id not in serialized["nodes"]


@pytest.mark.django_db
def test_shared_configuration_retrieve_projects_nodes_to_current_team(monkeypatch):
    region = _region("shared-configuration-detail-projection")
    current_node = _node(region, "shared-detail-node-current", 1)
    sibling_node = _node(region, "shared-detail-node-sibling", 2)
    collector = Collector.objects.create(
        id="shared-detail-collector",
        name="shared-detail-collector",
        service_type="exec",
        node_operating_system="linux",
        executable_path="/bin/collector",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
    )
    shared_config = CollectorConfiguration.objects.create(
        id="shared-detail-config",
        name="shared-detail-config",
        collector=collector,
        config_template="template",
        cloud_region=region,
        created_by="admin",
        updated_by="admin",
    )
    shared_config.nodes.add(current_node, sibling_node)
    _patch_broad_permission(monkeypatch)

    response = collector_configuration_view.CollectorConfigurationViewSet.as_view({"get": "retrieve"})(
        _request(method="get"),
        pk=shared_config.id,
    )

    assert response.status_code == 200
    assert response.data["nodes"] == [current_node.id]
    assert sibling_node.id not in response.data["nodes"]


def test_superuser_target_organizations_must_be_assignable(monkeypatch):
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)

    response = node_permission.authorize_target_organizations(_request(), SimpleNamespace(), [2])

    assert response.status_code == 403


@pytest.mark.django_db
def test_controller_install_rejects_unassignable_organization_batch_without_side_effects(
    monkeypatch,
):
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    installed = []
    delayed = []
    monkeypatch.setattr(
        installer_view.InstallerService,
        "install_controller",
        lambda *args, **kwargs: installed.append((args, kwargs)) or 1,
    )
    monkeypatch.setattr(
        installer_view.install_controller,
        "delay",
        lambda *args, **kwargs: delayed.append((args, kwargs)),
    )

    response = installer_view.InstallerViewSet.as_view({"post": "controller_install"})(
        _request(
            {
                "cloud_region_id": 1,
                "work_node": "worker",
                "package_id": 1,
                "cpu_architecture": "x86_64",
                "nodes": [
                    {
                        "ip": "10.0.3.1",
                        "node_name": "assignable",
                        "os": "linux",
                        "organizations": [1],
                        "port": 22,
                        "username": "root",
                    },
                    {
                        "ip": "10.0.3.2",
                        "node_name": "unassignable",
                        "os": "linux",
                        "organizations": [2],
                        "port": 22,
                        "username": "root",
                    },
                ],
            },
            permissions=("cloud_region_node-Edit",),
        )
    )

    assert response.status_code == 403
    assert installed == []
    assert delayed == []


@pytest.mark.django_db
def test_controller_install_allows_assignment_to_authorized_sibling_organization(
    monkeypatch,
):
    monkeypatch.setattr(_ScopedSystemMgmt, "assignable_team_ids", [1, 2])
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    installed = []
    delayed = []
    timeouts = []
    monkeypatch.setattr(
        installer_view.InstallerService,
        "install_controller",
        lambda *args, **kwargs: installed.append((args, kwargs)) or 1,
    )
    monkeypatch.setattr(
        installer_view.install_controller,
        "delay",
        lambda *args, **kwargs: delayed.append((args, kwargs)),
    )
    monkeypatch.setattr(
        installer_view.timeout_controller_install_task,
        "apply_async",
        lambda *args, **kwargs: timeouts.append((args, kwargs)),
    )

    response = installer_view.InstallerViewSet.as_view({"post": "controller_install"})(
        _request(
            {
                "cloud_region_id": 1,
                "work_node": "worker",
                "package_id": 1,
                "cpu_architecture": "x86_64",
                "nodes": [
                    {
                        "ip": "10.0.3.3",
                        "node_name": "authorized-sibling",
                        "os": "linux",
                        "organizations": [2],
                        "port": 22,
                        "username": "root",
                    }
                ],
            },
            permissions=("cloud_region_node-Edit",),
        )
    )

    assert response.status_code == 200
    assert installed[0][0][3][0]["organizations"] == [2]
    assert delayed == [((1,), {})]
    assert len(timeouts) == 1


def test_controller_manual_install_rejects_empty_organizations(monkeypatch):
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)

    response = installer_view.InstallerViewSet.as_view({"post": "controller_manual_install"})(
        _request(
            {
                "cloud_region_id": 1,
                "os": "linux",
                "cpu_architecture": "x86_64",
                "package_id": 1,
                "nodes": [
                    {
                        "ip": "10.0.4.1",
                        "node_id": "manual-node",
                        "organizations": [],
                    }
                ],
            },
            permissions=("cloud_region_node-Edit",),
        )
    )

    assert response.status_code == 400


def test_get_install_command_rejects_unassignable_organization_before_token(
    monkeypatch,
):
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    generated = []
    monkeypatch.setattr(
        installer_view.InstallerService,
        "get_install_command",
        lambda *args, **kwargs: generated.append((args, kwargs)) or "command",
    )

    response = installer_view.InstallerViewSet.as_view({"post": "get_install_command"})(
        _request(
            {
                "ip": "10.0.5.1",
                "node_id": "manual-token-node",
                "os": "linux",
                "cpu_architecture": "x86_64",
                "package_id": 1,
                "cloud_region_id": 1,
                "organizations": [2],
            },
            permissions=("cloud_region_node-Edit",),
        )
    )

    assert response.status_code == 403
    assert generated == []


def _installer_payload(action, organizations, *, node_id="strict-install-node"):
    node = {
        "ip": "10.0.6.1",
        "node_id": node_id,
        "node_name": node_id,
        "os": "linux",
        "cpu_architecture": "x86_64",
        "organizations": organizations,
        "port": 22,
        "username": "root",
    }
    if action == "controller_install":
        return {
            "cloud_region_id": 1,
            "work_node": "worker",
            "package_id": 1,
            "cpu_architecture": "x86_64",
            "nodes": [node],
        }
    if action == "controller_manual_install":
        return {
            "cloud_region_id": 1,
            "os": "linux",
            "cpu_architecture": "x86_64",
            "package_id": 1,
            "nodes": [node],
        }
    return {
        "ip": node["ip"],
        "node_id": node["node_id"],
        "node_name": node["node_name"],
        "os": node["os"],
        "cpu_architecture": node["cpu_architecture"],
        "package_id": 1,
        "cloud_region_id": 1,
        "organizations": organizations,
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    "action",
    ["controller_install", "controller_manual_install", "get_install_command"],
)
@pytest.mark.parametrize(
    "organizations",
    [[True], [1.0], ["01"], [0], [-1], [""], []],
)
def test_installer_endpoints_reject_noncanonical_organizations_before_business_logic(
    monkeypatch,
    action,
    organizations,
):
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    business_calls = []
    monkeypatch.setattr(
        installer_view.InstallerService,
        "install_controller",
        lambda *args, **kwargs: business_calls.append((args, kwargs)) or 1,
    )
    monkeypatch.setattr(
        installer_view.InstallerService,
        "get_install_command",
        lambda *args, **kwargs: business_calls.append((args, kwargs)) or "command",
    )
    monkeypatch.setattr(installer_view.install_controller, "delay", lambda *args, **kwargs: None)
    monkeypatch.setattr(installer_view.timeout_controller_install_task, "apply_async", lambda *args, **kwargs: None)

    response = installer_view.InstallerViewSet.as_view({"post": action})(
        _request(
            _installer_payload(
                action,
                organizations,
                node_id="" if action == "controller_install" else "strict-install-node",
            ),
            permissions=("cloud_region_node-Edit",),
        )
    )

    assert response.status_code == 400
    assert business_calls == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "action",
    ["controller_install", "controller_manual_install", "get_install_command"],
)
def test_installer_endpoints_accept_canonical_numeric_string_organization(monkeypatch, action):
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)
    business_calls = []
    monkeypatch.setattr(
        installer_view.InstallerService,
        "install_controller",
        lambda *args, **kwargs: business_calls.append((args, kwargs)) or 1,
    )
    monkeypatch.setattr(
        installer_view.InstallerService,
        "get_install_command",
        lambda *args, **kwargs: business_calls.append((args, kwargs)) or "command",
    )
    monkeypatch.setattr(installer_view.install_controller, "delay", lambda *args, **kwargs: None)
    monkeypatch.setattr(installer_view.timeout_controller_install_task, "apply_async", lambda *args, **kwargs: None)

    response = installer_view.InstallerViewSet.as_view({"post": action})(
        _request(
            _installer_payload(
                action,
                ["1"],
                node_id="" if action == "controller_install" else "strict-install-node",
            ),
            permissions=("cloud_region_node-Edit",),
        )
    )

    assert response.status_code == 200
    if action == "controller_manual_install":
        assert _response_data(response)[0]["organizations"] == [1]
    else:
        assert business_calls


def _patch_install_command_side_effect(monkeypatch, generated_tokens):
    def fake_get_install_command(user, ip, node_id, *args, **kwargs):
        generated_tokens.append(node_id)
        generate_node_token(node_id, ip, user)
        return "command"

    monkeypatch.setattr(
        installer_view.InstallerService,
        "get_install_command",
        fake_get_install_command,
    )


@pytest.mark.django_db
def test_get_install_command_rejects_existing_sibling_node_before_token_side_effect(
    monkeypatch,
):
    region = _region("install-token-sibling")
    sibling_node = _node(region, "install-token-node-sibling", 2)
    SidecarApiToken.objects.create(node_id=sibling_node.id, token="original-token")
    _patch_broad_permission(monkeypatch)
    generated_tokens = []
    _patch_install_command_side_effect(monkeypatch, generated_tokens)

    response = installer_view.InstallerViewSet.as_view({"post": "get_install_command"})(
        _request(
            _installer_payload("get_install_command", [1], node_id=sibling_node.id),
            permissions=("cloud_region_node-Edit",),
        )
    )

    assert response.status_code == 403
    assert generated_tokens == []
    assert SidecarApiToken.objects.get(node_id=sibling_node.id).token == "original-token"


@pytest.mark.django_db
def test_get_install_command_allows_existing_current_team_node(monkeypatch):
    region = _region("install-token-current")
    current_node = _node(region, "install-token-node-current", 1)
    _patch_broad_permission(monkeypatch)
    generated_tokens = []
    _patch_install_command_side_effect(monkeypatch, generated_tokens)

    response = installer_view.InstallerViewSet.as_view({"post": "get_install_command"})(
        _request(
            _installer_payload("get_install_command", [1], node_id=current_node.id),
            permissions=("cloud_region_node-Edit",),
        )
    )

    assert response.status_code == 200
    assert generated_tokens == [current_node.id]
    assert SidecarApiToken.objects.filter(node_id=current_node.id).exists()


@pytest.mark.django_db
def test_get_install_command_allows_new_node_id(monkeypatch):
    _patch_broad_permission(monkeypatch)
    generated_tokens = []
    _patch_install_command_side_effect(monkeypatch, generated_tokens)

    response = installer_view.InstallerViewSet.as_view({"post": "get_install_command"})(
        _request(
            _installer_payload("get_install_command", [1], node_id="install-token-node-new"),
            permissions=("cloud_region_node-Edit",),
        )
    )

    assert response.status_code == 200
    assert generated_tokens == ["install-token-node-new"]
    assert SidecarApiToken.objects.filter(node_id="install-token-node-new").exists()


@pytest.mark.django_db
def test_controller_install_allows_new_node_id_before_node_registration(monkeypatch):
    _patch_broad_permission(monkeypatch)
    installed = []
    delayed = []
    timeouts = []
    monkeypatch.setattr(
        installer_view.InstallerService,
        "install_controller",
        lambda *args, **kwargs: installed.append((args, kwargs)) or 1,
    )
    monkeypatch.setattr(
        installer_view.install_controller,
        "delay",
        lambda *args, **kwargs: delayed.append((args, kwargs)),
    )
    monkeypatch.setattr(
        installer_view.timeout_controller_install_task,
        "apply_async",
        lambda *args, **kwargs: timeouts.append((args, kwargs)),
    )

    response = installer_view.InstallerViewSet.as_view({"post": "controller_install"})(
        _request(
            _installer_payload(
                "controller_install",
                [1],
                node_id="auto-install-node-new",
            ),
            permissions=("cloud_region_node-Edit",),
        )
    )

    assert response.status_code == 200
    assert installed
    assert delayed == [((1,), {})]
    assert len(timeouts) == 1


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
def test_collector_install_task_status_is_projected_from_current_team_nodes(monkeypatch):
    region = _region("collector-install-status-projection")
    current_node = _node(region, "collector-install-status-current", 1)
    sibling_node = _node(region, "collector-install-status-sibling", 2)
    task = CollectorTask.objects.create(
        type="install",
        status="error",
        package_version_id=1,
    )
    CollectorTaskNode.objects.create(task=task, node=current_node, status="success", result={})
    CollectorTaskNode.objects.create(task=task, node=sibling_node, status="error", result={})
    _patch_broad_permission(monkeypatch)

    response = installer_view.InstallerViewSet.as_view({"post": "collector_install_nodes"})(
        _request(permissions=("cloud_region_node-OperateCollector",)),
        task_id=str(task.id),
    )
    data = _response_data(response)

    assert data["status"] == "finished"
    assert data["summary"]["success"] == 1
    assert data["summary"]["error"] == 0


@pytest.mark.django_db
def test_collector_action_task_status_is_projected_from_current_team_nodes(monkeypatch):
    region = _region("collector-action-status-projection")
    current_node = _node(region, "collector-action-status-current", 1)
    sibling_node = _node(region, "collector-action-status-sibling", 2)
    collector = Collector.objects.create(
        id="collector-action-status",
        name="collector-action-status",
        service_type="exec",
        node_operating_system="linux",
        executable_path="/bin/collector",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
    )
    task = CollectorActionTask.objects.create(
        collector=collector,
        cloud_region=region,
        action="start",
        status="error",
        total_count=2,
    )
    CollectorActionTaskNode.objects.create(task=task, node=current_node, status="success", result={})
    CollectorActionTaskNode.objects.create(task=task, node=sibling_node, status="error", result={})
    _patch_broad_permission(monkeypatch)

    response = node_view.NodeViewSet.as_view({"post": "collector_action_nodes"})(
        _request(),
        task_id=str(task.id),
    )
    data = _response_data(response)

    assert data["status"] == "finished"
    assert data["summary"]["success"] == 1
    assert data["summary"]["error"] == 0


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ({"total": 0}, "waiting"),
        ({"total": 2, "waiting": 2}, "waiting"),
        ({"total": 2, "waiting": 1, "success": 1}, "running"),
        ({"total": 2, "running": 1, "error": 1}, "running"),
        ({"total": 1, "success": 1}, "finished"),
    ],
)
def test_project_task_status_uses_only_projected_summary(summary, expected):
    assert project_task_status_from_summary(summary) == expected


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
@pytest.mark.parametrize(
    "organizations",
    [[True], [1.0], ["01"], [1, None], [1, ""], [1, "invalid"]],
)
def test_legacy_controller_task_snapshot_rejects_any_noncanonical_organization(
    organizations,
):
    region = _region("controller-task-invalid-snapshot")
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="running",
        work_node="worker",
        package_version_id=1,
        created_by="admin",
        updated_by="admin",
    )
    ControllerTaskNode.objects.create(
        task=task,
        node_id="",
        ip="10.0.2.1",
        node_name="legacy-invalid",
        os="linux",
        organizations=organizations,
        port=22,
        username="root",
        password="",
        status="waiting",
    )

    task_nodes = InstallerService.get_authorized_controller_task_nodes(
        task.id,
        authorized_nodes=Node.objects.none(),
        scope=SimpleNamespace(data_team_ids=frozenset({1})),
    )

    assert task_nodes == []


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
