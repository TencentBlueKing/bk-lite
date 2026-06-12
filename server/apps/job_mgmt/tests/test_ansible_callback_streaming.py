"""ansible_task_callback 终态时为各目标补发 done 哨兵（Important #2，避免 SSE 空等）。"""
from unittest.mock import patch

import pytest

from apps.job_mgmt.constants import ExecutionStatus, JobType, TargetSource
from apps.job_mgmt.models import JobExecution

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _make_running_execution():
    return JobExecution.objects.create(
        name="t",
        job_type=JobType.SCRIPT,
        status=ExecutionStatus.RUNNING,
        target_source=TargetSource.MANUAL,
        target_list=[{"target_id": 5, "name": "h1", "ip": "1.1.1.1"}],
        team=[1],
        created_by="u",
        updated_by="u",
    )


def test_ansible_callback_success_emits_done_sentinel_per_target():
    execution = _make_running_execution()
    from apps.job_mgmt.nats_api import ansible_task_callback

    with patch("apps.job_mgmt.nats_api.publish_done_sentinel") as mock_done, \
         patch("apps.job_mgmt.nats_api.send_callback"):
        ansible_task_callback(
            {
                "task_id": execution.id,
                "task_type": "adhoc",
                "status": "success",
                "success": True,
                "result": [
                    {"host": "1.1.1.1", "status": "success", "stdout": "ok", "stderr": "", "exit_code": 0}
                ],
            }
        )

    mock_done.assert_called_once_with(execution.id, "5", ExecutionStatus.SUCCESS)


def test_ansible_callback_failure_emits_done_sentinel_for_all_targets():
    execution = _make_running_execution()
    from apps.job_mgmt.nats_api import ansible_task_callback

    with patch("apps.job_mgmt.nats_api.publish_done_sentinel") as mock_done, \
         patch("apps.job_mgmt.nats_api.send_callback"):
        # 非法结果格式 → 走 _fail_execution 收敛路径
        ansible_task_callback(
            {
                "task_id": execution.id,
                "task_type": "adhoc",
                "status": "failed",
                "success": False,
                "result": "not-a-list",
                "error": "boom",
            }
        )

    done_targets = {c.args[1] for c in mock_done.call_args_list}
    assert done_targets == {"5"}
    assert all(c.args[2] == ExecutionStatus.FAILED for c in mock_done.call_args_list)
