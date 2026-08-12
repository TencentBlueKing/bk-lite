"""定时任务团队边界的 Celery 与存量治理服务回归。"""

from io import StringIO
from importlib import import_module
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command
from django.db.models.query import QuerySet

from apps.job_mgmt import tasks
from apps.job_mgmt.constants import JobType
from apps.job_mgmt.models import JobExecution, ScheduledTask, Script, Target

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

AUTHZ_SERVICE = "apps.job_mgmt.services.scheduled_task_authz.ScheduledTaskService"
VIEW_SERVICE = "apps.job_mgmt.views.scheduled_task.ScheduledTaskService"


def _task(**overrides):
    defaults = {
        "name": "team-boundary-task",
        "job_type": JobType.SCRIPT,
        "schedule_type": "cron",
        "cron_expression": "* * * * *",
        "script_content": "echo hi",
        "script_type": "shell",
        "target_source": "node_mgmt",
        "target_list": [{"node_id": "n1"}],
        "team": [1],
        "is_enabled": True,
    }
    defaults.update(overrides)
    return ScheduledTask.objects.create(**defaults)


class TestScheduledTaskCeleryBoundary:
    def test_celery_disables_manual_task_without_targets(self):
        task = _task(target_source="manual", target_list=[], is_enabled=True)

        with patch("apps.job_mgmt.tasks._dispatch_execution_job") as dispatch, patch(
            AUTHZ_SERVICE + ".toggle_periodic_task_or_raise",
            return_value=True,
        ) as toggle:
            tasks.execute_scheduled_task(task.id)

        task.refresh_from_db()
        assert task.is_enabled is False
        assert JobExecution.objects.filter(scheduled_task=task).count() == 0
        toggle.assert_called_once_with(task.id, False)
        dispatch.assert_not_called()

    def test_celery_defense_disables_stale_cross_team_task(self):
        script = Script.objects.create(name="foreign", content="echo foreign", script_type="shell", team=[2])
        task = _task(script=script, script_content="", team=[1], is_enabled=True)
        before_count = JobExecution.objects.count()

        with patch("apps.job_mgmt.tasks._dispatch_execution_job") as dispatch, patch(
            AUTHZ_SERVICE + ".toggle_periodic_task_or_raise"
        ) as toggle:
            tasks.execute_scheduled_task(task.id)

        task.refresh_from_db()
        assert task.is_enabled is False
        assert JobExecution.objects.count() == before_count
        dispatch.assert_not_called()
        toggle.assert_called_once_with(task.id, False)

    def test_celery_rechecks_resource_boundary_after_lock(self):
        script = Script.objects.create(name="owned", content="echo owned", script_type="shell", team=[1])
        task = _task(script=script, script_content="", team=[1], is_enabled=True)
        before_count = JobExecution.objects.count()
        original_get = QuerySet.get
        scheduled_task_get_count = 0

        def change_script_team_before_locked_get(queryset, *args, **kwargs):
            nonlocal scheduled_task_get_count
            if queryset.model is ScheduledTask:
                scheduled_task_get_count += 1
                if scheduled_task_get_count == 1:
                    Script.objects.filter(id=script.id).update(team=[2])
            return original_get(queryset, *args, **kwargs)

        with patch.object(QuerySet, "get", new=change_script_team_before_locked_get), patch(
            "apps.job_mgmt.tasks._dispatch_execution_job"
        ) as dispatch, patch(
            AUTHZ_SERVICE + ".toggle_periodic_task_or_raise",
            return_value=True,
        ):
            tasks.execute_scheduled_task(task.id)

        task.refresh_from_db()
        assert task.is_enabled is False
        assert JobExecution.objects.count() == before_count
        dispatch.assert_not_called()

    def test_celery_rechecks_disabled_snapshot_after_lock(self):
        task = _task(is_enabled=False)
        original_get = QuerySet.get
        scheduled_task_get_count = 0

        def enable_task_before_locked_get(queryset, *args, **kwargs):
            nonlocal scheduled_task_get_count
            if queryset.model is ScheduledTask:
                scheduled_task_get_count += 1
                if scheduled_task_get_count == 1:
                    ScheduledTask.objects.filter(id=task.id).update(is_enabled=True)
            return original_get(queryset, *args, **kwargs)

        with patch.object(QuerySet, "get", new=enable_task_before_locked_get), patch(
            "apps.job_mgmt.tasks._dispatch_execution_job",
            return_value=True,
        ), patch(
            "apps.job_mgmt.tasks.ScheduledTaskService.toggle_periodic_task_or_raise",
            return_value=True,
        ) as toggle:
            tasks.execute_scheduled_task(task.id)

        task.refresh_from_db()
        assert task.is_enabled is True
        assert JobExecution.objects.filter(scheduled_task=task).count() == 1
        toggle.assert_not_called()

    def test_celery_uses_locked_task_snapshot_after_concurrent_update(self):
        old_script = Script.objects.create(name="old", content="echo old", script_type="shell", team=[1])
        new_script = Script.objects.create(name="new", content="echo new", script_type="shell", team=[2])
        task = _task(script=old_script, script_content="", team=[1], is_enabled=True)
        original_get = QuerySet.get
        scheduled_task_get_count = 0

        def update_task_before_locked_get(queryset, *args, **kwargs):
            nonlocal scheduled_task_get_count
            if queryset.model is ScheduledTask:
                scheduled_task_get_count += 1
                if scheduled_task_get_count == 1:
                    ScheduledTask.objects.filter(id=task.id).update(script=new_script, team=[2])
            return original_get(queryset, *args, **kwargs)

        with patch.object(QuerySet, "get", new=update_task_before_locked_get), patch(
            "apps.job_mgmt.tasks._dispatch_execution_job",
            return_value=True,
        ):
            tasks.execute_scheduled_task(task.id)

        execution = JobExecution.objects.get(scheduled_task=task)
        assert execution.script_id == new_script.id
        assert execution.script_content == new_script.content
        assert execution.team == [2]

    def test_celery_uses_locked_script_snapshot_after_concurrent_update(self):
        script = Script.objects.create(name="script", content="echo old", script_type="shell", team=[1])
        task = _task(script=script, script_content="", team=[1], is_enabled=True)
        original_get = QuerySet.get
        script_get_count = 0

        def update_script_before_locked_get(queryset, *args, **kwargs):
            nonlocal script_get_count
            if queryset.model is Script:
                script_get_count += 1
                if script_get_count == 1:
                    Script.objects.filter(id=script.id).update(content="echo locked")
            return original_get(queryset, *args, **kwargs)

        with patch.object(QuerySet, "get", new=update_script_before_locked_get), patch(
            "apps.job_mgmt.tasks._dispatch_execution_job",
            return_value=True,
        ):
            tasks.execute_scheduled_task(task.id)

        execution = JobExecution.objects.get(scheduled_task=task)
        assert execution.script_id == script.id
        assert execution.script_content == "echo locked"

    def test_celery_keeps_invalid_task_retryable_when_beat_sync_fails(self):
        script = Script.objects.create(name="foreign", content="echo foreign", script_type="shell", team=[2])
        task = _task(script=script, script_content="", team=[1], is_enabled=True)

        with patch(AUTHZ_SERVICE + ".toggle_periodic_task_or_raise", return_value=False):
            tasks.execute_scheduled_task(task.id)

        task.refresh_from_db()
        assert task.is_enabled is True
        assert JobExecution.objects.filter(scheduled_task=task).count() == 0


class TestScheduledTaskTeamBoundaryAudit:
    @pytest.fixture(autouse=True)
    def _clear_preexisting_tasks(self):
        ScheduledTask.objects.all().delete()

    def test_dry_run_reports_unique_normalization_without_writing(self):
        script = Script.objects.create(name="team-one", content="echo one", script_type="shell", team=[1])
        task = _task(script=script, script_content="", team=[1, 2])
        stdout = StringIO()

        call_command("audit_scheduled_task_team_boundary", stdout=stdout)

        task.refresh_from_db()
        assert task.team == [1, 2]
        assert task.is_enabled is True
        assert f"task={task.id} action=normalize team=1" in stdout.getvalue()
        assert "DRY-RUN keep=0 normalize=1 disable=0" in stdout.getvalue()

    def test_dry_run_reports_manual_task_without_targets_as_disable(self):
        task = _task(target_source="manual", target_list=[])
        stdout = StringIO()

        call_command("audit_scheduled_task_team_boundary", stdout=stdout)

        task.refresh_from_db()
        assert task.is_enabled is True
        assert f"task={task.id} action=disable" in stdout.getvalue()
        assert "缺少手动执行目标" in stdout.getvalue()

    def test_apply_disables_manual_task_without_targets(self):
        task = _task(target_source="manual", target_list=[])

        with patch(VIEW_SERVICE + ".toggle_periodic_task_or_raise", return_value=True):
            call_command(
                "audit_scheduled_task_team_boundary",
                "--apply",
                "--backup-confirmed",
                "--limit=100",
                stdout=StringIO(),
            )

        task.refresh_from_db()
        assert task.is_enabled is False

    def test_apply_normalizes_only_unique_team(self):
        script = Script.objects.create(name="team-one", content="echo one", script_type="shell", team=[1])
        target = Target.objects.create(name="team-one", ip="127.0.0.4", team=[1])
        task = _task(
            script=script,
            script_content="",
            target_source="manual",
            target_list=[{"target_id": target.id}],
            team=[1, 2],
        )

        call_command(
            "audit_scheduled_task_team_boundary",
            "--apply",
            "--backup-confirmed",
            "--limit=100",
            stdout=StringIO(),
        )

        task.refresh_from_db()
        assert task.team == [1]
        assert task.is_enabled is True

    @pytest.mark.parametrize(
        ("task_overrides", "reason"),
        [
            ({"team": [1, 2]}, "无法唯一"),
            (
                {
                    "job_type": JobType.FILE_DISTRIBUTION,
                    "script_content": "",
                    "files": [{"name": "temporary", "file_key": "job-files/temporary"}],
                    "target_path": "/tmp",
                    "team": [1],
                },
                "临时文件",
            ),
        ],
    )
    def test_apply_disables_ambiguous_or_temporary_tasks(self, task_overrides, reason):
        task = _task(**task_overrides)
        stdout = StringIO()

        with patch(VIEW_SERVICE + ".toggle_periodic_task_or_raise") as toggle:
            call_command(
                "audit_scheduled_task_team_boundary",
                "--apply",
                "--backup-confirmed",
                "--limit=100",
                stdout=stdout,
            )

        task.refresh_from_db()
        assert task.is_enabled is False
        assert reason in stdout.getvalue()
        toggle.assert_called_once_with(task.id, False)

    def test_apply_resynchronizes_beat_for_already_disabled_invalid_task(self):
        task = _task(team=[1, 2], is_enabled=False)

        with patch(VIEW_SERVICE + ".toggle_periodic_task_or_raise") as toggle:
            call_command(
                "audit_scheduled_task_team_boundary",
                "--apply",
                "--backup-confirmed",
                "--limit=100",
                stdout=StringIO(),
            )

        task.refresh_from_db()
        assert task.is_enabled is False
        toggle.assert_called_once_with(task.id, False)

    def test_apply_rolls_back_when_beat_sync_fails(self):
        task = _task(team=[1, 2], is_enabled=True)

        with patch(VIEW_SERVICE + ".toggle_periodic_task_or_raise", return_value=False), pytest.raises(CommandError):
            call_command(
                "audit_scheduled_task_team_boundary",
                "--apply",
                "--backup-confirmed",
                "--limit=100",
                stdout=StringIO(),
            )

        task.refresh_from_db()
        assert task.is_enabled is True

    def test_apply_requires_backup_confirmation_and_bounded_batch(self):
        _task(team=[1, 2])

        with pytest.raises(CommandError, match="backup|备份"):
            call_command("audit_scheduled_task_team_boundary", "--apply", "--limit=1", stdout=StringIO())
        with pytest.raises(CommandError, match="limit"):
            call_command("audit_scheduled_task_team_boundary", "--apply", "--backup-confirmed", stdout=StringIO())

    def test_apply_reports_stable_resume_cursor(self):
        first = _task(name="first", team=[1, 2])
        second = _task(name="second", team=[1, 2])
        first_stdout = StringIO()

        with patch(VIEW_SERVICE + ".toggle_periodic_task_or_raise"):
            call_command(
                "audit_scheduled_task_team_boundary",
                "--apply",
                "--backup-confirmed",
                "--limit=1",
                stdout=first_stdout,
            )

        assert f"last_processed_id={first.id} has_more=true" in first_stdout.getvalue()
        second_stdout = StringIO()
        with patch(VIEW_SERVICE + ".toggle_periodic_task_or_raise"):
            call_command(
                "audit_scheduled_task_team_boundary",
                "--apply",
                "--backup-confirmed",
                f"--start-after-id={first.id}",
                "--limit=1",
                stdout=second_stdout,
            )

        assert f"task={second.id}" in second_stdout.getvalue()
        assert f"last_processed_id={second.id} has_more=false" in second_stdout.getvalue()


class TestScheduledExecutionBoundaryMigration:
    def test_only_unambiguous_linked_executions_are_marked_and_reversible(self):
        task = _task()
        linked = JobExecution.objects.create(name="beat", job_type=JobType.SCRIPT, scheduled_task=task, team=[1])
        prefixed_manual = JobExecution.objects.create(name="[手动触发] legal-manual", job_type=JobType.SCRIPT, team=[1])
        ordinary = JobExecution.objects.create(name="manual", job_type=JobType.SCRIPT, team=[1])
        migration = import_module("apps.job_mgmt.migrations.0016_jobexecution_enforce_scheduled_team_boundary")

        class Apps:
            @staticmethod
            def get_model(app_label, model_name):
                assert (app_label, model_name) == ("job_mgmt", "JobExecution")
                return JobExecution

        migration.mark_existing_scheduled_executions(Apps(), None)
        linked.refresh_from_db()
        prefixed_manual.refresh_from_db()
        ordinary.refresh_from_db()
        assert linked.enforce_scheduled_team_boundary is True
        assert prefixed_manual.enforce_scheduled_team_boundary is False
        assert ordinary.enforce_scheduled_team_boundary is False

        migration.unmark_existing_scheduled_executions(Apps(), None)
        linked.refresh_from_db()
        prefixed_manual.refresh_from_db()
        assert linked.enforce_scheduled_team_boundary is False
        assert prefixed_manual.enforce_scheduled_team_boundary is False
