from queue import Queue
from types import SimpleNamespace
import json
from io import BytesIO
from pathlib import Path

import pytest
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.node_mgmt.constants.node import NodeConstants
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.models import CloudRegion, Collector, Controller, Node, PackageVersion, SidecarEnv
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.services.installer_session import InstallerSessionService
from apps.node_mgmt.services.sidecar import Sidecar
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.services.version_upgrade import VersionUpgradeService
from apps.node_mgmt.tasks import installer as installer_tasks
from apps.node_mgmt.tasks.version_discovery import _calculate_upgrade_info
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture
from apps.node_mgmt.management.commands.collector_package_init import Command as CollectorPackageInitCommand
from apps.node_mgmt.management.commands.backfill_node_cpu_architecture import Command as BackfillNodeCpuArchitectureCommand
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
        captured.append((package_type, options["cpu_architecture"]))

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
        ("controller", NodeConstants.ARM64_ARCH),
        ("collector", NodeConstants.X86_64_ARCH),
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

    VerifyArchitectureRolloutCommand().handle(version="9.9.9")
    output = capsys.readouterr().out

    assert "Linux ARM64 controller package present: yes" in output
    assert "Installer artifacts present" in output


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
