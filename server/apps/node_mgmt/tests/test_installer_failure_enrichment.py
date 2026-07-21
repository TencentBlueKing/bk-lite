from types import SimpleNamespace

import pytest

from apps.node_mgmt.constants.installer import InstallerConstants
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
        super().__init__(
            result={InstallerConstants.EXECUTION_PHASE_KEY: InstallerConstants.EXECUTION_PHASE_BOOTSTRAP_RUNNING}
        )
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


@pytest.mark.parametrize(
    ("password", "private_key", "passphrase"),
    [
        ("invalid-ciphertext", "", ""),
        ("", "invalid-ciphertext", ""),
        ("", "valid-ciphertext", "invalid-ciphertext"),
    ],
)
def test_install_controller_on_nodes_converges_credential_decryption_failure(
    monkeypatch, password, private_key, passphrase
):
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
