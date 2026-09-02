from types import SimpleNamespace

import pytest

from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode
from apps.node_mgmt.tasks import installer as installer_tasks
from apps.node_mgmt.tasks.installer import _handle_step_exception
from apps.node_mgmt.utils.installer_schema import build_installer_event_record, normalize_failure
from apps.node_mgmt.utils.task_result_schema import normalize_task_result_for_read


class _DummyNode:
    def __init__(self, result=None, cpu_architecture=""):
        self.result = result or {}
        self.cpu_architecture = cpu_architecture

    def save(self, update_fields=None):
        return None


class _InstallNode(_DummyNode):
    def __init__(self, password="", private_key="", passphrase=""):
        super().__init__(result={InstallerConstants.EXECUTION_PHASE_KEY: InstallerConstants.EXECUTION_PHASE_BOOTSTRAP_RUNNING})
        self.password = password
        self.private_key = private_key
        self.passphrase = passphrase
        self.status = InstallerConstants.STEP_STATUS_RUNNING
        self.cpu_architecture = ""


class _FailingCryptor:
    def decode(self, ciphertext):
        if ciphertext == "invalid-ciphertext":
            raise ValueError("invalid encrypted value")
        return "decoded-value"


@pytest.mark.django_db
def test_uninstall_controller_without_credentials_records_exact_failure(monkeypatch):
    region = CloudRegion.objects.create(name="uninstall-no-credentials")
    task = ControllerTask.objects.create(cloud_region=region, type="uninstall", status="pending")
    node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.1.1.1",
        os="linux",
        port=22,
        username="root",
        password="",
        private_key="",
        status="waiting",
        result={},
    )
    monkeypatch.setattr(installer_tasks, "AESCryptor", lambda: SimpleNamespace())
    monkeypatch.setattr(
        installer_tasks,
        "exec_command_to_remote",
        lambda *args, **kwargs: pytest.fail("无凭据时不应执行远程命令"),
    )

    installer_tasks.uninstall_controller(task.id)

    task.refresh_from_db()
    node.refresh_from_db()
    assert task.status == "finished"
    assert node.status == "error"
    assert node.result["steps"][0]["action"] == "credential_check"
    assert node.result["steps"][0]["status"] == "error"
    assert node.result["steps"][0]["message"] == ("Windows requires a password; Linux requires a password or private key.")
    assert node.result["final_message"] == "Credential validation failed"
    assert node.result["overall_status"] == "error"


@pytest.mark.parametrize(
    ("password", "private_key", "passphrase"),
    [
        ("invalid-ciphertext", "", ""),
        ("", "invalid-ciphertext", ""),
        ("", "valid-ciphertext", "invalid-ciphertext"),
    ],
)
def test_install_controller_on_nodes_converges_credential_decryption_failure(monkeypatch, password, private_key, passphrase):
    node = _InstallNode(password=password, private_key=private_key, passphrase=passphrase)
    dispatch_calls = []
    monkeypatch.setattr(installer_tasks, "AESCryptor", _FailingCryptor)
    monkeypatch.setattr(
        installer_tasks,
        "_dispatch_or_finalize_controller_task",
        lambda task_id: dispatch_calls.append(task_id),
    )

    installer_tasks.install_controller_on_nodes(SimpleNamespace(id=4076), [node], SimpleNamespace())

    assert node.status == InstallerConstants.STEP_STATUS_ERROR
    assert node.result[InstallerConstants.EXECUTION_PHASE_KEY] == InstallerConstants.EXECUTION_PHASE_FINISHED
    assert node.result["overall_status"] == InstallerConstants.OVERALL_STATUS_ERROR
    assert node.result["final_message"] == "Credential decryption failed"
    assert node.result["steps"][-1]["status"] == InstallerConstants.STEP_STATUS_ERROR
    assert dispatch_calls == [4076]


def test_normalize_failure_classifies_object_missing_and_preserves_context():
    failure = normalize_failure(
        message="Download failed: get object failed: nats: object not found",
        error="Download failed: get object failed: nats: object not found",
        details={
            "bucket": "bklite",
            "file_key": "linux/arm64/Controller/3.1.22/fusion-collectors-arm64.tar.gz",
            "cpu_architecture": "arm64",
        },
    )

    assert failure is not None
    assert failure["type"] == "object_missing"
    assert failure["summary"] == "Required installation package was not found in object storage"
    assert failure["context"]["bucket"] == "bklite"
    assert failure["context"]["cpu_architecture"] == "arm64"


def test_normalize_failure_classifies_file_busy_and_extracts_target_path():
    failure = normalize_failure(
        message="Extract failed: open /opt/fusion-collectors/bin/vector: text file busy",
        error="Extract failed: open /opt/fusion-collectors/bin/vector: text file busy",
        details={},
    )

    assert failure is not None
    assert failure["type"] == "file_busy"
    assert failure["context"]["target_path"] == "/opt/fusion-collectors/bin/vector"


def test_stop_service_event_uses_current_installer_protocol_position():
    record = build_installer_event_record(
        {
            "step": "stop_service",
            "status": "success",
            "message": "Existing controller service stopped",
        }
    )

    assert record["action"] == "stop_service"
    assert record["details"]["step_index"] == 5
    assert record["details"]["step_total"] == 9


def test_normalize_failure_marks_manual_windows_recovery_as_non_retriable():
    failure = normalize_failure(
        message="Transactional Windows installation failed",
        error="previous installation retained at C:\\fusion-collectors.bklite-backup for recovery",
        details={"error_type": "manual_recovery_required"},
    )

    assert failure is not None
    assert failure["type"] == "manual_recovery_required"
    assert failure["retriable"] is False


def test_windows_transaction_failure_remains_canonical_after_ansible_wrapper_error():
    disk_error = (
        "Transactional Windows installation failed: extract package to staging directory: "
        "write C:\\fusion-collectors.bklite-staging\\bin\\winlogbeat\\winlogbeat.exe: "
        "There is not enough space on the disk."
    )
    normalized = normalize_task_result_for_read(
        {
            "overall_status": "error",
            "failure": {
                "message": "Target host is unreachable over WinRM HTTPS (non-zero return code)",
                "raw_error": "Target host is unreachable over WinRM HTTPS (non-zero return code)",
            },
            "steps": [
                {
                    "action": "run",
                    "status": "running",
                    "message": "Run installer",
                },
                {
                    "action": "extract",
                    "status": "error",
                    "message": disk_error,
                    "details": {
                        "installer_event": True,
                        "raw_step": "run_package_installer",
                        "error": disk_error,
                    },
                },
                {
                    "action": "unknown",
                    "status": "error",
                    "message": "Unexpected error: Target host is unreachable over WinRM HTTPS (non-zero return code)",
                    "details": {
                        "error": "Target host is unreachable over WinRM HTTPS (non-zero return code)",
                    },
                },
            ],
        }
    )

    assert normalized["failure"]["type"] == "disk"
    assert normalized["installer_summary"]["last_step"] == "extract"
    assert normalized["installer_summary"]["last_status"] == "error"
    assert normalized["installer_summary"]["missing_steps"] == ["fetch_session", "prepare_dirs", "download", "write_config", "install"]


def test_normalize_failure_preserves_clock_skew_type_and_context():
    failure = normalize_failure(
        message="Node clock is 726 seconds ahead of Server",
        error="Node clock is 726 seconds ahead of Server",
        details={
            "error_type": "clock_skew",
            "node_time": "2026-07-29T10:12:06Z",
            "server_time": "2026-07-29T10:00:00Z",
            "clock_offset_seconds": 726.0,
            "clock_skew_seconds": 726.0,
            "max_clock_skew_seconds": 300,
        },
    )

    assert failure is not None
    assert failure["type"] == "clock_skew"
    assert failure["retriable"] is False
    assert failure["context"] == {
        "node_time": "2026-07-29T10:12:06Z",
        "server_time": "2026-07-29T10:00:00Z",
        "clock_offset_seconds": 726.0,
        "clock_skew_seconds": 726.0,
        "max_clock_skew_seconds": 300,
    }


def test_clock_check_event_is_optional_for_historical_installer_summaries():
    installer_steps = [
        ("fetch_session", "success"),
        ("prepare_dirs", "success"),
        ("download", "success"),
        ("extract", "success"),
        ("write_config", "success"),
        ("install", "success"),
    ]
    normalized = normalize_task_result_for_read(
        {
            "overall_status": "running",
            "steps": [
                {
                    "action": action,
                    "status": status,
                    "message": action,
                    "details": {"installer_event": True, "raw_step": action},
                }
                for action, status in installer_steps
            ]
            + [{"action": "connectivity_check", "status": "running", "message": "waiting"}],
        }
    )

    assert normalized["installer_summary"]["expected_count"] == 6
    assert normalized["installer_summary"]["completed_count"] == 6
    assert normalized["installer_summary"]["missing_steps"] == []

    with_clock_check = normalize_task_result_for_read(
        {
            "overall_status": "running",
            "steps": [
                {
                    "action": "clock_check",
                    "status": "success",
                    "message": "clock checked",
                    "details": {"installer_event": True, "raw_step": "clock_check"},
                }
            ]
            + normalized["installer_summary"]["steps"]
            + [{"action": "connectivity_check", "status": "running", "message": "waiting"}],
        }
    )
    assert with_clock_check["installer_summary"]["expected_count"] == 7
    assert with_clock_check["installer_summary"]["completed_count"] == 7
    assert "clock_check" in with_clock_check["installer_summary"]["completed_steps"]
    assert with_clock_check["installer_summary"]["missing_steps"] == []
    assert [step["action"] for step in with_clock_check["installer_summary"]["steps"]] == [
        "clock_check",
        *[action for action, _ in installer_steps],
    ]


def test_clock_check_counts_toward_installer_progress_when_present():
    normalized = normalize_task_result_for_read(
        {
            "overall_status": "running",
            "steps": [
                {
                    "action": action,
                    "status": status,
                    "message": action,
                    "details": {"installer_event": True, "raw_step": action},
                }
                for action, status in (
                    ("fetch_session", "success"),
                    ("clock_check", "success"),
                    ("prepare_dirs", "success"),
                    ("download", "running"),
                )
            ]
            + [{"action": "connectivity_check", "status": "waiting", "message": "waiting"}],
        }
    )

    summary = normalized["installer_summary"]
    assert summary["expected_count"] == 7
    assert summary["completed_count"] == 3
    assert summary["completed_steps"] == ["fetch_session", "clock_check", "prepare_dirs"]
    assert summary["expected_steps"][1] == "clock_check"
    assert summary["missing_steps"] == ["extract", "write_config", "install"]


def test_stop_service_counts_toward_current_installer_progress_when_present():
    installer_steps = [
        "fetch_session",
        "clock_check",
        "prepare_dirs",
        "download",
        "stop_service",
        "extract",
        "write_config",
        "install",
    ]
    normalized = normalize_task_result_for_read(
        {
            "overall_status": "running",
            "steps": [
                {
                    "action": action,
                    "status": "success",
                    "message": action,
                    "details": {"installer_event": True, "raw_step": action},
                }
                for action in installer_steps
            ]
            + [{"action": "connectivity_check", "status": "running", "message": "waiting"}],
        }
    )

    summary = normalized["installer_summary"]
    assert summary["expected_steps"] == installer_steps
    assert summary["expected_count"] == 8
    assert summary["completed_count"] == 8
    assert summary["missing_steps"] == []


def test_normalize_failure_ignores_successful_status_messages():
    assert normalize_failure(message="Sidecar acknowledged action", details={}) is None
    assert normalize_failure(message="Collector action completed", details={}) is None

    failure = normalize_failure(message="Collector action failed", details={})
    assert failure is not None
    assert failure["type"] == "unknown"


def test_normalize_failure_classifies_ssh_auth_failure_before_connection():
    failure = normalize_failure(
        message=(
            "Step failed: Failed to create SSH client: ssh: handshake failed: "
            "ssh: unable to authenticate, attempted methods [none password], "
            "no supported methods remain"
        ),
        error=(
            "Failed to create SSH client: ssh: handshake failed: ssh: unable "
            "to authenticate, attempted methods [none password], no supported methods remain"
        ),
        details={},
    )

    assert failure is not None
    assert failure["type"] == "auth"
    assert failure["summary"] == "Authentication failed while accessing the required resource"


def test_normalize_failure_classifies_winrm_certificate_error():
    failure = normalize_failure(
        message=(
            "Ansible task failed: WinRM HTTPS certificate validation failed: the Ansible "
            "Executor does not trust the target host certificate "
            "(ntlm: HTTPSConnectionPool(... CERTIFICATE_VERIFY_FAILED ... unable to get local issuer certificate))"
        ),
        error=(
            "WinRM HTTPS certificate validation failed: the Ansible Executor does not trust "
            "the target host certificate (CERTIFICATE_VERIFY_FAILED)"
        ),
        details={},
    )

    assert failure is not None
    assert failure["type"] == "certificate"
    assert failure["retriable"] is False
    assert "HTTPS certificate validation failed" in failure["summary"]


def test_normalize_failure_classifies_bootstrap_x509_certificate_error():
    failure = normalize_failure(
        message=(
            "Fetch failed: Get https://server.example/installer/session?token=<redacted>: "
            "tls: failed to verify certificate: x509: certificate signed by unknown authority"
        ),
        error="x509: certificate signed by unknown authority",
        details={"step": "fetch_session"},
    )

    assert failure is not None
    assert failure["type"] == "certificate"
    assert failure["retriable"] is False
    assert "HTTPS certificate validation failed" in failure["summary"]


def test_normalize_failure_classifies_winrm_unreachable_as_connection():
    failure = normalize_failure(
        message="Target host is unreachable over WinRM HTTPS (connection refused)",
        error="fatal: [10.10.40.57]: UNREACHABLE! => connection refused",
        details={},
    )

    assert failure is not None
    assert failure["type"] == "connection"
    assert failure["retriable"] is True


def test_normalize_failure_classifies_busy_winrm_session_before_connection():
    failure = normalize_failure(
        message=(
            "WinRM session is busy or stalled (WSMan fault 170 while sending module input). "
            "Wait for the current WinRM operation to finish, then retry."
        ),
        error="WSManFaultError 请求的资源在使用中。 wsmanfault_code: 170; winrm send_input failed",
        details={},
    )

    assert failure is not None
    assert failure["type"] == "winrm_busy"
    assert failure["retriable"] is True
    assert "WinRM session is busy" in failure["summary"]


def test_build_installer_event_record_attaches_typed_failure_metadata():
    event = build_installer_event_record(
        {
            "step": "download_package",
            "status": "failed",
            "message": "Download failed: get object failed: nats: object not found",
            "error": "Download failed: get object failed: nats: object not found",
            "error_type": "object_missing",
            "bucket": "bklite",
            "file_key": "linux/arm64/Controller/3.1.22/fusion-collectors-arm64.tar.gz",
            "cpu_architecture": "arm64",
            "timestamp": "2026-04-28T08:55:32Z",
        }
    )

    assert event["details"]["failure"]["type"] == "object_missing"
    assert event["details"]["failure"]["summary"]
    assert event["details"]["bucket"] == "bklite"
    assert event["details"]["failure"]["context"]["file_key"] == "linux/arm64/Controller/3.1.22/fusion-collectors-arm64.tar.gz"


def test_build_installer_event_record_redacts_session_tokens_from_failures():
    raw_message = (
        'Fetch failed: Get "https://server.example/api/v1/node_mgmt/open_api/'
        'installer/session?token=01234567-89ab-cdef-0123-456789abcdef": unknown authority'
    )

    event = build_installer_event_record(
        {
            "step": "fetch_session",
            "status": "failed",
            "message": raw_message,
            "error": raw_message,
        }
    )

    assert "01234567-89ab-cdef-0123-456789abcdef" not in event["message"]
    assert "token=<redacted>" in event["message"]
    assert "01234567-89ab-cdef-0123-456789abcdef" not in event["details"]["error"]
    assert "01234567-89ab-cdef-0123-456789abcdef" not in event["details"]["failure"]["raw_error"]


def test_installer_event_step_position_keeps_legacy_and_new_protocols_separate():
    legacy_event = build_installer_event_record({"step": "download_package", "status": "running"})
    assert legacy_event["details"]["step_index"] == 3
    assert legacy_event["details"]["step_total"] == 7

    new_event = build_installer_event_record(
        {
            "step": "download_package",
            "status": "running",
            "step_index": 4,
            "step_total": 8,
        }
    )
    assert new_event["details"]["step_index"] == 4
    assert new_event["details"]["step_total"] == 8


def test_handle_step_exception_carries_forward_installer_context():
    node = _DummyNode(
        result={
            "steps": [
                {
                    "action": "download",
                    "status": "error",
                    "message": "Download failed",
                    "timestamp": "2026-04-28T08:55:32Z",
                    "details": {
                        "installer_event": True,
                        "bucket": "bklite",
                        "file_key": "linux/x86_64/Controller/3.1.22/fusion-collectors.tar.gz",
                    },
                }
            ]
        },
        cpu_architecture="x86_64",
    )

    _handle_step_exception(node, "Download failed: get object failed: nats: object not found")

    latest_step = node.result["steps"][-1]
    failure = latest_step["details"]["failure"]
    assert failure["type"] == "object_missing"
    assert failure["context"]["bucket"] == "bklite"
    assert failure["context"]["cpu_architecture"] == "x86_64"


def test_normalize_task_result_for_read_preserves_failure_summary_context():
    normalized = normalize_task_result_for_read(
        {
            "overall_status": "error",
            "steps": [
                {
                    "action": "extract",
                    "status": "error",
                    "message": "Extract failed: open /opt/fusion-collectors/bin/vector: text file busy",
                    "timestamp": "2026-04-28T08:46:26Z",
                    "details": {
                        "error": "Extract failed: open /opt/fusion-collectors/bin/vector: text file busy",
                    },
                }
            ],
        }
    )

    assert normalized["failure"]["type"] == "file_busy"
    assert normalized["failure"]["summary"] == "A running process is blocking the target file from being replaced"
    assert normalized["failure"]["context"]["target_path"] == "/opt/fusion-collectors/bin/vector"


def test_normalize_task_result_for_read_summarizes_missing_installer_events():
    normalized = normalize_task_result_for_read(
        {
            "overall_status": "running",
            "steps": [
                {
                    "action": "credential_check",
                    "status": "success",
                    "message": "Validate credentials (password)",
                },
                {
                    "action": "run",
                    "status": "success",
                    "message": "Installer bootstrap completed",
                },
                {
                    "action": "connectivity_check",
                    "status": "running",
                    "message": "Wait for node connection",
                },
            ],
        }
    )

    summary = normalized["installer_summary"]
    assert summary["state"] == "no_installer_events"
    assert summary["observed_count"] == 0
    assert summary["completed_count"] == 0
    assert summary["missing_steps"] == []
    assert summary["anomalies"] == ["no_installer_events"]

    display = normalized["controller_install_display"]
    assert display["state"] == "installer_no_report"
    assert display["phase"] == "installer_execution"
    assert display["severity"] == "warning"
    assert display["installer_steps_received"] is False


def test_normalize_task_result_for_read_deduplicates_installer_events_and_flags_connectivity_wait():
    installer_steps = [
        ("fetch_session", "success", "Installer session fetched"),
        ("prepare_dirs", "success", "Directories prepared"),
        ("download", "success", "Controller package downloaded"),
        ("extract", "success", "Extracted 3144 files"),
        ("write_config", "success", "Installer runtime configured"),
        ("install", "success", "Package installer finished"),
    ]
    duplicated_steps = []
    for _ in range(2):
        duplicated_steps.extend(
            {
                "action": action,
                "status": status,
                "message": message,
                "details": {
                    "installer_event": True,
                    "raw_step": action,
                },
            }
            for action, status, message in installer_steps
        )

    normalized = normalize_task_result_for_read(
        {
            "overall_status": "running",
            "steps": [
                {"action": "credential_check", "status": "success", "message": "Validate credentials"},
                {"action": "run", "status": "success", "message": "Installer bootstrap completed"},
                *duplicated_steps,
                {"action": "connectivity_check", "status": "running", "message": "Wait for node connection"},
            ],
        }
    )

    summary = normalized["installer_summary"]
    assert summary["state"] == "installer_success_connectivity_pending"
    assert summary["expected_count"] == 6
    assert summary["observed_count"] == 12
    assert summary["completed_count"] == 6
    assert summary["duplicate_count"] == 6
    assert summary["missing_steps"] == []
    assert summary["last_step"] == "install"
    assert summary["last_status"] == "success"
    assert summary["anomalies"] == ["duplicated_events", "installer_success_connectivity_pending"]
    assert [step["action"] for step in summary["steps"]] == [step[0] for step in installer_steps]

    display = normalized["controller_install_display"]
    assert display["state"] == "connectivity_waiting"
    assert display["phase"] == "node_connectivity"
    assert display["severity"] == "processing"
    assert display["installer_steps_received"] is True


def test_normalize_task_result_for_read_treats_installer_events_as_command_dispatched():
    normalized = normalize_task_result_for_read(
        {
            "overall_status": "running",
            "steps": [
                {"action": "credential_check", "status": "success", "message": "Validate credentials"},
                {"action": "run", "status": "running", "message": "Run installer"},
                {
                    "action": "fetch_session",
                    "status": "success",
                    "message": "Installer session fetched",
                    "details": {
                        "installer_event": True,
                        "raw_step": "fetch_session",
                    },
                },
            ],
        }
    )

    display = normalized["controller_install_display"]
    assert display["state"] == "installer_running"
    assert display["phase"] == "installer_execution"
    assert display["severity"] == "processing"
    assert display["installer_steps_received"] is True


def test_normalize_task_result_for_read_reports_success_without_detail():
    normalized = normalize_task_result_for_read(
        {
            "overall_status": "success",
            "steps": [
                {
                    "action": "credential_check",
                    "status": "success",
                    "message": "Validate credentials (password)",
                },
                {
                    "action": "run",
                    "status": "success",
                    "message": "Installer bootstrap completed",
                },
                {
                    "action": "connectivity_check",
                    "status": "success",
                    "message": "Sidecar connectivity confirmed",
                },
            ],
        }
    )

    summary = normalized["installer_summary"]
    assert summary["state"] == "installer_success_without_detail"
    assert summary["missing_steps"] == []

    display = normalized["controller_install_display"]
    assert display["state"] == "success_without_detail"
    assert display["phase"] == "node_connectivity"
    assert display["severity"] == "success"
    assert display["installer_steps_received"] is False


def test_normalize_task_result_for_read_reports_no_report_connectivity_timeout():
    normalized = normalize_task_result_for_read(
        {
            "overall_status": "error",
            "steps": [
                {
                    "action": "credential_check",
                    "status": "success",
                    "message": "Validate credentials (password)",
                },
                {
                    "action": "run",
                    "status": "success",
                    "message": "Installer bootstrap completed",
                },
                {
                    "action": "connectivity_check",
                    "status": "error",
                    "message": "Connectivity check timeout",
                    "details": {"timeout": True},
                },
            ],
        }
    )

    summary = normalized["installer_summary"]
    assert summary["state"] == "installer_no_report_connectivity_timeout"
    assert summary["missing_steps"] == []

    display = normalized["controller_install_display"]
    assert display["state"] == "installer_no_report"
    assert display["phase"] == "installer_execution"
    assert display["severity"] == "error"
    assert display["installer_steps_received"] is False


def test_normalize_task_result_for_read_reports_complete_success_display_state():
    installer_steps = [
        ("fetch_session", "success", "Installer session fetched"),
        ("prepare_dirs", "success", "Directories prepared"),
        ("download", "success", "Controller package downloaded"),
        ("extract", "success", "Extracted 3144 files"),
        ("write_config", "success", "Installer runtime configured"),
        ("install", "success", "Package installer finished"),
    ]

    normalized = normalize_task_result_for_read(
        {
            "overall_status": "success",
            "steps": [
                {"action": "credential_check", "status": "success", "message": "Validate credentials"},
                {"action": "run", "status": "success", "message": "Installer bootstrap completed"},
                *[
                    {
                        "action": action,
                        "status": status,
                        "message": message,
                        "details": {"installer_event": True, "raw_step": action},
                    }
                    for action, status, message in installer_steps
                ],
                {"action": "connectivity_check", "status": "success", "message": "Sidecar connectivity confirmed"},
            ],
        }
    )

    summary = normalized["installer_summary"]
    assert summary["state"] == "installer_success_connectivity_confirmed"
    assert summary["expected_count"] == 6
    assert summary["completed_count"] == 6

    display = normalized["controller_install_display"]
    assert display["state"] == "success"
    assert display["phase"] == "node_connectivity"
    assert display["severity"] == "success"
    assert display["installer_steps_received"] is True


def test_normalize_task_result_for_read_terminal_success_dominates_partial_installer_telemetry():
    normalized = normalize_task_result_for_read(
        {
            "overall_status": "success",
            "steps": [
                {"action": "credential_check", "status": "success", "message": "Validate credentials"},
                {"action": "run", "status": "success", "message": "Installer bootstrap completed"},
                {
                    "action": "fetch_session",
                    "status": "success",
                    "message": "Installer session fetched",
                    "details": {"installer_event": True, "raw_step": "fetch_session"},
                },
                {
                    "action": "extract",
                    "status": "success",
                    "message": "Controller package staged and activated",
                    "details": {"installer_event": True, "raw_step": "extract_package"},
                },
                {"action": "connectivity_check", "status": "success", "message": "Sidecar connectivity confirmed"},
            ],
        }
    )

    summary = normalized["installer_summary"]
    assert summary["state"] == "installer_success_with_incomplete_detail"
    assert summary["missing_steps"] == ["prepare_dirs", "download", "write_config", "install"]
    assert "incomplete_installer_events" in summary["anomalies"]

    display = normalized["controller_install_display"]
    assert display == {
        "state": "success_with_incomplete_detail",
        "phase": "node_connectivity",
        "severity": "success",
        "installer_steps_received": True,
    }


def test_normalize_task_result_for_read_reports_incomplete_installer_events():
    normalized = normalize_task_result_for_read(
        {
            "overall_status": "error",
            "steps": [
                {
                    "action": "fetch_session",
                    "status": "success",
                    "message": "Installer session fetched",
                    "details": {"installer_event": True, "raw_step": "fetch_session"},
                },
                {
                    "action": "download",
                    "status": "error",
                    "message": "Download failed",
                    "details": {"installer_event": True, "raw_step": "download_package", "error": "Download failed"},
                },
            ],
        }
    )

    summary = normalized["installer_summary"]
    assert summary["state"] == "incomplete_installer_events"
    assert summary["completed_count"] == 1
    assert summary["last_step"] == "download"
    assert summary["last_status"] == "error"
    assert summary["missing_steps"] == ["prepare_dirs", "extract", "write_config", "install"]
    assert summary["anomalies"] == ["incomplete_installer_events"]

    display = normalized["controller_install_display"]
    assert display["state"] == "installer_failed"
    assert display["phase"] == "installer_execution"
    assert display["severity"] == "error"
