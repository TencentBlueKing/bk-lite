"""Ansible 回调、取消收敛与终态 outbox 的真实数据库竞争测试。"""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connection
from django.utils import timezone

from apps.job_mgmt.constants import CallbackType, ExecutionStatus, JobType, TargetSource
from apps.job_mgmt.models import JobCompletionOutbox, JobExecution
from apps.job_mgmt.nats_api import ansible_task_callback
from apps.job_mgmt.services.completion_outbox_service import deliver_outbox_record
from apps.job_mgmt.tasks import finalize_cancelling_execution

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


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

    def paused_write(locked_execution, data, **kwargs):
        callback_has_lock.set()
        assert allow_callback_commit.wait(timeout=10)
        return original_write(locked_execution, data, **kwargs)

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


def test_timeout_finalizer_first_is_reconciled_by_one_real_callback():
    """兜底先提交时，协调窗口内的真实回调纠正占位结果且复用同一 outbox。"""
    execution = _execution(status=ExecutionStatus.CANCELLING)

    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries") as schedule:
        finalize_cancelling_execution(execution.id)

        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED
        assert execution.terminal_source == JobExecution.TerminalSource.CANCEL_TIMEOUT
        assert "远端结果未知" in execution.execution_results[0]["error_message"]
        record = JobCompletionOutbox.objects.get(execution_id=execution.id)
        record_id = record.pk
        assert record.next_retry_at > timezone.now()
        assert schedule.call_count == 0

        first = ansible_task_callback(_callback(execution.id, stdout="real-result"))
        second = ansible_task_callback(_callback(execution.id, stdout="duplicate"))

    execution.refresh_from_db()
    record.refresh_from_db()
    assert first == {"success": True, "message": "回调处理成功"}
    assert second == {"success": True, "message": "任务已处理"}
    assert execution.status == ExecutionStatus.CANCELLED
    assert execution.terminal_source == JobExecution.TerminalSource.ANSIBLE_CALLBACK
    assert execution.execution_results[0]["stdout"] == "real-result"
    assert record.pk == record_id
    assert record.payload["status"] == ExecutionStatus.SUCCESS
    assert record.next_retry_at is None
    assert JobCompletionOutbox.objects.filter(execution_id=execution.id).count() == 1
    schedule.assert_called_once_with((record_id,))


def test_delivery_claim_first_fences_late_real_callback():
    """投递已获得租约后，占位结果已可能对外可见，不得再改写数据库终态。"""
    _skip_non_postgresql()
    execution = _execution(status=ExecutionStatus.CANCELLING)
    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        finalize_cancelling_execution(execution.id)
    record = JobCompletionOutbox.objects.get(execution_id=execution.id)
    JobCompletionOutbox.objects.filter(pk=record.pk).update(next_retry_at=timezone.now())

    delivery_started = threading.Event()
    allow_delivery = threading.Event()

    def paused_publish(*_args, **_kwargs):
        delivery_started.set()
        assert allow_delivery.wait(timeout=10)

    with patch(
        "apps.job_mgmt.services.completion_outbox_service.publish_done_sentinel",
        side_effect=paused_publish,
    ):
        with ThreadPoolExecutor(max_workers=2) as executor:
            delivery = executor.submit(_thread_call, lambda: deliver_outbox_record(record.pk))
            assert delivery_started.wait(timeout=10)
            callback = _thread_call(lambda: ansible_task_callback(_callback(execution.id, stdout="too-late")))
            allow_delivery.set()
            assert delivery.result(timeout=10) is True

    execution.refresh_from_db()
    assert callback == {"success": True, "message": "任务已处理"}
    assert execution.terminal_source == JobExecution.TerminalSource.CANCEL_TIMEOUT
    assert "远端结果未知" in execution.execution_results[0]["error_message"]


def test_ambiguous_failed_attempt_fences_late_real_callback():
    """远端可能已收到、但本地记为失败的投递不能被当成“从未对外”。"""
    execution = _execution(status=ExecutionStatus.CANCELLING)
    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        finalize_cancelling_execution(execution.id)
    record = JobCompletionOutbox.objects.get(execution_id=execution.id)
    JobCompletionOutbox.objects.filter(pk=record.pk).update(next_retry_at=timezone.now())

    observed = []

    def visible_then_response_lost(*args):
        observed.append(args)
        raise RuntimeError("response lost")

    with patch(
        "apps.job_mgmt.services.completion_outbox_service.publish_done_sentinel",
        side_effect=visible_then_response_lost,
    ):
        with pytest.raises(RuntimeError, match="response lost"):
            deliver_outbox_record(record.pk)

    record.refresh_from_db()
    assert observed
    assert record.status == JobCompletionOutbox.Status.PENDING
    assert record.attempts == 1

    callback = ansible_task_callback(_callback(execution.id, stdout="too-late"))

    execution.refresh_from_db()
    assert callback == {"success": True, "message": "任务已处理"}
    assert execution.terminal_source == JobExecution.TerminalSource.CANCEL_TIMEOUT
    assert "远端结果未知" in execution.execution_results[0]["error_message"]


def test_callback_row_lock_first_refreshes_payload_before_delivery_claim():
    """回调先锁住执行时，投递 claim 必须等到真实载荷与终态一起提交。"""
    _skip_non_postgresql()
    execution = _execution(status=ExecutionStatus.CANCELLING)
    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        finalize_cancelling_execution(execution.id)
    record = JobCompletionOutbox.objects.get(execution_id=execution.id)
    JobCompletionOutbox.objects.filter(pk=record.pk).update(next_retry_at=timezone.now())

    callback_has_lock = threading.Event()
    allow_callback_commit = threading.Event()
    from apps.job_mgmt import nats_api

    original_write = nats_api._write_ansible_terminal

    def paused_write(locked_execution, data, **kwargs):
        callback_has_lock.set()
        assert allow_callback_commit.wait(timeout=10)
        return original_write(locked_execution, data, **kwargs)

    with patch("apps.job_mgmt.nats_api._write_ansible_terminal", side_effect=paused_write), patch(
        "apps.job_mgmt.services.completion_outbox_service.publish_done_sentinel"
    ) as publish, patch("apps.job_mgmt.tasks.deliver_job_completion_outbox.delay"):
        with ThreadPoolExecutor(max_workers=2) as executor:
            callback = executor.submit(_thread_call, lambda: ansible_task_callback(_callback(execution.id, stdout="real")))
            assert callback_has_lock.wait(timeout=10)
            delivery = executor.submit(_thread_call, lambda: deliver_outbox_record(record.pk))
            allow_callback_commit.set()
            assert callback.result(timeout=10) == {"success": True, "message": "回调处理成功"}
            assert delivery.result(timeout=10) is True

    execution.refresh_from_db()
    record.refresh_from_db()
    assert execution.execution_results[0]["stdout"] == "real"
    assert record.payload["status"] == ExecutionStatus.SUCCESS
    publish.assert_called_once_with(execution.id, "target-1", ExecutionStatus.SUCCESS)


def test_legacy_timeout_placeholder_without_outbox_is_not_reconciled():
    execution = _execution(status=ExecutionStatus.CANCELLED)
    execution.terminal_source = None
    execution.execution_results = [
        {
            "target_key": "target-1",
            "status": ExecutionStatus.CANCELLED,
            "error_message": "任务已取消，远端结果未知",
        }
    ]
    execution.save(update_fields=["terminal_source", "execution_results", "updated_at"])

    result = ansible_task_callback(_callback(execution.id, stdout="late-real-result"))

    execution.refresh_from_db()
    assert result == {"success": True, "message": "任务已处理"}
    assert execution.terminal_source is None
    assert "远端结果未知" in execution.execution_results[0]["error_message"]
    assert not JobCompletionOutbox.objects.filter(execution_id=execution.id).exists()


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
