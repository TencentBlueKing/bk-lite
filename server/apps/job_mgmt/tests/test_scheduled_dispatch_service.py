"""tasks._dispatch_execution_job 的派发封装测试

`execute_scheduled_task` 依赖 :func:`_dispatch_execution_job` 的返回值决定是否把执行
记录置 FAILED（避免 PENDING 孤立）。该 helper 走 ``current_app.send_task``，与
service 层的 ``dispatch_celery_task``（走 ``.delay``）并行，需独立锁定契约：

- 未知作业类型 → 返回 False（不发起派发）；
- send_task 抛异常（broker 不可用）→ 返回 False；
- 派发成功 → 返回 True 且回填 ``celery_task_id``。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.job_mgmt.constants import JobType
from apps.job_mgmt.tasks import _dispatch_execution_job


@pytest.mark.unit
class TestDispatchExecutionJob:
    def test_unknown_job_type_returns_false_without_dispatch(self):
        with patch("apps.job_mgmt.tasks.current_app") as mock_app:
            assert _dispatch_execution_job("not-a-job-type", 1) is False
            mock_app.send_task.assert_not_called()

    def test_broker_error_returns_false(self):
        with patch("apps.job_mgmt.tasks.current_app") as mock_app, patch("apps.job_mgmt.tasks.JobExecution") as mock_exec:
            mock_app.send_task.side_effect = ConnectionError("broker down")
            assert _dispatch_execution_job(JobType.SCRIPT, 7) is False
            # 失败时不回填 celery_task_id
            mock_exec.objects.filter.assert_not_called()

    def test_success_backfills_celery_task_id(self):
        with patch("apps.job_mgmt.tasks.current_app") as mock_app, patch("apps.job_mgmt.tasks.JobExecution") as mock_exec:
            mock_app.send_task.return_value = SimpleNamespace(id="celery-xyz")
            mock_update = MagicMock()
            mock_exec.objects.filter.return_value = mock_update

            assert _dispatch_execution_job(JobType.SCRIPT, 7) is True

            mock_app.send_task.assert_called_once_with("apps.job_mgmt.tasks.execute_script_task", args=[7])
            mock_exec.objects.filter.assert_called_once_with(id=7)
            mock_update.update.assert_called_once_with(celery_task_id="celery-xyz")
