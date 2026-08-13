"""Ansible 终态回调的执行身份契约。"""

import pytest

from apps.job_mgmt.constants import ExecutionStatus, JobType, TargetSource
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.nats_api import ansible_task_callback
from apps.job_mgmt.services.ansible_callback_service import issue_ansible_callback_identity

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _execution():
    return JobExecution.objects.create(
        name="callback-auth",
        job_type=JobType.SCRIPT,
        status=ExecutionStatus.RUNNING,
        target_source=TargetSource.MANUAL,
        target_list=[{"target_id": 1, "name": "host", "ip": "127.0.0.1"}],
        team=[1],
    )


def _payload(execution, context=None):
    payload = {
        "task_id": execution.id,
        "result": [{"host": "127.0.0.1", "status": "success", "stdout": "ok"}],
    }
    if context is not None:
        payload["callback_context"] = context
    return payload


def test_missing_callback_identity_cannot_write_terminal_state():
    execution = _execution()
    issue_ansible_callback_identity(execution)

    result = ansible_task_callback(_payload(execution))

    execution.refresh_from_db()
    assert result == {"success": False, "message": "回调身份校验失败"}
    assert execution.status == ExecutionStatus.RUNNING


def test_forged_callback_token_cannot_write_terminal_state():
    execution = _execution()
    context = issue_ansible_callback_identity(execution)
    context["token"] = "forged"

    result = ansible_task_callback(_payload(execution, context))

    execution.refresh_from_db()
    assert result == {"success": False, "message": "回调身份校验失败"}
    assert execution.status == ExecutionStatus.RUNNING


def test_stale_callback_attempt_cannot_write_terminal_state():
    execution = _execution()
    stale_context = issue_ansible_callback_identity(execution)
    issue_ansible_callback_identity(execution)

    result = ansible_task_callback(_payload(execution, stale_context))

    execution.refresh_from_db()
    assert result == {"success": False, "message": "回调身份校验失败"}
    assert execution.status == ExecutionStatus.RUNNING


def test_current_callback_identity_can_write_terminal_state():
    execution = _execution()
    context = issue_ansible_callback_identity(execution)

    result = ansible_task_callback(_payload(execution, context))

    execution.refresh_from_db()
    assert result["success"] is True
    assert execution.status == ExecutionStatus.SUCCESS
