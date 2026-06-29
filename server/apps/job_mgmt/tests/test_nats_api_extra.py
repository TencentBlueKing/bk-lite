"""nats_api NATS 开放接口补测（直接调用注册函数覆盖各分支）"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.job_mgmt import nats_api
from apps.job_mgmt.constants import DangerousLevel, ExecutionStatus, JobType
from apps.job_mgmt.models import DangerousRule, DistributionFile, JobExecution, Script

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


class TestModuleData:
    def test_module_list(self):
        result = nats_api.get_job_mgmt_module_list()
        assert any(m["name"] == "script" for m in result)

    def test_module_data_script(self):
        Script.objects.create(name="s1", content="echo", script_type="shell", team=[1])
        out = nats_api.get_job_mgmt_module_data("script", None, 1, 10, 1)
        assert out["count"] == 1 and out["items"][0]["name"] == "s1"

    def test_module_data_system_child(self):
        DangerousRule.objects.create(name="r1", pattern="rm", level=DangerousLevel.CONFIRM, team=[1])
        out = nats_api.get_job_mgmt_module_data("system", "dangerous_rule", 1, 10, 1)
        assert out["count"] == 1


def _exec(**over):
    defaults = {
        "name": "e",
        "job_type": JobType.SCRIPT,
        "status": ExecutionStatus.RUNNING,
        "target_list": [{"target_id": 1, "name": "h1", "ip": "1.1.1.1"}],
        "started_at": timezone.now(),
        "team": [1],
    }
    defaults.update(over)
    return JobExecution.objects.create(**defaults)


class TestAnsibleCallback:
    def test_missing_task_id(self):
        assert nats_api.ansible_task_callback({})["success"] is False

    def test_not_found(self):
        assert nats_api.ansible_task_callback({"task_id": 999999})["success"] is False

    def test_already_terminal(self):
        ex = _exec(status=ExecutionStatus.SUCCESS)
        out = nats_api.ansible_task_callback({"task_id": ex.id})
        assert out["success"] is True and "已处理" in out["message"]

    def test_invalid_result_format_fails(self):
        ex = _exec()
        with patch("apps.job_mgmt.nats_api.publish_done_sentinel"), patch("apps.job_mgmt.nats_api.send_callback"):
            out = nats_api.ansible_task_callback({"task_id": ex.id, "result": "not-a-list"})
        assert out["success"] is False
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.FAILED

    def test_happy_per_host_success(self):
        ex = _exec()
        data = {"task_id": ex.id, "result": [{"host": "1.1.1.1", "status": "success", "stdout": "ok", "exit_code": 0}]}
        with patch("apps.job_mgmt.nats_api.publish_done_sentinel"), patch("apps.job_mgmt.nats_api.send_callback"):
            out = nats_api.ansible_task_callback(data)
        assert out["success"] is True
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.SUCCESS

    def test_missing_target_filled_as_failed(self):
        ex = _exec(target_list=[{"target_id": 1, "ip": "1.1.1.1", "name": "h1"}, {"target_id": 2, "ip": "2.2.2.2", "name": "h2"}])
        data = {"task_id": ex.id, "result": [{"host": "1.1.1.1", "status": "success"}]}
        with patch("apps.job_mgmt.nats_api.publish_done_sentinel"), patch("apps.job_mgmt.nats_api.send_callback"):
            out = nats_api.ansible_task_callback(data)
        assert out["success"] is True
        ex.refresh_from_db()
        assert ex.failed_count == 1 and ex.success_count == 1


class TestJobScriptExecute:
    def _payload(self, **over):
        p = {
            "name": "j",
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "n1"}],
            "script_type": "shell",
            "script_content": "echo",
            "team": [1],
        }
        p.update(over)
        return p

    @pytest.mark.parametrize(
        "override",
        [
            {"name": ""},
            {"target_source": "bad"},
            {"target_list": []},
            {"script_type": "bad"},
            {"script_content": ""},
            {"team": []},
        ],
    )
    def test_validation_failures(self, override):
        assert nats_api.job_script_execute(self._payload(**override))["result"] is False

    def test_callback_url_ssrf_blocked(self):
        with patch("apps.job_mgmt.nats_api.SSRFValidator.validate_callback", side_effect=nats_api.SSRFError("blocked")):
            out = nats_api.job_script_execute(self._payload(callback_url="http://169.254.169.254/"))
        assert out["result"] is False

    def test_dangerous_command_blocked(self):
        DangerousRule.objects.create(name="rm", pattern="rm -rf", level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[])
        out = nats_api.job_script_execute(self._payload(script_content="rm -rf /"))
        assert out["result"] is False

    def test_happy_path(self):
        with patch("apps.job_mgmt.nats_api.execute_script_task") as MT:
            MT.delay.return_value = MagicMock(id="c1")
            out = nats_api.job_script_execute(self._payload(params=[{"name": "p", "value": "v"}]))
        assert out["result"] is True and "task_id" in out["data"]


class TestJobFileDistribute:
    def _payload(self, **over):
        p = {
            "name": "fd",
            "file_keys": ["k1"],
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "n1"}],
            "target_path": "/tmp/app",
            "team": [1],
        }
        p.update(over)
        return p

    @pytest.mark.parametrize(
        "override",
        [{"name": ""}, {"file_keys": []}, {"target_source": "bad"}, {"target_list": []}, {"target_path": ""}, {"team": []}],
    )
    def test_validation_failures(self, override):
        assert nats_api.job_file_distribute(self._payload(**override))["result"] is False

    def test_missing_files(self):
        out = nats_api.job_file_distribute(self._payload(file_keys=["nope"]))
        assert out["result"] is False

    def test_dangerous_path_blocked(self):
        from apps.job_mgmt.constants import MatchType
        from apps.job_mgmt.models import DangerousPath

        DangerousPath.objects.create(name="etc", pattern="/etc", match_type=MatchType.EXACT, level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[])
        DistributionFile.objects.create(original_name="f", file_key="k1", expire_at=timezone.now() + timedelta(days=1), team=1)
        out = nats_api.job_file_distribute(self._payload(target_path="/etc/x"))
        assert out["result"] is False

    def test_happy_path(self):
        DistributionFile.objects.create(original_name="f", file_key="k1", expire_at=timezone.now() + timedelta(days=1), team=1)
        with patch("apps.job_mgmt.nats_api.distribute_files_task") as MT:
            MT.delay.return_value = MagicMock(id="c1")
            out = nats_api.job_file_distribute(self._payload())
        assert out["result"] is True


class TestQueries:
    def test_batch_query_empty(self):
        assert nats_api.job_status_batch_query({"task_ids": []})["result"] is False

    def test_batch_query_found_and_not_found(self):
        ex = _exec()
        out = nats_api.job_status_batch_query({"task_ids": [ex.id, 999999]})
        statuses = {r["task_id"]: r["status"] for r in out["data"]}
        assert statuses[999999] == "not_found"

    def test_detail_query_missing_id(self):
        assert nats_api.job_detail_query({})["result"] is False

    def test_detail_query_not_found(self):
        assert nats_api.job_detail_query({"task_id": 999999, "team": [1]})["result"] is False

    def test_detail_query_found(self):
        ex = _exec()
        out = nats_api.job_detail_query({"task_id": ex.id, "team": [1]})
        assert out["result"] is True and out["data"]["task_id"] == ex.id

    def test_detail_query_requires_team(self):
        ex = _exec()
        out = nats_api.job_detail_query({"task_id": ex.id})
        assert out["result"] is False
        assert "team" in out["message"]

    def test_detail_query_rejects_cross_team(self):
        ex = _exec(team=[2])
        out = nats_api.job_detail_query({"task_id": ex.id, "team": [1]})
        assert out["result"] is False
        assert "无权" in out["message"]

    def test_target_list_filters_and_pagination(self):
        from apps.job_mgmt.models import Target

        Target.objects.create(name="web1", ip="10.0.0.1", os_type="linux", ssh_user="r", team=[1])
        Target.objects.create(name="db1", ip="10.0.0.2", os_type="windows", ssh_user="r", team=[1])
        out = nats_api.job_target_list({"name": "web", "ip": "10.0", "os_type": "linux", "page": 1, "page_size": 10})
        assert out["result"] is True and out["data"]["count"] == 1

    def test_target_list_page_size_all(self):
        from apps.job_mgmt.models import Target

        Target.objects.create(name="t", ip="10.0.0.9", ssh_user="r", team=[1])
        out = nats_api.job_target_list({"page_size": -1})
        assert out["result"] is True
