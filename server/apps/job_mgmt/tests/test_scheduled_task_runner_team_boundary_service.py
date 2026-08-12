"""定时执行在 runner 最终读取 Target 时保持团队凭据边界。"""

import threading
from unittest.mock import patch

import pytest
from django.db import close_old_connections

from apps.job_mgmt.constants import ExecutionStatus, ExecutorDriver, JobType, TargetSource
from apps.job_mgmt.models import JobExecution, Playbook, ScheduledTask, Target
from apps.job_mgmt.services.file_distribution_runner import FileDistributionRunner
from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService
from apps.job_mgmt.services.playbook_execution import PlaybookExecution
from apps.job_mgmt.services.script_execution_runner import ScriptExecutionRunner
from apps.job_mgmt.utils.team_authz import is_team_authorized as real_is_team_authorized

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def _isolate_script_stream_side_effects():
    with patch("apps.job_mgmt.services.script_execution_runner.ensure_stream_sync"), patch(
        "apps.job_mgmt.services.script_execution_runner.publish_done_sentinel"
    ):
        yield


def _scheduled_execution(job_type, target, *, move_target=True, **overrides):
    task_values = {
        "name": "runner-team-boundary",
        "job_type": job_type,
        "schedule_type": "cron",
        "cron_expression": "* * * * *",
        "script_content": "echo hi" if job_type == JobType.SCRIPT else "",
        "script_type": "shell" if job_type == JobType.SCRIPT else "",
        "target_source": TargetSource.MANUAL,
        "target_list": [{"target_id": target.id, "name": target.name, "ip": target.ip}],
        "team": [1],
    }
    task_values.update(overrides)
    task = ScheduledTask.objects.create(**task_values)
    execution = JobExecution.objects.create(
        name=task.name,
        job_type=job_type,
        scheduled_task=task,
        enforce_scheduled_team_boundary=True,
        playbook=task.playbook,
        script_content=task.script_content,
        script_type=task.script_type,
        files=task.files,
        target_path=task.target_path,
        target_source=task.target_source,
        target_list=task.target_list,
        team=[1],
    )
    if move_target:
        Target.objects.filter(id=target.id).update(team=[2])
    return execution


def _assert_rejected(execution, executor):
    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.FAILED
    assert "未授权" in str(execution.execution_results)
    executor.assert_not_called()


def test_script_runner_rejects_target_moved_after_execution_snapshot():
    target = Target.objects.create(name="moved", ip="127.0.0.10", team=[1])
    execution = _scheduled_execution(JobType.SCRIPT, target)

    with patch("apps.job_mgmt.services.script_execution_runner.ensure_stream_sync"), patch(
        "apps.job_mgmt.services.script_execution_runner.Executor"
    ) as executor:
        ScriptExecutionRunner(execution.id).run()

    _assert_rejected(execution, executor)


def test_playbook_runner_rejects_target_moved_after_execution_snapshot():
    target = Target.objects.create(
        name="moved",
        ip="127.0.0.11",
        team=[1],
        driver=ExecutorDriver.ANSIBLE,
        cloud_region_id=1,
    )
    playbook = Playbook.objects.create(name="owned", team=[1])
    execution = _scheduled_execution(JobType.PLAYBOOK, target, playbook=playbook)

    with patch.object(PlaybookExecution, "_get_ansible_node", return_value="node-1"), patch(
        "apps.job_mgmt.services.playbook_execution.AnsibleExecutor"
    ) as executor:
        PlaybookExecution(execution.id).run()

    _assert_rejected(execution, executor)


def test_file_runner_rejects_target_moved_after_execution_snapshot():
    target = Target.objects.create(name="moved", ip="127.0.0.12", team=[1])
    execution = _scheduled_execution(
        JobType.FILE_DISTRIBUTION,
        target,
        files=[{"name": "payload.txt", "file_key": "job-files/payload"}],
        target_path="/tmp",
    )

    with patch("apps.job_mgmt.services.file_distribution_runner.Executor") as executor:
        FileDistributionRunner(execution.id).run()

    _assert_rejected(execution, executor)


def test_script_runner_keeps_same_team_scheduled_execution_compatible():
    target = Target.objects.create(name="owned", ip="127.0.0.20", node_id="node-20", ssh_user="root", ssh_password="secret", team=[1])
    execution = _scheduled_execution(JobType.SCRIPT, target, move_target=False)

    with patch("apps.job_mgmt.services.script_execution_runner.ensure_stream_sync"), patch(
        "apps.job_mgmt.services.script_execution_runner.Executor"
    ) as executor:
        executor.return_value.execute_ssh_stream.return_value = "success"
        ScriptExecutionRunner(execution.id).run()

    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.SUCCESS
    executor.return_value.execute_ssh_stream.assert_called_once()


def test_false_boundary_marker_preserves_linked_legacy_execution():
    target = Target.objects.create(
        name="legacy",
        ip="127.0.0.23",
        node_id="node-23",
        ssh_user="root",
        ssh_password="secret",
        team=[1],
    )
    execution = _scheduled_execution(JobType.SCRIPT, target, move_target=False)
    JobExecution.objects.filter(id=execution.id).update(enforce_scheduled_team_boundary=False)
    Target.objects.filter(id=target.id).update(team=[2])

    with patch("apps.job_mgmt.services.script_execution_runner.ensure_stream_sync"), patch(
        "apps.job_mgmt.services.script_execution_runner.Executor"
    ) as executor:
        executor.return_value.execute_ssh_stream.return_value = "success"
        ScriptExecutionRunner(execution.id).run()

    execution.refresh_from_db()
    assert execution.scheduled_task_id is not None
    assert execution.status == ExecutionStatus.SUCCESS
    executor.return_value.execute_ssh_stream.assert_called_once()


def test_playbook_runner_keeps_same_team_scheduled_execution_compatible():
    target = Target.objects.create(
        name="owned",
        ip="127.0.0.21",
        team=[1],
        driver=ExecutorDriver.ANSIBLE,
        cloud_region_id=1,
        ssh_user="root",
        ssh_password="secret",
    )
    playbook = Playbook.objects.create(name="owned", team=[1])
    execution = _scheduled_execution(JobType.PLAYBOOK, target, move_target=False, playbook=playbook)

    with patch.object(PlaybookExecution, "_get_ansible_node", return_value="node-1"), patch(
        "apps.job_mgmt.services.playbook_execution.AnsibleExecutor"
    ) as executor:
        executor.return_value.playbook.return_value = {"task_id": "accepted"}
        PlaybookExecution(execution.id).run()

    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.RUNNING
    executor.return_value.playbook.assert_called_once()


def test_file_runner_keeps_same_team_scheduled_execution_compatible():
    target = Target.objects.create(
        name="owned",
        ip="127.0.0.22",
        node_id="node-22",
        ssh_user="root",
        ssh_password="secret",
        team=[1],
    )
    execution = _scheduled_execution(
        JobType.FILE_DISTRIBUTION,
        target,
        move_target=False,
        files=[{"name": "payload.txt", "file_key": "job-files/payload"}],
        target_path="/tmp",
    )

    with patch("apps.job_mgmt.services.file_distribution_runner.Executor") as executor:
        executor.return_value.download_to_remote.return_value = {"success": True}
        FileDistributionRunner(execution.id).run()

    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.SUCCESS
    executor.return_value.download_to_remote.assert_called_once()


def test_runner_linearizes_target_snapshot_before_concurrent_team_update():
    target = Target.objects.create(
        name="owned",
        ip="127.0.0.30",
        node_id="node-30",
        driver=ExecutorDriver.SIDECAR,
        ssh_user="old-user",
        ssh_password="old-secret",
        team=[1],
    )
    execution = _scheduled_execution(JobType.SCRIPT, target, move_target=False)
    lock_checked = threading.Event()
    release_check = threading.Event()
    update_done = threading.Event()
    errors = []

    def blocking_authorization(resource_team, authorized_team_ids):
        lock_checked.set()
        assert release_check.wait(timeout=5)
        return real_is_team_authorized(resource_team, authorized_team_ids)

    original_build = ExecutionTaskBaseService._build_ssh_credentials

    def build_after_update(cls, locked_target):
        assert update_done.wait(timeout=5)
        return original_build(locked_target)

    def run_execution():
        close_old_connections()
        try:
            ScriptExecutionRunner(execution.id).run()
        except Exception as exc:  # pragma: no cover - 线程异常转回主断言
            errors.append(exc)
        finally:
            close_old_connections()

    def move_target():
        close_old_connections()
        try:
            Target.objects.filter(id=target.id).update(team=[2], ssh_user="new-user")
            update_done.set()
        except Exception as exc:  # pragma: no cover - 线程异常转回主断言
            errors.append(exc)
        finally:
            close_old_connections()

    with patch("apps.job_mgmt.services.script_execution_runner.ensure_stream_sync"), patch(
        "apps.job_mgmt.services.script_execution_runner.Executor"
    ) as executor, patch(
        "apps.job_mgmt.services.execution_base_service.is_team_authorized",
        side_effect=blocking_authorization,
    ), patch.object(
        ExecutionTaskBaseService,
        "_build_ssh_credentials",
        new=classmethod(build_after_update),
    ):
        executor.return_value.execute_ssh_stream.return_value = "success"
        runner_thread = threading.Thread(target=run_execution)
        runner_thread.start()
        assert lock_checked.wait(timeout=5)
        update_thread = threading.Thread(target=move_target)
        update_thread.start()
        assert update_done.wait(timeout=0.2) is False
        release_check.set()
        runner_thread.join(timeout=10)
        update_thread.join(timeout=10)

    assert not runner_thread.is_alive()
    assert not update_thread.is_alive()
    assert errors == []
    target.refresh_from_db()
    execution.refresh_from_db()
    assert target.team == [2]
    assert target.ssh_user == "new-user"
    assert execution.status == ExecutionStatus.SUCCESS
    assert executor.return_value.execute_ssh_stream.call_args.kwargs["username"] == "old-user"
