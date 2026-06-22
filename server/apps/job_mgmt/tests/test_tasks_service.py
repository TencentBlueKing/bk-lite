"""作业 Celery 任务测试（execute_scheduled_task / cleanup / _dispatch_execution_job）

直接以函数方式调用 shared_task；外部派发 / S3 / celery 均 mock。
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.job_mgmt import tasks
from apps.job_mgmt.constants import ConcurrencyPolicy, DangerousLevel, ExecutionStatus, JobType
from apps.job_mgmt.models import DangerousPath, DangerousRule, DistributionFile, JobExecution, ScheduledTask

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _task(**over):
    defaults = {
        "name": "st",
        "job_type": JobType.SCRIPT,
        "schedule_type": "cron",
        "cron_expression": "* * * * *",
        "script_content": "echo hi",
        "script_type": "shell",
        "target_source": "node_mgmt",
        "target_list": [{"node_id": "n1"}],
        "team": [1],
        "is_enabled": True,
        "concurrency_policy": ConcurrencyPolicy.RUN,
    }
    defaults.update(over)
    return ScheduledTask.objects.create(**defaults)


class TestThinTaskWrappers:
    def test_execute_script_task_calls_runner(self):
        with patch("apps.job_mgmt.tasks.ScriptExecutionRunner") as R:
            tasks.execute_script_task(1)
        R.assert_called_once_with(1)
        R.return_value.run.assert_called_once()

    def test_distribute_files_task_calls_runner(self):
        with patch("apps.job_mgmt.tasks.FileDistributionRunner") as R:
            tasks.distribute_files_task(2)
        R.return_value.run.assert_called_once()

    def test_execute_playbook_task_calls_runner(self):
        with patch("apps.job_mgmt.tasks.PlaybookExecution") as R:
            tasks.execute_playbook_task(3)
        R.return_value.run.assert_called_once()


class TestExecuteScheduledTask:
    def test_missing_task_returns_silently(self):
        tasks.execute_scheduled_task(999999)  # 不抛
        assert JobExecution.objects.count() == 0

    def test_disabled_task_skips(self):
        st = _task(is_enabled=False)
        tasks.execute_scheduled_task(st.id)
        assert JobExecution.objects.filter(scheduled_task=st).count() == 0

    def test_happy_path_creates_execution_and_dispatches(self):
        st = _task()
        with patch("apps.job_mgmt.tasks._dispatch_execution_job", return_value=True) as disp:
            tasks.execute_scheduled_task(st.id)
        disp.assert_called_once()
        ex = JobExecution.objects.get(scheduled_task=st)
        assert ex.status == ExecutionStatus.PENDING
        st.refresh_from_db()
        assert st.run_count == 1

    def test_dispatch_failure_marks_execution_failed(self):
        st = _task()
        with patch("apps.job_mgmt.tasks._dispatch_execution_job", return_value=False):
            tasks.execute_scheduled_task(st.id)
        ex = JobExecution.objects.get(scheduled_task=st)
        assert ex.status == ExecutionStatus.FAILED

    def test_no_target_returns_without_execution(self):
        st = _task(target_list=[])
        tasks.execute_scheduled_task(st.id)
        assert JobExecution.objects.filter(scheduled_task=st).count() == 0

    def test_concurrency_skip_when_running_exists(self):
        st = _task(concurrency_policy=ConcurrencyPolicy.SKIP)
        JobExecution.objects.create(name="r", job_type=JobType.SCRIPT, status=ExecutionStatus.RUNNING, scheduled_task=st, team=[1])
        tasks.execute_scheduled_task(st.id)
        # 仍只有那条 running，未新建
        assert JobExecution.objects.filter(scheduled_task=st).count() == 1

    def test_concurrency_queue_retries(self):
        st = _task(concurrency_policy=ConcurrencyPolicy.QUEUE)
        JobExecution.objects.create(name="r", job_type=JobType.SCRIPT, status=ExecutionStatus.PENDING, scheduled_task=st, team=[1])
        with patch.object(tasks.execute_scheduled_task, "apply_async") as retry:
            tasks.execute_scheduled_task(st.id)
        retry.assert_called_once()

    def test_dangerous_command_blocks(self):
        DangerousRule.objects.create(name="no-rm", pattern="rm -rf", level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[])
        st = _task(script_content="rm -rf /")
        tasks.execute_scheduled_task(st.id)
        assert JobExecution.objects.filter(scheduled_task=st).count() == 0

    def test_dangerous_path_blocks_file_distribution(self):
        DangerousPath.objects.create(name="etc", pattern="/etc", match_type="exact", level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[])
        st = _task(job_type=JobType.FILE_DISTRIBUTION, script_content="", target_path="/etc/x", files=[{"file_key": "k"}])
        tasks.execute_scheduled_task(st.id)
        assert JobExecution.objects.filter(scheduled_task=st).count() == 0


class TestDispatchExecutionJob:
    def _exec(self, job_type):
        return JobExecution.objects.create(name="e", job_type=job_type, status=ExecutionStatus.PENDING, team=[1])

    def test_script_dispatch_sets_celery_id(self):
        ex = self._exec(JobType.SCRIPT)
        with patch("apps.job_mgmt.tasks.current_app") as app:
            app.send_task.return_value = MagicMock(id="celery-1")
            assert tasks._dispatch_execution_job(JobType.SCRIPT, ex.id) is True
        ex.refresh_from_db()
        assert ex.celery_task_id == "celery-1"

    def test_unknown_job_type_returns_false(self):
        ex = self._exec(JobType.SCRIPT)
        assert tasks._dispatch_execution_job("weird", ex.id) is False

    def test_broker_error_returns_false(self):
        ex = self._exec(JobType.PLAYBOOK)
        with patch("apps.job_mgmt.tasks.current_app") as app:
            app.send_task.side_effect = ConnectionError("broker down")
            assert tasks._dispatch_execution_job(JobType.PLAYBOOK, ex.id) is False


class TestCleanupExpiredFiles:
    def test_deletes_expired_only(self):
        expired = DistributionFile.objects.create(original_name="old", file_key="k1", expire_at=timezone.now() - timedelta(days=1), team=1)
        fresh = DistributionFile.objects.create(original_name="new", file_key="k2", expire_at=timezone.now() + timedelta(days=1), team=1)
        with patch("apps.job_mgmt.tasks.async_to_sync", lambda fn: (lambda *a, **k: None)):
            tasks.cleanup_expired_distribution_files_task()
        assert not DistributionFile.objects.filter(id=expired.id).exists()
        assert DistributionFile.objects.filter(id=fresh.id).exists()

    def test_no_expired_files_noop(self):
        DistributionFile.objects.create(original_name="new", file_key="k", expire_at=timezone.now() + timedelta(days=1), team=1)
        with patch("apps.job_mgmt.tasks.async_to_sync", lambda fn: (lambda *a, **k: None)):
            tasks.cleanup_expired_distribution_files_task()  # 不抛
