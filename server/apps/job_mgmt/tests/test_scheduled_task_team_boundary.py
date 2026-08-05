"""定时任务以单一任务团队约束引用资源的回归测试（Issue #4128）。"""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from apps.job_mgmt import tasks
from apps.job_mgmt.constants import JobType
from apps.job_mgmt.models import JobExecution, Playbook, ScheduledTask, Script, Target

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

URL = "/api/v1/job_mgmt/api/scheduled_task/"
SERIALIZER_SERVICE = "apps.job_mgmt.serializers.scheduled_task.ScheduledTaskService"
VIEW_SERVICE = "apps.job_mgmt.views.scheduled_task.ScheduledTaskService"


def _payload(**overrides):
    payload = {
        "name": "team-boundary-task",
        "job_type": JobType.SCRIPT,
        "schedule_type": "cron",
        "cron_expression": "* * * * *",
        "script_content": "echo hi",
        "script_type": "shell",
        "target_source": "node_mgmt",
        "target_list": [{"node_id": "n1", "name": "node", "ip": "127.0.0.1"}],
        "team": [1],
    }
    payload.update(overrides)
    return payload


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


class TestScheduledTaskWriteBoundary:
    def test_create_rejects_multiple_task_teams(self, su_client):
        before_count = ScheduledTask.objects.count()
        with patch(SERIALIZER_SERVICE + ".create_periodic_task", return_value=MagicMock(id=99)):
            response = su_client.post(URL, _payload(team=[1, 2]), format="json")

        assert response.status_code == 400
        assert "单一" in str(response.data)
        assert ScheduledTask.objects.count() == before_count

    def test_create_rejects_cross_team_script_even_for_superuser(self, su_client):
        script = Script.objects.create(name="foreign", content="echo foreign", script_type="shell", team=[2])
        payload = _payload(script=script.id, script_content="", team=[1])
        before_count = ScheduledTask.objects.count()

        with patch(SERIALIZER_SERVICE + ".create_periodic_task", return_value=MagicMock(id=99)):
            response = su_client.post(URL, payload, format="json")

        assert response.status_code == 400
        assert "脚本" in str(response.data)
        assert ScheduledTask.objects.count() == before_count

    def test_create_rejects_cross_team_manual_target(self, su_client):
        target = Target.objects.create(name="foreign", ip="127.0.0.2", team=[2])
        payload = _payload(
            target_source="manual",
            target_list=[{"target_id": target.id, "name": target.name, "ip": target.ip}],
            team=[1],
        )
        before_count = ScheduledTask.objects.count()

        with patch(SERIALIZER_SERVICE + ".create_periodic_task", return_value=MagicMock(id=99)):
            response = su_client.post(URL, payload, format="json")

        assert response.status_code == 400
        assert "目标" in str(response.data)
        assert ScheduledTask.objects.count() == before_count

    def test_create_rejects_cross_team_playbook_even_for_superuser(self, su_client):
        playbook = Playbook.objects.create(name="foreign", team=[2])
        payload = _payload(
            job_type=JobType.PLAYBOOK,
            playbook=playbook.id,
            script_content="",
            script_type="",
            team=[1],
        )
        before_count = ScheduledTask.objects.count()

        with patch(SERIALIZER_SERVICE + ".create_periodic_task", return_value=MagicMock(id=99)):
            response = su_client.post(URL, payload, format="json")

        assert response.status_code == 400
        assert "Playbook" in str(response.data)
        assert ScheduledTask.objects.count() == before_count

    def test_partial_update_revalidates_retained_script_against_new_team(self, su_client):
        script = Script.objects.create(name="owned", content="echo owned", script_type="shell", team=[1])
        task = _task(script=script, script_content="")

        with patch(SERIALIZER_SERVICE + ".update_periodic_task", return_value=MagicMock(id=99)):
            response = su_client.patch(f"{URL}{task.id}/", {"team": [2]}, format="json")

        assert response.status_code == 400
        task.refresh_from_db()
        assert task.team == [1]

    def test_create_rejects_temporary_file_distribution(self, su_client):
        payload = _payload(
            job_type=JobType.FILE_DISTRIBUTION,
            script_content="",
            script_type="",
            files=[{"name": "temporary.txt", "file_key": "job-files/temporary"}],
            target_path="/tmp",
        )
        before_count = ScheduledTask.objects.count()

        with patch(SERIALIZER_SERVICE + ".create_periodic_task", return_value=MagicMock(id=99)):
            response = su_client.post(URL, payload, format="json")

        assert response.status_code == 400
        assert "永久" in str(response.data)
        assert ScheduledTask.objects.count() == before_count

    def test_create_accepts_resources_authorized_to_single_task_team(self, su_client):
        script = Script.objects.create(name="shared", content="echo shared", script_type="shell", team=[1, 2])
        target = Target.objects.create(name="owned", ip="127.0.0.3", team=[1])
        payload = _payload(
            script=script.id,
            script_content="",
            target_source="manual",
            target_list=[{"target_id": target.id, "name": target.name, "ip": target.ip}],
            team=[1],
        )

        with patch(SERIALIZER_SERVICE + ".create_periodic_task", return_value=MagicMock(id=99)):
            response = su_client.post(URL, payload, format="json")

        assert response.status_code == 201
        assert ScheduledTask.objects.filter(name="team-boundary-task").latest("id").team == [1]


class TestScheduledTaskExecutionBoundary:
    def test_run_now_rejects_stale_cross_team_reference(self, su_client):
        script = Script.objects.create(name="foreign", content="echo foreign", script_type="shell", team=[2])
        task = _task(script=script, script_content="", team=[1])
        before_count = JobExecution.objects.count()

        with patch("apps.job_mgmt.views.scheduled_task.dispatch_celery_task") as dispatch:
            response = su_client.post(f"{URL}{task.id}/run_now/", {}, format="json")

        assert response.status_code == 400
        assert "脚本" in str(response.data)
        assert JobExecution.objects.count() == before_count
        dispatch.assert_not_called()

    def test_enabling_stale_cross_team_task_is_rejected(self, su_client):
        script = Script.objects.create(name="foreign", content="echo foreign", script_type="shell", team=[2])
        task = _task(script=script, script_content="", team=[1], is_enabled=False)

        with patch(VIEW_SERVICE + ".toggle_periodic_task") as toggle:
            response = su_client.post(f"{URL}{task.id}/toggle/", {"is_enabled": True}, format="json")

        assert response.status_code == 400
        task.refresh_from_db()
        assert task.is_enabled is False
        toggle.assert_not_called()

    def test_patch_can_disable_stale_cross_team_task(self, su_client):
        script = Script.objects.create(name="foreign", content="echo foreign", script_type="shell", team=[2])
        task = _task(script=script, script_content="", team=[1, 2], is_enabled=True)

        with patch(SERIALIZER_SERVICE + ".update_periodic_task", return_value=MagicMock(id=99)):
            response = su_client.patch(f"{URL}{task.id}/", {"is_enabled": False}, format="json")

        assert response.status_code == 200
        task.refresh_from_db()
        assert task.is_enabled is False

    def test_disabled_task_cannot_be_updated_with_invalid_boundary(self, su_client):
        script = Script.objects.create(name="foreign", content="echo foreign", script_type="shell", team=[2])
        task = _task(script=script, script_content="", team=[1], is_enabled=False)

        with patch(SERIALIZER_SERVICE + ".update_periodic_task", return_value=MagicMock(id=99)):
            response = su_client.patch(f"{URL}{task.id}/", {"team": [1, 2]}, format="json")

        assert response.status_code == 400
        task.refresh_from_db()
        assert task.team == [1]

    def test_disabling_cannot_be_combined_with_invalid_boundary_update(self, su_client):
        task = _task(team=[1], is_enabled=True)

        with patch(SERIALIZER_SERVICE + ".update_periodic_task", return_value=MagicMock(id=99)):
            response = su_client.patch(
                f"{URL}{task.id}/",
                {"is_enabled": False, "team": [1, 2]},
                format="json",
            )

        assert response.status_code == 400
        task.refresh_from_db()
        assert task.is_enabled is True
        assert task.team == [1]

    def test_celery_defense_disables_stale_cross_team_task(self):
        script = Script.objects.create(name="foreign", content="echo foreign", script_type="shell", team=[2])
        task = _task(script=script, script_content="", team=[1], is_enabled=True)
        before_count = JobExecution.objects.count()

        with patch("apps.job_mgmt.tasks._dispatch_execution_job") as dispatch, patch(
            "apps.job_mgmt.tasks.ScheduledTaskService.toggle_periodic_task"
        ) as toggle:
            tasks.execute_scheduled_task(task.id)

        task.refresh_from_db()
        assert task.is_enabled is False
        assert JobExecution.objects.count() == before_count
        dispatch.assert_not_called()
        toggle.assert_called_once_with(task.id, False)


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

        call_command("audit_scheduled_task_team_boundary", "--apply", stdout=StringIO())

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

        with patch(VIEW_SERVICE + ".toggle_periodic_task") as toggle:
            call_command("audit_scheduled_task_team_boundary", "--apply", stdout=stdout)

        task.refresh_from_db()
        assert task.is_enabled is False
        assert reason in stdout.getvalue()
        toggle.assert_called_once_with(task.id, False)

    def test_apply_resynchronizes_beat_for_already_disabled_invalid_task(self):
        task = _task(team=[1, 2], is_enabled=False)

        with patch(VIEW_SERVICE + ".toggle_periodic_task") as toggle:
            call_command("audit_scheduled_task_team_boundary", "--apply", stdout=StringIO())

        task.refresh_from_db()
        assert task.is_enabled is False
        toggle.assert_called_once_with(task.id, False)
