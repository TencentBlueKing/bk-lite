from queue import Queue
from types import SimpleNamespace
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.node_mgmt.constants.node import NodeConstants
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.models import CloudRegion, Collector, CollectorConfiguration, Controller, Node, PackageVersion, SidecarEnv
from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.services.installer_session import InstallerSessionService
from apps.node_mgmt.services.sidecar import Sidecar
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.filters.package import PackageVersionFilter
from apps.node_mgmt.services.version_upgrade import VersionUpgradeService
from apps.node_mgmt.tasks import installer as installer_tasks
from apps.node_mgmt.tasks.version_discovery import _calculate_upgrade_info
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture
from apps.node_mgmt.management.commands.collector_package_init import Command as CollectorPackageInitCommand
from apps.node_mgmt.management.commands.backfill_node_cpu_architecture import Command as BackfillNodeCpuArchitectureCommand
from apps.node_mgmt.management.commands.backfill_package_storage_paths import Command as BackfillPackageStoragePathsCommand
from apps.node_mgmt.management.commands.controller_package_init import Command as ControllerPackageInitCommand
from apps.node_mgmt.management.commands.installer_init import Command as InstallerInitCommand
from apps.node_mgmt.management.commands.verify_architecture_rollout import Command as VerifyArchitectureRolloutCommand
from apps.node_mgmt.management.services.node_init.definition_loader import load_definition_records
from apps.node_mgmt.management.services.node_init.collector_init import import_collector
from apps.node_mgmt.management.services.node_init.controller_init import controller_init
from apps.node_mgmt.nats.node import NatsService
from apps.node_mgmt.serializers.collector import CollectorSerializer
from apps.node_mgmt.views.collector import CollectorViewSet
from apps.node_mgmt.views.installer import InstallerViewSet
from apps.node_mgmt.views.sidecar import OpenSidecarViewSet


def _build_admin_user():
    return User.objects.create(
        username=f"installer-test-user-{User.objects.count() + 1}",
        domain="domain.com",
        locale="en",
        is_superuser=True,
        roles=["admin"],
        group_list=[{"id": 1, "name": "Team"}],
    )


def _json_response_data(response):
    return json.loads(response.content)


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
def test_resolve_package_by_architecture_falls_back_to_generic_package():
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

    resolved = PackageService.resolve_package_by_architecture(seed.id, "arm64")

    assert resolved is not None
    assert resolved.id == seed.id


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

    Sidecar.create_default_config(node, [])

    collector_ids = set(CollectorConfiguration.objects.filter(nodes=node).values_list("collector_id", flat=True))
    assert "telegraf_linux_arm64_default" in collector_ids


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
        InstallerSessionService,
        "build_session_config",
        lambda token, arch="": {
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
        lambda token, arch="": {
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

    assert (
        f"[dry-run] {package_obj.id}: copy linux/Controller/1.0.1/fusion-collectors-linux-amd64.zip -> linux/x86_64/Controller/1.0.1/fusion-collectors-linux-amd64.zip"
        in output
    )


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
def test_nats_batch_create_child_configs_falls_back_to_generic_collector_configuration():
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
        introduction="generic",
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

    child = generic_config.childconfig_set.get(id="child-arm-telegraf")
    assert child.collector_config_id == generic_config.id


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
def test_nats_batch_create_child_configs_uses_generic_for_unknown_node_architecture():
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
        introduction="generic",
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
def test_nats_batch_create_child_configs_uses_unique_arch_parent_for_unknown_node_architecture():
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
    arm_collector = Collector.objects.create(
        id="telegraf_linux_unknown_unique_arm64",
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
    arm_config = arm_collector.collectorconfiguration_set.create(
        id="cfg-arm-telegraf-unknown-unique",
        name="cfg-arm-telegraf-unknown-unique",
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    arm_config.nodes.add(node)

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

    child = arm_config.childconfig_set.get(id="child-unknown-telegraf-unique-arch")
    assert child.collector_config_id == arm_config.id


@pytest.mark.django_db
def test_nats_batch_create_child_configs_rejects_multiple_arch_parents_for_unknown_node_architecture():
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
    arm_collector = Collector.objects.create(
        id="telegraf_linux_unknown_multi_arm64",
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
    x86_collector = Collector.objects.create(
        id="telegraf_linux_unknown_multi_x86",
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
    arm_config = arm_collector.collectorconfiguration_set.create(
        id="cfg-arm-telegraf-unknown-multi",
        name="cfg-arm-telegraf-unknown-multi",
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    x86_config = x86_collector.collectorconfiguration_set.create(
        id="cfg-x86-telegraf-unknown-multi",
        name="cfg-x86-telegraf-unknown-multi",
        config_template="[[inputs.cpu]]",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    arm_config.nodes.add(node)
    x86_config.nodes.add(node)

    with pytest.raises(BaseAppException, match="multiple architecture-specific matches"):
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
    from nats_client.clients import request
    from nats_client.exceptions import NatsClientException
    import jsonpickle

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
    assert response.data["display_name"] == "Vector（ARM64）"


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
