"""定时任务视图测试（CRUD / toggle / run_now / batch_delete / crontab_preview）

PeriodicTask（celery-beat）相关操作统一 mock，避免依赖 django_celery_beat 表。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.job_mgmt.constants import JobType
from apps.job_mgmt.models import ScheduledTask
from apps.job_mgmt.services.dangerous_checker import DangerousCheckResult

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


class TestScheduledTaskNormalizeLineEndings:
    """入库前规范化 script_content 换行符;脚本类型走 _resolve 防 PATCH 误规范化。"""

    def test_create_normalizes_crlf(self, su_client):
        with patch(SVC + ".create_periodic_task", return_value=MagicMock(id=99)):
            resp = su_client.post(
                URL,
                _create_payload(script_content="echo a\r\necho b\r\n"),
                format="json",
            )
        assert resp.status_code == 201
        t = ScheduledTask.objects.get(name="task1")
        assert "\r" not in t.script_content
        assert t.script_content.startswith("echo a\necho b")

    def test_create_powershell_keeps_crlf(self, su_client):
        crlf = "Write-Host hi\r\n$x = 1\r\n"
        with patch(SVC + ".create_periodic_task", return_value=MagicMock(id=99)):
            resp = su_client.post(
                URL,
                _create_payload(script_type="powershell", script_content=crlf),
                format="json",
            )
        assert resp.status_code == 201
        t = ScheduledTask.objects.get(name="task1")
        # powershell 保留 CRLF
        assert "\r" in t.script_content

    def test_update_normalizes_crlf(self, su_client):
        t = _make_task(script_content="echo", script_type="shell")
        with patch(SVC + ".update_periodic_task", return_value=MagicMock(id=99)):
            resp = su_client.put(
                f"{URL}{t.id}/",
                _create_payload(name="t2", script_content="echo 1\r\necho 2\r\n"),
                format="json",
            )
        assert resp.status_code == 200
        t.refresh_from_db()
        assert "\r" not in t.script_content
        assert t.script_content.startswith("echo 1\necho 2")

    def test_update_powershell_preserves_crlf(self, su_client):
        """PATCH 只改 content(不传 script_type),instance 是 powershell → 走 _resolve 不误规范"""
        crlf = "Write-Host hi\r\n$x = 1\r\n"
        t = _make_task(script_type="powershell", script_content=crlf)
        with patch(SVC + ".update_periodic_task", return_value=MagicMock(id=99)):
            resp = su_client.put(
                f"{URL}{t.id}/",
                _create_payload(name="t2", script_content=crlf, script_type="powershell"),
                format="json",
            )
        assert resp.status_code == 200
        t.refresh_from_db()
        assert "\r" in t.script_content

    def test_update_partial_no_content_keeps_existing(self, su_client):
        """PATCH 不传 script_content 时 instance 原值保留,不被规范化。"""
        t = _make_task(script_content="echo", script_type="shell")
        with patch(SVC + ".update_periodic_task", return_value=MagicMock(id=99)):
            resp = su_client.patch(
                f"{URL}{t.id}/",
                {"description": "no-content-change"},
                format="json",
            )
        assert resp.status_code == 200
        t.refresh_from_db()
        assert t.script_content == "echo"


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

    def test_run_now_dangerous_script_returns_400_without_creating_execution(self, su_client):
        """run_now 在高危命令命中时应直接返回 400，不创建 JobExecution。"""
        from apps.job_mgmt.models import JobExecution

        task = _make_task(script_content="rm -rf /")
        bad_result = DangerousCheckResult()
        bad_result.add_match(
            SimpleNamespace(id=1, name="禁止删根", pattern="rm -rf", level="forbidden"),
            "rm -rf /",
        )
        before_count = JobExecution.objects.count()
        with patch("apps.job_mgmt.views.scheduled_task.DangerousChecker.check_command", return_value=bad_result):
            resp = su_client.post(f"{URL}{task.id}/run_now/", {}, format="json")
        assert resp.status_code == 400
        assert "高危" in resp.data.get("error", "")
        assert JobExecution.objects.count() == before_count, "高危命中时不应创建执行记录"

    def test_run_now_dangerous_path_returns_400_without_creating_execution(self, su_client):
        """run_now 在高危路径命中时应直接返回 400，不创建 JobExecution。"""
        from apps.job_mgmt.models import JobExecution

        task = _make_task(job_type=JobType.FILE_DISTRIBUTION, target_path="/etc/passwd")
        bad_result = DangerousCheckResult()
        bad_result.add_match(
            SimpleNamespace(id=2, name="禁止系统路径", pattern="/etc/", level="forbidden"),
            "/etc/passwd",
        )
        before_count = JobExecution.objects.count()
        with patch("apps.job_mgmt.views.scheduled_task.DangerousChecker.check_path", return_value=bad_result):
            resp = su_client.post(f"{URL}{task.id}/run_now/", {}, format="json")
        assert resp.status_code == 400
        assert "高危" in resp.data.get("error", "")
        assert JobExecution.objects.count() == before_count, "高危路径命中时不应创建执行记录"

    def test_run_now_safe_script_proceeds_normally(self, su_client):
        """run_now 在安全脚本时应正常创建执行记录并触发任务。"""
        task = _make_task(script_content="echo hello")
        safe_result = DangerousCheckResult()  # can_execute=True by default
        with patch("apps.job_mgmt.views.scheduled_task.DangerousChecker.check_command", return_value=safe_result):
            with patch("apps.job_mgmt.views.scheduled_task.dispatch_celery_task", return_value="task-ok"):
                resp = su_client.post(f"{URL}{task.id}/run_now/", {}, format="json")
        assert resp.status_code == 200
        assert "execution_id" in resp.data

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
