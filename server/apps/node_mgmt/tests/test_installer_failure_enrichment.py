import pytest

from apps.node_mgmt.tasks.installer import _handle_step_exception
from apps.node_mgmt.utils.installer_schema import build_installer_event_record, normalize_failure
from apps.node_mgmt.utils.task_result_schema import normalize_task_result_for_read


class _DummyNode:
    def __init__(self, result=None, cpu_architecture=""):
        self.result = result or {}
        self.cpu_architecture = cpu_architecture

    def save(self, update_fields=None):
        return None


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
