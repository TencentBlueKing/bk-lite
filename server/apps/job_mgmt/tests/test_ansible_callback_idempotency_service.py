"""Ansible 回调、取消收敛与终态 outbox 的真实数据库竞争测试。"""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connection

from apps.job_mgmt.constants import CallbackType, ExecutionStatus, JobType, TargetSource
from apps.job_mgmt.models import JobCompletionOutbox, JobExecution
from apps.job_mgmt.nats_api import ansible_task_callback
from apps.job_mgmt.tasks import finalize_cancelling_execution

pytestmark = pytest.mark.django_db(transaction=True)


def _execution(status=ExecutionStatus.RUNNING, callback_type=CallbackType.WEB, callback_url=None):
    return JobExecution.objects.create(
        name="callback-race",
        job_type=JobType.SCRIPT,
        status=status,
        target_source=TargetSource.MANUAL,
        target_list=[{"target_id": "target-1", "name": "host-1", "ip": "10.0.0.1"}],
        total_count=1,
        timeout=60,
        callback_type=callback_type,
        callback_url=callback_url,
        team=[1],
        created_by="testuser",
        updated_by="testuser",
    )


def _callback(execution_id, host_status="success", stdout="ok"):
    return {
        "task_id": execution_id,
        "result": [
            {
                "host": "10.0.0.1",
                "status": host_status,
                "stdout": stdout,
                "stderr": "",
                "exit_code": 0 if host_status == "success" else 1,
            }
        ],
    }


def _thread_call(func, barrier=None):
    close_old_connections()
    try:
        if barrier:
            barrier.wait(timeout=10)
        return func()
    finally:
        close_old_connections()


def _skip_non_postgresql():
    if connection.vendor != "postgresql":
        pytest.skip("需要 PostgreSQL 行锁语义")


def test_concurrent_callbacks_commit_one_terminal_result_and_one_effect_set():
    _skip_non_postgresql()
    execution = _execution()
    barrier = threading.Barrier(2)
    calls = [
        lambda: ansible_task_callback(_callback(execution.id, "success", "winner-a")),
        lambda: ansible_task_callback(_callback(execution.id, "failed", "winner-b")),
    ]

    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda call: _thread_call(call, barrier), calls))

    execution.refresh_from_db()
    assert execution.status in (ExecutionStatus.SUCCESS, ExecutionStatus.FAILED)
    assert execution.execution_results[0]["stdout"] in ("winner-a", "winner-b")
    assert sorted(response["message"] for response in responses) == ["任务已处理", "回调处理成功"]
    assert JobCompletionOutbox.objects.filter(execution_id=execution.id).count() == 1


def test_callback_holding_row_lock_fences_timeout_finalizer():
    _skip_non_postgresql()
    execution = _execution(status=ExecutionStatus.CANCELLING)
    callback_has_lock = threading.Event()
    allow_callback_commit = threading.Event()

    from apps.job_mgmt import nats_api

    original_write = nats_api._write_ansible_terminal

    def paused_write(locked_execution, data):
        callback_has_lock.set()
        assert allow_callback_commit.wait(timeout=10)
        return original_write(locked_execution, data)

    with patch("apps.job_mgmt.nats_api._write_ansible_terminal", side_effect=paused_write), patch(
        "apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"
    ):
        with ThreadPoolExecutor(max_workers=2) as executor:
            callback_future = executor.submit(_thread_call, lambda: ansible_task_callback(_callback(execution.id)))
            assert callback_has_lock.wait(timeout=10)
            finalizer_future = executor.submit(_thread_call, lambda: finalize_cancelling_execution(execution.id))
            allow_callback_commit.set()
            assert callback_future.result(timeout=10)["success"] is True
            finalizer_future.result(timeout=10)

    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.CANCELLED
    assert execution.execution_results[0]["stdout"] == "ok"
    assert "远端结果未知" not in execution.execution_results[0].get("error_message", "")
    assert JobCompletionOutbox.objects.filter(execution_id=execution.id).count() == 1


def test_invalid_callback_observes_current_cancelling_state():
    execution = _execution()
    JobExecution.objects.filter(id=execution.id).update(status=ExecutionStatus.CANCELLING)

    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        result = ansible_task_callback({"task_id": execution.id, "result": "invalid"})

    execution.refresh_from_db()
    assert result["success"] is False
    assert execution.status == ExecutionStatus.CANCELLED
    assert JobCompletionOutbox.objects.filter(execution_id=execution.id).count() == 1


def test_outbox_failure_rolls_back_terminal_write():
    execution = _execution()
    with patch(
        "apps.job_mgmt.nats_api.enqueue_terminal_effects",
        side_effect=RuntimeError("outbox unavailable"),
    ):
        with pytest.raises(RuntimeError, match="outbox unavailable"):
            ansible_task_callback(_callback(execution.id))

    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.RUNNING
    assert execution.execution_results == []
    assert not JobCompletionOutbox.objects.filter(execution_id=execution.id).exists()


def test_broker_enqueue_failure_keeps_committed_pending_outbox():
    execution = _execution(callback_url="https://example.com/callback")
    with patch(
        "apps.job_mgmt.tasks.deliver_job_completion_outbox.delay",
        side_effect=RuntimeError("broker down"),
    ):
        result = ansible_task_callback(_callback(execution.id))

    execution.refresh_from_db()
    records = JobCompletionOutbox.objects.filter(execution_id=execution.id)
    assert result["success"] is True
    assert execution.status == ExecutionStatus.SUCCESS
    assert records.count() == 2
    assert set(records.values_list("status", flat=True)) == {JobCompletionOutbox.Status.PENDING}
