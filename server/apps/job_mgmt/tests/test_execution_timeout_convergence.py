"""作业执行超时收敛测试。"""

import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.job_mgmt.constants import ExecutionStatus, JobType, TargetSource
from apps.job_mgmt.models import JobCompletionOutbox, JobExecution
from apps.job_mgmt.services.celery_dispatch import dispatch_celery_task
from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService
from apps.job_mgmt.services.execution_timeout_service import ExecutionTimeoutService
from apps.job_mgmt.tasks import _dispatch_execution_job, dispatch_pending_job_completion_outbox

pytestmark = pytest.mark.integration


def _make_execution(status: str, **kwargs) -> JobExecution:
    defaults = {
        "name": "timeout-test",
        "job_type": JobType.SCRIPT,
        "status": status,
        "target_source": TargetSource.MANUAL,
        "target_list": [
            {"target_id": 1, "name": "host-1", "ip": "192.0.2.1"},
            {"target_id": 2, "name": "host-2", "ip": "192.0.2.2"},
        ],
        "timeout": 60,
        "total_count": 2,
        "team": [1],
        "created_by": "tester",
        "updated_by": "tester",
    }
    defaults.update(kwargs)
    return JobExecution.objects.create(**defaults)


@pytest.mark.django_db
def test_expired_running_execution_converges_to_timeout_with_terminal_effects():
    now = timezone.now()
    execution = _make_execution(
        ExecutionStatus.RUNNING,
        started_at=now - timedelta(seconds=120),
        converge_deadline_at=now - timedelta(seconds=1),
        execution_results=[
            {
                "target_key": "1",
                "name": "host-1",
                "ip": "192.0.2.1",
                "status": ExecutionStatus.SUCCESS,
            }
        ],
    )

    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        assert ExecutionTimeoutService.converge(execution.id, now=now) is True

    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.TIMEOUT
    assert execution.finished_at == now
    assert execution.converge_deadline_at is None
    assert execution.success_count == 1
    assert execution.failed_count == 1
    assert execution.execution_results == [
        {
            "target_key": "1",
            "name": "host-1",
            "ip": "192.0.2.1",
            "status": ExecutionStatus.SUCCESS,
        },
        {
            "target_key": "2",
            "name": "host-2",
            "ip": "192.0.2.2",
            "status": ExecutionStatus.TIMEOUT,
            "error_message": "执行超时，未收到最终结果",
        },
    ]
    assert (
        JobCompletionOutbox.objects.filter(
            execution_id=execution.id,
            kind=JobCompletionOutbox.Kind.DONE_SENTINEL,
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_claiming_execution_arms_deadline_from_user_timeout():
    now = timezone.now()
    execution = _make_execution(ExecutionStatus.PENDING, timeout=90)

    with patch("apps.job_mgmt.services.execution_base_service.timezone.now", return_value=now):
        claimed, _ = ExecutionTaskBaseService(execution.id, "test_task").prepare_execution()

    assert claimed is not None
    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.RUNNING
    assert execution.converge_deadline_at == now + timedelta(seconds=150)


@pytest.mark.django_db
def test_dispatch_arms_separate_pending_deadline():
    now = timezone.now()
    execution = _make_execution(ExecutionStatus.PENDING)
    task = MagicMock()
    task.delay.return_value = SimpleNamespace(id="celery-task-1")

    with patch("apps.job_mgmt.services.execution_timeout_service.timezone.now", return_value=now):
        assert dispatch_celery_task(task, execution) == "celery-task-1"

    execution.refresh_from_db()
    assert execution.converge_deadline_at == now + timedelta(seconds=300)


@pytest.mark.django_db
def test_scheduled_dispatch_arms_pending_deadline():
    now = timezone.now()
    execution = _make_execution(ExecutionStatus.PENDING)

    with patch("apps.job_mgmt.services.execution_timeout_service.timezone.now", return_value=now), patch("apps.job_mgmt.tasks.current_app.send_task"):
        assert _dispatch_execution_job(JobType.SCRIPT, execution.id) is True

    execution.refresh_from_db()
    assert execution.converge_deadline_at == now + timedelta(seconds=300)


@pytest.mark.django_db
def test_periodic_reconciliation_only_converges_due_executions():
    now = timezone.now()
    expired = _make_execution(
        ExecutionStatus.RUNNING,
        started_at=now - timedelta(seconds=120),
        converge_deadline_at=now - timedelta(seconds=1),
    )
    active = _make_execution(
        ExecutionStatus.RUNNING,
        started_at=now,
        converge_deadline_at=now + timedelta(seconds=60),
    )
    legacy = _make_execution(ExecutionStatus.RUNNING, started_at=now - timedelta(days=1))

    with patch("apps.job_mgmt.tasks.timezone.now", return_value=now), patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        result = dispatch_pending_job_completion_outbox()

    expired.refresh_from_db()
    active.refresh_from_db()
    legacy.refresh_from_db()
    assert result["timeout_converged"] == 1
    assert expired.status == ExecutionStatus.TIMEOUT
    assert active.status == ExecutionStatus.RUNNING
    assert legacy.status == ExecutionStatus.RUNNING


@pytest.mark.django_db
def test_late_runner_result_cannot_resurrect_timed_out_execution():
    now = timezone.now()
    execution = _make_execution(
        ExecutionStatus.RUNNING,
        started_at=now - timedelta(seconds=120),
        converge_deadline_at=now - timedelta(seconds=1),
    )
    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        assert ExecutionTimeoutService.converge(execution.id, now=now) is True

    execution.refresh_from_db()
    timeout_results = list(execution.execution_results)
    ExecutionTaskBaseService.finalize_execution(
        execution,
        "test_task",
        [
            {"target_key": "1", "status": ExecutionStatus.SUCCESS},
            {"target_key": "2", "status": ExecutionStatus.SUCCESS},
        ],
    )

    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.TIMEOUT
    assert execution.execution_results == timeout_results
    assert execution.terminal_source == JobExecution.TerminalSource.EXECUTION_TIMEOUT


@pytest.mark.django_db
def test_running_lease_renewal_uses_user_timeout_for_each_work_unit():
    now = timezone.now()
    execution = _make_execution(
        ExecutionStatus.RUNNING,
        timeout=30,
        converge_deadline_at=now - timedelta(seconds=1),
    )

    deadline = ExecutionTimeoutService.renew_running(execution.id, now=now, work_units=2)

    execution.refresh_from_db()
    assert deadline == now + timedelta(seconds=120)
    assert execution.converge_deadline_at == deadline


@pytest.mark.django_db
def test_expired_pending_execution_converges_to_failed():
    now = timezone.now()
    execution = _make_execution(
        ExecutionStatus.PENDING,
        converge_deadline_at=now - timedelta(seconds=1),
    )

    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        assert ExecutionTimeoutService.converge(execution.id, now=now) is True

    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.FAILED
    assert execution.terminal_source == JobExecution.TerminalSource.DISPATCH_TIMEOUT
    assert execution.started_at is None
    assert all(result["status"] == ExecutionStatus.FAILED for result in execution.execution_results)


@pytest.mark.django_db
def test_convergence_revokes_the_persisted_celery_task_after_commit(django_capture_on_commit_callbacks):
    now = timezone.now()
    execution = _make_execution(
        ExecutionStatus.RUNNING,
        celery_task_id="celery-stale-1",
        converge_deadline_at=now - timedelta(seconds=1),
    )

    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"), patch(
        "apps.job_mgmt.services.execution_timeout_service.current_app.control.revoke"
    ) as revoke, django_capture_on_commit_callbacks(execute=True):
        assert ExecutionTimeoutService.converge(execution.id, now=now) is True

    revoke.assert_called_once_with("celery-stale-1")


@pytest.mark.django_db
def test_late_runner_error_cannot_replace_timed_out_status():
    now = timezone.now()
    execution = _make_execution(
        ExecutionStatus.RUNNING,
        converge_deadline_at=now - timedelta(seconds=1),
    )
    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        assert ExecutionTimeoutService.converge(execution.id, now=now) is True

    ExecutionTaskBaseService.update_execution_status(
        execution,
        ExecutionStatus.FAILED,
        finished_at=now + timedelta(seconds=1),
    )

    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.TIMEOUT
    assert execution.terminal_source == JobExecution.TerminalSource.EXECUTION_TIMEOUT


@pytest.mark.django_db
def test_convergence_logs_a_stable_bounded_terminal_summary():
    now = timezone.now()
    execution = _make_execution(
        ExecutionStatus.RUNNING,
        converge_deadline_at=now - timedelta(seconds=1),
    )

    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"), patch(
        "apps.job_mgmt.services.execution_timeout_service.logger"
    ) as mock_logger:
        assert ExecutionTimeoutService.converge(execution.id, now=now) is True

    template = "job execution deadline converged: execution_id=%s, terminal_status=%s, terminal_source=%s"
    args = (execution.id, ExecutionStatus.TIMEOUT, JobExecution.TerminalSource.EXECUTION_TIMEOUT)
    mock_logger.info.assert_called_once_with(template, *args)
    record = logging.LogRecord("job", logging.INFO, __file__, 0, template, args, None)
    assert record.getMessage() == (
        f"job execution deadline converged: execution_id={execution.id}, " "terminal_status=timeout, terminal_source=execution_timeout"
    )
