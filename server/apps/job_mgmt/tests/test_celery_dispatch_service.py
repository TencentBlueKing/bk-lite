"""Celery 派发封装的 service 层测试（B3）

验证 :func:`dispatch_celery_task`：

- broker 派发成功时回填 ``celery_task_id``；
- broker 派发抛异常时将执行记录置为 FAILED 并返回 ``None`` —— 调用方据此返回 503，
  避免留下 PENDING 孤立记录。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.services.celery_dispatch import dispatch_celery_task


@pytest.fixture
def pending_execution(db):
    return JobExecution.objects.create(
        name="test-execution",
        job_type=JobType.SCRIPT,
        status=ExecutionStatus.PENDING,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestDispatchCeleryTask:
    def test_success_persists_celery_task_id(self, pending_execution):
        task_func = MagicMock(name="task_func")
        task_func.delay.return_value = SimpleNamespace(id="celery-abc")

        task_id = dispatch_celery_task(task_func, pending_execution)

        assert task_id == "celery-abc"
        pending_execution.refresh_from_db()
        assert pending_execution.celery_task_id == "celery-abc"
        assert pending_execution.status == ExecutionStatus.PENDING

    def test_broker_error_marks_execution_failed_and_returns_none(self, pending_execution):
        task_func = MagicMock(name="task_func")
        task_func.delay.side_effect = ConnectionError("broker unreachable")

        task_id = dispatch_celery_task(task_func, pending_execution)

        assert task_id is None
        pending_execution.refresh_from_db()
        assert pending_execution.status == ExecutionStatus.FAILED
        assert pending_execution.celery_task_id == ""

    def test_dispatch_failure_does_not_swallow_unrelated_db_changes(self, pending_execution):
        """status 字段持久化使用 update_fields，避免覆盖其他字段（如 callback_url）"""
        pending_execution.callback_url = "http://example.com/cb"
        pending_execution.save(update_fields=["callback_url", "updated_at"])

        task_func = MagicMock(name="task_func")
        task_func.delay.side_effect = RuntimeError("broker down")
        dispatch_celery_task(task_func, pending_execution)

        pending_execution.refresh_from_db()
        assert pending_execution.status == ExecutionStatus.FAILED
        assert pending_execution.callback_url == "http://example.com/cb"
