"""Ansible 回调终态写入的幂等性回归测试。"""

from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.job_mgmt.constants import ExecutionStatus, JobType, TargetSource
from apps.job_mgmt.models import JobExecution


@pytest.mark.unit
@pytest.mark.django_db
def test_stale_callback_losing_terminal_transition_does_not_notify():
    """竞争回调输掉终态 CAS 后，不得覆盖结果或重复发送通知。"""
    from apps.job_mgmt.nats_api import ansible_task_callback

    execution = MagicMock()
    execution.id = 4132
    execution.status = ExecutionStatus.RUNNING
    execution.target_list = [{"target_id": "target-1", "name": "host-1", "ip": "10.0.0.1"}]
    execution.started_at = timezone.now()
    execution.playbook_id = None

    transition = MagicMock()
    transition.update.return_value = 0
    callback_data = {
        "task_id": execution.id,
        "result": [
            {
                "host": "10.0.0.1",
                "status": "success",
                "stdout": "ok",
                "stderr": "",
                "exit_code": 0,
            }
        ],
    }

    with (
        patch("apps.job_mgmt.nats_api.JobExecution.objects.get", return_value=execution),
        patch("apps.job_mgmt.nats_api.JobExecution.objects.filter", return_value=transition),
        patch("apps.job_mgmt.nats_api.publish_done_sentinel") as publish_done_sentinel,
        patch("apps.job_mgmt.nats_api.send_callback") as send_callback,
    ):
        result = ansible_task_callback(callback_data)

    assert result == {"success": True, "message": "任务已处理"}
    transition.update.assert_called_once()
    execution.save.assert_not_called()
    publish_done_sentinel.assert_not_called()
    send_callback.assert_not_called()


@pytest.mark.unit
@pytest.mark.django_db
def test_invalid_stale_callback_preserves_concurrent_cancelling_state():
    """解析失败时若数据库已进入 CANCELLING，最终仍应收敛为 CANCELLED。"""
    from apps.job_mgmt.nats_api import ansible_task_callback

    execution = JobExecution.objects.create(
        name="callback-race",
        job_type=JobType.SCRIPT,
        status=ExecutionStatus.RUNNING,
        target_source=TargetSource.MANUAL,
        target_list=[{"target_id": "target-1", "name": "host-1", "ip": "10.0.0.1"}],
        timeout=60,
        team=[1],
        created_by="testuser",
        updated_by="testuser",
    )
    stale_execution = JobExecution.objects.get(id=execution.id)
    JobExecution.objects.filter(id=execution.id).update(status=ExecutionStatus.CANCELLING)

    with (
        patch("apps.job_mgmt.nats_api.JobExecution.objects.get", return_value=stale_execution),
        patch("apps.job_mgmt.nats_api.publish_done_sentinel"),
        patch("apps.job_mgmt.nats_api.send_callback") as send_callback,
    ):
        result = ansible_task_callback({"task_id": execution.id, "result": "invalid"})

    execution.refresh_from_db()
    assert result["success"] is False
    assert execution.status == ExecutionStatus.CANCELLED
    assert send_callback.call_args.args[0].status == ExecutionStatus.CANCELLED
