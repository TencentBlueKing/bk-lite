import asyncio
import json
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.job_mgmt.constants import ExecutionStatus, JobType, TargetSource, TriggerSource
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.nats_api import ansible_task_callback
from nats_client import clients
from nats_client.exceptions import NatsClientException


@pytest.mark.unit
@pytest.mark.django_db
def test_ansible_task_callback_masks_sensitive_output_in_logs_and_results():
    execution = JobExecution.objects.create(
        name="rpc-sensitive-test",
        job_type=JobType.SCRIPT,
        trigger_source=TriggerSource.MANUAL,
        target_source=TargetSource.MANUAL,
        status=ExecutionStatus.RUNNING,
        target_list=[{"target_id": 1, "name": "host-1", "ip": "10.0.0.1"}],
        total_count=1,
        team=[1],
        started_at=timezone.now(),
    )
    callback_payload = {
        "task_id": execution.id,
        "task_type": "adhoc",
        "status": "success",
        "success": True,
        "error": "inventory_content='[all]\\n10.0.0.1 ansible_password=hunter2'",
        "result": [
            {
                "host": "10.0.0.1",
                "status": "success",
                "stdout": "password=super-secret",
                "stderr": "private_key_content='-----BEGIN PRIVATE KEY-----abc'",
                "exit_code": 0,
                "error_message": "passphrase=my-passphrase",
            }
        ],
    }

    with patch("apps.job_mgmt.nats_api.logger") as mock_logger, patch("apps.job_mgmt.nats_api.send_callback"):
        result = ansible_task_callback(callback_payload)

    execution.refresh_from_db()
    first_log = " ".join(str(arg) for arg in mock_logger.info.call_args_list[0][0])
    persisted = execution.execution_results[0]

    assert result == {"success": True, "message": "回调处理成功"}
    assert "super-secret" not in first_log
    assert "hunter2" not in first_log
    assert "***" in first_log
    assert persisted["stdout"] == "password=***"
    assert persisted["stderr"] == "private_key_content='***'"
    assert persisted["error_message"] == "passphrase=***"


class _DummyResponse:
    def __init__(self, payload):
        self.data = json.dumps(payload).encode()


class _DummyNC:
    def __init__(self, payload):
        self.payload = payload

    async def request(self, subject, payload, timeout):
        return _DummyResponse(self.payload)

    async def close(self):
        return None


@pytest.mark.unit
def test_nats_request_masks_sensitive_error_details():
    async def fake_get_nc_client():
        return _DummyNC(
            {
                "success": False,
                "error": "RemoteError",
                "message": {"password": "top-secret"},
                "result": {"inventory_content": "[all]\\n10.0.0.1 ansible_password=hunter2"},
            }
        )

    with patch("nats_client.clients.get_nc_client", side_effect=fake_get_nc_client):
        with pytest.raises(NatsClientException) as exc_info:
            asyncio.run(clients.request("job", "ansible.playbook", payload="ignored"))

    message = str(exc_info.value)
    assert "top-secret" not in message
    assert "hunter2" not in message
    assert "***" in message


@pytest.mark.unit
def test_nats_request_fallback_log_masks_full_response():
    async def fake_get_nc_client():
        return _DummyNC(
            {
                "success": False,
                "message": "",
                "raw_payload": {"private_key_content": "-----BEGIN PRIVATE KEY-----abc"},
            }
        )

    with patch("nats_client.clients.get_nc_client", side_effect=fake_get_nc_client), patch("nats_client.clients.logger") as mock_logger:
        with pytest.raises(NatsClientException):
            asyncio.run(clients.request("job", "ansible.playbook", payload="ignored"))

    logged = " ".join(str(arg) for arg in mock_logger.error.call_args[0])
    assert "BEGIN PRIVATE KEY" not in logged
    assert "***" in logged
