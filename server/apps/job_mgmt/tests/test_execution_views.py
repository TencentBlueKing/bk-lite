"""作业执行视图测试（quick_execute / file_distribution / re_execute / cancel / targets）"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.job_mgmt.constants import DangerousLevel, ExecutionStatus, JobType, TargetSource
from apps.job_mgmt.models import DangerousPath, DangerousRule, DistributionFile, JobExecution, Playbook, Script

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

URL = "/api/v1/job_mgmt/api/execution/"
DISPATCH = "apps.job_mgmt.services.celery_dispatch.dispatch_celery_task"


def _node_target():
    return [{"node_id": "n1", "name": "n", "ip": "1.1.1.1"}]


class TestQuickExecuteNormalizeLineEndings:
    """入库前规范化临时输入脚本的换行符;script_id 模式由 Script 入口保证。"""

    def test_script_content_mode_normalizes_crlf(self, su_client):
        with patch(DISPATCH, return_value="celery-1"):
            resp = su_client.post(
                f"{URL}quick_execute/",
                {
                    "name": "j1",
                    "target_source": "node_mgmt",
                    "target_list": _node_target(),
                    "script_content": "echo a\r\necho b\r\n",
                    "script_type": "shell",
                },
                format="json",
            )
        assert resp.status_code == 201
        e = JobExecution.objects.get(id=resp.data["id"])
        assert "\r" not in e.script_content
        assert e.script_content.startswith("echo a\necho b")

    def test_script_content_mode_bat_keeps_crlf(self, su_client):
        crlf = "@echo off\r\nset x=1\r\n"
        with patch(DISPATCH, return_value="celery-1"):
            resp = su_client.post(
                f"{URL}quick_execute/",
                {
                    "name": "j2",
                    "target_source": "node_mgmt",
                    "target_list": _node_target(),
                    "script_content": crlf,
                    "script_type": "bat",
                },
                format="json",
            )
        assert resp.status_code == 201
        e = JobExecution.objects.get(id=resp.data["id"])
        assert "\r" in e.script_content


class TestQuickExecute:
    def test_script_content_mode(self, su_client):
        with patch(DISPATCH, return_value="celery-1"):
            resp = su_client.post(
                f"{URL}quick_execute/",
                {"name": "j1", "target_source": "node_mgmt", "target_list": _node_target(), "script_content": "echo hi", "script_type": "shell"},
                format="json",
            )
        assert resp.status_code == 201
        assert resp.data["job_type"] == JobType.SCRIPT

    def test_script_id_mode(self, su_client):
        script = Script.objects.create(name="s", content="echo lib", script_type="shell", team=[1], timeout=120)
        with patch(DISPATCH, return_value="celery-1"):
            resp = su_client.post(
                f"{URL}quick_execute/",
                {"name": "j2", "target_source": "node_mgmt", "target_list": _node_target(), "script_id": script.id},
                format="json",
            )
        assert resp.status_code == 201
        assert resp.data["script"] == script.id

    def test_playbook_mode(self, su_client):
        pb = Playbook.objects.create(name="p", version="v1.0.0", team=[1])
        with patch(DISPATCH, return_value="celery-1"):
            resp = su_client.post(
                f"{URL}quick_execute/",
                {"name": "j3", "target_source": "node_mgmt", "target_list": _node_target(), "playbook_id": pb.id},
                format="json",
            )
        assert resp.status_code == 201
        assert resp.data["job_type"] == JobType.PLAYBOOK

    def test_manual_target_not_exist_returns_400(self, su_client):
        with patch(DISPATCH, return_value="celery-1"):
            resp = su_client.post(
                f"{URL}quick_execute/",
                {"name": "j", "target_source": "manual", "target_list": [{"target_id": 999999}], "script_content": "echo", "script_type": "shell"},
                format="json",
            )
        assert resp.status_code == 400

    def test_dangerous_command_returns_400(self, su_client):
        DangerousRule.objects.create(name="no-rm", pattern="rm -rf", level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[])
        with patch(DISPATCH, return_value="celery-1"):
            resp = su_client.post(
                f"{URL}quick_execute/",
                {"name": "j", "target_source": "node_mgmt", "target_list": _node_target(), "script_content": "rm -rf /", "script_type": "shell"},
                format="json",
            )
        assert resp.status_code == 400

    def test_dispatch_failure_returns_503(self, su_client):
        with patch(DISPATCH, return_value=None):
            resp = su_client.post(
                f"{URL}quick_execute/",
                {"name": "j", "target_source": "node_mgmt", "target_list": _node_target(), "script_content": "echo", "script_type": "shell"},
                format="json",
            )
        assert resp.status_code == 503

    def test_validation_error_two_modes_returns_400(self, su_client):
        script = Script.objects.create(name="s", content="echo", script_type="shell", team=[1])
        resp = su_client.post(
            f"{URL}quick_execute/",
            {"name": "j", "target_source": "node_mgmt", "target_list": _node_target(), "script_id": script.id, "script_content": "echo"},
            format="json",
        )
        assert resp.status_code == 400


class TestFileDistribution:
    def _file(self, team=1):
        return DistributionFile.objects.create(original_name="f.tar", file_key="job-files/f", expire_at=timezone.now() + timedelta(days=7), team=team)

    def test_file_distribution_ok(self, su_client):
        f = self._file()
        with patch(DISPATCH, return_value="celery-1"):
            resp = su_client.post(
                f"{URL}file_distribution/",
                {"name": "fd", "file_ids": [f.id], "target_source": "node_mgmt", "target_list": _node_target(), "target_path": "/tmp/app"},
                format="json",
            )
        assert resp.status_code == 201
        assert resp.data["job_type"] == JobType.FILE_DISTRIBUTION

    def test_file_not_exist_returns_400(self, su_client):
        with patch(DISPATCH, return_value="celery-1"):
            resp = su_client.post(
                f"{URL}file_distribution/",
                {"name": "fd", "file_ids": [999999], "target_source": "node_mgmt", "target_list": _node_target(), "target_path": "/tmp"},
                format="json",
            )
        assert resp.status_code == 400

    def test_dangerous_path_returns_400(self, su_client):
        DangerousPath.objects.create(name="etc", pattern="/etc", match_type="exact", level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[])
        f = self._file()
        with patch(DISPATCH, return_value="celery-1"):
            resp = su_client.post(
                f"{URL}file_distribution/",
                {"name": "fd", "file_ids": [f.id], "target_source": "node_mgmt", "target_list": _node_target(), "target_path": "/etc/nginx"},
                format="json",
            )
        assert resp.status_code == 400


def _make_execution(**over):
    defaults = {
        "name": "orig",
        "job_type": JobType.SCRIPT,
        "status": ExecutionStatus.SUCCESS,
        "script_content": "echo",
        "script_type": "shell",
        "target_source": TargetSource.MANUAL,
        "target_list": [{"target_id": 1, "name": "h", "ip": "1.1.1.1"}],
        "execution_results": [],
        "team": [1],
    }
    defaults.update(over)
    return JobExecution.objects.create(**defaults)


class TestReExecute:
    def test_re_execute_script(self, su_client):
        original = _make_execution()
        with patch(DISPATCH, return_value="celery-1"):
            resp = su_client.post(f"{URL}{original.id}/re_execute/", {}, format="json")
        assert resp.status_code == 201
        assert resp.data["id"] != original.id

    def test_re_execute_no_target_returns_400(self, su_client):
        original = _make_execution(target_list=[])
        resp = su_client.post(f"{URL}{original.id}/re_execute/", {}, format="json")
        assert resp.status_code == 400


class TestCancel:
    def test_cancel_pending(self, su_client):
        execution = _make_execution(status=ExecutionStatus.PENDING, celery_task_id="task-x")
        with patch("apps.job_mgmt.views.execution.current_app") as mapp:
            resp = su_client.post(f"{URL}{execution.id}/cancel/", {}, format="json")
            mapp.control.revoke.assert_called_once()
        assert resp.status_code == 200
        execution.refresh_from_db()
        assert execution.status == ExecutionStatus.CANCELLED

    def test_cancel_terminal_returns_400(self, su_client):
        execution = _make_execution(status=ExecutionStatus.SUCCESS)
        resp = su_client.post(f"{URL}{execution.id}/cancel/", {}, format="json")
        assert resp.status_code == 400


class TestTargetsAndList:
    def test_targets_returns_results(self, su_client):
        execution = _make_execution(execution_results=[{"target_key": "1", "status": "success"}])
        resp = su_client.get(f"{URL}{execution.id}/targets/")
        assert resp.status_code == 200
        assert resp.data[0]["status"] == "success"

    def test_list_and_retrieve(self, su_client):
        execution = _make_execution()
        assert su_client.get(URL).status_code == 200
        assert su_client.get(f"{URL}{execution.id}/").status_code == 200
