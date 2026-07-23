"""ansible_task_callback 终态时持久化各目标 done 哨兵。"""
from unittest.mock import patch

import pytest

from apps.job_mgmt.constants import ExecutionStatus, JobType, TargetSource
from apps.job_mgmt.models import JobCompletionOutbox, JobExecution

pytestmark = pytest.mark.django_db


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


def test_ansible_callback_success_persists_done_sentinel_per_target():
    execution = _make_running_execution()
    from apps.job_mgmt.nats_api import ansible_task_callback

    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        ansible_task_callback(
            {
                "task_id": execution.id,
                "task_type": "adhoc",
                "status": "success",
                "success": True,
                "result": [{"host": "1.1.1.1", "status": "success", "stdout": "ok", "stderr": "", "exit_code": 0}],
            }
        )

    record = JobCompletionOutbox.objects.get(
        execution_id=execution.id,
        kind=JobCompletionOutbox.Kind.DONE_SENTINEL,
    )
    assert record.payload["target_key"] == "5"
    assert record.payload["status"] == ExecutionStatus.SUCCESS


def test_ansible_callback_failure_persists_done_sentinel_for_all_targets():
    execution = _make_running_execution()
    from apps.job_mgmt.nats_api import ansible_task_callback

    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
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

    records = JobCompletionOutbox.objects.filter(
        execution_id=execution.id,
        kind=JobCompletionOutbox.Kind.DONE_SENTINEL,
    )
    done_targets = {record.payload["target_key"] for record in records}
    assert done_targets == {"5"}
    assert all(record.payload["status"] == ExecutionStatus.FAILED for record in records)
