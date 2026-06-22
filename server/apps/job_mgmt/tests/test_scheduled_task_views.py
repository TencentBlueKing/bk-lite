"""定时任务视图测试（CRUD / toggle / run_now / batch_delete / crontab_preview）

PeriodicTask（celery-beat）相关操作统一 mock，避免依赖 django_celery_beat 表。
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.job_mgmt.constants import JobType
from apps.job_mgmt.models import ScheduledTask

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

URL = "/api/v1/job_mgmt/api/scheduled_task/"
SVC = "apps.job_mgmt.serializers.scheduled_task.ScheduledTaskService"
VIEW_SVC = "apps.job_mgmt.views.scheduled_task.ScheduledTaskService"


def _create_payload(**over):
    p = {
        "name": "task1",
        "job_type": "script",
        "schedule_type": "cron",
        "cron_expression": "* * * * *",
        "script_content": "echo hi",
        "script_type": "shell",
        "target_source": "node_mgmt",
        "target_list": [{"node_id": "n1", "name": "n", "ip": "1.1.1.1"}],
        "team": [1],
    }
    p.update(over)
    return p


def _make_task(**over):
    defaults = {
        "name": "t",
        "job_type": JobType.SCRIPT,
        "schedule_type": "cron",
        "cron_expression": "* * * * *",
        "script_content": "echo",
        "script_type": "shell",
        "target_source": "node_mgmt",
        "target_list": [{"node_id": "n1"}],
        "team": [1],
    }
    defaults.update(over)
    return ScheduledTask.objects.create(**defaults)


class TestScheduledTaskCrud:
    def test_create(self, su_client):
        with patch(SVC + ".create_periodic_task", return_value=MagicMock(id=99)):
            resp = su_client.post(URL, _create_payload(), format="json")
        assert resp.status_code == 201
        assert ScheduledTask.objects.filter(name="task1").exists()

    def test_create_invalid_missing_cron_returns_400(self, su_client):
        with patch(SVC + ".create_periodic_task", return_value=MagicMock(id=99)):
            resp = su_client.post(URL, _create_payload(cron_expression=""), format="json")
        assert resp.status_code == 400

    def test_update(self, su_client):
        task = _make_task()
        with patch(SVC + ".update_periodic_task", return_value=MagicMock(id=99)):
            resp = su_client.put(f"{URL}{task.id}/", _create_payload(name="task1-edit"), format="json")
        assert resp.status_code == 200
        task.refresh_from_db()
        assert task.name == "task1-edit"

    def test_list_and_retrieve(self, su_client):
        task = _make_task()
        assert su_client.get(URL).status_code == 200
        assert su_client.get(f"{URL}{task.id}/").status_code == 200

    def test_destroy(self, su_client):
        task = _make_task()
        with patch(VIEW_SVC + ".delete_periodic_task"):
            resp = su_client.delete(f"{URL}{task.id}/")
        assert resp.status_code in (200, 204)
        assert not ScheduledTask.objects.filter(id=task.id).exists()

    def test_batch_delete(self, su_client):
        t1 = _make_task(name="t1")
        t2 = _make_task(name="t2")
        with patch(VIEW_SVC + ".delete_periodic_task"):
            resp = su_client.post(f"{URL}batch_delete/", {"ids": [t1.id, t2.id]}, format="json")
        assert resp.status_code == 200
        assert resp.data["deleted_count"] == 2


class TestScheduledTaskActions:
    def test_toggle(self, su_client):
        task = _make_task(is_enabled=True)
        with patch(VIEW_SVC + ".toggle_periodic_task"):
            resp = su_client.post(f"{URL}{task.id}/toggle/", {"is_enabled": False}, format="json")
        assert resp.status_code == 200
        assert resp.data["is_enabled"] is False

    def test_run_now_triggers_execution(self, su_client):
        task = _make_task()
        with patch("apps.job_mgmt.views.scheduled_task.dispatch_celery_task", return_value="celery-1") as disp:
            resp = su_client.post(f"{URL}{task.id}/run_now/", {}, format="json")
        assert resp.status_code == 200
        assert "execution_id" in resp.data
        disp.assert_called_once()

    def test_run_now_no_target_returns_400(self, su_client):
        task = _make_task(target_list=[])
        resp = su_client.post(f"{URL}{task.id}/run_now/", {}, format="json")
        assert resp.status_code == 400

    def test_run_now_broker_down_returns_503(self, su_client):
        task = _make_task()
        with patch("apps.job_mgmt.views.scheduled_task.dispatch_celery_task", return_value=None):
            resp = su_client.post(f"{URL}{task.id}/run_now/", {}, format="json")
        assert resp.status_code == 503

    def test_crontab_preview_ok(self, su_client):
        resp = su_client.post(f"{URL}crontab_preview/", {"cron_expression": "* * * * *"}, format="json")
        assert resp.status_code == 200
        assert resp.data["result"] is True

    def test_crontab_preview_empty_returns_400(self, su_client):
        resp = su_client.post(f"{URL}crontab_preview/", {"cron_expression": ""}, format="json")
        assert resp.status_code == 400

    def test_crontab_preview_invalid_returns_400(self, su_client):
        resp = su_client.post(f"{URL}crontab_preview/", {"cron_expression": "bad expr"}, format="json")
        assert resp.status_code == 400
