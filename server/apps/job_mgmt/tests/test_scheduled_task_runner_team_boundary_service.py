"""定时执行在 runner 最终读取 Target 时保持团队凭据边界。"""

from unittest.mock import patch

import pytest

from apps.job_mgmt.constants import ExecutionStatus, ExecutorDriver, JobType, TargetSource
from apps.job_mgmt.models import JobExecution, Playbook, ScheduledTask, Target
from apps.job_mgmt.services.file_distribution_runner import FileDistributionRunner
from apps.job_mgmt.services.playbook_execution import PlaybookExecution
from apps.job_mgmt.services.script_execution_runner import ScriptExecutionRunner

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


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
