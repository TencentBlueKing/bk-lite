import base64
import json
from io import StringIO
from queue import Queue
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.management import call_command
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.filters.package import PackageVersionFilter
from apps.node_mgmt.management.commands.backfill_node_cpu_architecture import Command as BackfillNodeCpuArchitectureCommand
from apps.node_mgmt.management.commands.backfill_package_storage_paths import Command as BackfillPackageStoragePathsCommand
from apps.node_mgmt.management.commands.collector_package_init import Command as CollectorPackageInitCommand
from apps.node_mgmt.management.commands.controller_package_init import Command as ControllerPackageInitCommand
from apps.node_mgmt.management.commands.installer_init import Command as InstallerInitCommand
from apps.node_mgmt.management.commands.verify_architecture_rollout import Command as VerifyArchitectureRolloutCommand
from apps.node_mgmt.management.services.node_init.collector_init import import_collector
from apps.node_mgmt.management.services.node_init.controller_init import controller_init
from apps.node_mgmt.management.services.node_init.definition_loader import load_definition_records
from apps.node_mgmt.models import CloudRegion, Collector, CollectorConfiguration, Controller, Node, NodeComponentVersion, PackageVersion, SidecarEnv
from apps.node_mgmt.models.sidecar import ChildConfig, NodeOrganization
from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode
from apps.node_mgmt.nats.node import NatsService
from apps.node_mgmt.serializers.collector import CollectorSerializer
from apps.node_mgmt.serializers.package import PackageVersionSerializer
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.services.installer_session import InstallerSessionService
from apps.node_mgmt.services import node as node_service
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.services.cloudregion import RegionService
from apps.node_mgmt.services.sidecar import Sidecar
from apps.node_mgmt.services.version_upgrade import VersionUpgradeService
from apps.node_mgmt.tasks import installer as installer_tasks
from apps.node_mgmt.tasks import version_discovery
from apps.node_mgmt.tasks.version_discovery import _calculate_upgrade_info, _discover_controller_version
from apps.node_mgmt.utils import permission as node_permission
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture
from apps.node_mgmt.utils.token_auth import generate_node_token
from apps.node_mgmt.views import collector_configuration, node as node_view
from apps.node_mgmt.views.collector import CollectorViewSet
from apps.node_mgmt.views.installer import InstallerViewSet
from apps.node_mgmt.views.sidecar import OpenSidecarViewSet
from config.components.drf import AUTH_TOKEN_HEADER_NAME


def _build_admin_user():
    return User(
        username="installer-test-user",
        domain="domain.com",
        locale="en",
        is_superuser=True,
        roles=["admin"],
        group_list=[{"id": 1, "name": "Team"}],
    )


def _build_permission_user(*permissions):
    user = User(
        username="permission-test-user",
        domain="domain.com",
        locale="en",
        is_superuser=False,
        roles=[],
        group_list=[{"id": 1, "name": "Team"}],
    )
    user.permission = {"node": set(permissions)}
    return user


def _json_response_data(response):
    return json.loads(response.content)


class _FakeOrganizations(list):
    def all(self):
        return self


class _FakeNode:
    def __init__(self, node_id="node-1", organizations=None):
        self.id = node_id
        self.name = f"name-{node_id}"
        self.ip = "127.0.0.1"
        self.operating_system = "linux"
        self.install_method = "manual"
        self.nodeorganization_set = _FakeOrganizations([SimpleNamespace(organization=org) for org in (organizations or [2])])
        self.saved = False

    def save(self):
        self.saved = True


class _FakeNodeQuerySet(list):
    def filter(self, *args, **kwargs):
        if "id__in" in kwargs:
            ids = {str(value) for value in kwargs["id__in"]}
            return _FakeNodeQuerySet([node for node in self if str(node.id) in ids])
        if "cloud_region_id" in kwargs:
            return self
        return self

    def prefetch_related(self, *args):
        return self

    def distinct(self):
        return self

    def values_list(self, field, flat=False):
        if field == "id" and flat:
            return [node.id for node in self]
        return []


class _FakeConfigQuerySet(list):
    def select_related(self, *args):
        return self

    def prefetch_related(self, *args):
        return self

    def filter(self, **kwargs):
        return self


class _FakeConfig:
    id = "cfg-1"
    name = "cfg"
    config_template = "x"
    collector_id = "collector-1"
    cloud_region_id = 1
    is_pre = False
    collector = SimpleNamespace(node_operating_system="linux")

    def __init__(self, nodes):
        self.nodes = _FakeOrganizations(nodes)


def _make_node_request(data=None, method="post"):
    factory = APIRequestFactory()
    request_factory = getattr(factory, method)
    request = request_factory("/node-mgmt/test", data=data or {}, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=_build_admin_user())
    return request


def _make_permission_request(data=None, method="post", permissions=()):
    factory = APIRequestFactory()
    request_factory = getattr(factory, method)
    request = request_factory("/node-mgmt/test", data=data or {}, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=_build_permission_user(*permissions))
    return request


def _build_sidecar_request(method, path, *, query_params=None, headers=None):
    factory = APIRequestFactory()
    request_factory = getattr(factory, method)
    return request_factory(path, query_params or {}, format="json", **(headers or {}))


def _build_sidecar_auth_header(node_id):
    token = generate_node_token(node_id, "127.0.0.1", "tester")
    basic_token = base64.b64encode(f"{token}:unused".encode("utf-8")).decode("utf-8")
    return {AUTH_TOKEN_HEADER_NAME: f"Basic {basic_token}"}


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("x86_64", NodeConstants.X86_64_ARCH),
        ("amd64", NodeConstants.X86_64_ARCH),
        ("arm64", NodeConstants.ARM64_ARCH),
        ("aarch64", NodeConstants.ARM64_ARCH),
        ("sparc", NodeConstants.UNKNOWN_ARCH),
        ("", NodeConstants.UNKNOWN_ARCH),
        (None, NodeConstants.UNKNOWN_ARCH),
    ],
)
def test_normalize_cpu_architecture(raw_value, expected):
    assert normalize_cpu_architecture(raw_value) == expected


def test_authorize_node_ids_requires_operate_permission(monkeypatch):
    node = _FakeNode()
    monkeypatch.setattr(node_permission.Node.objects, "filter", lambda **kwargs: _FakeNodeQuerySet([node]))
    monkeypatch.setattr(
        node_permission,
        "get_node_permission",
        lambda request: {"instance": [{"id": node.id, "permission": ["View"]}], "team": []},
    )

    nodes, response = node_permission.authorize_node_ids(_make_node_request(), [node.id])

    assert nodes is None
    assert response.status_code == 403


def test_authorize_target_organizations_allows_in_scope_team_org(monkeypatch):
    node = _FakeNode(organizations=[2])

    class _ScopedSystemMgmt:
        def __init__(self, is_local_client=True):
            pass

        def get_authorized_groups_scoped(self, actor_context, include_children=False):
            return {"data": [2]}

    monkeypatch.setattr(node_permission, "SystemMgmt", _ScopedSystemMgmt)

    response = node_permission.authorize_target_organizations(_make_node_request(), node, [2])

    assert response is None


def test_authorize_target_organizations_rejects_new_out_of_scope_org(monkeypatch):
    node = _FakeNode(organizations=[2])

    class _ScopedSystemMgmt:
        def __init__(self, is_local_client=True):
            pass

        def get_authorized_groups_scoped(self, actor_context, include_children=False):
            return {"data": [2]}

    monkeypatch.setattr(node_permission, "SystemMgmt", _ScopedSystemMgmt)

    response = node_permission.authorize_target_organizations(_make_node_request(), node, [2, 3])

    assert response.status_code == 403


def test_authorize_target_organizations_rejects_existing_org_outside_team_scope(monkeypatch):
    node = _FakeNode(organizations=[2])

    class _ScopedSystemMgmt:
        def __init__(self, is_local_client=True):
            pass

        def get_authorized_groups_scoped(self, actor_context, include_children=False):
            return {"data": []}

    monkeypatch.setattr(node_permission, "SystemMgmt", _ScopedSystemMgmt)

    response = node_permission.authorize_target_organizations(_make_node_request(), node, [2])

    assert response.status_code == 403


def test_get_node_permission_rejects_forged_current_team(monkeypatch):
    captured = {}

    class _ScopedSystemMgmt:
        def __init__(self, is_local_client=True):
            captured["is_local_client"] = is_local_client

        def get_authorized_groups_scoped(self, actor_context, include_children=False):
            captured["actor_context"] = actor_context
            captured["include_children"] = include_children
            return {"result": True, "data": []}

    def _unexpected_permission(*args, **kwargs):
        raise AssertionError("get_permission_rules should not be called for forged current_team")

    monkeypatch.setattr(node_permission, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(node_permission, "get_permission_rules", _unexpected_permission)

    request = _make_permission_request()
    request.COOKIES["current_team"] = "2"

    permission = node_permission.get_node_permission(request)

    assert permission == {}
    assert captured == {
        "is_local_client": True,
        "actor_context": {
            "username": "permission-test-user",
            "domain": "domain.com",
            "current_team": 2,
            "is_superuser": False,
        },
        "include_children": False,
    }


def test_get_node_permission_uses_scoped_current_team(monkeypatch):
    captured = {}

    class _ScopedSystemMgmt:
        def __init__(self, is_local_client=True):
            captured["is_local_client"] = is_local_client

        def get_authorized_groups_scoped(self, actor_context, include_children=False):
            captured["actor_context"] = actor_context
            captured["include_children"] = include_children
            return {"result": True, "data": [1, 11]}

    def _fake_permission(user, current_team, app_name, permission_key, include_children=False):
        captured["permission_args"] = {
            "username": user.username,
            "domain": user.domain,
            "current_team": current_team,
            "app_name": app_name,
            "permission_key": permission_key,
            "include_children": include_children,
        }
        return {"instance": [], "team": [1, 11]}

    monkeypatch.setattr(node_permission, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(node_permission, "get_permission_rules", _fake_permission)

    request = _make_permission_request()
    request.COOKIES["include_children"] = "1"

    permission = node_permission.get_node_permission(request)

    assert permission == {"instance": [], "team": [1, 11]}
    assert captured == {
        "is_local_client": True,
        "actor_context": {
            "username": "permission-test-user",
            "domain": "domain.com",
            "current_team": 1,
            "is_superuser": False,
        },
        "include_children": True,
        "permission_args": {
            "username": "permission-test-user",
            "domain": "domain.com",
            "current_team": 1,
            "app_name": "node_mgmt",
            "permission_key": NodeConstants.MODULE,
            "include_children": True,
        },
    }


def _create_node_mgmt_region(name="test-region"):
    return CloudRegion.objects.create(
        name=name,
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )


def _create_node_mgmt_collector(region, collector_id="collector-1"):
    return Collector.objects.create(
        id=collector_id,
        name=f"collector-{collector_id}",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/collector",
        execute_parameters="",
        cloud_region=region if hasattr(Collector, "cloud_region") else None,
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )


def _create_node_mgmt_node(region, node_id="node-1", organization=1):
    node = Node.objects.create(
        id=node_id,
        name=node_id,
        ip=f"10.0.0.{node_id[-1] if node_id[-1].isdigit() else 1}",
        operating_system="linux",
        collector_configuration_directory="/etc/collector",
        cloud_region=region,
        install_method="manual",
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    NodeOrganization.objects.create(
        node=node,
        organization=organization,
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    return node


def _create_node_mgmt_configuration(region, collector, config_id, *, created_by="tester", bind_nodes=None):
    config = CollectorConfiguration.objects.create(
        id=config_id,
        name=f"config-{config_id}",
        config_template="template",
        collector=collector,
        cloud_region=region,
        created_by=created_by,
        updated_by=created_by,
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    if bind_nodes:
        config.nodes.add(*bind_nodes)
    return config


@pytest.mark.django_db
def test_get_authorized_collector_configuration_queryset_includes_authorized_nodes_and_creator(monkeypatch):
    region = _create_node_mgmt_region()
    collector = Collector.objects.create(
        id="collector-auth-1",
        name="collector-auth-1",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/collector",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    allowed_node = _create_node_mgmt_node(region, node_id="node-auth-1", organization=1)
    denied_node = _create_node_mgmt_node(region, node_id="node-auth-2", organization=2)
    allowed_config = _create_node_mgmt_configuration(region, collector, "cfg-auth-1", bind_nodes=[allowed_node])
    _create_node_mgmt_configuration(region, collector, "cfg-auth-2", bind_nodes=[denied_node])
    owned_config = _create_node_mgmt_configuration(
        region,
        collector,
        "cfg-auth-3",
        created_by="permission-test-user",
    )

    monkeypatch.setattr(node_permission, "get_node_permission", lambda request: {"team": [1], "instance": []})

    result_ids = set(node_permission.get_authorized_collector_configuration_queryset(_make_permission_request()).values_list("id", flat=True))

    assert result_ids == {allowed_config.id, owned_config.id}


@pytest.mark.django_db
def test_get_authorized_collector_configuration_queryset_excludes_creator_owned_bound_unauthorized_config(monkeypatch):
    region = _create_node_mgmt_region(name="bound-region")
    collector = Collector.objects.create(
        id="collector-bound-1",
        name="collector-bound-1",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/collector",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    denied_node = _create_node_mgmt_node(region, node_id="node-bound-1", organization=2)
    creator_owned_bound_config = _create_node_mgmt_configuration(
        region,
        collector,
        "cfg-bound-1",
        created_by="permission-test-user",
        bind_nodes=[denied_node],
    )

    monkeypatch.setattr(node_permission, "get_node_permission", lambda request: {"team": [1], "instance": []})

    result_ids = set(node_permission.get_authorized_collector_configuration_queryset(_make_permission_request()).values_list("id", flat=True))

    assert creator_owned_bound_config.id not in result_ids


@pytest.mark.django_db
def test_authorize_child_config_ids_rejects_out_of_scope_config(monkeypatch):
    region = _create_node_mgmt_region(name="child-region")
    collector = Collector.objects.create(
        id="collector-child-1",
        name="collector-child-1",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/collector",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    allowed_node = _create_node_mgmt_node(region, node_id="node-child-1", organization=1)
    denied_node = _create_node_mgmt_node(region, node_id="node-child-2", organization=2)
    allowed_config = _create_node_mgmt_configuration(region, collector, "cfg-child-1", bind_nodes=[allowed_node])
    denied_config = _create_node_mgmt_configuration(region, collector, "cfg-child-2", bind_nodes=[denied_node])
    ChildConfig.objects.create(
        id="child-allowed",
        collect_type="metrics",
        config_type="telegraf",
        content="allowed",
        collector_config=allowed_config,
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    denied_child = ChildConfig.objects.create(
        id="child-denied",
        collect_type="metrics",
        config_type="telegraf",
        content="denied",
        collector_config=denied_config,
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )

    monkeypatch.setattr(node_permission, "get_node_permission", lambda request: {"team": [1], "instance": []})

    child_configs, response = node_permission.authorize_child_config_ids(_make_permission_request(), [denied_child.id])

    assert child_configs is None
    assert response.status_code == 403


@pytest.mark.django_db
def test_authorize_mutable_collector_configuration_ids_rejects_shared_config_with_unauthorized_nodes(monkeypatch):
    region = _create_node_mgmt_region(name="mutable-region")
    collector = Collector.objects.create(
        id="collector-mutable-1",
        name="collector-mutable-1",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/collector",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    allowed_node = _create_node_mgmt_node(region, node_id="node-mutable-1", organization=1)
    denied_node = _create_node_mgmt_node(region, node_id="node-mutable-2", organization=2)
    shared_config = _create_node_mgmt_configuration(region, collector, "cfg-mutable-1", bind_nodes=[allowed_node, denied_node])

    monkeypatch.setattr(node_permission, "get_node_permission", lambda request: {"team": [1], "instance": []})

    configurations, response = node_permission.authorize_mutable_collector_configuration_ids(_make_permission_request(), [shared_config.id])

    assert configurations is None
    assert response.status_code == 403


@pytest.mark.django_db
def test_authorize_mutable_collector_configuration_ids_allows_unbound_creator_draft(monkeypatch):
    region = _create_node_mgmt_region(name="draft-region")
    collector = Collector.objects.create(
        id="collector-draft-1",
        name="collector-draft-1",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/collector",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    draft_config = _create_node_mgmt_configuration(
        region,
        collector,
        "cfg-draft-1",
        created_by="permission-test-user",
    )

    monkeypatch.setattr(node_permission, "get_node_permission", lambda request: {"team": [1], "instance": []})

    configurations, response = node_permission.authorize_mutable_collector_configuration_ids(_make_permission_request(), [draft_config.id])

    assert response is None
    assert [config.id for config in configurations] == [draft_config.id]


@pytest.mark.django_db
def test_authorize_mutable_child_config_ids_rejects_shared_parent_with_unauthorized_nodes(monkeypatch):
    region = _create_node_mgmt_region(name="mutable-child-region")
    collector = Collector.objects.create(
        id="collector-mutable-child-1",
        name="collector-mutable-child-1",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/collector",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    allowed_node = _create_node_mgmt_node(region, node_id="node-mutable-child-1", organization=1)
    denied_node = _create_node_mgmt_node(region, node_id="node-mutable-child-2", organization=2)
    shared_config = _create_node_mgmt_configuration(region, collector, "cfg-mutable-child-1", bind_nodes=[allowed_node, denied_node])
    child_config = ChildConfig.objects.create(
        id="child-mutable-1",
        collect_type="metrics",
        config_type="telegraf",
        content="shared",
        collector_config=shared_config,
        created_by="tester",
        updated_by="tester",
        domain="domain.com",
        updated_by_domain="domain.com",
    )

    monkeypatch.setattr(node_permission, "get_node_permission", lambda request: {"team": [1], "instance": []})

    child_configs, response = node_permission.authorize_mutable_child_config_ids(_make_permission_request(), [child_config.id])

    assert child_configs is None
    assert response.status_code == 403


def test_batch_operate_node_collector_requires_node_permission(monkeypatch):
    monkeypatch.setattr(node_view, "authorize_node_ids", lambda request, node_ids: (None, WebUtils.response_403("denied")))
    called = {"value": False}
    monkeypatch.setattr(
        node_view.NodeService,
        "batch_operate_node_collector",
        lambda *args, **kwargs: called.__setitem__("value", True),
    )

    response = node_view.NodeViewSet.as_view({"post": "batch_operate_node_collector"})(
        _make_node_request({"node_ids": ["node-1"], "collector_id": "collector-1", "operation": "restart"})
    )

    assert response.status_code == 403
    assert called["value"] is False


@pytest.mark.parametrize(
    ("view", "action", "request_data", "method", "required_permission", "service_attr"),
    [
        (
            node_view.NodeViewSet.as_view({"delete": "destroy"}),
            "destroy",
            None,
            "delete",
            "cloud_region_node-Delete",
            None,
        ),
        (
            node_view.NodeViewSet.as_view({"patch": "update_node"}),
            "update_node",
            {"name": "updated-node"},
            "patch",
            "cloud_region_node-Edit",
            None,
        ),
        (
            node_view.NodeViewSet.as_view({"post": "batch_binding_node_configuration"}),
            "batch_binding_node_configuration",
            {"node_ids": ["node-1"], "collector_configuration_id": "cfg-1"},
            "post",
            "cloud_region_node-EditMainConfiguration",
            "batch_binding_node_configuration",
        ),
        (
            node_view.NodeViewSet.as_view({"post": "batch_operate_node_collector"}),
            "batch_operate_node_collector",
            {"node_ids": ["node-1"], "collector_id": "collector-1", "operation": "restart"},
            "post",
            "cloud_region_node-OperateCollector",
            "batch_operate_node_collector",
        ),
        (
            collector_configuration.CollectorConfigurationViewSet.as_view({"post": "apply_to_node"}),
            "apply_to_node",
            [{"node_id": "node-1", "collector_configuration_id": "cfg-1"}],
            "post",
            "cloud_region_node-EditMainConfiguration",
            "apply_to_node",
        ),
        (
            collector_configuration.CollectorConfigurationViewSet.as_view({"post": "cancel_apply_to_node"}),
            "cancel_apply_to_node",
            {"node_id": "node-1", "collector_configuration_id": "cfg-1"},
            "post",
            "cloud_region_node-EditMainConfiguration",
            None,
        ),
    ],
)
def test_node_write_endpoints_require_explicit_action_permission(monkeypatch, view, action, request_data, method, required_permission, service_attr):
    if action in {"destroy", "update_node", "batch_binding_node_configuration", "batch_operate_node_collector"}:
        monkeypatch.setattr(node_view, "authorize_node_ids", lambda request, node_ids: ([_FakeNode()], None))
    else:
        monkeypatch.setattr(collector_configuration, "authorize_node_ids", lambda request, node_ids: ([_FakeNode()], None))

    if action == "batch_binding_node_configuration":
        monkeypatch.setattr(node_view, "authorize_mutable_collector_configuration_ids", lambda request, config_ids: ([_FakeConfig([])], None))
    elif action in {"apply_to_node", "cancel_apply_to_node"}:
        monkeypatch.setattr(
            collector_configuration,
            "authorize_mutable_collector_configuration_ids",
            lambda request, config_ids: ([_FakeConfig([])], None),
        )

    called = {"value": False}
    if service_attr:
        target = node_view.NodeService if hasattr(node_view.NodeService, service_attr) else collector_configuration.CollectorConfigurationService
        if action == "batch_operate_node_collector":
            monkeypatch.setattr(target, service_attr, lambda *args, **kwargs: called.__setitem__("value", True) or "task-1")
        else:
            monkeypatch.setattr(target, service_attr, lambda *args, **kwargs: called.__setitem__("value", True) or (True, "ok"))
    elif action == "cancel_apply_to_node":
        config = SimpleNamespace(nodes=SimpleNamespace(remove=lambda node: called.__setitem__("value", True)))
    elif action == "destroy":
        monkeypatch.setattr(node_view.NodeViewSet, "perform_destroy", lambda self, instance: called.__setitem__("value", True))

    if action == "update_node":
        monkeypatch.setattr(node_view.sync_node_properties_to_sidecar, "delay", lambda **kwargs: called.__setitem__("value", True))

    kwargs = {"pk": "node-1"} if action in {"destroy", "update_node"} else {}
    response = view(_make_permission_request(request_data, method=method, permissions=("cloud_region_node-View",)), **kwargs)

    assert response.status_code == 403
    assert called["value"] is False

    allowed_permissions = ("cloud_region_node-View", required_permission)
    response = view(_make_permission_request(request_data, method=method, permissions=allowed_permissions), **kwargs)

    assert response.status_code != 403


def test_config_node_asso_hides_unauthorized_nodes(monkeypatch):
    allowed = _FakeNode("node-allowed")
    denied = _FakeNode("node-denied")
    monkeypatch.setattr(
        collector_configuration,
        "get_authorized_node_queryset",
        lambda request: _FakeNodeQuerySet([allowed]),
    )
    monkeypatch.setattr(
        collector_configuration.CollectorConfiguration.objects,
        "select_related",
        lambda *args: _FakeConfigQuerySet([_FakeConfig([allowed, denied])]),
    )

    response = collector_configuration.CollectorConfigurationViewSet.as_view({"post": "get_config_node_asso"})(_make_node_request({}))
    payload = _json_response_data(response)

    assert payload["data"][0]["nodes"] == [
        {
            "id": "node-allowed",
            "name": "name-node-allowed",
            "ip": "127.0.0.1",
            "operating_system": "linux",
        }
    ]


def test_apply_to_node_prevalidates_permissions_before_mutation(monkeypatch):
    monkeypatch.setattr(
        collector_configuration,
        "authorize_node_ids",
        lambda request, node_ids: (None, WebUtils.response_403("denied")),
    )
    called = {"value": False}
    monkeypatch.setattr(
        collector_configuration.CollectorConfigurationService,
        "apply_to_node",
        lambda *args, **kwargs: called.__setitem__("value", True),
    )

    response = collector_configuration.CollectorConfigurationViewSet.as_view({"post": "apply_to_node"})(
        _make_node_request(
            [
                {"node_id": "node-1", "collector_configuration_id": "cfg-1"},
                {"node_id": "node-2", "collector_configuration_id": "cfg-1"},
            ]
        )
    )

    assert response.status_code == 403
    assert called["value"] is False


def test_apply_to_node_prevalidates_configuration_permissions_before_mutation(monkeypatch):
    monkeypatch.setattr(collector_configuration, "authorize_node_ids", lambda request, node_ids: ([_FakeNode()], None))
    monkeypatch.setattr(
        collector_configuration,
        "authorize_mutable_collector_configuration_ids",
        lambda request, config_ids: (None, WebUtils.response_403("denied")),
    )
    called = {"value": False}
    monkeypatch.setattr(
        collector_configuration.CollectorConfigurationService,
        "apply_to_node",
        lambda *args, **kwargs: called.__setitem__("value", True),
    )

    response = collector_configuration.CollectorConfigurationViewSet.as_view({"post": "apply_to_node"})(
        _make_node_request(
            [
                {"node_id": "node-1", "collector_configuration_id": "cfg-1"},
            ]
        )
    )

    assert response.status_code == 403
    assert called["value"] is False


def test_get_node_list_rejects_forged_current_team(monkeypatch):
    captured = {}

    class _ScopedSystemMgmt:
        def __init__(self, is_local_client=True):
            captured["is_local_client"] = is_local_client

        def get_authorized_groups_scoped(self, actor_context, include_children=False):
            captured["actor_context"] = actor_context
            captured["include_children"] = include_children
            return {"result": True, "data": []}

    def _unexpected_permission(*args, **kwargs):
        raise AssertionError("get_permission_rules should not be called for forged current_team")

    monkeypatch.setattr(node_service, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(node_service, "get_permission_rules", _unexpected_permission)

    result = node_service.NodeService.get_node_list(
        organization_ids=[],
        cloud_region_id=None,
        name="",
        ip="",
        os="",
        page=1,
        page_size=20,
        is_active=None,
        is_manual=None,
        is_container=None,
        permission_data={
            "username": "permission-test-user",
            "domain": "domain.com",
            "current_team": 2,
            "include_children": False,
            "is_superuser": False,
        },
    )

    assert result["count"] == 0
    assert list(result["nodes"]) == []
    assert captured == {
        "is_local_client": True,
        "actor_context": {
            "username": "permission-test-user",
            "domain": "domain.com",
            "current_team": 2,
            "is_superuser": False,
        },
        "include_children": False,
    }


def test_get_authorized_nodes_by_ids_uses_scoped_current_team(monkeypatch):
    captured = {}
    allowed_node = _FakeNode(node_id="node-scoped", organizations=[1])

    class _ScopedSystemMgmt:
        def __init__(self, is_local_client=True):
            captured["is_local_client"] = is_local_client

        def get_authorized_groups_scoped(self, actor_context, include_children=False):
            captured["actor_context"] = actor_context
            captured["include_children"] = include_children
            return {"result": True, "data": [1]}

    def _fake_permission(user, current_team, app_name, permission_key, include_children=False):
        captured["permission_args"] = {
            "username": user.username,
            "domain": user.domain,
            "current_team": current_team,
            "app_name": app_name,
            "permission_key": permission_key,
            "include_children": include_children,
        }
        return {"instance": [], "team": [1]}

    class _NodeManager:
        @staticmethod
        def all():
            return _FakeNodeQuerySet([allowed_node])

    monkeypatch.setattr(node_service, "SystemMgmt", _ScopedSystemMgmt)
    monkeypatch.setattr(node_service, "get_permission_rules", _fake_permission)
    monkeypatch.setattr(node_service.Node, "objects", _NodeManager())

    result = node_service.NodeService.get_authorized_nodes_by_ids(
        ["node-scoped"],
        permission_data={
            "username": "permission-test-user",
            "domain": "domain.com",
            "current_team": 1,
            "include_children": True,
            "is_superuser": False,
        },
    )

    assert result == [{"id": "node-scoped", "organization_ids": [1]}]
    assert captured == {
        "is_local_client": True,
        "actor_context": {
            "username": "permission-test-user",
            "domain": "domain.com",
            "current_team": 1,
            "is_superuser": False,
        },
        "include_children": True,
        "permission_args": {
            "username": "permission-test-user",
            "domain": "domain.com",
            "current_team": 1,
            "app_name": "node_mgmt",
            "permission_key": NodeConstants.MODULE,
            "include_children": True,
        },
    }


def test_batch_binding_configuration_prevalidates_configuration_permissions(monkeypatch):
    monkeypatch.setattr(node_view, "authorize_node_ids", lambda request, node_ids: ([_FakeNode()], None))
    monkeypatch.setattr(
        node_view,
        "authorize_mutable_collector_configuration_ids",
        lambda request, config_ids: (None, WebUtils.response_403("denied")),
    )
    called = {"value": False}
    monkeypatch.setattr(
        node_view.NodeService,
        "batch_binding_node_configuration",
        lambda *args, **kwargs: called.__setitem__("value", True),
    )

    response = node_view.NodeViewSet.as_view({"post": "batch_binding_node_configuration"})(
        _make_node_request({"node_ids": ["node-1"], "collector_configuration_id": "cfg-1"})
    )

    assert response.status_code == 403
    assert called["value"] is False


@pytest.mark.django_db
def test_resolve_package_by_architecture_prefers_exact_match():
    seed = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.2.3",
        name="fusion-collectors-x86_64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )
    arm = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.ARM64_ARCH,
        object="Controller",
        version="1.2.3",
        name="fusion-collectors-arm64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )

    resolved = PackageService.resolve_package_by_architecture(seed.id, "aarch64")

    assert resolved is not None
    assert resolved.id == arm.id


@pytest.mark.django_db
def test_resolve_package_by_architecture_accepts_legacy_empty_arch_for_x86_64():
    seed = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture="",
        object="Controller",
        version="2.0.0",
        name="fusion-collectors-generic.tar.gz",
        created_by="tester",
        updated_by="tester",
    )

    resolved = PackageService.resolve_package_by_architecture(seed.id, "x86_64")

    assert resolved is not None
    assert resolved.id == seed.id


@pytest.mark.django_db
def test_resolve_package_by_architecture_rejects_legacy_empty_arch_for_arm64():
    seed = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture="",
        object="Controller",
        version="2.0.1",
        name="fusion-collectors-legacy.tar.gz",
        created_by="tester",
        updated_by="tester",
    )

    resolved = PackageService.resolve_package_by_architecture(seed.id, "arm64")

    assert resolved is None


@pytest.mark.django_db
def test_resolve_collector_by_architecture_rejects_legacy_empty_arch_for_arm64():
    Collector.objects.create(
        id="telegraf_legacy_only",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="legacy x86",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )

    resolved = PackageService.resolve_collector_by_architecture(NodeConstants.LINUX_OS, "Telegraf", NodeConstants.ARM64_ARCH)

    assert resolved is None


@pytest.mark.django_db
def test_resolve_collector_by_architecture_accepts_legacy_empty_arch_for_x86_64():
    collector = Collector.objects.create(
        id="telegraf_legacy_x86",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="legacy x86",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )

    resolved = PackageService.resolve_collector_by_architecture(NodeConstants.LINUX_OS, "Telegraf", NodeConstants.X86_64_ARCH)

    assert resolved is not None
    assert resolved.id == collector.id


@pytest.mark.django_db
def test_installer_service_raises_when_arch_specific_package_missing():
    seed = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="3.0.0",
        name="fusion-collectors-x86_64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )

    with pytest.raises(BaseAppException):
        InstallerService.resolve_package_by_architecture(seed.id, "arm64")


@pytest.mark.django_db
def test_installer_service_accepts_legacy_empty_arch_controller_as_x86_64():
    seed = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture="",
        object="Controller",
        version="3.1.0",
        name="fusion-collectors-legacy.tar.gz",
        created_by="tester",
        updated_by="tester",
    )

    resolved = InstallerService.resolve_package_by_architecture(seed.id, "x86_64")

    assert resolved.id == seed.id


@pytest.mark.django_db
def test_installer_service_rejects_legacy_empty_arch_controller_for_arm64():
    seed = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture="",
        object="Controller",
        version="3.1.1",
        name="fusion-collectors-legacy.tar.gz",
        created_by="tester",
        updated_by="tester",
    )

    with pytest.raises(BaseAppException):
        InstallerService.resolve_package_by_architecture(seed.id, "arm64")


@pytest.mark.django_db
def test_build_session_config_resolves_package_and_installer_by_architecture(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="test-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    SidecarEnv.objects.create(
        key=NodeConstants.SERVER_URL_KEY,
        value="https://example.com",
        type="text",
        cloud_region=cloud_region,
    )
    SidecarEnv.objects.create(
        key=NodeConstants.NATS_SERVERS_KEY,
        value="nats://127.0.0.1:4222",
        type="text",
        cloud_region=cloud_region,
    )
    SidecarEnv.objects.create(
        key="NATS_ADMIN_USERNAME",
        value="admin",
        type="text",
        cloud_region=cloud_region,
    )
    SidecarEnv.objects.create(
        key=NodeConstants.NATS_ADMIN_PASSWORD_KEY,
        value="password",
        type="text",
        cloud_region=cloud_region,
    )

    x86_package = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.0",
        name="fusion-collectors-x86_64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )
    arm_package = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.ARM64_ARCH,
        object="Controller",
        version="1.0.0",
        name="fusion-collectors-arm64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )

    token_value = "token-arm64"
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.InstallTokenService.validate_and_get_token_data",
        lambda token: {
            "node_id": "node-arm",
            "ip": "10.0.0.1",
            "user": "tester",
            "os": "linux",
            "package_id": str(arm_package.id),
            "cloud_region_id": str(cloud_region.id),
            "organizations": [1],
            "node_name": "node-arm",
            "cpu_architecture": NodeConstants.ARM64_ARCH,
            "remaining_usage": 4,
        },
    )
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.PackageService.resolve_existing_file_path",
        lambda obj: PackageService.build_file_path(obj),
    )

    config = InstallerSessionService.build_session_config(token_value, NodeConstants.ARM64_ARCH)

    assert config["cpu_architecture"] == NodeConstants.ARM64_ARCH
    assert config["storage"]["file_key"] == PackageService.build_file_path(arm_package)
    assert config["installer"]["architecture"] == NodeConstants.ARM64_ARCH
    assert f"/{NodeConstants.ARM64_ARCH}/" in config["installer"]["object_key"]
    assert x86_package.id != arm_package.id


@pytest.mark.django_db
def test_version_upgrade_map_groups_by_architecture():
    PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.0",
        name="fusion-collectors-x86_64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )
    PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.1.0",
        name="fusion-collectors-x86_64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )
    PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.ARM64_ARCH,
        object="Controller",
        version="1.0.5",
        name="fusion-collectors-arm64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )

    versions_map = VersionUpgradeService.get_latest_versions_map(component_type="controller")

    assert versions_map["linux"]["Controller"][NodeConstants.X86_64_ARCH] == "1.1.0"
    assert versions_map["linux"]["Controller"][NodeConstants.ARM64_ARCH] == "1.0.5"


@pytest.mark.django_db
def test_calculate_upgrade_info_uses_architecture_specific_latest_version():
    latest_versions_map = {
        "linux": {
            "Controller": {
                NodeConstants.X86_64_ARCH: "1.2.0",
                NodeConstants.ARM64_ARCH: "1.5.0",
            }
        }
    }

    latest_version, upgradeable = _calculate_upgrade_info(
        current_version="1.4.0",
        component_name="Controller",
        os_type="linux",
        cpu_architecture=NodeConstants.ARM64_ARCH,
        latest_versions_map=latest_versions_map,
    )

    assert latest_version == "1.5.0"
    assert upgradeable is True


@pytest.mark.django_db
def test_discover_controller_version_preserves_existing_version_when_command_returns_empty(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="version-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    controller = Controller.objects.create(
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        name="Controller",
        description="linux x86",
        version_command="cat /opt/fusion-collectors/VERSION",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-version-empty",
        name="node-version-empty",
        ip="10.0.0.20",
        operating_system="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/tmp/config",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    version_record = NodeComponentVersion.objects.create(
        node=node,
        component_type="controller",
        component_id=str(controller.id),
        version="1.0.0",
        latest_version="1.1.0",
        upgradeable=True,
        message="旧版本信息",
        created_by="tester",
        updated_by="tester",
    )

    monkeypatch.setattr(version_discovery.Executor, "execute_local", lambda self, command, timeout=10: "   ")

    all_controllers = [controller]
    controllers_map = {(controller.os, controller.cpu_architecture): controller}
    _discover_controller_version(node, latest_versions_map={}, controllers_map=controllers_map, all_controllers=all_controllers)

    version_record.refresh_from_db()
    assert version_record.version == "1.0.0"
    assert version_record.latest_version == "1.1.0"
    assert version_record.upgradeable is True
    assert version_record.message == "命令执行成功但返回了空结果"
    assert NodeComponentVersion.objects.filter(node=node, component_type="controller").count() == 1


@pytest.mark.django_db
def test_discover_controller_version_reuses_existing_unknown_record_after_success(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="version-region-success",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    controller = Controller.objects.create(
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        name="Controller",
        description="linux x86",
        version_command="cat /opt/fusion-collectors/VERSION",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-version-success",
        name="node-version-success",
        ip="10.0.0.21",
        operating_system="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/tmp/config",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    version_record = NodeComponentVersion.objects.create(
        node=node,
        component_type="controller",
        component_id="unknown",
        version="unknown",
        latest_version="",
        upgradeable=False,
        message="未找到操作系统 linux 对应的控制器配置",
        created_by="tester",
        updated_by="tester",
    )

    monkeypatch.setattr(version_discovery.Executor, "execute_local", lambda self, command, timeout=10: "1.0.0")

    all_controllers = [controller]
    controllers_map = {(controller.os, controller.cpu_architecture): controller}
    _discover_controller_version(
        node,
        latest_versions_map={
            "linux": {
                "Controller": {
                    NodeConstants.X86_64_ARCH: "1.1.0",
                }
            }
        },
        controllers_map=controllers_map,
        all_controllers=all_controllers,
    )

    version_record.refresh_from_db()
    assert version_record.component_id == str(controller.id)
    assert version_record.version == "1.0.0"
    assert version_record.latest_version == "1.1.0"
    assert version_record.upgradeable is True
    assert version_record.message == "版本获取成功"
    assert NodeComponentVersion.objects.filter(node=node, component_type="controller").count() == 1


@pytest.mark.django_db
def test_controller_lookup_can_store_architecture_specific_records():
    linux_x86 = Controller.objects.create(
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        name="Controller",
        description="linux x86",
        version_command="cat /opt/fusion-collectors/VERSION",
        created_by="tester",
        updated_by="tester",
    )
    linux_arm = Controller.objects.create(
        os="linux",
        cpu_architecture=NodeConstants.ARM64_ARCH,
        name="Controller",
        description="linux arm",
        version_command="cat /opt/fusion-collectors/VERSION",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-1",
        name="node-1",
        ip="10.0.0.2",
        operating_system="linux",
        cpu_architecture=NodeConstants.ARM64_ARCH,
        collector_configuration_directory="/tmp/config",
        cloud_region=CloudRegion.objects.create(
            name="region-2",
            introduction="region",
            created_by="tester",
            updated_by="tester",
        ),
        created_by="tester",
        updated_by="tester",
    )

    matched = Controller.objects.filter(
        os=node.operating_system,
        cpu_architecture=node.cpu_architecture,
        name="Controller",
    ).first()

    assert matched is not None
    assert matched.id == linux_arm.id
    assert matched.id != linux_x86.id


@pytest.mark.django_db
def test_install_controller_on_nodes_detects_arch_and_resolves_package(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="install-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    seed_package = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="5.0.0",
        name="fusion-collectors-x86_64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )
    arm_package = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.ARM64_ARCH,
        object="Controller",
        version="5.0.0",
        name="fusion-collectors-arm64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )
    task = installer_tasks.ControllerTask.objects.create(
        cloud_region=cloud_region,
        type="install",
        status="waiting",
        work_node="work-node",
        package_version_id=seed_package.id,
        created_by="tester",
        updated_by="tester",
    )
    aes = AESCryptor()
    task_node = installer_tasks.ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.10",
        node_name="arm-node",
        os="linux",
        organizations=[1],
        port=22,
        username="root",
        password=aes.encode("secret"),
        status="waiting",
    )

    install_call = {}

    def fake_exec_command_to_remote(*args, **kwargs):
        return "aarch64"

    def fake_get_install_command(*args, **kwargs):
        install_call["args"] = args
        install_call["kwargs"] = kwargs
        return "echo install"

    monkeypatch.setattr(installer_tasks, "exec_command_to_remote", fake_exec_command_to_remote)
    monkeypatch.setattr(installer_tasks, "exec_command_to_remote_stream", lambda *args, **kwargs: "")
    monkeypatch.setattr(installer_tasks, "subscribe_lines_sync", lambda *args, **kwargs: (Queue(), lambda: None))
    monkeypatch.setattr(installer_tasks.InstallerService, "get_install_command", fake_get_install_command)
    monkeypatch.setattr(installer_tasks, "_dispatch_or_finalize_controller_task", lambda task_id: None)

    installer_tasks.install_controller_on_nodes(task, [task_node], seed_package)
    task_node.refresh_from_db()

    assert task_node.cpu_architecture == NodeConstants.ARM64_ARCH
    assert task_node.resolved_package_version_id == arm_package.id
    assert install_call["args"][4] == arm_package.id
    assert install_call["kwargs"]["cpu_architecture"] == NodeConstants.ARM64_ARCH


@pytest.mark.django_db
def test_update_node_client_persists_normalized_cpu_architecture(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="sidecar-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    request = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "node-arm",
            "node_details": {
                "ip": "10.0.0.20",
                "operating_system": "Linux",
                "collector_configuration_directory": "/etc/collector",
                "metrics": {},
                "status": {},
                "tags": [f"zone:{cloud_region.id}"],
                "log_file_list": [],
                "architecture": "aarch64",
            },
        },
    )

    response = Sidecar.update_node_client(request, "node-sidecar-arm")
    node = Node.objects.get(id="node-sidecar-arm")

    assert response.status_code == 202
    assert node.cpu_architecture == NodeConstants.ARM64_ARCH
    assert node.operating_system == NodeConstants.LINUX_OS


@pytest.mark.django_db
def test_update_node_client_falls_back_to_install_task_cpu_architecture(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="sidecar-fallback-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    install_task = ControllerTask.objects.create(
        type="install",
        package_version_id=1,
        status="success",
        cloud_region=cloud_region,
        work_node="worker-1",
        created_by="tester",
        updated_by="tester",
    )
    ControllerTaskNode.objects.create(
        task=install_task,
        ip="10.0.0.33",
        os=NodeConstants.LINUX_OS,
        port=22,
        username="tester",
        password="",
        private_key="",
        passphrase="",
        status="success",
        result={},
        cpu_architecture=NodeConstants.X86_64_ARCH,
    )

    request = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "node-fallback-arch",
            "node_details": {
                "ip": "10.0.0.33",
                "operating_system": "Linux",
                "collector_configuration_directory": "/etc/collector",
                "metrics": {},
                "status": {},
                "tags": [f"zone:{cloud_region.id}"],
                "log_file_list": [],
            },
        },
    )

    response = Sidecar.update_node_client(request, "node-sidecar-fallback-arch")
    node = Node.objects.get(id="node-sidecar-fallback-arch")

    assert response.status_code == 202
    assert node.cpu_architecture == NodeConstants.X86_64_ARCH


@pytest.mark.django_db
def test_update_node_client_uses_cpu_architecture_tag_before_task_fallback(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="sidecar-tag-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    install_task = ControllerTask.objects.create(
        type="install",
        package_version_id=1,
        status="success",
        cloud_region=cloud_region,
        work_node="worker-1",
        created_by="tester",
        updated_by="tester",
    )
    ControllerTaskNode.objects.create(
        task=install_task,
        ip="10.0.0.35",
        os=NodeConstants.LINUX_OS,
        port=22,
        username="tester",
        password="",
        private_key="",
        passphrase="",
        status="success",
        result={},
        cpu_architecture=NodeConstants.X86_64_ARCH,
    )

    request = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "node-tag-arch",
            "node_details": {
                "ip": "10.0.0.35",
                "operating_system": "Linux",
                "collector_configuration_directory": "/etc/collector",
                "metrics": {},
                "status": {},
                "tags": [f"zone:{cloud_region.id}", "cpu_architecture:arm64"],
                "log_file_list": [],
            },
        },
    )

    response = Sidecar.update_node_client(request, "node-sidecar-tag-arch")
    node = Node.objects.get(id="node-sidecar-tag-arch")

    assert response.status_code == 202
    assert node.cpu_architecture == NodeConstants.ARM64_ARCH


@pytest.mark.django_db
def test_update_node_client_defaults_container_node_cpu_architecture_to_x86(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="sidecar-container-default-arch-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    request = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "node-container-default-arch",
            "node_details": {
                "ip": "10.0.0.36",
                "operating_system": "Linux",
                "collector_configuration_directory": "/etc/collector",
                "metrics": {},
                "status": {},
                "tags": [
                    f"zone:{cloud_region.id}",
                    f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_CONTAINER}",
                ],
                "log_file_list": [],
            },
        },
    )

    response = Sidecar.update_node_client(request, "node-sidecar-container-default-arch")
    node = Node.objects.get(id="node-sidecar-container-default-arch")

    assert response.status_code == 202
    assert node.node_type == ControllerConstants.NODE_TYPE_CONTAINER
    assert node.cpu_architecture == NodeConstants.X86_64_ARCH


@pytest.mark.django_db
def test_update_node_client_prefers_container_node_cpu_architecture_tag_over_x86_default(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="sidecar-container-tag-arch-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    request = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "node-container-tag-arch",
            "node_details": {
                "ip": "10.0.0.37",
                "operating_system": "Linux",
                "collector_configuration_directory": "/etc/collector",
                "metrics": {},
                "status": {},
                "tags": [
                    f"zone:{cloud_region.id}",
                    f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_CONTAINER}",
                    f"{Sidecar.CPU_ARCHITECTURE_TAG}:arm64",
                ],
                "log_file_list": [],
            },
        },
    )

    response = Sidecar.update_node_client(request, "node-sidecar-container-tag-arch")
    node = Node.objects.get(id="node-sidecar-container-tag-arch")

    assert response.status_code == 202
    assert node.node_type == ControllerConstants.NODE_TYPE_CONTAINER
    assert node.cpu_architecture == NodeConstants.ARM64_ARCH


@pytest.mark.django_db
def test_update_node_client_does_not_overwrite_existing_cpu_architecture_with_empty_value(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="sidecar-keep-arch-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    Node.objects.create(
        id="node-sidecar-keep-arch",
        name="node-sidecar-keep-arch",
        ip="10.0.0.34",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )

    request = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "node-sidecar-keep-arch",
            "node_details": {
                "ip": "10.0.0.34",
                "operating_system": "Linux",
                "collector_configuration_directory": "/etc/collector",
                "metrics": {},
                "status": {},
                "tags": [f"zone:{cloud_region.id}"],
                "log_file_list": [],
            },
        },
    )

    response = Sidecar.update_node_client(request, "node-sidecar-keep-arch")
    node = Node.objects.get(id="node-sidecar-keep-arch")

    assert response.status_code == 202
    assert node.cpu_architecture == NodeConstants.X86_64_ARCH


@pytest.mark.django_db
def test_update_node_client_updates_architecture_without_rebinding_existing_default_configs(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="sidecar-rebind-arch-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    node = Node.objects.create(
        id="node-sidecar-rebind-arch",
        name="node-sidecar-rebind-arch",
        ip="10.0.0.36",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )

    generic_telegraf = Collector.objects.create(
        id="telegraf_linux_rebind_generic",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        controller_default_run=True,
        default_config={"nats": "[[inputs.cpu]]"},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    Collector.objects.create(
        id="telegraf_linux_rebind_arm64",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        executable_path="/opt/telegraf-arm64",
        execute_parameters="--config %s",
        introduction="arm64",
        icon="telegraf",
        controller_default_run=True,
        default_config={"nats": "[[inputs.cpu]]\n  interval = '5s'"},
        tags=[],
        package_name="telegraf-arm64",
        created_by="tester",
        updated_by="tester",
    )

    telegraf_config = CollectorConfiguration.objects.create(
        id="cfg-sidecar-rebind-telegraf",
        name=f"Telegraf-{node.id}",
        collector=generic_telegraf,
        config_template="[[inputs.cpu]]",
        is_pre=True,
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    telegraf_config.nodes.add(node)

    request = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "node-sidecar-rebind-arch",
            "node_details": {
                "ip": "10.0.0.36",
                "operating_system": "Linux",
                "collector_configuration_directory": "/etc/collector",
                "metrics": {},
                "status": {},
                "tags": [f"zone:{cloud_region.id}"],
                "log_file_list": [],
                "architecture": "arm64",
            },
        },
    )

    response = Sidecar.update_node_client(request, node.id)

    node.refresh_from_db()
    telegraf_config.refresh_from_db()

    assert response.status_code == 202
    assert node.cpu_architecture == NodeConstants.ARM64_ARCH
    assert telegraf_config.collector_id == generic_telegraf.id


@pytest.mark.django_db
def test_sidecar_configuration_endpoint_rejects_foreign_configuration_access():
    cloud_region = CloudRegion.objects.create(
        name="sidecar-authz-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    collector = Collector.objects.create(
        id="collector-sidecar-authz-render",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        controller_default_run=True,
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    node_a = Node.objects.create(
        id="node-sidecar-authz-a",
        name="node-sidecar-authz-a",
        ip="10.0.0.41",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    node_b = Node.objects.create(
        id="node-sidecar-authz-b",
        name="node-sidecar-authz-b",
        ip="10.0.0.42",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    foreign_config = CollectorConfiguration.objects.create(
        id="cfg-sidecar-foreign-render",
        name="cfg-sidecar-foreign-render",
        collector=collector,
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    foreign_config.nodes.add(node_b)

    view = OpenSidecarViewSet.as_view({"get": "configuration"})
    request = _build_sidecar_request(
        "get",
        f"/node/sidecar/configurations/render/{node_a.id}/{foreign_config.id}",
        headers=_build_sidecar_auth_header(node_a.id),
    )

    response = view(request, node_id=node_a.id, configuration_id=foreign_config.id)

    assert response.status_code == 404
    assert _json_response_data(response)["error"] == "Configuration not found"


@pytest.mark.django_db
def test_sidecar_env_endpoint_rejects_foreign_configuration_access():
    cloud_region = CloudRegion.objects.create(
        name="sidecar-authz-env-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    collector = Collector.objects.create(
        id="collector-sidecar-authz-env",
        name="TelegrafEnv",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        controller_default_run=True,
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    node_a = Node.objects.create(
        id="node-sidecar-env-a",
        name="node-sidecar-env-a",
        ip="10.0.0.43",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    node_b = Node.objects.create(
        id="node-sidecar-env-b",
        name="node-sidecar-env-b",
        ip="10.0.0.44",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    aes = AESCryptor()
    foreign_config = CollectorConfiguration.objects.create(
        id="cfg-sidecar-foreign-env",
        name="cfg-sidecar-foreign-env",
        collector=collector,
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        env_config={"DB_PASSWORD": aes.encode("secret")},
        created_by="tester",
        updated_by="tester",
    )
    foreign_config.nodes.add(node_b)

    view = OpenSidecarViewSet.as_view({"get": "configuration_env"})
    request = _build_sidecar_request(
        "get",
        f"/node/sidecar/env_config/{node_a.id}/{foreign_config.id}",
        headers=_build_sidecar_auth_header(node_a.id),
    )

    response = view(request, node_id=node_a.id, configuration_id=foreign_config.id)

    assert response.status_code == 404
    assert _json_response_data(response)["error"] == "Configuration not found"


@pytest.mark.django_db
def test_sidecar_configuration_endpoint_rejects_old_configuration_after_unbind():
    cloud_region = CloudRegion.objects.create(
        name="sidecar-unbind-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    collector = Collector.objects.create(
        id="collector-sidecar-unbind",
        name="TelegrafUnbind",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        controller_default_run=True,
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-sidecar-unbind",
        name="node-sidecar-unbind",
        ip="10.0.0.45",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    config = CollectorConfiguration.objects.create(
        id="cfg-sidecar-unbind",
        name="cfg-sidecar-unbind",
        collector=collector,
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    config.nodes.add(node)

    view = OpenSidecarViewSet.as_view({"get": "configuration"})
    headers = _build_sidecar_auth_header(node.id)
    first_request = _build_sidecar_request(
        "get",
        f"/node/sidecar/configurations/render/{node.id}/{config.id}",
        headers=headers,
    )
    first_response = view(first_request, node_id=node.id, configuration_id=config.id)
    assert first_response.status_code == 200
    cached_etag = first_response["ETag"]

    config.nodes.remove(node)

    second_request = _build_sidecar_request(
        "get",
        f"/node/sidecar/configurations/render/{node.id}/{config.id}",
        headers={**headers, "HTTP_IF_NONE_MATCH": cached_etag},
    )
    second_response = view(second_request, node_id=node.id, configuration_id=config.id)

    assert second_response.status_code == 404
    assert _json_response_data(second_response)["error"] == "Configuration not found"


@pytest.mark.django_db
def test_sidecar_render_304_path_checks_binding_without_full_object_fetch(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="sidecar-304-query-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    collector = Collector.objects.create(
        id="collector-sidecar-304-query",
        name="Telegraf304",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        controller_default_run=True,
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-sidecar-304-query",
        name="node-sidecar-304-query",
        ip="10.0.0.46",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    config = CollectorConfiguration.objects.create(
        id="cfg-sidecar-304-query",
        name="cfg-sidecar-304-query",
        collector=collector,
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    config.nodes.add(node)

    assignment_checks = []
    object_fetches = []
    cache_store = {}

    original_bound_check = Sidecar.configuration_bound_to_node
    original_bound_assignment = Sidecar.get_bound_assignment_or_404

    def wrapped_bound_check(node_id, configuration_id):
        assignment_checks.append((node_id, configuration_id))
        return original_bound_check(node_id, configuration_id)

    def wrapped_bound_assignment(*args, **kwargs):
        object_fetches.append((args, kwargs))
        return original_bound_assignment(*args, **kwargs)

    monkeypatch.setattr(Sidecar, "configuration_bound_to_node", wrapped_bound_check)
    monkeypatch.setattr(Sidecar, "get_bound_assignment_or_404", wrapped_bound_assignment)
    monkeypatch.setattr(
        "apps.node_mgmt.services.sidecar.cache",
        SimpleNamespace(
            get=lambda key: cache_store.get(key),
            set=lambda key, value, timeout: cache_store.__setitem__(key, value),
        ),
    )

    view = OpenSidecarViewSet.as_view({"get": "configuration"})
    headers = _build_sidecar_auth_header(node.id)
    first_request = _build_sidecar_request(
        "get",
        f"/node/sidecar/configurations/render/{node.id}/{config.id}",
        headers=headers,
    )
    first_response = view(first_request, node_id=node.id, configuration_id=config.id)
    assert first_response.status_code == 200

    second_request = _build_sidecar_request(
        "get",
        f"/node/sidecar/configurations/render/{node.id}/{config.id}",
        headers=headers,
    )
    second_request.META["HTTP_IF_NONE_MATCH"] = first_response["ETag"]
    second_response = view(second_request, node_id=node.id, configuration_id=config.id)

    assert second_response.status_code == 304
    assert assignment_checks == [(node.id, config.id)]
    assert len(object_fetches) == 1


@pytest.mark.django_db
def test_sidecar_configuration_env_reuses_cached_cloud_region_env(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="sidecar-env-cache-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    collector = Collector.objects.create(
        id="collector-sidecar-env-cache",
        name="TelegrafEnvCache",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        controller_default_run=True,
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-sidecar-env-cache",
        name="node-sidecar-env-cache",
        ip="10.0.0.47",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    aes = AESCryptor()
    config = CollectorConfiguration.objects.create(
        id="cfg-sidecar-env-cache",
        name="cfg-sidecar-env-cache",
        collector=collector,
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        env_config={"DB_PASSWORD": aes.encode("cfg-secret")},
        created_by="tester",
        updated_by="tester",
    )
    config.nodes.add(node)
    SidecarEnv.objects.create(
        key=NodeConstants.NATS_PASSWORD_KEY,
        value=aes.encode("region-secret"),
        type="secret",
        cloud_region=cloud_region,
    )

    original_env_loader = RegionService.get_cloud_region_envconfig
    env_loader_calls = []

    def wrapped_env_loader(cloud_region_id, keys=None):
        env_loader_calls.append((cloud_region_id, tuple(keys) if keys is not None else None))
        return original_env_loader(cloud_region_id, keys=keys)

    monkeypatch.setattr(RegionService, "get_cloud_region_envconfig", wrapped_env_loader)

    view = OpenSidecarViewSet.as_view({"get": "configuration_env"})
    request = _build_sidecar_request(
        "get",
        f"/node/sidecar/env_config/{node.id}/{config.id}",
        headers=_build_sidecar_auth_header(node.id),
    )

    response = view(request, node_id=node.id, configuration_id=config.id)

    assert response.status_code == 200
    payload = _json_response_data(response)
    assert payload["env_config"][NodeConstants.NATS_PASSWORD_KEY] == "region-secret"
    assert payload["env_config"]["DB_PASSWORD"] == "cfg-secret"
    assert env_loader_calls == [(cloud_region.id, tuple(NodeConstants.CLOUD_REGION_NATS_SECRET_KEYS))]


@pytest.mark.django_db
def test_sidecar_configuration_env_ignores_unrelated_bad_cloud_region_secret(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="sidecar-env-cache-bad-secret-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    collector = Collector.objects.create(
        id="collector-sidecar-env-cache-bad-secret",
        name="TelegrafEnvCacheBadSecret",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        controller_default_run=True,
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-sidecar-env-cache-bad-secret",
        name="node-sidecar-env-cache-bad-secret",
        ip="10.0.0.48",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    aes = AESCryptor()
    config = CollectorConfiguration.objects.create(
        id="cfg-sidecar-env-cache-bad-secret",
        name="cfg-sidecar-env-cache-bad-secret",
        collector=collector,
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        env_config={"DB_PASSWORD": aes.encode("cfg-secret")},
        created_by="tester",
        updated_by="tester",
    )
    config.nodes.add(node)
    SidecarEnv.objects.create(
        key=NodeConstants.NATS_PASSWORD_KEY,
        value=aes.encode("region-secret"),
        type="secret",
        cloud_region=cloud_region,
    )
    SidecarEnv.objects.create(
        key="UNRELATED_SECRET",
        value="not-valid-ciphertext",
        type="secret",
        cloud_region=cloud_region,
    )

    decode_calls = []
    original_decode_rows = RegionService._decode_env_rows

    def wrapped_decode_rows(env_rows, keys=None):
        decode_calls.append(set(keys) if keys is not None else None)
        return original_decode_rows(env_rows, keys=keys)

    monkeypatch.setattr(RegionService, "_decode_env_rows", wrapped_decode_rows)

    view = OpenSidecarViewSet.as_view({"get": "configuration_env"})
    request = _build_sidecar_request(
        "get",
        f"/node/sidecar/env_config/{node.id}/{config.id}",
        headers=_build_sidecar_auth_header(node.id),
    )

    response = view(request, node_id=node.id, configuration_id=config.id)

    assert response.status_code == 200
    payload = _json_response_data(response)
    assert payload["env_config"][NodeConstants.NATS_PASSWORD_KEY] == "region-secret"
    assert payload["env_config"]["DB_PASSWORD"] == "cfg-secret"
    assert decode_calls == [set(NodeConstants.CLOUD_REGION_NATS_SECRET_KEYS)]


@pytest.mark.django_db
def test_create_default_config_for_empty_architecture_skips_arm64_collectors(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="sidecar-empty-arch-default-config",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-empty-arch-default-config",
        name="node-empty-arch-default-config",
        ip="10.0.0.31",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    monkeypatch.setattr(Sidecar, "get_cloud_region_envconfig", lambda _node: {"SIDECAR_INPUT_MODE": "nats"})

    Collector.objects.create(
        id="telegraf_linux_default_generic",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        controller_default_run=True,
        default_config={"nats": "[[inputs.cpu]]"},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    Collector.objects.create(
        id="filebeat_linux_default_x86",
        name="Filebeat",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        executable_path="/opt/filebeat",
        execute_parameters="-c %s",
        introduction="x86_64",
        icon="filebeat",
        controller_default_run=True,
        default_config={"nats": "filebeat.inputs: []"},
        tags=[],
        package_name="filebeat",
        created_by="tester",
        updated_by="tester",
    )
    Collector.objects.create(
        id="vector_linux_default_arm64",
        name="Vector",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        executable_path="/opt/vector",
        execute_parameters="--config %s",
        introduction="arm64",
        icon="vector",
        controller_default_run=True,
        default_config={"nats": "sources: {}"},
        tags=[],
        package_name="vector",
        created_by="tester",
        updated_by="tester",
    )

    Sidecar.create_default_config(node, [])

    collector_ids = set(CollectorConfiguration.objects.filter(nodes=node).values_list("collector_id", flat=True))
    assert "telegraf_linux_default_generic" in collector_ids
    assert "filebeat_linux_default_x86" in collector_ids
    assert "vector_linux_default_arm64" not in collector_ids


@pytest.mark.django_db
def test_create_default_config_for_arm64_node_keeps_arm64_collectors(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="sidecar-arm64-default-config",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-arm64-default-config",
        name="node-arm64-default-config",
        ip="10.0.0.32",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    monkeypatch.setattr(Sidecar, "get_cloud_region_envconfig", lambda _node: {"SIDECAR_INPUT_MODE": "nats"})

    Collector.objects.create(
        id="telegraf_linux_arm64_default",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        executable_path="/opt/telegraf-arm64",
        execute_parameters="--config %s",
        introduction="arm64",
        icon="telegraf",
        controller_default_run=True,
        default_config={"nats": "[[inputs.cpu]]"},
        tags=[],
        package_name="telegraf-arm64",
        created_by="tester",
        updated_by="tester",
    )
    Collector.objects.create(
        id="telegraf_linux_legacy_x86_default",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="legacy x86",
        icon="telegraf",
        controller_default_run=True,
        default_config={"nats": "[[inputs.cpu]]"},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )

    Sidecar.create_default_config(node, [])

    collector_ids = set(CollectorConfiguration.objects.filter(nodes=node).values_list("collector_id", flat=True))
    assert "telegraf_linux_arm64_default" in collector_ids
    assert "telegraf_linux_legacy_x86_default" not in collector_ids


@pytest.mark.django_db
def test_repair_node_config_rebinds_defaults_by_node_architecture(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="repair-node-config-arch-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    monkeypatch.setattr(Sidecar, "get_cloud_region_envconfig", lambda _node: {"SIDECAR_INPUT_MODE": "nats"})

    queued_nodes = []

    class _FakeDelay:
        @staticmethod
        def delay(node_id):
            queued_nodes.append(node_id)

    monkeypatch.setattr(
        "apps.node_mgmt.management.commands.repair_node_config.converge_collector_action_task_for_node",
        _FakeDelay,
    )

    node = Node.objects.create(
        id="node-repair-arch-config",
        name="node-repair-arch-config",
        ip="10.0.0.37",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )

    x86_telegraf = Collector.objects.create(
        id="telegraf_linux_repair_x86",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        executable_path="/opt/telegraf-x86",
        execute_parameters="--config %s",
        introduction="x86_64",
        icon="telegraf",
        controller_default_run=True,
        default_config={"nats": "[[inputs.cpu]]"},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    arm_telegraf = Collector.objects.create(
        id="telegraf_linux_repair_arm",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        executable_path="/opt/telegraf-arm64",
        execute_parameters="--config %s",
        introduction="arm64",
        icon="telegraf",
        controller_default_run=True,
        default_config={"nats": "[[inputs.cpu]]\n  interval = '10s'"},
        tags=[],
        package_name="telegraf-arm64",
        created_by="tester",
        updated_by="tester",
    )

    config = CollectorConfiguration.objects.create(
        id="cfg-repair-node-config-arch",
        name=f"Telegraf-{node.id}",
        collector=arm_telegraf,
        config_template="[[inputs.cpu]]\n  interval = '10s'",
        is_pre=True,
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    config.nodes.add(node)

    out = StringIO()
    call_command("repair_node_config", stdout=out)

    config.refresh_from_db()
    assert config.collector_id == x86_telegraf.id
    assert queued_nodes == [node.id]


@pytest.mark.django_db
def test_installer_manifest_endpoint_returns_architecture_map():
    factory = APIRequestFactory()
    view = InstallerViewSet.as_view({"get": "manifest"})
    request = factory.get("/node_mgmt/api/installer/manifest/")
    force_authenticate(request, user=_build_admin_user())

    response = view(request)

    assert response.status_code == 200
    payload = _json_response_data(response)["data"]
    assert NodeConstants.LINUX_OS in payload["artifacts"]
    assert NodeConstants.ARM64_ARCH in payload["artifacts"][NodeConstants.LINUX_OS]
    assert payload["artifacts"][NodeConstants.LINUX_OS][NodeConstants.ARM64_ARCH]["cpu_architecture"] == NodeConstants.ARM64_ARCH


@pytest.mark.django_db
def test_installer_metadata_endpoint_uses_arch_query_param():
    factory = APIRequestFactory()
    view = InstallerViewSet.as_view({"get": "metadata"})
    request = factory.get("/node_mgmt/api/installer/metadata/linux/", {"arch": "arm64"})
    force_authenticate(request, user=_build_admin_user())

    response = view(request, target_os="linux")

    assert response.status_code == 200
    payload = _json_response_data(response)["data"]
    assert payload["cpu_architecture"] == NodeConstants.ARM64_ARCH
    assert f"/{NodeConstants.ARM64_ARCH}/" in payload["object_key"]


@pytest.mark.django_db
def test_installer_download_endpoint_passes_architecture_to_service(monkeypatch):
    captured = {}
    factory = APIRequestFactory()
    view = InstallerViewSet.as_view({"get": "linux_download"})

    def fake_download_linux_installer(arch):
        captured["arch"] = arch
        return b"installer-binary", None

    monkeypatch.setattr(InstallerService, "download_linux_installer", fake_download_linux_installer)
    request = factory.get("/node_mgmt/api/installer/linux/download/", {"arch": "arm64"})
    force_authenticate(request, user=_build_admin_user())

    response = view(request)

    assert response.status_code == 200
    assert captured["arch"] == NodeConstants.ARM64_ARCH


@pytest.mark.django_db
def test_open_api_installer_session_uses_arch_query_param(monkeypatch):
    factory = APIRequestFactory()
    view = OpenSidecarViewSet.as_view({"get": "installer_session"})

    monkeypatch.setattr(
        "apps.node_mgmt.views.sidecar.InstallTokenService.validate_and_get_token_data",
        lambda token: {
            "node_id": "node-1",
            "ip": "10.0.0.1",
            "user": "tester",
            "os": NodeConstants.LINUX_OS,
            "package_id": "1",
            "cloud_region_id": "1",
            "organizations": [1],
            "node_name": "node-1",
            "cpu_architecture": NodeConstants.ARM64_ARCH,
            "remaining_usage": 3,
        },
    )
    monkeypatch.setattr(
        InstallerSessionService,
        "build_session_config",
        lambda token, arch="", token_data=None: {
            "node_id": "node-1",
            "remaining_usage": 3,
            "cpu_architecture": arch,
            "installer": {"architecture": arch},
        },
    )
    request = factory.get("/node_mgmt/open_api/installer/session", {"token": "abc", "arch": "arm64"})

    response = view(request)

    assert response.status_code == 200
    assert json.loads(response.content)["cpu_architecture"] == NodeConstants.ARM64_ARCH
    assert response["X-Token-Remaining-Usage"] == "3"


@pytest.mark.django_db
def test_open_api_installer_session_consumes_token_once(monkeypatch):
    factory = APIRequestFactory()
    view = OpenSidecarViewSet.as_view({"get": "installer_session"})
    calls = {"count": 0}

    def fake_validate(token):
        calls["count"] += 1
        return {
            "node_id": "node-1",
            "ip": "10.0.0.1",
            "user": "tester",
            "os": NodeConstants.LINUX_OS,
            "package_id": "1",
            "cloud_region_id": "1",
            "organizations": [1],
            "node_name": "node-1",
            "cpu_architecture": NodeConstants.ARM64_ARCH,
            "remaining_usage": 4,
        }

    monkeypatch.setattr(
        "apps.node_mgmt.views.sidecar.InstallTokenService.validate_and_get_token_data",
        fake_validate,
    )
    monkeypatch.setattr(
        InstallerSessionService,
        "build_session_config",
        lambda token, arch="", token_data=None: {
            "node_id": token_data["node_id"],
            "remaining_usage": token_data["remaining_usage"],
            "cpu_architecture": arch or token_data["cpu_architecture"],
            "installer": {"architecture": arch or token_data["cpu_architecture"]},
        },
    )

    request = factory.get("/node_mgmt/open_api/installer/session", {"token": "abc", "arch": "arm64"})

    response = view(request)

    assert response.status_code == 200
    assert calls["count"] == 1


@pytest.mark.django_db
def test_open_api_linux_download_prefers_query_arch_over_token(monkeypatch):
    factory = APIRequestFactory()
    view = OpenSidecarViewSet.as_view({"get": "linux_download_installer"})
    captured = {}

    monkeypatch.setattr(
        "apps.node_mgmt.views.sidecar.InstallTokenService.validate_and_get_token_data",
        lambda token: {"os": "linux", "cpu_architecture": NodeConstants.X86_64_ARCH},
    )

    def fake_download_linux_installer(arch):
        captured["arch"] = arch
        return b"installer-binary", None

    monkeypatch.setattr(InstallerService, "download_linux_installer", fake_download_linux_installer)
    request = factory.get("/node_mgmt/open_api/installer/linux/download", {"token": "abc", "arch": "arm64"})

    response = view(request)

    assert response.status_code == 200
    assert captured["arch"] == NodeConstants.ARM64_ARCH


@pytest.mark.django_db
def test_open_api_linux_bootstrap_contains_arch_detection_and_routed_urls(monkeypatch):
    factory = APIRequestFactory()
    view = OpenSidecarViewSet.as_view({"get": "linux_bootstrap"})

    monkeypatch.setattr(
        "apps.node_mgmt.views.sidecar.InstallTokenService.validate_and_get_token_data",
        lambda token: {"cpu_architecture": NodeConstants.ARM64_ARCH},
    )
    monkeypatch.setattr(
        InstallerSessionService,
        "build_session_config",
        lambda token, arch="", token_data=None: {
            "installer": {"filename": "bklite-controller-installer"},
            "install_dir": "/opt/fusion-collectors",
            "server_url": "https://example.com/api/v1/node_mgmt/open_api/node",
        },
    )
    request = factory.get("/node_mgmt/open_api/installer/linux_bootstrap", {"token": "abc"})

    response = view(request)
    content = response.content.decode("utf-8")

    assert response.status_code == 200
    assert 'DETECTED_ARCH="$(uname -m' in content
    assert 'EXPECTED_ARCH="arm64"' in content
    assert "installer/linux/download?token=abc&arch=$DETECTED_ARCH" in content
    assert "installer/session?token=abc&arch=$DETECTED_ARCH" in content


@pytest.mark.django_db
def test_open_api_linux_bootstrap_consumes_token_once(monkeypatch):
    factory = APIRequestFactory()
    view = OpenSidecarViewSet.as_view({"get": "linux_bootstrap"})
    calls = {"count": 0}

    def fake_validate(token):
        calls["count"] += 1
        return {"cpu_architecture": NodeConstants.ARM64_ARCH}

    monkeypatch.setattr(
        "apps.node_mgmt.views.sidecar.InstallTokenService.validate_and_get_token_data",
        fake_validate,
    )
    monkeypatch.setattr(
        InstallerSessionService,
        "build_session_config",
        lambda token, arch="", token_data=None: {
            "installer": {"filename": "bklite-controller-installer"},
            "install_dir": "/opt/fusion-collectors",
            "server_url": "https://example.com/api/v1/node_mgmt/open_api/node",
        },
    )

    request = factory.get("/node_mgmt/open_api/installer/linux_bootstrap", {"token": "abc"})

    response = view(request)

    assert response.status_code == 200
    assert calls["count"] == 1


@pytest.mark.django_db
def test_get_install_command_view_passes_cpu_architecture(monkeypatch):
    factory = APIRequestFactory()
    view = InstallerViewSet.as_view({"post": "get_install_command"})
    captured = {}

    def fake_get_install_command(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "curl command"

    monkeypatch.setattr(InstallerService, "get_install_command", fake_get_install_command)

    request = factory.post(
        "/node_mgmt/api/installer/get_install_command/",
        {
            "ip": "10.0.0.30",
            "node_id": "node-30",
            "os": "linux",
            "package_id": 1,
            "cloud_region_id": 1,
            "organizations": [1],
            "node_name": "node-30",
            "cpu_architecture": "arm64",
        },
        format="json",
    )
    force_authenticate(request, user=_build_admin_user())

    response = view(request)

    assert response.status_code == 200
    assert _json_response_data(response)["data"] == "curl command"
    assert captured["kwargs"]["cpu_architecture"] == NodeConstants.ARM64_ARCH


@pytest.mark.django_db
def test_controller_manual_install_includes_normalized_cpu_architecture():
    factory = APIRequestFactory()
    view = InstallerViewSet.as_view({"post": "controller_manual_install"})
    request = factory.post(
        "/node_mgmt/api/installer/controller/manual_install/",
        {
            "cloud_region_id": 1,
            "os": NodeConstants.LINUX_OS,
            "cpu_architecture": "aarch64",
            "package_id": 1,
            "nodes": [
                {
                    "ip": "10.0.0.11",
                    "node_id": "node-11",
                    "node_name": "linux-arm-node",
                    "organizations": [1],
                }
            ],
        },
        format="json",
    )
    force_authenticate(request, user=_build_admin_user())

    response = view(request)

    assert response.status_code == 200
    payload = _json_response_data(response)["data"]
    assert payload[0]["cpu_architecture"] == NodeConstants.ARM64_ARCH


@pytest.mark.django_db
def test_controller_manual_install_rejects_missing_cpu_architecture():
    factory = APIRequestFactory()
    view = InstallerViewSet.as_view({"post": "controller_manual_install"})
    request = factory.post(
        "/node_mgmt/api/installer/controller/manual_install/",
        {
            "cloud_region_id": 1,
            "os": NodeConstants.LINUX_OS,
            "cpu_architecture": "",
            "package_id": 1,
            "nodes": [
                {
                    "ip": "10.0.0.12",
                    "node_id": "node-12",
                    "node_name": "linux-node",
                    "organizations": [1],
                }
            ],
        },
        format="json",
    )
    force_authenticate(request, user=_build_admin_user())

    response = view(request)

    assert response.status_code == 400


@pytest.mark.django_db
def test_controller_install_view_rejects_windows_arm64_payload():
    factory = APIRequestFactory()
    view = InstallerViewSet.as_view({"post": "controller_install"})
    request = factory.post(
        "/node_mgmt/api/installer/controller/install/",
        {
            "cloud_region_id": 1,
            "work_node": "worker-1",
            "package_id": 1,
            "cpu_architecture": "arm64",
            "nodes": [
                {
                    "ip": "10.0.0.40",
                    "node_name": "windows-arm",
                    "os": NodeConstants.WINDOWS_OS,
                    "organizations": [1],
                    "port": 22,
                    "username": "root",
                    "password": "secret",
                    "private_key": "",
                    "passphrase": "",
                }
            ],
        },
        format="json",
    )
    force_authenticate(request, user=_build_admin_user())

    with pytest.raises(BaseAppException, match="Unsupported CPU architecture for os=windows"):
        view(request)


@pytest.mark.django_db
def test_package_list_filters_controller_versions_by_exact_architecture():
    PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.0",
        name="controller-x86_64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )
    arm_package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        object="Controller",
        version="1.0.0",
        name="controller-arm64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )

    queryset = PackageVersion.objects.filter(type="controller", object="Controller", os=NodeConstants.LINUX_OS)
    filtered = PackageVersionFilter(
        data={
            "type": "controller",
            "object": "Controller",
            "os": NodeConstants.LINUX_OS,
            "cpu_architecture": "aarch64",
        },
        queryset=queryset,
    ).qs

    assert list(filtered.values_list("id", flat=True)) == [arm_package.id]


@pytest.mark.django_db
def test_package_list_treats_legacy_empty_arch_controller_as_x86_64():
    legacy_package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.LINUX_OS,
        cpu_architecture="",
        object="Controller",
        version="0.9.0",
        name="controller-legacy.zip",
        created_by="tester",
        updated_by="tester",
    )
    x86_package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.0",
        name="controller-x86_64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )

    queryset = PackageVersion.objects.filter(type="controller", object="Controller", os=NodeConstants.LINUX_OS)
    filtered = PackageVersionFilter(
        data={
            "type": "controller",
            "object": "Controller",
            "os": NodeConstants.LINUX_OS,
            "cpu_architecture": NodeConstants.X86_64_ARCH,
        },
        queryset=queryset,
    ).qs

    assert set(filtered.values_list("id", flat=True)) == {x86_package.id, legacy_package.id}


@pytest.mark.django_db
def test_package_version_serializer_exposes_normalized_cpu_architecture():
    package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.LINUX_OS,
        cpu_architecture="amd64",
        object="Controller",
        version="1.0.1",
        name="fusion-collectors-linux-amd64.zip",
        created_by="tester",
        updated_by="tester",
    )

    data = PackageVersionSerializer(package).data

    assert data["cpu_architecture"] == NodeConstants.X86_64_ARCH


@pytest.mark.django_db
def test_package_version_serializer_treats_legacy_empty_arch_controller_as_x86_64():
    package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.LINUX_OS,
        cpu_architecture="",
        object="Controller",
        version="1.0.1",
        name="fusion-collectors-linux-legacy.zip",
        created_by="tester",
        updated_by="tester",
    )

    data = PackageVersionSerializer(package).data

    assert data["cpu_architecture"] == NodeConstants.X86_64_ARCH


@pytest.mark.django_db
def test_install_controller_requires_cpu_architecture():
    cloud_region = CloudRegion.objects.create(
        name="installer-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.0",
        name="fusion-collectors.tar.gz",
        created_by="tester",
        updated_by="tester",
    )

    with pytest.raises(BaseAppException, match="Missing or unsupported CPU architecture"):
        InstallerService.install_controller(
            cloud_region.id,
            "work-node",
            package.id,
            [
                {
                    "ip": "10.0.0.13",
                    "node_name": "linux-node",
                    "os": NodeConstants.LINUX_OS,
                    "organizations": [1],
                    "port": 22,
                    "username": "root",
                    "password": "secret",
                    "private_key": "",
                    "passphrase": "",
                }
            ],
            "",
        )


def test_installer_init_command_supports_cpu_architecture(tmp_path, monkeypatch):
    uploaded = {}
    file_path = tmp_path / "bklite-controller-installer"
    file_path.write_bytes(b"binary")

    async def fake_upload_file_to_s3(file, s3_file_path):
        uploaded["path"] = s3_file_path
        uploaded["name"] = file.name

    monkeypatch.setattr("apps.node_mgmt.management.commands.installer_init.upload_file_to_s3", fake_upload_file_to_s3)

    InstallerInitCommand().handle(
        os="linux",
        cpu_architecture=NodeConstants.ARM64_ARCH,
        file_path=str(file_path),
    )

    assert uploaded["path"].endswith("installer/linux/arm64/bklite-controller-installer")


@pytest.mark.django_db
def test_package_init_commands_accept_cpu_architecture(monkeypatch, tmp_path):
    captured = []

    def fake_package_version_upload(package_type, options):
        captured.append((package_type, options["cpu_architecture"], options.get("force_upload", False)))

    monkeypatch.setattr(
        "apps.node_mgmt.management.commands.controller_package_init.package_version_upload",
        fake_package_version_upload,
    )
    monkeypatch.setattr(
        "apps.node_mgmt.management.commands.collector_package_init.package_version_upload",
        fake_package_version_upload,
    )

    ControllerPackageInitCommand().handle(
        os="linux",
        object="Controller",
        pk_version="1.0.0",
        file_path=str(tmp_path / "controller.tar.gz"),
        cpu_architecture=NodeConstants.ARM64_ARCH,
    )
    CollectorPackageInitCommand().handle(
        os="linux",
        object="SomeCollector",
        pk_version="1.0.0",
        file_path=str(tmp_path / "collector.tar.gz"),
        cpu_architecture=NodeConstants.X86_64_ARCH,
    )

    assert captured == [
        ("controller", NodeConstants.ARM64_ARCH, False),
        ("collector", NodeConstants.X86_64_ARCH, False),
    ]


@pytest.mark.django_db
def test_verify_architecture_rollout_succeeds_when_required_artifacts_exist(monkeypatch, capsys):
    PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="9.9.9",
        name="fusion-collectors-x86_64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )
    PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.ARM64_ARCH,
        object="Controller",
        version="9.9.9",
        name="fusion-collectors-arm64.tar.gz",
        created_by="tester",
        updated_by="tester",
    )

    async def fake_list_s3_files():
        return [
            "installer/windows/x86_64/bklite-controller-installer.exe",
            "installer/linux/x86_64/bklite-controller-installer",
            "installer/linux/arm64/bklite-controller-installer",
        ]

    monkeypatch.setattr(
        "apps.node_mgmt.management.commands.verify_architecture_rollout.list_s3_files",
        fake_list_s3_files,
    )

    VerifyArchitectureRolloutCommand().handle(package_version="9.9.9")
    output = capsys.readouterr().out

    assert "Linux ARM64 controller package present: yes" in output
    assert "Installer artifacts present" in output


@pytest.mark.django_db
def test_package_service_resolves_legacy_object_path(monkeypatch):
    package_obj = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.1",
        name="fusion-collectors-linux-amd64.zip",
        created_by="tester",
        updated_by="tester",
    )

    class DummyStore:
        async def get_info(self, key):
            if key == "linux/Controller/1.0.1/fusion-collectors-linux-amd64.zip":
                return SimpleNamespace(size=1, description="fusion-collectors-linux-amd64.zip")
            raise __import__("nats.js.errors", fromlist=["ObjectNotFoundError"]).ObjectNotFoundError()

    class DummyJetstream:
        object_store = DummyStore()

        async def connect(self):
            return None

        async def close(self):
            return None

    monkeypatch.setattr("apps.rpc.jetstream.JetStreamService", DummyJetstream)

    resolved = PackageService.resolve_existing_file_path(package_obj)

    assert resolved == "linux/Controller/1.0.1/fusion-collectors-linux-amd64.zip"


@pytest.mark.django_db
def test_package_service_delete_file_tolerates_legacy_only(monkeypatch):
    package_obj = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.1",
        name="fusion-collectors-linux-amd64.zip",
        created_by="tester",
        updated_by="tester",
    )
    deleted = []
    from nats.js.errors import ObjectNotFoundError

    async def fake_delete(path):
        if path == "linux/x86_64/Controller/1.0.1/fusion-collectors-linux-amd64.zip":
            raise ObjectNotFoundError()
        deleted.append(path)

    monkeypatch.setattr("apps.node_mgmt.services.package.delete_s3_file", fake_delete)

    assert PackageService.delete_file(package_obj) is True
    assert deleted == ["linux/Controller/1.0.1/fusion-collectors-linux-amd64.zip"]


@pytest.mark.django_db
def test_installer_session_uses_existing_legacy_file_key(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="test-region-legacy",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    SidecarEnv.objects.create(key=NodeConstants.SERVER_URL_KEY, value="https://example.com", type="text", cloud_region=cloud_region)
    SidecarEnv.objects.create(key=NodeConstants.NATS_SERVERS_KEY, value="nats://127.0.0.1:4222", type="text", cloud_region=cloud_region)
    SidecarEnv.objects.create(key="NATS_ADMIN_USERNAME", value="admin", type="text", cloud_region=cloud_region)
    SidecarEnv.objects.create(key=NodeConstants.NATS_ADMIN_PASSWORD_KEY, value="password", type="text", cloud_region=cloud_region)

    package_obj = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.1",
        name="fusion-collectors-linux-amd64.zip",
        created_by="tester",
        updated_by="tester",
    )

    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.InstallTokenService.validate_and_get_token_data",
        lambda token: {
            "package_id": package_obj.id,
            "cloud_region_id": cloud_region.id,
            "ip": "10.0.0.1",
            "user": "admin",
            "node_id": "node-1",
            "node_name": "node-1",
            "os": "linux",
            "remaining_usage": 1,
            "organizations": [1],
            "cpu_architecture": NodeConstants.X86_64_ARCH,
        },
    )
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.generate_node_token",
        lambda *args, **kwargs: "sidecar-token",
    )
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.PackageService.resolve_existing_file_path",
        lambda obj: "linux/Controller/1.0.1/fusion-collectors-linux-amd64.zip",
    )

    config = InstallerSessionService.build_session_config("token")

    assert config["storage"]["file_key"] == "linux/Controller/1.0.1/fusion-collectors-linux-amd64.zip"
    assert config["package"]["file_key"] == "linux/Controller/1.0.1/fusion-collectors-linux-amd64.zip"


@pytest.mark.django_db
def test_package_version_upload_force_reuploads_existing_version(monkeypatch, tmp_path):
    PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.1",
        name="old.zip",
        created_by="tester",
        updated_by="tester",
    )
    uploaded = {}
    file_path = tmp_path / "fusion-collectors-linux-amd64.zip"
    file_path.write_bytes(b"payload")

    def fake_upload(file, data):
        uploaded["name"] = file.name
        uploaded["path"] = PackageService.build_file_path(SimpleNamespace(**data))

    monkeypatch.setattr("apps.node_mgmt.management.utils.PackageService.upload_file", fake_upload)

    from apps.node_mgmt.management.utils import package_version_upload

    package_version_upload(
        "controller",
        {
            "os": "linux",
            "object": "Controller",
            "cpu_architecture": NodeConstants.X86_64_ARCH,
            "pk_version": "1.0.1",
            "file_path": str(file_path),
            "force_upload": True,
        },
    )

    assert uploaded["name"] == "fusion-collectors-linux-amd64.zip"
    assert uploaded["path"] == "linux/x86_64/Controller/1.0.1/fusion-collectors-linux-amd64.zip"


@pytest.mark.django_db
def test_backfill_package_storage_paths_dry_run_reports_legacy_copy(monkeypatch, capsys):
    package_obj = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.1",
        name="fusion-collectors-linux-amd64.zip",
        created_by="tester",
        updated_by="tester",
    )

    async def fake_inspect(obj):
        return False, True, PackageService.build_file_path(obj), PackageService.build_legacy_file_path(obj)

    monkeypatch.setattr(BackfillPackageStoragePathsCommand, "_inspect_paths", staticmethod(fake_inspect))

    BackfillPackageStoragePathsCommand().handle(
        package_type="controller", os_name="", object_name="", package_version="", cpu_architecture="", apply=False
    )
    output = capsys.readouterr().out

    expected_output = (
        f"[dry-run] {package_obj.id}: copy linux/Controller/1.0.1/fusion-collectors-linux-amd64.zip "
        "-> linux/x86_64/Controller/1.0.1/fusion-collectors-linux-amd64.zip"
    )
    assert expected_output in output


@pytest.mark.django_db
def test_definition_loader_merges_enterprise_overlay(tmp_path):
    community_dir = tmp_path / "community"
    enterprise_dir = tmp_path / "enterprise"
    community_dir.mkdir(parents=True)
    enterprise_dir.mkdir(parents=True)

    (community_dir / "builtin.json").write_text(
        json.dumps(
            [
                {
                    "id": "controller_linux",
                    "os": "linux",
                    "cpu_architecture": "x86_64",
                    "name": "Controller",
                    "description": "community",
                    "version_command": "cat /opt/fusion-collectors/VERSION",
                }
            ]
        ),
        encoding="utf-8",
    )
    (enterprise_dir / "builtin.json").write_text(
        json.dumps(
            [
                {
                    "id": "controller_linux",
                    "os": "linux",
                    "cpu_architecture": "x86_64",
                    "name": "Controller",
                    "description": "enterprise override",
                    "version_command": "cat /enterprise/VERSION",
                },
                {
                    "id": "controller_linux_arm64",
                    "os": "linux",
                    "cpu_architecture": "arm64",
                    "name": "Controller",
                    "description": "enterprise arm64",
                    "version_command": "cat /enterprise/VERSION",
                },
            ]
        ),
        encoding="utf-8",
    )

    records = load_definition_records(str(community_dir), str(enterprise_dir))
    record_map = {record["id"]: record for record in records}

    assert record_map["controller_linux"]["description"] == "enterprise override"
    assert record_map["controller_linux_arm64"]["cpu_architecture"] == NodeConstants.ARM64_ARCH


@pytest.mark.django_db
def test_controller_init_loads_json_definitions(monkeypatch, tmp_path):
    community_dir = tmp_path / "controllers"
    community_dir.mkdir(parents=True)
    (community_dir / "builtin.json").write_text(
        json.dumps(
            [
                {
                    "id": "controller_linux",
                    "os": "linux",
                    "cpu_architecture": "x86_64",
                    "name": "Controller",
                    "description": "community controller",
                    "version_command": "cat /opt/fusion-collectors/VERSION",
                }
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "apps.node_mgmt.management.services.node_init.controller_init.COMMUNITY_CONTROLLER_DIRECTORY",
        str(community_dir),
    )
    monkeypatch.setattr(
        "apps.node_mgmt.management.services.node_init.controller_init.ENTERPRISE_CONTROLLER_DIRECTORY",
        str(tmp_path / "missing-enterprise"),
    )

    controller_init()

    controller = Controller.objects.get(os="linux", cpu_architecture="x86_64", name="Controller")
    assert controller.description == "community controller"


@pytest.mark.django_db
def test_import_collector_supports_architecture_specific_records():
    import_collector(
        [
            {
                "id": "telegraf_linux",
                "name": "Telegraf",
                "service_type": "exec",
                "node_operating_system": "linux",
                "cpu_architecture": "",
                "executable_path": "/opt/fusion-collectors/bin/telegraf",
                "execute_parameters": "--config %s",
                "validation_parameters": "",
                "default_template": "",
                "introduction": "generic telegraf",
                "icon": "telegraf",
                "controller_default_run": True,
                "default_config": {},
                "tags": ["linux"],
                "package_name": "telegraf",
            },
            {
                "id": "telegraf_linux_arm64",
                "name": "Telegraf",
                "service_type": "exec",
                "node_operating_system": "linux",
                "cpu_architecture": "arm64",
                "executable_path": "/opt/fusion-collectors/bin/telegraf-arm64",
                "execute_parameters": "--config %s",
                "validation_parameters": "",
                "default_template": "",
                "introduction": "arm telegraf",
                "icon": "telegraf",
                "controller_default_run": True,
                "default_config": {},
                "tags": ["linux"],
                "package_name": "telegraf-arm64",
            },
        ]
    )

    generic = Collector.objects.get(id="telegraf_linux")
    arm = Collector.objects.get(id="telegraf_linux_arm64")

    assert generic.cpu_architecture == ""
    assert arm.cpu_architecture == NodeConstants.ARM64_ARCH
    assert arm.package_name == "telegraf-arm64"


@pytest.mark.django_db
def test_nats_batch_create_configs_prefers_architecture_specific_collector():
    cloud_region = CloudRegion.objects.create(
        name="region-nats-config",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-arm-config",
        name="node-arm-config",
        ip="10.0.0.21",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    Collector.objects.create(
        id="telegraf_linux",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    arm_collector = Collector.objects.create(
        id="telegraf_linux_arm64",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        executable_path="/opt/telegraf-arm64",
        execute_parameters="--config %s",
        introduction="arm64",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf-arm64",
        created_by="tester",
        updated_by="tester",
    )

    NatsService().batch_create_configs(
        [
            {
                "id": "cfg-arm-telegraf",
                "name": "cfg-arm-telegraf",
                "content": "[[inputs.cpu]]",
                "node_id": node.id,
                "collector_name": "Telegraf",
                "env_config": {},
            }
        ]
    )

    config = arm_collector.collectorconfiguration_set.get(id="cfg-arm-telegraf")
    assert config.collector_id == arm_collector.id


@pytest.mark.django_db
def test_nats_batch_create_child_configs_rejects_legacy_x86_parent_for_arm64_node():
    cloud_region = CloudRegion.objects.create(
        name="region-nats-child",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-arm-child",
        name="node-arm-child",
        ip="10.0.0.22",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    generic_collector = Collector.objects.create(
        id="telegraf_linux",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="legacy x86",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    generic_config = generic_collector.collectorconfiguration_set.create(
        id="cfg-generic-telegraf",
        name="cfg-generic-telegraf",
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    generic_config.nodes.add(node)

    with pytest.raises(BaseAppException, match="Collector configuration not found"):
        NatsService().batch_create_child_configs(
            [
                {
                    "id": "child-arm-telegraf",
                    "collect_type": "metrics",
                    "type": "input",
                    "content": "[[inputs.mem]]",
                    "node_id": node.id,
                    "collector_name": "Telegraf",
                    "env_config": {},
                }
            ]
        )


@pytest.mark.django_db
def test_nats_batch_create_child_configs_prefers_exact_architecture_collector_configuration():
    cloud_region = CloudRegion.objects.create(
        name="region-nats-child-exact",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-arm-child-exact",
        name="node-arm-child-exact",
        ip="10.0.0.23",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    generic_collector = Collector.objects.create(
        id="telegraf_linux_exact_generic",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    arm_collector = Collector.objects.create(
        id="telegraf_linux_exact_arm64",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        executable_path="/opt/telegraf-arm64",
        execute_parameters="--config %s",
        introduction="arm64",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf-arm64",
        created_by="tester",
        updated_by="tester",
    )
    generic_config = generic_collector.collectorconfiguration_set.create(
        id="cfg-generic-telegraf-exact",
        name="cfg-generic-telegraf-exact",
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    generic_config.nodes.add(node)
    arm_config = arm_collector.collectorconfiguration_set.create(
        id="cfg-arm-telegraf-exact",
        name="cfg-arm-telegraf-exact",
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    arm_config.nodes.add(node)

    NatsService().batch_create_child_configs(
        [
            {
                "id": "child-arm-telegraf-exact",
                "collect_type": "metrics",
                "type": "input",
                "content": "[[inputs.mem]]",
                "node_id": node.id,
                "collector_name": "Telegraf",
                "env_config": {},
            }
        ]
    )

    child = arm_config.childconfig_set.get(id="child-arm-telegraf-exact")
    assert child.collector_config_id == arm_config.id


@pytest.mark.django_db
def test_nats_batch_create_child_configs_uses_x86_compatible_parent_for_unknown_node_architecture():
    cloud_region = CloudRegion.objects.create(
        name="region-nats-child-unknown",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-unknown-child",
        name="node-unknown-child",
        ip="10.0.0.24",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    generic_collector = Collector.objects.create(
        id="telegraf_linux_unknown_generic",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="legacy x86",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    arm_collector = Collector.objects.create(
        id="telegraf_linux_unknown_arm64",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        executable_path="/opt/telegraf-arm64",
        execute_parameters="--config %s",
        introduction="arm64",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf-arm64",
        created_by="tester",
        updated_by="tester",
    )
    generic_config = generic_collector.collectorconfiguration_set.create(
        id="cfg-generic-telegraf-unknown",
        name="cfg-generic-telegraf-unknown",
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    generic_config.nodes.add(node)
    arm_config = arm_collector.collectorconfiguration_set.create(
        id="cfg-arm-telegraf-unknown",
        name="cfg-arm-telegraf-unknown",
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    arm_config.nodes.add(node)

    NatsService().batch_create_child_configs(
        [
            {
                "id": "child-unknown-telegraf",
                "collect_type": "metrics",
                "type": "input",
                "content": "[[inputs.mem]]",
                "node_id": node.id,
                "collector_name": "Telegraf",
                "env_config": {},
            }
        ]
    )

    child = generic_config.childconfig_set.get(id="child-unknown-telegraf")
    assert child.collector_config_id == generic_config.id


@pytest.mark.django_db
def test_nats_batch_create_child_configs_uses_unique_x86_parent_for_unknown_node_architecture():
    cloud_region = CloudRegion.objects.create(
        name="region-nats-child-unknown-unique-arch",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-unknown-child-unique-arch",
        name="node-unknown-child-unique-arch",
        ip="10.0.0.29",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    x86_collector = Collector.objects.create(
        id="telegraf_linux_unknown_unique_x86",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        executable_path="/opt/telegraf-x86",
        execute_parameters="--config %s",
        introduction="x86_64",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    x86_config = x86_collector.collectorconfiguration_set.create(
        id="cfg-x86-telegraf-unknown-unique",
        name="cfg-x86-telegraf-unknown-unique",
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    x86_config.nodes.add(node)

    NatsService().batch_create_child_configs(
        [
            {
                "id": "child-unknown-telegraf-unique-arch",
                "collect_type": "metrics",
                "type": "input",
                "content": "[[inputs.mem]]",
                "node_id": node.id,
                "collector_name": "Telegraf",
                "env_config": {},
            }
        ]
    )

    child = x86_config.childconfig_set.get(id="child-unknown-telegraf-unique-arch")
    assert child.collector_config_id == x86_config.id


@pytest.mark.django_db
def test_nats_batch_create_child_configs_rejects_multiple_x86_compatible_parents_for_unknown_node_architecture():
    cloud_region = CloudRegion.objects.create(
        name="region-nats-child-unknown-multi-arch",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-unknown-child-multi-arch",
        name="node-unknown-child-multi-arch",
        ip="10.0.0.30",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    x86_collector = Collector.objects.create(
        id="telegraf_linux_unknown_multi_x86_a",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        executable_path="/opt/telegraf-x86-a",
        execute_parameters="--config %s",
        introduction="x86_64 a",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    x86_config = x86_collector.collectorconfiguration_set.create(
        id="cfg-x86-telegraf-unknown-multi-a",
        name="cfg-x86-telegraf-unknown-multi-a",
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    x86_config_b = x86_collector.collectorconfiguration_set.create(
        id="cfg-x86-telegraf-unknown-multi-b",
        name="cfg-x86-telegraf-unknown-multi-b",
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    x86_config.nodes.add(node)
    x86_config_b.nodes.add(node)

    with pytest.raises(BaseAppException, match="multiple x86_64 matches"):
        NatsService().batch_create_child_configs(
            [
                {
                    "id": "child-unknown-telegraf-multi-arch",
                    "collect_type": "metrics",
                    "type": "input",
                    "content": "[[inputs.mem]]",
                    "node_id": node.id,
                    "collector_name": "Telegraf",
                    "env_config": {},
                }
            ]
        )


@pytest.mark.django_db
def test_nats_batch_create_child_configs_rejects_ambiguous_generic_collector_configurations():
    cloud_region = CloudRegion.objects.create(
        name="region-nats-child-ambiguous",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-ambiguous-child",
        name="node-ambiguous-child",
        ip="10.0.0.25",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    generic_collector = Collector.objects.create(
        id="telegraf_linux_ambiguous_generic",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    first_config = generic_collector.collectorconfiguration_set.create(
        id="cfg-generic-telegraf-ambiguous-a",
        name="cfg-generic-telegraf-ambiguous-a",
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    second_config = generic_collector.collectorconfiguration_set.create(
        id="cfg-generic-telegraf-ambiguous-b",
        name="cfg-generic-telegraf-ambiguous-b",
        config_template="[[inputs.mem]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    first_config.nodes.add(node)
    second_config.nodes.add(node)

    with pytest.raises(BaseAppException):
        NatsService().batch_create_child_configs(
            [
                {
                    "id": "child-ambiguous-telegraf",
                    "collect_type": "metrics",
                    "type": "input",
                    "content": "[[inputs.disk]]",
                    "node_id": node.id,
                    "collector_name": "Telegraf",
                    "env_config": {},
                }
            ]
        )


@pytest.mark.django_db
def test_nats_batch_create_child_configs_auto_creates_missing_default_parent_configuration():
    cloud_region = CloudRegion.objects.create(
        name="region-nats-child-autocreate",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    SidecarEnv.objects.create(
        cloud_region=cloud_region,
        key="SIDECAR_INPUT_MODE",
        value="nats",
        type="text",
    )
    node = Node.objects.create(
        id="node-child-autocreate",
        name="node-child-autocreate",
        ip="10.0.0.26",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    Collector.objects.create(
        id="telegraf_linux_autocreate",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        controller_default_run=True,
        default_config={"nats": "[[inputs.cpu]]\n  interval = '10s'"},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )

    NatsService().batch_create_child_configs(
        [
            {
                "id": "child-autocreate-telegraf",
                "collect_type": "host",
                "type": "cpu",
                "content": "[[inputs.cpu]]",
                "node_id": node.id,
                "collector_name": "Telegraf",
                "env_config": {},
            }
        ]
    )

    parent_config = CollectorConfiguration.objects.get(nodes=node, collector__name="Telegraf")
    child = parent_config.childconfig_set.get(id="child-autocreate-telegraf")
    assert parent_config.is_pre is True
    assert child.collector_config_id == parent_config.id


@pytest.mark.django_db
def test_nats_batch_create_child_configs_reports_missing_default_config_for_parent_creation():
    cloud_region = CloudRegion.objects.create(
        name="region-nats-child-missing-default",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-child-missing-default",
        name="node-child-missing-default",
        ip="10.0.0.27",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    Collector.objects.create(
        id="telegraf_linux_missing_default",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        controller_default_run=True,
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )

    with pytest.raises(BaseAppException, match="缺少 default_config"):
        NatsService().batch_create_child_configs(
            [
                {
                    "id": "child-missing-default-telegraf",
                    "collect_type": "host",
                    "type": "cpu",
                    "content": "[[inputs.cpu]]",
                    "node_id": node.id,
                    "collector_name": "Telegraf",
                    "env_config": {},
                }
            ]
        )


@pytest.mark.django_db
def test_nats_batch_create_child_configs_reports_bulk_create_failures():
    cloud_region = CloudRegion.objects.create(
        name="region-nats-child-bulk-failure",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-child-bulk-failure",
        name="node-child-bulk-failure",
        ip="10.0.0.28",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    collector = Collector.objects.create(
        id="telegraf_linux_bulk_failure",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    parent_config = collector.collectorconfiguration_set.create(
        id="cfg-bulk-failure",
        name="cfg-bulk-failure",
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    parent_config.nodes.add(node)

    with patch("apps.node_mgmt.nats.node.ChildConfig.objects.bulk_create", side_effect=Exception("db write failed")):
        with pytest.raises(BaseAppException, match="批量创建子配置失败"):
            NatsService().batch_create_child_configs(
                [
                    {
                        "id": "child-bulk-failure-telegraf",
                        "collect_type": "host",
                        "type": "cpu",
                        "content": "[[inputs.cpu]]",
                        "node_id": node.id,
                        "collector_name": "Telegraf",
                        "env_config": {},
                    }
                ]
            )


@pytest.mark.django_db
def test_nats_client_request_includes_error_message_from_nats_response(monkeypatch):
    from nats_client.clients import request
    from nats_client.exceptions import NatsClientException

    class _FakeResponse:
        data = json.dumps(
            {
                "success": False,
                "error": "BaseAppException",
                "message": "Collector configuration not found for node node-1 and collector Telegraf",
            }
        ).encode()

    class _FakeNc:
        async def request(self, *args, **kwargs):
            return _FakeResponse()

        async def close(self):
            return None

    async def _fake_get_nc_client(*args, **kwargs):
        return _FakeNc()

    monkeypatch.setattr("nats_client.clients.get_nc_client", _fake_get_nc_client)

    with pytest.raises(NatsClientException, match="BaseAppException: Collector configuration not found"):
        import asyncio

        asyncio.run(request("apps.node_mgmt.nats.node", "batch_create_configs_and_child_configs"))


@pytest.mark.django_db
def test_nats_client_request_falls_back_to_pickled_base_app_exception_message(monkeypatch):
    import jsonpickle

    from nats_client.clients import request
    from nats_client.exceptions import NatsClientException

    class _FakeResponse:
        data = json.dumps(
            {
                "success": False,
                "error": "BaseAppException",
                "pickled_exc": jsonpickle.encode(BaseAppException("collector default config missing")),
            }
        ).encode()

    class _FakeNc:
        async def request(self, *args, **kwargs):
            return _FakeResponse()

        async def close(self):
            return None

    async def _fake_get_nc_client(*args, **kwargs):
        return _FakeNc()

    monkeypatch.setattr("nats_client.clients.get_nc_client", _fake_get_nc_client)

    with pytest.raises(NatsClientException, match="BaseAppException: collector default config missing"):
        import asyncio

        asyncio.run(request("apps.node_mgmt.nats.node", "batch_create_configs_and_child_configs"))


@pytest.mark.django_db
def test_install_managed_component_nats_creates_task_and_dispatches_async_worker(monkeypatch):
    captured = {}

    def fake_install_collector(collector_package, nodes):
        captured["collector_package"] = collector_package
        captured["nodes"] = nodes
        return 1

    class _FakeDelay:
        def delay(self, task_id):
            captured["task_id"] = task_id

    monkeypatch.setattr("apps.node_mgmt.nats.node.InstallerService.install_collector", fake_install_collector)
    monkeypatch.setattr("apps.node_mgmt.nats.node.install_collector_task", _FakeDelay())

    from apps.node_mgmt.nats.node import install_managed_component

    result = install_managed_component({"collector_package": 12, "nodes": ["node-1", "node-2"]})

    assert result == {"task_id": 1}
    assert captured == {
        "collector_package": 12,
        "nodes": ["node-1", "node-2"],
        "task_id": 1,
    }


@pytest.mark.django_db
def test_install_collector_nats_creates_task_and_dispatches_async_worker(monkeypatch):
    captured = {}

    def fake_install_collector(collector_package, nodes):
        captured["collector_package"] = collector_package
        captured["nodes"] = nodes
        return 2

    class _FakeDelay:
        def delay(self, task_id):
            captured["task_id"] = task_id

    from apps.node_mgmt.nats import node as nats_node

    monkeypatch.setattr(nats_node.InstallerService, "install_collector", fake_install_collector)
    monkeypatch.setattr(nats_node, "install_collector_task", _FakeDelay(), raising=False)

    result = nats_node.install_collector({"collector_package": 13, "nodes": ["node-3", "node-4"]})

    assert result == {"task_id": 2}
    assert captured == {
        "collector_package": 13,
        "nodes": ["node-3", "node-4"],
        "task_id": 2,
    }


@pytest.mark.django_db
def test_base_app_exception_str_uses_message():
    exc = BaseAppException("collector config missing")

    assert str(exc) == "collector config missing"


@pytest.mark.django_db
def test_collector_filter_supports_architecture_alias_and_list_exposes_architecture_display(monkeypatch):
    monkeypatch.setattr(
        "apps.node_mgmt.views.collector.LanguageLoader",
        lambda *args, **kwargs: SimpleNamespace(get=lambda key: None),
    )
    Collector.objects.create(
        id="telegraf_linux",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture="",
        executable_path="/opt/telegraf",
        execute_parameters="--config %s",
        introduction="generic",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf",
        created_by="tester",
        updated_by="tester",
    )
    Collector.objects.create(
        id="telegraf_linux_arm64",
        name="Telegraf",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        executable_path="/opt/telegraf-arm64",
        execute_parameters="--config %s",
        introduction="arm64",
        icon="telegraf",
        default_config={},
        tags=[],
        package_name="telegraf-arm64",
        created_by="tester",
        updated_by="tester",
    )

    factory = APIRequestFactory()
    view = CollectorViewSet.as_view({"get": "list"})
    request = factory.get("/node_mgmt/api/collector/", {"cpu_architecture": "aarch64"})
    force_authenticate(request, user=_build_admin_user())

    response = view(request)

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["id"] == "telegraf_linux_arm64"
    assert response.data[0]["cpu_architecture"] == NodeConstants.ARM64_ARCH
    assert response.data[0]["architecture_display"] == "ARM64"
    assert response.data[0]["display_name"] == "Telegraf（ARM64）"


@pytest.mark.django_db
def test_collector_serializer_normalizes_cpu_architecture_alias():
    serializer = CollectorSerializer(
        data={
            "id": "vector_linux_alias",
            "name": "Vector",
            "service_type": "exec",
            "node_operating_system": NodeConstants.LINUX_OS,
            "cpu_architecture": "amd64",
            "executable_path": "/opt/vector",
            "execute_parameters": "--config %s",
            "validation_parameters": "",
            "default_template": "",
            "introduction": "vector",
            "icon": "vector",
            "controller_default_run": False,
            "default_config": {},
            "tags": [],
            "package_name": "vector",
            "is_pre": False,
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["cpu_architecture"] == NodeConstants.X86_64_ARCH
    assert set(serializer.validated_data["tags"]) == {NodeConstants.LINUX_OS, NodeConstants.X86_64_ARCH}


@pytest.mark.django_db
def test_collector_tag_filter_uses_flat_all_and_semantics():
    Collector.objects.create(
        id="collector-tag-filter-x86",
        name="Tag Filter X86",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        executable_path="/opt/x86",
        execute_parameters="--config %s",
        introduction="x86",
        icon="collector",
        tags=["monitor", "linux", "jmx", NodeConstants.X86_64_ARCH],
        created_by="tester",
        updated_by="tester",
    )
    Collector.objects.create(
        id="collector-tag-filter-arm",
        name="Tag Filter ARM",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        executable_path="/opt/arm",
        execute_parameters="--config %s",
        introduction="arm",
        icon="collector",
        tags=["monitor", "linux", "exporter", NodeConstants.ARM64_ARCH],
        created_by="tester",
        updated_by="tester",
    )

    factory = APIRequestFactory()
    view = CollectorViewSet.as_view({"get": "list"})
    request = factory.get(
        "/node_mgmt/api/collector/",
        {"tags": f"monitor,{NodeConstants.X86_64_ARCH},{NodeConstants.ARM64_ARCH}"},
    )
    force_authenticate(request, user=_build_admin_user())

    response = view(request)

    assert response.status_code == 200
    assert response.data == []


@pytest.mark.django_db
def test_collector_retrieve_exposes_architecture_display(monkeypatch):
    monkeypatch.setattr(
        "apps.node_mgmt.views.collector.LanguageLoader",
        lambda *args, **kwargs: SimpleNamespace(get=lambda key: None),
    )
    collector = Collector.objects.create(
        id="vector_linux_arm64",
        name="Vector",
        service_type="exec",
        node_operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.ARM64_ARCH,
        executable_path="/opt/vector-arm64",
        execute_parameters="--config %s",
        introduction="vector arm64",
        icon="vector",
        default_config={},
        tags=[],
        package_name="vector-arm64",
        created_by="tester",
        updated_by="tester",
    )

    factory = APIRequestFactory()
    view = CollectorViewSet.as_view({"get": "retrieve"})
    request = factory.get(f"/node_mgmt/api/collector/{collector.id}/")
    force_authenticate(request, user=_build_admin_user())

    response = view(request, pk=collector.id)

    assert response.status_code == 200
    assert response.data["id"] == collector.id
    assert response.data["cpu_architecture"] == NodeConstants.ARM64_ARCH
    assert response.data["architecture_display"] == "ARM64"


@pytest.mark.django_db
def test_trigger_converge_tasks_if_needed_schedules_legacy_install_task_without_install_node_id(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="legacy-converge-trigger-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    task = installer_tasks.ControllerTask.objects.create(
        cloud_region=cloud_region,
        type="install",
        status="running",
        work_node="worker-1",
        package_version_id=1,
        created_by="tester",
        updated_by="tester",
    )
    ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.77",
        node_name="legacy-node",
        os=NodeConstants.LINUX_OS,
        organizations=[1],
        port=22,
        username="root",
        password="",
        status=InstallerConstants.STEP_STATUS_RUNNING,
        result={
            InstallerConstants.EXECUTION_PHASE_KEY: InstallerConstants.EXECUTION_PHASE_CONNECTIVITY_WAITING,
            "steps": [{"action": "connectivity_check", "status": "running", "message": "Wait for node connection"}],
        },
    )
    called = []

    monkeypatch.setattr(Sidecar, "_is_debounce_elapsed", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        "apps.node_mgmt.services.sidecar.converge_controller_install_connectivity_for_node.delay",
        lambda node_id: called.append(node_id),
    )

    Sidecar.trigger_converge_tasks_if_needed("legacy-install-node", "10.0.0.77", {})

    assert called == ["legacy-install-node"]


@pytest.mark.django_db
def test_converge_controller_install_connectivity_for_node_prefers_install_node_id_with_shared_ip():
    cloud_region = CloudRegion.objects.create(
        name="shared-ip-converge-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    stale_task = installer_tasks.ControllerTask.objects.create(
        cloud_region=cloud_region,
        type="install",
        status="running",
        work_node="worker-1",
        package_version_id=1,
        created_by="tester",
        updated_by="tester",
    )
    current_task = installer_tasks.ControllerTask.objects.create(
        cloud_region=cloud_region,
        type="install",
        status="running",
        work_node="worker-1",
        package_version_id=1,
        created_by="tester",
        updated_by="tester",
    )
    common_result = {
        InstallerConstants.EXECUTION_PHASE_KEY: InstallerConstants.EXECUTION_PHASE_CONNECTIVITY_WAITING,
        "steps": [{"action": "connectivity_check", "status": "running", "message": "Wait for node connection"}],
    }
    stale_task_node = ControllerTaskNode.objects.create(
        task=stale_task,
        ip="10.0.0.88",
        node_name="stale-node",
        os=NodeConstants.LINUX_OS,
        organizations=[1],
        port=22,
        username="root",
        password="",
        status=InstallerConstants.STEP_STATUS_RUNNING,
        result={**common_result, InstallerConstants.INSTALL_NODE_ID_KEY: "stale-install-node"},
    )
    current_task_node = ControllerTaskNode.objects.create(
        task=current_task,
        ip="10.0.0.88",
        node_name="current-node",
        os=NodeConstants.LINUX_OS,
        organizations=[1],
        port=22,
        username="root",
        password="",
        status=InstallerConstants.STEP_STATUS_RUNNING,
        result={**common_result, InstallerConstants.INSTALL_NODE_ID_KEY: "current-install-node"},
    )
    Node.objects.create(
        id="current-install-node",
        name="current-node",
        ip="10.0.0.88",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/tmp/config",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )

    installer_tasks.converge_controller_install_connectivity_for_node("current-install-node")

    stale_task_node.refresh_from_db()
    current_task_node.refresh_from_db()
    assert stale_task_node.status == InstallerConstants.STEP_STATUS_RUNNING
    assert current_task_node.status == InstallerConstants.STEP_STATUS_SUCCESS


@pytest.mark.django_db
def test_converge_controller_install_connectivity_triggers_version_discovery_when_install_task_finishes(monkeypatch):
    cloud_region = CloudRegion.objects.create(
        name="version-refresh-converge-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    task = installer_tasks.ControllerTask.objects.create(
        cloud_region=cloud_region,
        type="install",
        status="running",
        work_node="worker-1",
        package_version_id=1,
        created_by="tester",
        updated_by="tester",
    )
    task_node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.90",
        node_name="version-node",
        os=NodeConstants.LINUX_OS,
        organizations=[1],
        port=22,
        username="root",
        password="",
        status=InstallerConstants.STEP_STATUS_RUNNING,
        result={
            InstallerConstants.EXECUTION_PHASE_KEY: InstallerConstants.EXECUTION_PHASE_CONNECTIVITY_WAITING,
            "steps": [{"action": "connectivity_check", "status": "running", "message": "Wait for node connection"}],
        },
    )
    Node.objects.create(
        id="version-install-node",
        name="version-node",
        ip="10.0.0.90",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/tmp/config",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    called = []
    monkeypatch.setattr(installer_tasks.discover_node_versions, "delay", lambda: called.append("discover"))

    installer_tasks.converge_controller_install_connectivity_for_node("version-install-node")

    task.refresh_from_db()
    task_node.refresh_from_db()
    assert task.status == "finished"
    assert task_node.status == InstallerConstants.STEP_STATUS_SUCCESS
    assert called == ["discover"]


@pytest.mark.django_db
def test_converge_controller_install_connectivity_for_node_falls_back_for_legacy_task_without_install_node_id():
    cloud_region = CloudRegion.objects.create(
        name="legacy-converge-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    legacy_task = installer_tasks.ControllerTask.objects.create(
        cloud_region=cloud_region,
        type="install",
        status="running",
        work_node="worker-1",
        package_version_id=1,
        created_by="tester",
        updated_by="tester",
    )
    mismatched_task = installer_tasks.ControllerTask.objects.create(
        cloud_region=cloud_region,
        type="install",
        status="running",
        work_node="worker-1",
        package_version_id=1,
        created_by="tester",
        updated_by="tester",
    )
    common_result = {
        InstallerConstants.EXECUTION_PHASE_KEY: InstallerConstants.EXECUTION_PHASE_CONNECTIVITY_WAITING,
        "steps": [{"action": "connectivity_check", "status": "running", "message": "Wait for node connection"}],
    }
    legacy_task_node = ControllerTaskNode.objects.create(
        task=legacy_task,
        ip="10.0.0.89",
        node_name="legacy-node",
        os=NodeConstants.LINUX_OS,
        organizations=[1],
        port=22,
        username="root",
        password="",
        status=InstallerConstants.STEP_STATUS_RUNNING,
        result=common_result,
    )
    mismatched_task_node = ControllerTaskNode.objects.create(
        task=mismatched_task,
        ip="10.0.0.89",
        node_name="other-node",
        os=NodeConstants.LINUX_OS,
        organizations=[1],
        port=22,
        username="root",
        password="",
        status=InstallerConstants.STEP_STATUS_RUNNING,
        result={**common_result, InstallerConstants.INSTALL_NODE_ID_KEY: "other-install-node"},
    )
    Node.objects.create(
        id="legacy-install-node",
        name="legacy-node",
        ip="10.0.0.89",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/tmp/config",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )

    installer_tasks.converge_controller_install_connectivity_for_node("legacy-install-node")

    legacy_task_node.refresh_from_db()
    mismatched_task_node.refresh_from_db()
    assert legacy_task_node.status == InstallerConstants.STEP_STATUS_SUCCESS
    assert mismatched_task_node.status == InstallerConstants.STEP_STATUS_RUNNING


@pytest.mark.django_db
def test_install_connectivity_converge_matches_generated_node_id_not_ip():
    cloud_region = CloudRegion.objects.create(
        name="connectivity-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    stale_task = ControllerTask.objects.create(
        cloud_region=cloud_region,
        type="install",
        status="running",
        work_node="worker-1",
        package_version_id=1,
        created_by="tester",
        updated_by="tester",
    )
    current_task = ControllerTask.objects.create(
        cloud_region=cloud_region,
        type="install",
        status="running",
        work_node="worker-1",
        package_version_id=1,
        created_by="tester",
        updated_by="tester",
    )
    common_result = {
        InstallerConstants.EXECUTION_PHASE_KEY: InstallerConstants.EXECUTION_PHASE_CONNECTIVITY_WAITING,
        "steps": [{"action": "connectivity_check", "status": "running", "message": "Wait for node connection"}],
    }
    stale_task_node = ControllerTaskNode.objects.create(
        task=stale_task,
        ip="10.0.0.88",
        node_name="stale-node",
        os=NodeConstants.LINUX_OS,
        organizations=[1],
        port=22,
        username="root",
        password="",
        status=InstallerConstants.STEP_STATUS_RUNNING,
        result={**common_result, InstallerConstants.INSTALL_NODE_ID_KEY: "stale-install-node"},
    )
    current_task_node = ControllerTaskNode.objects.create(
        task=current_task,
        ip="10.0.0.88",
        node_name="current-node",
        os=NodeConstants.LINUX_OS,
        organizations=[1],
        port=22,
        username="root",
        password="",
        status=InstallerConstants.STEP_STATUS_RUNNING,
        result={**common_result, InstallerConstants.INSTALL_NODE_ID_KEY: "current-install-node"},
    )
    Node.objects.create(
        id="current-install-node",
        name="current-node",
        ip="10.0.0.88",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/tmp/config",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )

    installer_tasks.converge_controller_install_connectivity_for_node("current-install-node")

    stale_task_node.refresh_from_db()
    current_task_node.refresh_from_db()
    assert stale_task_node.status == InstallerConstants.STEP_STATUS_RUNNING
    assert current_task_node.status == InstallerConstants.STEP_STATUS_SUCCESS


@pytest.mark.django_db
def test_backfill_node_cpu_architecture_updates_linux_node(monkeypatch, capsys):
    cloud_region = CloudRegion.objects.create(
        name="backfill-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    task = installer_tasks.ControllerTask.objects.create(
        cloud_region=cloud_region,
        type="install",
        status="success",
        work_node="worker-1",
        package_version_id=1,
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="legacy-linux-node",
        name="legacy-linux-node",
        ip="10.0.0.99",
        operating_system="linux",
        cpu_architecture="",
        collector_configuration_directory="/tmp/config",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    aes = AESCryptor()
    installer_tasks.ControllerTaskNode.objects.create(
        task=task,
        ip=node.ip,
        node_name=node.name,
        os=node.operating_system,
        organizations=[1],
        port=22,
        username="root",
        password=aes.encode("secret"),
        status="success",
    )

    monkeypatch.setattr(
        "apps.node_mgmt.management.commands.backfill_node_cpu_architecture.exec_command_to_remote",
        lambda *args, **kwargs: "aarch64",
    )

    BackfillNodeCpuArchitectureCommand().handle(node_ids=[node.id], limit=10, dry_run=False)
    node.refresh_from_db()
    output = capsys.readouterr().out

    assert node.cpu_architecture == NodeConstants.ARM64_ARCH
    assert "[ok] legacy-linux-node: arm64" in output


@pytest.mark.django_db
def test_backfill_node_cpu_architecture_skips_nodes_without_credentials(capsys):
    cloud_region = CloudRegion.objects.create(
        name="backfill-region-2",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="legacy-node-no-creds",
        name="legacy-node-no-creds",
        ip="10.0.0.100",
        operating_system="linux",
        cpu_architecture="",
        collector_configuration_directory="/tmp/config",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )

    BackfillNodeCpuArchitectureCommand().handle(node_ids=[node.id], limit=10, dry_run=False)
    node.refresh_from_db()
    output = capsys.readouterr().out

    assert node.cpu_architecture == ""
    assert "no reusable install credentials" in output
