import time
from queue import Queue

import pytest
import yaml
from django.core.cache import cache

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.management.commands.installer_init import Command as InstallerInitCommand
from apps.node_mgmt.models import ControllerTask, ControllerTaskNode, Node, PackageVersion
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.serializers.installer import (
    ControllerInstallRequestSerializer,
    ControllerManualInstallRequestSerializer,
    ControllerUninstallNodeSerializer,
    InstallNodeSerializer,
)
from apps.node_mgmt.services.install_token import InstallTokenService
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.services.windows_remote_bootstrap import (
    AnsibleExecutorResolver,
    WindowsBootstrapTarget,
    WindowsRemoteBootstrapService,
)
from apps.node_mgmt.tasks import installer as installer_tasks
from apps.node_mgmt.utils.task_result_schema import normalize_task_result_for_read


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


@pytest.mark.parametrize(
    ("serializer_class", "data"),
    [
        (
            ControllerInstallRequestSerializer,
            {
                "cloud_region_id": 7,
                "work_node": "executor-node",
                "package_id": 1,
                "cpu_architecture": "x86_64",
                "nodes": [],
            },
        ),
        (
            ControllerManualInstallRequestSerializer,
            {
                "cloud_region_id": 7,
                "os": NodeConstants.WINDOWS_OS,
                "package_id": 1,
                "cpu_architecture": "x86_64",
                "nodes": [],
            },
        ),
    ],
)
def test_controller_install_requests_reject_empty_nodes(serializer_class, data):
    serializer = serializer_class(data=data)

    assert serializer.is_valid() is False
    assert "nodes" in serializer.errors


@pytest.mark.django_db
def test_windows_manual_install_does_not_require_winrm_credentials():
    serializer = ControllerManualInstallRequestSerializer(
        data={
            "cloud_region_id": 7,
            "os": NodeConstants.WINDOWS_OS,
            "package_id": 1,
            "cpu_architecture": NodeConstants.X86_64_ARCH,
            "nodes": [
                {
                    "ip": "10.0.0.5",
                    "os": NodeConstants.WINDOWS_OS,
                    "organizations": [1],
                    "node_id": "manual-windows-node",
                }
            ],
        }
    )

    assert serializer.is_valid(), serializer.errors


def test_manual_recovery_failure_survives_later_generic_failure_projection():
    result = normalize_task_result_for_read(
        {
            "overall_status": "error",
            "steps": [
                {
                    "action": "install",
                    "status": "error",
                    "message": "Previous installation requires manual recovery",
                    "details": {"error_type": "manual_recovery_required"},
                },
                {
                    "action": "run",
                    "status": "error",
                    "message": "Installation failed",
                    "details": {"error": "bootstrap command failed"},
                },
            ],
        }
    )

    assert result["failure"]["type"] == "manual_recovery_required"
    assert result["failure"]["retriable"] is False


def test_controller_remote_install_rejects_mixed_operating_systems():
    serializer = ControllerInstallRequestSerializer(
        data={
            "cloud_region_id": 7,
            "work_node": "executor-node",
            "package_id": 1,
            "cpu_architecture": "x86_64",
            "nodes": [
                {
                    "ip": "10.0.0.1",
                    "os": NodeConstants.LINUX_OS,
                    "organizations": [1],
                    "port": 22,
                    "username": "root",
                },
                {
                    "ip": "10.0.0.2",
                    "os": NodeConstants.WINDOWS_OS,
                    "organizations": [1],
                    "port": 5986,
                    "username": "Administrator",
                    "password": "credential",
                },
            ],
        }
    )

    assert serializer.is_valid() is False
    assert "nodes" in serializer.errors


@pytest.mark.django_db
def test_controller_install_rejects_existing_package_for_other_operating_system():
    windows_package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.WINDOWS_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="package-os-mismatch-test",
        name="controller-windows-mismatch",
    )

    with pytest.raises(BaseAppException, match="operating system mismatch"):
        InstallerService.install_controller(
            cloud_region_id=1,
            work_node="executor-node",
            package_version_id=windows_package.id,
            nodes=[
                {
                    "ip": "10.0.0.4",
                    "node_name": "linux-node",
                    "os": NodeConstants.LINUX_OS,
                    "cpu_architecture": NodeConstants.X86_64_ARCH,
                    "organizations": [1],
                    "port": 22,
                    "username": "root",
                }
            ],
            cpu_architecture=NodeConstants.X86_64_ARCH,
        )

    assert ControllerTask.objects.filter(package_version_id=windows_package.id).exists() is False


@pytest.mark.django_db
def test_retry_controller_rejects_manual_recovery_required_result(monkeypatch):
    region = CloudRegion.objects.create(name="manual-recovery-region")
    package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.WINDOWS_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="manual-recovery-test",
        name="controller-windows",
    )
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="finished",
        package_version_id=package.id,
    )
    task_node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.3",
        node_name="windows-node",
        os=NodeConstants.WINDOWS_OS,
        organizations=[1],
        port=5986,
        status="error",
        result={
            "overall_status": "error",
            "failure": {"type": "manual_recovery_required"},
            "execution_attempt": 2,
        },
    )
    monkeypatch.setattr(installer_tasks, "_dispatch_or_finalize_controller_task", lambda task_id: None)

    with pytest.raises(BaseAppException, match="Manual recovery is required"):
        installer_tasks.retry_controller(task.id, [task_node.id])

    task_node.refresh_from_db()
    assert task_node.status == "error"
    assert task_node.result["failure"]["type"] == "manual_recovery_required"
    assert task_node.result["execution_attempt"] == 2


@pytest.mark.django_db
def test_retry_controller_preserves_generated_install_node_id(monkeypatch):
    region = CloudRegion.objects.create(name="retry-preserve-node-id-region")
    package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.WINDOWS_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="retry-preserve-node-id",
        name="controller-windows",
    )
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="finished",
        package_version_id=package.id,
    )
    task_node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.57",
        node_name="windows-node",
        os=NodeConstants.WINDOWS_OS,
        organizations=[1],
        port=5986,
        username="old-user",
        status="error",
        result={
            InstallerConstants.EXECUTION_ATTEMPT_KEY: 2,
            InstallerConstants.INSTALL_NODE_ID_KEY: "existing-install-node-id",
        },
    )
    monkeypatch.setattr(installer_tasks, "_dispatch_or_finalize_controller_task", lambda task_id: None)

    installer_tasks.retry_controller(
        task.id,
        [task_node.id],
        port=7443,
        username="replacement-user",
    )

    task_node.refresh_from_db()
    assert task_node.port == 7443
    assert task_node.username == "replacement-user"
    assert task_node.result == {
        InstallerConstants.EXECUTION_ATTEMPT_KEY: 3,
        InstallerConstants.INSTALL_NODE_ID_KEY: "existing-install-node-id",
    }


@pytest.mark.django_db
def test_retry_controller_updates_explicit_winrm_configuration(monkeypatch):
    region = CloudRegion.objects.create(name="retry-winrm-config-region")
    package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.WINDOWS_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="retry-winrm-config",
        name="controller-windows",
    )
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="finished",
        package_version_id=package.id,
    )
    task_node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.85",
        node_name="windows-node",
        os=NodeConstants.WINDOWS_OS,
        organizations=[1],
        port=5986,
        username="Administrator",
        password="encrypted-password",
        status="error",
        winrm_scheme="https",
        winrm_transport="ntlm",
        winrm_cert_validation=True,
        result={InstallerConstants.EXECUTION_ATTEMPT_KEY: 1},
    )
    monkeypatch.setattr(installer_tasks, "_dispatch_or_finalize_controller_task", lambda task_id: None)

    installer_tasks.retry_controller(
        task.id,
        [task_node.id],
        port=7443,
        winrm_scheme="https",
        winrm_transport="ntlm",
        winrm_cert_validation=False,
    )

    task_node.refresh_from_db()
    assert task_node.port == 7443
    assert task_node.winrm_scheme == "https"
    assert task_node.winrm_transport == "ntlm"
    assert task_node.winrm_cert_validation is False


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
            port=7443,
            user="Administrator",
            password="credential",
        ),
        timeout=60,
        execution_id="0123456789abcdef0123456789abcdef",
        progress_subject="installer.progress.0123456789abcdef0123456789abcdef",
    )

    assert executor.instance_id == "executor-node"
    assert len(executor.playbook_calls) == 3
    stage, execution, cleanup = executor.playbook_calls
    assert stage["host_credentials"] == [
        {
            "host": "10.0.0.8",
            "port": 7443,
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
    assert stage["extra_vars"]["ansible_winrm_connection_timeout"] == 60

    playbook = yaml.safe_load(execution["playbook_content"])
    block = playbook[0]["tasks"][0]
    commands = block["block"]
    assert commands[0]["name"] == "Verify supported Windows and PowerShell version"
    assert "PowerShell 5.1" in commands[0]["ansible.windows.win_shell"]
    assert commands[1]["ansible.windows.win_file"]["state"] == "absent"
    assert commands[2]["ansible.windows.win_file"]["state"] == "directory"
    assert commands[3]["ansible.windows.win_acl"]["rights"] == "FullControl"
    assert commands[4]["ansible.windows.win_acl"]["user"] == "SYSTEM"
    assert commands[5]["ansible.windows.win_acl_inheritance"]["state"] == "absent"
    assert commands[6]["no_log"] is True
    assert commands[7]["ansible.windows.win_command"]["argv"][1:4] == [
        "--url-file",
        "{{ bklite_session_file }}",
        "--require-https",
    ]
    assert "--skip-tls" not in commands[7]["ansible.windows.win_command"]["argv"]
    assert commands[7]["ansible.windows.win_command"]["argv"][-10:] == [
        "--execution-id",
        "{{ bklite_execution_id }}",
        "--task-node-id",
        "{{ bklite_task_node_id }}",
        "--attempt",
        "{{ bklite_execution_attempt }}",
        "--deadline-unix",
        "{{ bklite_execution_deadline_unix }}",
        "--progress-subject",
        "{{ bklite_progress_subject }}",
    ]
    assert len(block["always"]) == 3
    assert all(task.get("ignore_errors") is True for task in block["always"][:2])
    assert block["always"][2]["ansible.builtin.fail"]["msg"] == "BK-Lite temporary file cleanup failed"
    assert execution["extra_vars"]["bklite_session_url"].endswith("/secret")
    assert execution["extra_vars"]["bklite_session_user"] == "Administrator"
    assert execution["extra_vars"]["bklite_session_file"].endswith("/session.url")
    assert execution["extra_vars"]["bklite_execution_id"] == "0123456789abcdef0123456789abcdef"
    assert execution["extra_vars"]["ansible_winrm_connection_timeout"] == 60
    cleanup_playbook = yaml.safe_load(cleanup["playbook_content"])
    cleanup_tasks = cleanup_playbook[0]["tasks"]
    cleanup_paths = {
        task["ansible.windows.win_file"]["path"]
        for task in cleanup_tasks
        if "ansible.windows.win_file" in task
    }
    assert cleanup_paths == {
        "C:/Windows/Temp/bklite-controller-bootstrap-31-2.exe",
        "C:/Windows/Temp/bklite-controller-session-0123456789abcdef0123456789abcdef",
    }
    assert cleanup["extra_vars"]["ansible_winrm_connection_timeout"] == 60
    assert output.startswith("BKINSTALL_EVENT ")


def test_windows_remote_bootstrap_certificate_opt_out_applies_to_bootstrap_https():
    executor = FakeExecutor("executor-node")
    service = WindowsRemoteBootstrapService(executor_factory=lambda _: executor, resolver=FakeResolver)

    service.run(
        cloud_region_id=7,
        task_node_id=32,
        attempt=1,
        cpu_architecture="x86_64",
        session_url="https://server.example/api/installer/session/secret",
        target=WindowsBootstrapTarget(
            host="10.0.0.8",
            port=5986,
            user="Administrator",
            password="credential",
            validate_certificate=False,
        ),
        timeout=60,
        execution_id="1123456789abcdef0123456789abcdef",
        progress_subject="installer.progress.1123456789abcdef0123456789abcdef",
    )

    execution = executor.playbook_calls[1]
    playbook = yaml.safe_load(execution["playbook_content"])
    argv = playbook[0]["tasks"][0]["block"][7]["ansible.windows.win_command"]["argv"]

    assert "--require-https" in argv
    assert "--skip-tls" in argv


def test_windows_preflight_uses_win_shell_instead_of_nested_powershell_command():
    playbook = yaml.safe_load(WindowsRemoteBootstrapService._execution_playbook())
    task = playbook[0]["tasks"][0]["block"][0]
    command = task["ansible.windows.win_shell"]

    assert "ansible.builtin.raw" not in task
    assert "powershell.exe" not in command
    assert "-Command" not in command
    assert "$os = [Environment]::OSVersion.Version" in command
    assert "$ps = $PSVersionTable.PSVersion" in command
    assert "PowerShell 5.1" in command


def test_windows_uninstall_playbook_is_idempotent_and_bounded():
    playbook = yaml.safe_load(WindowsRemoteBootstrapService._uninstall_playbook())
    task = playbook[0]["tasks"][0]
    module_args = task["ansible.windows.win_shell"]
    command = module_args["_raw_params"]

    assert set(module_args) == {"_raw_params"}
    assert "Get-Service -Name 'sidecar'" in command
    assert "Stop-Service -Name 'sidecar' -Force" in command
    assert "sc.exe delete sidecar" in command
    assert "Remove-Item -LiteralPath" in command
    assert "C:\\fusion-collectors" in command
    assert "C:\\fusion-collectors.bklite-staging" in command
    assert "C:\\fusion-collectors.bklite-backup" in command
    assert "C:\\fusion-collectors.bklite-install.fence" in command
    assert "C:\\fusion-collectors.bklite-install.lock" in command
    assert "Remove-Item -Path {}" not in command


def test_windows_remote_uninstall_submits_secure_winrm_playbook():
    executor = FakeExecutor("executor-node")
    service = WindowsRemoteBootstrapService(executor_factory=lambda _: executor, resolver=FakeResolver)

    service.uninstall(
        cloud_region_id=7,
        task_node_id=41,
        target=WindowsBootstrapTarget(
            host="10.0.0.8",
            port=7443,
            user="Administrator",
            password="credential",
        ),
        timeout=60,
    )

    assert len(executor.playbook_calls) == 1
    call = executor.playbook_calls[0]
    assert call["task_id"].startswith("controller-uninstall-41-")
    assert call["timeout"] == 60
    assert "execute_timeout" not in call
    assert call["extra_vars"]["ansible_winrm_connection_timeout"] == 60
    assert call["host_credentials"][0] == {
        "host": "10.0.0.8",
        "port": 7443,
        "user": "Administrator",
        "password": "credential",
        "connection": "winrm",
        "winrm_scheme": "https",
        "winrm_transport": "ntlm",
        "winrm_cert_validation": True,
    }
    module_args = yaml.safe_load(call["playbook_content"])[0]["tasks"][0]["ansible.windows.win_shell"]
    assert set(module_args) == {"_raw_params"}


@pytest.mark.django_db
def test_windows_uninstall_routes_through_winrm_and_removes_exact_node(monkeypatch):
    region = CloudRegion.objects.create(name="windows-uninstall-region")
    node = Node.objects.create(
        id="windows-uninstall-node",
        name="windows-node",
        ip="10.0.0.57",
        operating_system=NodeConstants.WINDOWS_OS,
        collector_configuration_directory="C:\\fusion-collectors\\generated",
        cloud_region=region,
    )
    task = ControllerTask.objects.create(
        cloud_region=region,
        work_node="executor-node",
        type="uninstall",
        status="waiting",
    )
    task_node = ControllerTaskNode.objects.create(
        task=task,
        node_id=node.id,
        ip=node.ip,
        os=NodeConstants.WINDOWS_OS,
        port=7443,
        username="Administrator",
        password=AESCryptor().encode("credential"),
        winrm_scheme="https",
        winrm_transport="ntlm",
        winrm_cert_validation=True,
        status="waiting",
    )
    captured = {}

    class FakeWindowsRemoteService:
        def uninstall(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(installer_tasks, "WindowsRemoteBootstrapService", FakeWindowsRemoteService)
    monkeypatch.setattr(
        installer_tasks,
        "exec_command_to_remote",
        lambda *args, **kwargs: pytest.fail("Windows uninstall must not use SSH"),
    )

    installer_tasks.uninstall_controller(task.id)

    task.refresh_from_db()
    task_node.refresh_from_db()
    assert task.status == "finished"
    assert task_node.status == "success"
    assert task_node.password == ""
    assert not Node.objects.filter(id=node.id).exists()
    assert captured["cloud_region_id"] == region.id
    assert captured["task_node_id"] == task_node.id
    assert captured["target"] == WindowsBootstrapTarget(
        host=node.ip,
        port=7443,
        user="Administrator",
        password="credential",
        scheme="https",
        transport="ntlm",
        validate_certificate=True,
    )


@pytest.mark.django_db
def test_windows_uninstall_failure_retains_node_and_clears_credentials(monkeypatch):
    region = CloudRegion.objects.create(name="windows-uninstall-failure-region")
    node = Node.objects.create(
        id="windows-uninstall-failure-node",
        name="windows-node",
        ip="10.0.0.58",
        operating_system=NodeConstants.WINDOWS_OS,
        collector_configuration_directory="C:\\fusion-collectors\\generated",
        cloud_region=region,
    )
    task = ControllerTask.objects.create(
        cloud_region=region,
        work_node="executor-node",
        type="uninstall",
        status="waiting",
    )
    task_node = ControllerTaskNode.objects.create(
        task=task,
        node_id=node.id,
        ip=node.ip,
        os=NodeConstants.WINDOWS_OS,
        port=5986,
        username="Administrator",
        password=AESCryptor().encode("credential"),
        status="waiting",
    )

    class FailingWindowsRemoteService:
        def uninstall(self, **kwargs):
            raise BaseAppException("remote uninstall failed")

    monkeypatch.setattr(installer_tasks, "WindowsRemoteBootstrapService", FailingWindowsRemoteService)

    installer_tasks.uninstall_controller(task.id)

    task_node.refresh_from_db()
    assert task_node.status == "error"
    assert task_node.password == ""
    assert Node.objects.filter(id=node.id).exists()


def test_windows_remote_bootstrap_rechecks_ownership_after_staging():
    executor = FakeExecutor("executor-node")
    service = WindowsRemoteBootstrapService(executor_factory=lambda _: executor, resolver=FakeResolver)

    with pytest.raises(BaseAppException, match="cancelled before execution"):
        service.run(
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
            execution_id="cancelled-execution",
            ownership_validator=lambda: False,
        )

    assert len(executor.playbook_calls) == 2
    stage, cleanup = executor.playbook_calls
    assert stage["task_id"] == "controller-bootstrap-stage-31-2"
    assert cleanup["task_id"] == "controller-bootstrap-cleanup-31-2"


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


def test_windows_remote_bootstrap_fallback_cleanup_cannot_mask_success():
    executor = FakeExecutor("executor-node")
    executor.query_results[-1] = {"status": "failed", "error": "temporary cleanup connection failure"}
    service = WindowsRemoteBootstrapService(executor_factory=lambda _: executor, resolver=FakeResolver)

    output = service.run(
        cloud_region_id=7,
        task_node_id=31,
        attempt=1,
        cpu_architecture="x86_64",
        session_url="https://server.example/session",
        target=WindowsBootstrapTarget("10.0.0.8", 5986, "Administrator", "credential"),
        timeout=60,
    )

    assert output.startswith("BKINSTALL_EVENT ")


def test_windows_remote_bootstrap_replays_terminal_failure_events_before_raising():
    executor = FakeExecutor("executor-node")
    executor.query_results = [
        {"status": "success", "result": {"result": []}},
        {
            "status": "failed",
            "error": "bootstrap failed",
            "result": {
                "result": [
                    {
                        "stdout": 'BKINSTALL_EVENT {"step":"download_package","status":"failed","error":"object missing"}'
                    }
                ]
            },
        },
        {"status": "success", "result": {"result": []}},
    ]
    service = WindowsRemoteBootstrapService(executor_factory=lambda _: executor, resolver=FakeResolver)
    events = []

    with pytest.raises(BaseAppException, match="bootstrap failed"):
        service.run(
            cloud_region_id=7,
            task_node_id=31,
            attempt=1,
            cpu_architecture="x86_64",
            session_url="https://server.example/session",
            target=WindowsBootstrapTarget("10.0.0.8", 5986, "Administrator", "credential"),
            timeout=60,
            event_callback=events.append,
        )

    assert events == ['BKINSTALL_EVENT {"step":"download_package","status":"failed","error":"object missing"}']


def test_windows_remote_bootstrap_progress_callback_cannot_mask_primary_failure():
    executor = FakeExecutor("executor-node")
    executor.query_results = [
        {"status": "success", "result": {"result": []}},
        {
            "status": "failed",
            "error": "bootstrap failed",
            "result": {
                "result": [
                    {
                        "stdout": 'BKINSTALL_EVENT {"step":"download_package","status":"failed","error":"object missing"}'
                    }
                ]
            },
        },
        {"status": "success", "result": {"result": []}},
    ]
    service = WindowsRemoteBootstrapService(executor_factory=lambda _: executor, resolver=FakeResolver)

    with pytest.raises(BaseAppException, match="bootstrap failed"):
        service.run(
            cloud_region_id=7,
            task_node_id=31,
            attempt=1,
            cpu_architecture="x86_64",
            session_url="https://server.example/session",
            target=WindowsBootstrapTarget("10.0.0.8", 5986, "Administrator", "credential"),
            timeout=60,
            event_callback=lambda _: (_ for _ in ()).throw(RuntimeError("progress persistence failed")),
        )


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


@pytest.mark.parametrize("session_url", ["http://server.example/session?token=secret", "https:relative-session"])
def test_windows_remote_bootstrap_rejects_insecure_installer_session_url(session_url):
    executor = FakeExecutor("executor-node")
    service = WindowsRemoteBootstrapService(executor_factory=lambda _: executor, resolver=FakeResolver)

    with pytest.raises(BaseAppException, match="HTTPS installer session URL"):
        service.run(
            cloud_region_id=7,
            task_node_id=31,
            attempt=1,
            cpu_architecture="x86_64",
            session_url=session_url,
            target=WindowsBootstrapTarget("10.0.0.8", 5986, "Administrator", "credential"),
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


def test_windows_remote_bootstrap_describes_winrm_certificate_failure():
    result = {
        "status": "failed",
        "error": "ansible playbook failed with exit code 4",
        "result": {
            "result": [
                {
                    "host": "10.10.40.57",
                    "status": "failed",
                    "raw_status": "FAILED",
                    "stdout": "",
                    "stderr": "",
                    "error_message": "",
                }
            ],
            "result_summary": {
                "stdout_combined": (
                    "TASK [Copy bootstrap] **********************************************************\n"
                    "fatal: [10.10.40.57]: UNREACHABLE! => {\n"
                    '  "changed": false,\n'
                    '  "msg": "ntlm: HTTPSConnectionPool(host=\'10.10.40.57\', port=5986): '
                    "Max retries exceeded with url: /wsman (Caused by SSLError(SSLCertVerificationError(1, "
                    "'[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer "
                    "certificate (_ssl.c:1000)')))\",\n"
                    '  "unreachable": true\n'
                    "}\n"
                )
            },
        },
    }

    message = WindowsRemoteBootstrapService._describe_ansible_failure(result)

    assert "WinRM HTTPS certificate validation failed" in message
    assert "does not trust the target host certificate" in message
    assert "certificate validation can be disabled explicitly" in message
    assert "task_id" not in message


def test_windows_remote_bootstrap_describes_busy_winrm_session():
    result = {
        "status": "failed",
        "result": {
            "result": [
                {
                    "host": "10.10.40.117",
                    "status": "failed",
                    "raw_status": "FAILED",
                    "error_message": 'winrm send_input failed; stdout: stderr',
                }
            ],
            "result_summary": {
                "stdout_combined": (
                    "WSMan OperationTimeout during send input, attempting to continue.\n"
                    "WSManFaultError 请求的资源在使用中。 "
                    "(extended fault data: {'http_status_code': 500, 'wsmanfault_code': 170})\n"
                    'fatal: [10.10.40.117]: FAILED! => {"msg": "winrm send_input failed; stdout: stderr"}'
                )
            },
        },
    }

    message = WindowsRemoteBootstrapService._describe_ansible_failure(result)

    assert "WinRM session is busy" in message
    assert "WSMan fault 170" in message
    assert "NATS" not in message


def test_installer_init_uploads_windows_bootstrap_artifact(tmp_path, monkeypatch):
    import io

    uploaded = {}
    file_path = tmp_path / "bklite-controller-bootstrap.exe"
    file_path.write_bytes(b"bootstrap")

    class RejectUnboundedRead:
        def __init__(self, raw_file):
            self.raw_file = raw_file
            self.name = raw_file.name

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.raw_file.close()

        def read(self, size=-1):
            if size is None or size < 0:
                raise AssertionError("installer artifact must not be read into memory at once")
            return self.raw_file.read(size)

        def seek(self, *args):
            return self.raw_file.seek(*args)

    async def fake_upload(file, object_key):
        uploaded["object_key"] = object_key
        uploaded["content"] = file.read(4) + file.read(64)

    def guarded_open(path, mode="r", *args, **kwargs):
        return RejectUnboundedRead(io.open(path, mode, *args, **kwargs))

    monkeypatch.setattr("builtins.open", guarded_open)
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
    assert uploaded["content"] == b"bootstrap"


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
        status="running",
        result={
            "execution_phase": "bootstrap_running",
            "execution_attempt": 1,
            "execution_deadline_unix": int(time.time()) + 3600,
        },
    )
    calls = []
    subscriptions = []
    command_calls = []

    class FakeBootstrapService:
        def run(self, **kwargs):
            calls.append(kwargs)
            return 'BKINSTALL_EVENT {"action":"install","status":"success","message":"done"}'

    monkeypatch.setattr(installer_tasks, "WindowsRemoteBootstrapService", FakeBootstrapService)

    def fake_subscribe(topic, timeout, stop_event):
        subscriptions.append(topic)
        return Queue(), lambda: None

    monkeypatch.setattr(installer_tasks, "subscribe_lines_sync", fake_subscribe)
    def fake_install_command(*args, **kwargs):
        command_calls.append(kwargs)
        return "https://server.example/session/secret"

    monkeypatch.setattr(installer_tasks.InstallerService, "get_install_command", fake_install_command)
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
    assert calls[0]["progress_subject"] == subscriptions[0]
    assert subscriptions[0] == f"installer.progress.{calls[0]['execution_id']}"
    assert command_calls[0]["task_node_id"] == task_node.id
    assert command_calls[0]["execution_id"] == calls[0]["execution_id"]
    assert command_calls[0]["execution_attempt"] == 1
    assert command_calls[0]["execution_deadline_unix"] > int(time.time())
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
    step_count = len(task_node.result["steps"])
    installer_tasks._apply_installer_events_to_node(
        task_node,
        'BKINSTALL_EVENT {"action":"install","status":"success","message":"done"}',
    )
    task_node.refresh_from_db()
    assert len(task_node.result["steps"]) == step_count


@pytest.mark.django_db
def test_pending_connectivity_converges_when_node_connected_before_phase_transition(monkeypatch):
    region = CloudRegion.objects.create(name="early-connectivity-region")
    node_id = "early-connected-windows-node"
    Node.objects.create(
        id=node_id,
        name="windows-node",
        ip="10.0.0.88",
        operating_system=NodeConstants.WINDOWS_OS,
        collector_configuration_directory="C:\\fusion-collectors\\generated",
        cloud_region=region,
    )
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="running",
        work_node="region-nats-executor",
    )
    task_node = ControllerTaskNode.objects.create(
        task=task,
        node_id=node_id,
        ip="10.0.0.88",
        os=NodeConstants.WINDOWS_OS,
        port=5986,
        status="running",
        result={
            InstallerConstants.INSTALL_NODE_ID_KEY: node_id,
            "steps": [
                {"action": "run", "status": "success", "message": "Installer bootstrap completed"},
                {"action": "connectivity_check", "status": "running", "message": "Wait for node connection"},
            ],
        },
    )
    dispatched = []
    monkeypatch.setattr(installer_tasks, "_dispatch_or_finalize_controller_task", dispatched.append)

    installer_tasks._save_node_pending_connectivity(
        task_node,
        "Installation command succeeded, waiting connectivity confirmation",
    )

    task_node.refresh_from_db()
    assert task_node.status == "success"
    assert task_node.result["overall_status"] == "success"
    assert task_node.result["execution_phase"] == "finished"
    assert task_node.result["steps"][-1]["status"] == "success"
    assert dispatched == [task.id]


@pytest.mark.django_db
def test_first_installer_event_completes_command_dispatch_and_activates_child_step():
    region = CloudRegion.objects.create(name="installer-event-dispatch-region")
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="running",
    )
    task_node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.90",
        os=NodeConstants.WINDOWS_OS,
        port=5986,
        status="running",
        result={
            "steps": [
                {"action": "run", "status": "running", "message": "Run installer"},
            ],
        },
    )

    installer_tasks._apply_installer_events_to_node(
        task_node,
        'BKINSTALL_EVENT {"step":"fetch_session","status":"running","message":"Fetching session"}',
    )

    task_node.refresh_from_db()
    steps = task_node.result["steps"]
    assert next(step for step in steps if step["action"] == "run")["status"] == "success"
    assert next(step for step in steps if step["action"] == "fetch_session")["status"] == "running"
    assert sum(step["status"] == "running" for step in steps) == 1


@pytest.mark.django_db
def test_connectivity_callback_is_latched_while_windows_bootstrap_is_still_running(monkeypatch):
    region = CloudRegion.objects.create(name="latched-connectivity-region")
    node_id = "latched-windows-node"
    Node.objects.create(
        id=node_id,
        name="windows-node",
        ip="10.0.0.89",
        operating_system=NodeConstants.WINDOWS_OS,
        collector_configuration_directory="C:\\fusion-collectors\\generated",
        cloud_region=region,
    )
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="running",
        work_node="region-nats-executor",
    )
    task_node = ControllerTaskNode.objects.create(
        task=task,
        node_id=node_id,
        ip="10.0.0.89",
        os=NodeConstants.WINDOWS_OS,
        port=5986,
        status="running",
        result={
            InstallerConstants.INSTALL_NODE_ID_KEY: node_id,
            InstallerConstants.EXECUTION_PHASE_KEY: InstallerConstants.EXECUTION_PHASE_BOOTSTRAP_RUNNING,
            "steps": [
                {"action": "run", "status": "running", "message": "Run installer"},
            ],
        },
    )
    dispatched = []
    monkeypatch.setattr(installer_tasks, "_dispatch_or_finalize_controller_task", dispatched.append)

    installer_tasks.converge_controller_install_connectivity_for_node(node_id)

    task_node.refresh_from_db()
    assert task_node.status == "running"
    assert task_node.result["execution_phase"] == "bootstrap_running"
    assert task_node.result["connectivity_observed"] is True
    assert task_node.result["connectivity_observed_node_id"] == node_id
    assert task_node.result["connectivity_observed_at"]
    assert task_node.connectivity_observed_node_id == node_id
    assert task_node.connectivity_observed_at is not None
    assert dispatched == []

    installer_tasks._update_step_status(
        task_node,
        "success",
        "Installer bootstrap completed",
    )
    installer_tasks._advance_step(
        task_node,
        "success",
        "Installer bootstrap completed",
        next_steps=[
            installer_tasks._build_step(
                "connectivity_check",
                "running",
                "Wait for node connection",
            )
        ],
    )
    installer_tasks._save_node_pending_connectivity(
        task_node,
        "Installation command succeeded, waiting connectivity confirmation",
    )

    task_node.refresh_from_db()
    assert task_node.status == "success"
    assert task_node.result["overall_status"] == "success"
    assert task_node.result["execution_phase"] == "finished"
    assert dispatched == [task.id]


@pytest.mark.django_db
def test_windows_remote_session_token_rejects_revoked_execution_claim(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "windows-remote-session-fence-test",
        }
    }
    cache.clear()
    region = CloudRegion.objects.create(name="session-fence-region")
    task = ControllerTask.objects.create(cloud_region=region, type="install", status="running")
    execution_id = "0123456789abcdef0123456789abcdef"
    execution_deadline_unix = int(time.time()) + 3600
    task_node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.8",
        node_name="windows-session-fence",
        os=NodeConstants.WINDOWS_OS,
        organizations=[1],
        port=5986,
        status="running",
        result={
            "installer_execution_id": execution_id,
            "execution_attempt": 1,
            "execution_phase": "bootstrap_running",
            "execution_deadline_unix": execution_deadline_unix,
        },
    )
    token = InstallTokenService.generate_install_token(
        node_id="install-node-id",
        ip=task_node.ip,
        user="tester",
        os=NodeConstants.WINDOWS_OS,
        package_id="1",
        cloud_region_id=str(region.id),
        organizations=[1],
        node_name=task_node.node_name,
        install_mode="auto",
        task_node_id=task_node.id,
        execution_id=execution_id,
        execution_attempt=1,
        execution_deadline_unix=execution_deadline_unix,
    )

    assert InstallTokenService.validate_and_get_token_data(token)["execution_id"] == execution_id

    task_node.result = {"execution_attempt": 2, "execution_phase": "bootstrap_running"}
    task_node.save(update_fields=["result"])
    with pytest.raises(BaseAppException, match="no longer active"):
        InstallTokenService.validate_and_get_token_data(token)


@pytest.mark.django_db
def test_installer_progress_rejects_stale_execution_events():
    region = CloudRegion.objects.create(name="progress-fencing-region")
    task = ControllerTask.objects.create(cloud_region=region, type="install", status="running")
    task_node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.8",
        node_name="windows-node",
        os=NodeConstants.WINDOWS_OS,
        organizations=[1],
        port=5986,
        username="Administrator",
        password="encrypted",
        result={
            "execution_attempt": 2,
            "installer_execution_id": "current-execution",
            "steps": [],
        },
    )
    current_event = 'BKINSTALL_EVENT {"action":"download","status":"running","message":"current"}'
    stale_event = 'BKINSTALL_EVENT {"action":"download","status":"running","message":"stale"}'

    assert not installer_tasks._apply_installer_events_for_execution(
        task_node.id, stale_event, "old-execution", 1
    )
    assert installer_tasks._apply_installer_events_for_execution(
        task_node.id, current_event, "current-execution", 2
    )
    closed_result = installer_tasks._close_installer_execution(task_node.id, "current-execution", 2)
    assert "installer_execution_id" not in closed_result
    assert not installer_tasks._apply_installer_events_for_execution(
        task_node.id, stale_event, "current-execution", 2
    )

    task_node.refresh_from_db()
    messages = [step.get("message") for step in task_node.result.get("steps", [])]
    assert "current" in messages
    assert "stale" not in messages


@pytest.mark.django_db
def test_installer_execution_claim_rejects_duplicate_delivery_and_fences_terminal_events():
    region = CloudRegion.objects.create(name="progress-claim-region")
    task = ControllerTask.objects.create(cloud_region=region, type="install", status="running")
    task_node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.9",
        node_name="windows-node",
        os=NodeConstants.WINDOWS_OS,
        organizations=[1],
        port=5986,
        result={"execution_phase": "bootstrap_running", "execution_attempt": 3, "steps": []},
    )

    assert installer_tasks._claim_installer_execution(task_node.id, "first-execution", 3) is not None
    assert installer_tasks._claim_installer_execution(task_node.id, "duplicate-execution", 3) is None

    terminal_event = 'BKINSTALL_EVENT {"action":"download","status":"running","message":"first"}'
    finished = installer_tasks._finish_installer_execution(task_node.id, terminal_event, "first-execution", 3)
    assert finished is not None
    assert "installer_execution_id" not in finished
    assert installer_tasks._finish_installer_execution(
        task_node.id,
        'BKINSTALL_EVENT {"action":"install","status":"error","message":"stale"}',
        "first-execution",
        3,
    ) is None

    task_node.refresh_from_db()
    messages = [step.get("message") for step in task_node.result.get("steps", [])]
    assert "first" in messages
    assert "stale" not in messages


@pytest.mark.django_db
def test_controller_timeout_fences_stuck_windows_bootstrap(monkeypatch):
    region = CloudRegion.objects.create(name="bootstrap-timeout-region")
    task = ControllerTask.objects.create(cloud_region=region, type="install", status="running")
    task_node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.10",
        node_name="windows-node",
        os=NodeConstants.WINDOWS_OS,
        organizations=[1],
        port=5986,
        password="encrypted-password",
        result={
            "execution_phase": "bootstrap_running",
            "execution_attempt": 1,
            "installer_execution_id": "stuck-execution",
            "steps": [{"action": "run", "status": "running", "message": "Run installer"}],
        },
        status="running",
    )
    monkeypatch.setattr(installer_tasks, "_dispatch_or_finalize_controller_task", lambda task_id: None)

    installer_tasks.timeout_controller_install_task(task.id)

    task_node.refresh_from_db()
    assert task_node.status == "error"
    assert task_node.password == ""
    assert task_node.result["execution_attempt"] == 2
    assert "installer_execution_id" not in task_node.result
    assert task_node.result["steps"][-1]["status"] == "error"
    assert not installer_tasks._apply_installer_events_for_execution(
        task_node.id,
        'BKINSTALL_EVENT {"action":"install","status":"success","message":"late"}',
        "stuck-execution",
        1,
    )

    task_node.status = "running"
    task_node.result = {
        "execution_phase": "bootstrap_running",
        "execution_attempt": 3,
        "installer_execution_id": "retry-execution",
        "steps": [{"action": "run", "status": "running", "message": "Retry installer"}],
    }
    task_node.save(update_fields=["status", "result"])

    installer_tasks.timeout_controller_install_task(task.id, expected_attempt=1)
    assert installer_tasks._fail_installer_execution(
        task_node.id,
        "stuck-execution",
        1,
        "late failure",
        RuntimeError("late failure"),
    ) is None

    task_node.refresh_from_db()
    assert task_node.status == "running"
    assert task_node.result["execution_attempt"] == 3
    assert task_node.result["installer_execution_id"] == "retry-execution"


@pytest.mark.django_db(transaction=True)
def test_each_dispatched_controller_node_gets_its_own_timeout(monkeypatch):
    region = CloudRegion.objects.create(name="per-node-timeout-region")
    task = ControllerTask.objects.create(cloud_region=region, type="install", status="waiting")
    nodes = [
        ControllerTaskNode.objects.create(
            task=task,
            ip=f"10.0.1.{index}",
            node_name=f"windows-{index}",
            os=NodeConstants.WINDOWS_OS,
            organizations=[1],
            port=5986,
            status="waiting",
            result={"execution_attempt": 1},
        )
        for index in range(1, 5)
    ]
    dispatched = []
    timeouts = []
    monkeypatch.setattr(installer_tasks.install_controller_for_node, "delay", lambda *args: dispatched.append(args))
    monkeypatch.setattr(
        installer_tasks.timeout_controller_install_task,
        "apply_async",
        lambda *args, **kwargs: timeouts.append((args, kwargs)),
    )

    installer_tasks._dispatch_or_finalize_controller_task(task.id)
    assert len(dispatched) == 3
    assert len(timeouts) == 3
    assert {call[1]["args"][2][0] for call in timeouts} == {node.id for node in nodes[:3]}

    first = nodes[0]
    first.status = "error"
    first.result = {"execution_phase": "finished", "execution_attempt": 1}
    first.save(update_fields=["status", "result"])
    installer_tasks._dispatch_or_finalize_controller_task(task.id)

    assert len(dispatched) == 4
    assert len(timeouts) == 4
    assert timeouts[-1][1]["args"] == [task.id, 1, [nodes[3].id]]


@pytest.mark.django_db(transaction=True)
def test_controller_dispatch_failure_releases_node_and_does_not_start_without_timeout(monkeypatch):
    region = CloudRegion.objects.create(name="dispatch-failure-region")
    task = ControllerTask.objects.create(cloud_region=region, type="install", status="waiting")
    task_node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.2.1",
        node_name="windows-dispatch-failure",
        os=NodeConstants.WINDOWS_OS,
        organizations=[1],
        port=5986,
        password="encrypted-password",
        status="waiting",
        result={"execution_attempt": 1},
    )
    installer_calls = []
    monkeypatch.setattr(installer_tasks.install_controller_for_node, "delay", lambda *args: installer_calls.append(args))
    monkeypatch.setattr(
        installer_tasks.timeout_controller_install_task,
        "apply_async",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("broker unavailable")),
    )

    installer_tasks._dispatch_or_finalize_controller_task(task.id)

    task_node.refresh_from_db()
    assert installer_calls == []
    assert task_node.status == "error"
    assert task_node.password == ""
    assert task_node.result["overall_status"] == "error"
    assert task_node.result["steps"][-1]["action"] == "dispatch"


@pytest.mark.django_db(transaction=True)
def test_controller_dispatch_failure_converges_large_batch_without_recursion(monkeypatch):
    region = CloudRegion.objects.create(name="dispatch-large-failure-region")
    task = ControllerTask.objects.create(cloud_region=region, type="install", status="waiting")
    for index in range(1100):
        ControllerTaskNode.objects.create(
            task=task,
            ip=f"10.20.{index // 250}.{index % 250 + 1}",
            node_name=f"windows-dispatch-failure-{index}",
            os=NodeConstants.WINDOWS_OS,
            organizations=[1],
            port=5986,
            password="encrypted-password",
            status="waiting",
            result={"execution_attempt": 1},
        )
    timeout_calls = []
    monkeypatch.setattr(installer_tasks.install_controller_for_node, "delay", lambda *args: pytest.fail("must not run"))

    def fail_timeout(*args, **kwargs):
        timeout_calls.append((args, kwargs))
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(installer_tasks.timeout_controller_install_task, "apply_async", fail_timeout)

    installer_tasks._dispatch_or_finalize_controller_task(task.id)

    task.refresh_from_db()
    nodes = ControllerTaskNode.objects.filter(task=task)
    assert len(timeout_calls) == 1
    assert task.status == "finished"
    assert nodes.filter(status="error", password="").count() == 1100


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
    "payload",
    [
        {"os": "windows", "password": ""},
        {
            "os": "windows",
            "password": "credential",
            "winrm_scheme": "http",
            "winrm_transport": "basic",
        },
    ],
)
@pytest.mark.django_db
def test_windows_remote_request_rejects_unsafe_credentials(payload):
    serializer = ControllerInstallRequestSerializer(
        data={
            "cloud_region_id": 7,
            "work_node": "executor-node",
            "package_id": 1,
            "cpu_architecture": NodeConstants.X86_64_ARCH,
            "nodes": [
                {
                    "ip": "10.0.0.8",
                    "organizations": [1],
                    "port": 5986,
                    "username": "Administrator",
                    **payload,
                }
            ],
        }
    )

    assert not serializer.is_valid()
    assert "nodes" in serializer.errors


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize(
    "winrm_overrides",
    [
        {"winrm_scheme": "http"},
        {"winrm_transport": "kerberos"},
        {"winrm_transport": "credssp"},
        {"winrm_transport": "basic"},
    ],
)
def test_windows_remote_install_accepts_only_the_stable_winrm_profile(winrm_overrides):
    serializer = ControllerInstallRequestSerializer(
        data={
            "cloud_region_id": 7,
            "work_node": "executor-node",
            "package_id": 1,
            "cpu_architecture": NodeConstants.X86_64_ARCH,
            "nodes": [
                {
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
            ],
        }
    )

    assert not serializer.is_valid()
    assert "nodes" in serializer.errors


@pytest.mark.unit
@pytest.mark.django_db
def test_windows_remote_install_allows_explicit_certificate_validation_opt_out():
    serializer = ControllerInstallRequestSerializer(
        data={
            "cloud_region_id": 7,
            "work_node": "executor-node",
            "package_id": 1,
            "cpu_architecture": NodeConstants.X86_64_ARCH,
            "nodes": [
                {
                    "ip": "10.0.0.8",
                    "os": "windows",
                    "organizations": [1],
                    "port": 5986,
                    "username": "Administrator",
                    "password": "credential",
                    "winrm_scheme": "https",
                    "winrm_transport": "ntlm",
                    "winrm_cert_validation": False,
                }
            ],
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["nodes"][0]["winrm_cert_validation"] is False


@pytest.mark.unit
def test_windows_remote_bootstrap_passes_certificate_validation_opt_out_to_executor():
    target = WindowsBootstrapTarget(
        host="10.0.0.8",
        port=5986,
        user="Administrator",
        password="credential",
        validate_certificate=False,
    )

    WindowsRemoteBootstrapService._validate_target(target)

    assert WindowsRemoteBootstrapService._host_credentials(target)[0]["winrm_cert_validation"] is False


@pytest.mark.unit
@pytest.mark.django_db
def test_windows_remote_install_accepts_custom_https_port():
    serializer = ControllerInstallRequestSerializer(
        data={
            "cloud_region_id": 7,
            "work_node": "executor-node",
            "package_id": 1,
            "cpu_architecture": NodeConstants.X86_64_ARCH,
            "nodes": [
                {
                    "ip": "10.0.0.8",
                    "os": "windows",
                    "organizations": [1],
                    "port": 7443,
                    "username": "Administrator",
                    "password": "credential",
                    "winrm_scheme": "https",
                    "winrm_transport": "ntlm",
                    "winrm_cert_validation": True,
                }
            ],
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["nodes"][0]["port"] == 7443


@pytest.mark.unit
@pytest.mark.django_db
def test_windows_remote_install_defaults_to_https_port():
    serializer = ControllerInstallRequestSerializer(
        data={
            "cloud_region_id": 7,
            "work_node": "executor-node",
            "package_id": 1,
            "cpu_architecture": NodeConstants.X86_64_ARCH,
            "nodes": [
                {
                    "ip": "10.0.0.8",
                    "os": "windows",
                    "organizations": [1],
                    "username": "Administrator",
                    "password": "credential",
                }
            ],
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["nodes"][0]["port"] == 5986
    assert serializer.validated_data["nodes"][0]["winrm_cert_validation"] is False


@pytest.mark.unit
def test_windows_remote_uninstall_defaults_to_certificate_validation_disabled():
    serializer = ControllerUninstallNodeSerializer(
        data={
            "node_id": "windows-node",
            "ip": "10.0.0.8",
            "os": "windows",
            "username": "Administrator",
            "password": "credential",
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["port"] == 5986
    assert serializer.validated_data["winrm_cert_validation"] is False


@pytest.mark.unit
def test_windows_remote_uninstall_allows_explicit_certificate_validation():
    serializer = ControllerUninstallNodeSerializer(
        data={
            "node_id": "windows-node",
            "ip": "10.0.0.8",
            "os": "windows",
            "username": "Administrator",
            "password": "credential",
            "winrm_cert_validation": True,
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["winrm_cert_validation"] is True


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
