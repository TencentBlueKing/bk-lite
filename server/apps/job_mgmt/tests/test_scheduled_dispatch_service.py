"""tasks._dispatch_execution_job 的派发封装测试

`execute_scheduled_task` 依赖 :func:`_dispatch_execution_job` 的返回值决定是否把执行
记录置 FAILED（避免 PENDING 孤立）。该 helper 走 ``current_app.send_task``，与
service 层的 ``dispatch_celery_task``（走 ``.delay``）并行，需独立锁定契约：

- 未知作业类型 → 返回 False（不发起派发）；
- send_task 抛异常（broker 不可用）→ 返回 False；
- 派发前写入 ``celery_task_id``，成功时返回 True。
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

    def test_broker_error_retains_task_id_and_revokes(self):
        with patch("apps.job_mgmt.tasks.current_app") as mock_app, patch("apps.job_mgmt.tasks.JobExecution") as mock_exec:
            mock_app.send_task.side_effect = ConnectionError("broker down")
            mock_exec.objects.filter.return_value.update.return_value = 1

            assert _dispatch_execution_job(JobType.SCRIPT, 7) is False

            persisted_task_id = mock_exec.objects.filter.return_value.update.call_args_list[0].kwargs["celery_task_id"]
            mock_app.send_task.assert_called_once_with(
                "apps.job_mgmt.tasks.execute_script_task",
                args=[7],
                task_id=persisted_task_id,
            )
            mock_app.control.revoke.assert_called_once_with(persisted_task_id)
            mock_exec.objects.filter.assert_called_once_with(id=7)
            mock_exec.objects.filter.return_value.update.assert_called_once_with(celery_task_id=persisted_task_id)

    def test_missing_execution_returns_false_without_dispatch(self):
        with patch("apps.job_mgmt.tasks.current_app") as mock_app, patch("apps.job_mgmt.tasks.JobExecution") as mock_exec:
            mock_exec.objects.filter.return_value.update.return_value = 0

            assert _dispatch_execution_job(JobType.SCRIPT, 7) is False

            mock_app.send_task.assert_not_called()

    def test_persist_error_returns_false_without_dispatch(self):
        with patch("apps.job_mgmt.tasks.current_app") as mock_app, patch("apps.job_mgmt.tasks.JobExecution") as mock_exec:
            mock_exec.objects.filter.return_value.update.side_effect = OSError("database unavailable")

            assert _dispatch_execution_job(JobType.SCRIPT, 7) is False

            mock_app.send_task.assert_not_called()

    def test_broker_and_revoke_errors_retain_task_id(self):
        with patch("apps.job_mgmt.tasks.current_app") as mock_app, patch("apps.job_mgmt.tasks.JobExecution") as mock_exec:
            mock_exec.objects.filter.return_value.update.return_value = 1
            mock_app.send_task.side_effect = ConnectionError("publish result unknown")
            mock_app.control.revoke.side_effect = ConnectionError("control unavailable")

            assert _dispatch_execution_job(JobType.SCRIPT, 7) is False

            mock_exec.objects.filter.return_value.update.assert_called_once()

    def test_success_persists_task_id_before_dispatch(self):
        with patch("apps.job_mgmt.tasks.current_app") as mock_app, patch("apps.job_mgmt.tasks.JobExecution") as mock_exec:
            mock_update = MagicMock()
            mock_exec.objects.filter.return_value = mock_update
            events = []
            mock_update.update.side_effect = lambda **kwargs: events.append(("persist", kwargs)) or 1
            mock_app.send_task.side_effect = lambda *args, **kwargs: events.append(("dispatch", kwargs)) or SimpleNamespace(id=kwargs["task_id"])

            assert _dispatch_execution_job(JobType.SCRIPT, 7) is True

            mock_exec.objects.filter.assert_called_once_with(id=7)
            persisted_task_id = events[0][1]["celery_task_id"]
            assert events == [
                ("persist", {"celery_task_id": persisted_task_id}),
                ("dispatch", {"args": [7], "task_id": persisted_task_id}),
            ]
