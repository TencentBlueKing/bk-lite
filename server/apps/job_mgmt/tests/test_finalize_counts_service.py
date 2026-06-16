"""finalize / update_execution_counts 的 service 层测试（B2）

验证 :meth:`ExecutionTaskBaseService.update_execution_counts` 在事务内使用
``select_for_update`` 包裹"读 execution_results → 计数 → 写 counts"，
消除并发读改写窗口；同时保证传入的实例字段被回写为最新值。
"""

import pytest

from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService


@pytest.fixture
def execution_with_results(db):
    return JobExecution.objects.create(
        name="test-finalize",
        job_type=JobType.SCRIPT,
        status=ExecutionStatus.RUNNING,
        execution_results=[
            {"status": ExecutionStatus.SUCCESS},
            {"status": ExecutionStatus.SUCCESS},
            {"status": ExecutionStatus.FAILED},
            {"status": ExecutionStatus.TIMEOUT},
            {"status": ExecutionStatus.RUNNING},  # 未完成不计入失败
        ],
        total_count=5,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestUpdateExecutionCounts:
    def test_counts_computed_from_execution_results(self, execution_with_results):
        ExecutionTaskBaseService.update_execution_counts(execution_with_results)
        execution_with_results.refresh_from_db()
        assert execution_with_results.success_count == 2
        assert execution_with_results.failed_count == 2

    def test_in_memory_instance_reflects_updated_counts(self, execution_with_results):
        """避免调用方读到旧值导致 final_status 判断错误"""
        ExecutionTaskBaseService.update_execution_counts(execution_with_results)
        assert execution_with_results.success_count == 2
        assert execution_with_results.failed_count == 2

    def test_empty_results_set_counts_to_zero(self, db):
        execution = JobExecution.objects.create(
            name="empty",
            job_type=JobType.SCRIPT,
            status=ExecutionStatus.RUNNING,
            execution_results=[],
        )
        ExecutionTaskBaseService.update_execution_counts(execution)
        execution.refresh_from_db()
        assert execution.success_count == 0
        assert execution.failed_count == 0

    def test_select_for_update_runs_inside_transaction(self, execution_with_results, mocker):
        """实现要点：必须在事务里调用 select_for_update（否则 Django 抛 TransactionManagementError）。"""
        atomic_spy = mocker.spy(__import__("django.db", fromlist=["transaction"]).transaction, "atomic")
        ExecutionTaskBaseService.update_execution_counts(execution_with_results)
        assert atomic_spy.called, "update_execution_counts 必须包裹在 transaction.atomic 内"
