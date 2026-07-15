"""ScheduledTask 批量删除的团队权限回归测试。"""

from unittest.mock import patch

import pytest

from apps.job_mgmt.constants import JobType
from apps.job_mgmt.models import ScheduledTask

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

URL = "/api/v1/job_mgmt/api/scheduled_task/batch_delete/"
VIEW_SVC = "apps.job_mgmt.views.scheduled_task.ScheduledTaskService"


def _make_task(name, team):
    return ScheduledTask.objects.create(
        name=name,
        job_type=JobType.SCRIPT,
        schedule_type="cron",
        cron_expression="* * * * *",
        script_content="echo",
        script_type="shell",
        target_source="node_mgmt",
        target_list=[{"node_id": "n1"}],
        team=team,
    )


def _grant_delete_permission(api_client, authenticated_user):
    authenticated_user.permission = {"job": {"cron_task-Delete"}}
    api_client.cookies["current_team"] = "1"


def test_batch_delete_only_deletes_authorized_team_tasks(api_client, authenticated_user):
    own_task = _make_task("own", [1])
    foreign_task = _make_task("foreign", [2])
    _grant_delete_permission(api_client, authenticated_user)

    rules = {"team": [1], "instance": []}
    with (
        patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules),
        patch(VIEW_SVC + ".delete_periodic_task") as delete_periodic_task,
    ):
        response = api_client.post(URL, {"ids": [own_task.id, foreign_task.id]}, format="json")

    assert response.status_code == 200
    assert response.data["deleted_count"] == 1
    assert not ScheduledTask.objects.filter(id=own_task.id).exists()
    assert ScheduledTask.objects.filter(id=foreign_task.id).exists()
    delete_periodic_task.assert_called_once_with(own_task.id)


def test_batch_delete_foreign_team_id_is_noop(api_client, authenticated_user):
    foreign_task = _make_task("foreign", [2])
    _grant_delete_permission(api_client, authenticated_user)

    rules = {"team": [1], "instance": []}
    with (
        patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules),
        patch(VIEW_SVC + ".delete_periodic_task") as delete_periodic_task,
    ):
        response = api_client.post(URL, {"ids": [foreign_task.id]}, format="json")

    assert response.status_code == 200
    assert response.data["deleted_count"] == 0
    assert ScheduledTask.objects.filter(id=foreign_task.id).exists()
    delete_periodic_task.assert_not_called()


def test_batch_delete_superuser_keeps_cross_team_semantics(su_client):
    own_task = _make_task("own", [1])
    foreign_task = _make_task("foreign", [2])

    with patch(VIEW_SVC + ".delete_periodic_task"):
        response = su_client.post(URL, {"ids": [own_task.id, foreign_task.id]}, format="json")

    assert response.status_code == 200
    assert response.data["deleted_count"] == 2
    assert not ScheduledTask.objects.filter(id__in=[own_task.id, foreign_task.id]).exists()
