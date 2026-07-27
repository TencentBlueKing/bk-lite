import pytest
import yaml

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.management.commands.installer_init import Command as InstallerInitCommand
from apps.node_mgmt.models import ControllerTask, ControllerTaskNode, Node, PackageVersion
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.serializers.installer import InstallNodeSerializer
from apps.node_mgmt.services.windows_remote_bootstrap import (
    AnsibleExecutorResolver,
    WindowsBootstrapTarget,
    WindowsRemoteBootstrapService,
)
from apps.node_mgmt.tasks import installer as installer_tasks


class FakeExecutor:
    def __init__(self, instance_id):
        self.instance_id = instance_id
        self.playbook_calls = []
        self.query_results = [
            {"status": "success", "result": {"result": []}},
            {
                "status": "success",
                "result": {
                    "result": [
                        {
                            "status": "success",
                            "stdout": 'BKINSTALL_EVENT {"action":"install","status":"success"}',
                        }
                    ]
                },
            },
            {"status": "success", "result": {"result": []}},
        ]

    def playbook(self, **kwargs):
        self.playbook_calls.append(kwargs)
        return {"accepted": True, "task_id": kwargs["task_id"]}

    def task_query(self, task_id, timeout=10):
        return self.query_results.pop(0)


class FakeResolver:
    @classmethod
    def resolve(cls, cloud_region_id):
        assert cloud_region_id == 7
        return "executor-node"


def test_windows_remote_bootstrap_stages_and_runs_native_worker():
    executor = FakeExecutor("executor-node")
    service = WindowsRemoteBootstrapService(executor_factory=lambda _: executor, resolver=FakeResolver)

    output = service.run(
        cloud_region_id=7,
        task_node_id=31,
        attempt=2,
        cpu_architecture="x86_64",
        session_url="https://server.example/api/installer/session/secret",
        target=WindowsBootstrapTarget(
            host="10.0.0.8",
            port=5986,
            user="Administrator",
            password="credential",
        ),
        timeout=60,
    )

    assert executor.instance_id == "executor-node"
    assert len(executor.playbook_calls) == 3
    stage, execution, cleanup = executor.playbook_calls
    assert stage["host_credentials"] == [
        {
            "host": "10.0.0.8",
            "port": 5986,
            "user": "Administrator",
            "password": "credential",
            "connection": "winrm",
            "winrm_scheme": "https",
            "winrm_transport": "ntlm",
            "winrm_cert_validation": True,
        }
    ]
    assert stage["files"][0]["file_key"].endswith("windows/x86_64/bklite-controller-bootstrap.exe")
    assert stage["file_distribution"]["target_path"] == "C:/Windows/Temp"

    playbook = yaml.safe_load(execution["playbook_content"])
    block = playbook[0]["tasks"][0]
    commands = block["block"]
    assert commands[0]["name"] == "Verify supported Windows and PowerShell version"
    assert "PowerShell 5.1" in commands[0]["ansible.builtin.raw"]
    assert commands[1]["no_log"] is True
    assert commands[2]["ansible.windows.win_command"]["argv"][1] == "--url-file"
    assert len(block["always"]) == 2
    assert execution["extra_vars"]["bklite_session_url"].endswith("/secret")
    cleanup_playbook = yaml.safe_load(cleanup["playbook_content"])
    cleanup_tasks = cleanup_playbook[0]["tasks"]
    assert {task["ansible.windows.win_file"]["path"] for task in cleanup_tasks} == {
        "C:/Windows/Temp/bklite-controller-bootstrap-31-2.exe",
        "C:/Windows/Temp/bklite-controller-session-31-2.url",
    }
    assert output.startswith("BKINSTALL_EVENT ")


def test_windows_remote_bootstrap_rejects_failed_ansible_task():
    executor = FakeExecutor("executor-node")
    executor.query_results = [
        {"status": "failed", "error": "connection refused"},
        {"status": "success", "result": {"result": []}},
    ]
    service = WindowsRemoteBootstrapService(executor_factory=lambda _: executor, resolver=FakeResolver)

    with pytest.raises(BaseAppException, match="Ansible task failed"):
        service.run(
            cloud_region_id=7,
            task_node_id=31,
            attempt=1,
            cpu_architecture="x86_64",
            session_url="https://server.example/session",
            target=WindowsBootstrapTarget("10.0.0.8", 5986, "Administrator", "credential"),
            timeout=60,
        )

    assert len(executor.playbook_calls) == 2
    assert executor.playbook_calls[-1]["task_id"] == "controller-bootstrap-cleanup-31-1"


@pytest.mark.unit
def test_windows_remote_bootstrap_rejects_unsafe_persisted_winrm_profile():
    executor = FakeExecutor("executor-node")
    service = WindowsRemoteBootstrapService(executor_factory=lambda _: executor, resolver=FakeResolver)

    with pytest.raises(BaseAppException, match="HTTPS, NTLM"):
        service.run(
            cloud_region_id=7,
            task_node_id=31,
            attempt=1,
            cpu_architecture="x86_64",
            session_url="https://server.example/session",
            target=WindowsBootstrapTarget(
                "10.0.0.8",
                5985,
                "Administrator",
                "credential",
                scheme="http",
            ),
            timeout=60,
        )

    assert executor.playbook_calls == []


def test_windows_remote_bootstrap_extracts_events_from_ansible_combined_output():
    result = {
        "result": {
            "result": [{"status": "success", "stdout": ""}],
            "result_summary": {
                "stdout_combined": (
                    "ok: [10.0.0.8] => {\n"
                    '  "bklite_bootstrap_result.stdout": "BKINSTALL_EVENT '
                    '{\\"step\\":\\"complete\\",\\"status\\":\\"success\\"}\\r\\n"\n'
                    "}"
                )
            },
        }
    }

    assert WindowsRemoteBootstrapService._extract_stdout(result) == ('BKINSTALL_EVENT {"step":"complete","status":"success"}')


def test_installer_init_uploads_windows_bootstrap_artifact(tmp_path, monkeypatch):
    uploaded = {}
    file_path = tmp_path / "bklite-controller-bootstrap.exe"
    file_path.write_bytes(b"bootstrap")

    async def fake_upload(file, object_key):
        uploaded["object_key"] = object_key

    monkeypatch.setattr(
        "apps.node_mgmt.management.commands.installer_init.upload_file_to_s3",
        fake_upload,
    )

    InstallerInitCommand().handle(
        os="windows",
        cpu_architecture="x86_64",
        variant="bootstrap",
        file_path=str(file_path),
    )

    assert uploaded["object_key"] == "installer/windows/x86_64/bklite-controller-bootstrap.exe"


@pytest.mark.django_db
def test_install_task_routes_windows_through_winrm_bootstrap(monkeypatch):
    region = CloudRegion.objects.create(name="windows-task-region")
    package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.WINDOWS_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.0",
        name="controller-windows.exe",
    )
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="waiting",
        work_node="region-nats-executor",
        package_version_id=package.id,
    )
    task_node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.8",
        node_name="windows-node",
        os=NodeConstants.WINDOWS_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        organizations=[1],
        port=5986,
        username="Administrator",
        password=AESCryptor().encode("credential"),
        winrm_scheme="https",
        winrm_transport="ntlm",
        winrm_cert_validation=True,
        status="waiting",
    )
    calls = []

    class FakeBootstrapService:
        def run(self, **kwargs):
            calls.append(kwargs)
            return 'BKINSTALL_EVENT {"action":"install","status":"success","message":"done"}'

    monkeypatch.setattr(installer_tasks, "WindowsRemoteBootstrapService", FakeBootstrapService)
    monkeypatch.setattr(
        installer_tasks.InstallerService,
        "get_install_command",
        lambda *args, **kwargs: "https://server.example/session/secret",
    )
    monkeypatch.setattr(installer_tasks, "_dispatch_or_finalize_controller_task", lambda task_id: None)
    monkeypatch.setattr(
        installer_tasks,
        "exec_command_to_remote",
        lambda *args, **kwargs: pytest.fail("Windows installation must not use SSH"),
    )

    installer_tasks.install_controller_on_nodes(task, [task_node], package)

    task_node.refresh_from_db()
    assert len(calls) == 1
    assert calls[0]["cloud_region_id"] == region.id
    assert calls[0]["session_url"].endswith("/secret")
    assert calls[0]["target"] == WindowsBootstrapTarget(
        host="10.0.0.8",
        port=5986,
        user="Administrator",
        password="credential",
        scheme="https",
        transport="ntlm",
        validate_certificate=True,
    )
    assert task_node.result["overall_status"] == "running"
    assert any(step.get("message") == "done" for step in task_node.result["steps"])


@pytest.mark.django_db
def test_ansible_executor_resolver_selects_healthy_region_executor():
    region = CloudRegion.objects.create(name="windows-bootstrap-region")
    Node.objects.create(
        id="unhealthy-executor",
        name="unhealthy",
        ip="10.0.0.2",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region,
        node_type=ControllerConstants.NODE_TYPE_CONTAINER,
        status={"collectors": [{"collector_id": "ansibleexecutor_linux", "status": 1}]},
    )
    Node.objects.create(
        id="healthy-executor",
        name="healthy",
        ip="10.0.0.3",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region,
        node_type=ControllerConstants.NODE_TYPE_CONTAINER,
        status={"collectors": [{"collector_id": "ansibleexecutor_linux", "status": 0}]},
    )

    assert AnsibleExecutorResolver.resolve(region.id) == "healthy-executor"


@pytest.mark.parametrize(
    ("payload", "error_field"),
    [
        ({"os": "windows", "password": ""}, "password"),
        (
            {
                "os": "windows",
                "password": "credential",
                "winrm_scheme": "http",
                "winrm_transport": "basic",
            },
            "params_error",
        ),
    ],
)
def test_windows_install_node_serializer_rejects_unsafe_credentials(payload, error_field):
    serializer = InstallNodeSerializer(
        data={
            "ip": "10.0.0.8",
            "organizations": [1],
            "port": 5986,
            "username": "Administrator",
            **payload,
        }
    )

    assert not serializer.is_valid()
    assert error_field in serializer.errors


@pytest.mark.unit
@pytest.mark.parametrize(
    "winrm_overrides",
    [
        {"winrm_scheme": "http"},
        {"port": 5985},
        {"winrm_transport": "kerberos"},
        {"winrm_transport": "credssp"},
        {"winrm_transport": "basic"},
        {"winrm_cert_validation": False},
    ],
)
def test_windows_remote_install_accepts_only_the_stable_winrm_profile(winrm_overrides):
    serializer = InstallNodeSerializer(
        data={
            "ip": "10.0.0.8",
            "os": "windows",
            "organizations": [1],
            "port": 5986,
            "username": "Administrator",
            "password": "credential",
            "winrm_scheme": "https",
            "winrm_transport": "ntlm",
            "winrm_cert_validation": True,
            **winrm_overrides,
        }
    )

    assert not serializer.is_valid()
    assert "params_error" in serializer.errors


@pytest.mark.unit
def test_linux_remote_install_keeps_the_existing_ssh_auth_contract():
    serializer = InstallNodeSerializer(
        data={
            "ip": "10.0.0.9",
            "os": "linux",
            "organizations": [1],
            "port": 22,
            "username": "root",
            "private_key": "private-key",
        }
    )

    assert serializer.is_valid(), serializer.errors
