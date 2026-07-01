"""NATS 开放接口单元测试"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
@pytest.mark.django_db
class TestJobScriptExecute:
    def test_success(self):
        from apps.job_mgmt.nats_api import job_script_execute

        data = {
            "name": "test-script",
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "n1", "name": "host1", "ip": "1.2.3.4", "os": "linux", "cloud_region_id": "r1"}],
            "script_type": "shell",
            "script_content": "echo hello",
            "team": [1],
            "timeout": 60,
        }

        with patch("apps.job_mgmt.services.dangerous_checker.DangerousChecker.check_command") as mock_check, patch(
            "apps.job_mgmt.nats_api.execute_script_task.delay"
        ) as mock_delay:
            mock_result = MagicMock()
            mock_result.can_execute = True
            mock_result.forbidden = []
            mock_check.return_value = mock_result
            mock_delay.return_value.id = "fake-celery-task-id"

            result = job_script_execute(data)

        assert result["result"] is True
        assert "task_id" in result["data"]

    def test_empty_target_list(self):
        from apps.job_mgmt.nats_api import job_script_execute

        data = {
            "name": "test",
            "target_source": "node_mgmt",
            "target_list": [],
            "script_type": "shell",
            "script_content": "echo hello",
            "team": [1],
        }
        result = job_script_execute(data)
        assert result["result"] is False
        assert "目标列表" in result["message"]

    def test_dangerous_command_blocked(self):
        from apps.job_mgmt.nats_api import job_script_execute

        data = {
            "name": "test",
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "n1", "name": "h1", "ip": "1.1.1.1", "os": "linux", "cloud_region_id": "r1"}],
            "script_type": "shell",
            "script_content": "rm -rf /",
            "team": [1],
        }

        with patch("apps.job_mgmt.services.dangerous_checker.DangerousChecker.check_command") as mock_check:
            mock_result = MagicMock()
            mock_result.can_execute = False
            mock_result.forbidden = [{"rule_name": "禁止删除根目录"}]
            mock_check.return_value = mock_result

            result = job_script_execute(data)

        assert result["result"] is False
        assert "高危命令" in result["message"]

    def test_missing_required_fields(self):
        from apps.job_mgmt.nats_api import job_script_execute

        result = job_script_execute({})
        assert result["result"] is False

    def _valid_data(self, **overrides):
        data = {
            "name": "test-script",
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "n1", "name": "host1", "ip": "1.2.3.4", "os": "linux", "cloud_region_id": "r1"}],
            "script_type": "shell",
            "script_content": "echo hello",
            "team": [1],
            "timeout": 60,
        }
        data.update(overrides)
        return data

    def test_callback_type_invalid_rejected(self):
        from apps.job_mgmt.nats_api import job_script_execute

        result = job_script_execute(self._valid_data(callback_type="ws"))
        assert result["result"] is False
        assert "callback_type" in result["message"]

    def test_callback_nats_requires_subject(self):
        from apps.job_mgmt.nats_api import job_script_execute

        result = job_script_execute(self._valid_data(callback_type="nats"))
        assert result["result"] is False
        assert "callback_subject" in result["message"]

    def test_callback_nats_success_persists_config(self):
        from apps.job_mgmt.nats_api import job_script_execute

        data = self._valid_data(callback_type="nats", callback_subject="bklite.alert_job_result")
        with patch("apps.job_mgmt.services.dangerous_checker.DangerousChecker.check_command") as mock_check, patch(
            "apps.job_mgmt.nats_api.execute_script_task.delay"
        ) as mock_delay:
            mock_check.return_value = MagicMock(can_execute=True, forbidden=[])
            mock_delay.return_value.id = "fake-celery-task-id"
            result = job_script_execute(data)

        assert result["result"] is True
        from apps.job_mgmt.models import JobExecution

        execution = JobExecution.objects.get(id=result["data"]["task_id"])
        assert execution.callback_type == "nats"
        assert execution.callback_subject == "bklite.alert_job_result"


@pytest.mark.unit
@pytest.mark.django_db
class TestJobFileDistribute:
    def test_empty_file_ids(self):
        from apps.job_mgmt.nats_api import job_file_distribute

        data = {
            "name": "test",
            "file_keys": [],
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "n1", "name": "h1", "ip": "1.1.1.1", "os": "linux", "cloud_region_id": "r1"}],
            "target_path": "/tmp/",
            "team": [1],
        }
        result = job_file_distribute(data)
        assert result["result"] is False
        assert "file_keys" in result["message"]

    def test_files_not_found(self):
        from apps.job_mgmt.nats_api import job_file_distribute

        data = {
            "name": "test",
            "file_keys": ["job-files/2026/01/01/nonexistent.rpm"],
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "n1", "name": "h1", "ip": "1.1.1.1", "os": "linux", "cloud_region_id": "r1"}],
            "target_path": "/tmp/",
            "team": [1],
        }

        with patch("apps.job_mgmt.services.dangerous_checker.DangerousChecker.check_path") as mock_check:
            mock_result = MagicMock()
            mock_result.can_execute = True
            mock_result.forbidden = []
            mock_check.return_value = mock_result

            result = job_file_distribute(data)

        assert result["result"] is False
        assert "不存在" in result["message"]


@pytest.mark.unit
@pytest.mark.django_db
class TestJobStatusBatchQuery:
    def test_not_found_ids(self):
        from apps.job_mgmt.nats_api import job_status_batch_query

        result = job_status_batch_query({"task_ids": [99999, 99998]})
        assert result["result"] is True
        assert all(item["status"] == "not_found" for item in result["data"])

    def test_empty_task_ids(self):
        from apps.job_mgmt.nats_api import job_status_batch_query

        result = job_status_batch_query({"task_ids": []})
        assert result["result"] is False


@pytest.mark.unit
@pytest.mark.django_db
class TestJobDetailQuery:
    def test_not_found(self):
        from apps.job_mgmt.nats_api import job_detail_query

        result = job_detail_query({"task_id": 99999})
        assert result["result"] is False
        assert "不存在" in result["message"]

    def test_missing_task_id(self):
        from apps.job_mgmt.nats_api import job_detail_query

        result = job_detail_query({})
        assert result["result"] is False


@pytest.mark.unit
@pytest.mark.django_db
class TestJobTargetList:
    def test_returns_all_targets(self):
        from apps.job_mgmt.models import Target
        from apps.job_mgmt.nats_api import job_target_list

        Target.objects.create(name="web-01", ip="10.0.0.1", os_type="linux", team=[1])
        Target.objects.create(name="db-01", ip="10.0.0.2", os_type="windows", team=[2])

        result = job_target_list({})
        assert result["result"] is True
        assert result["data"]["count"] == 2
        assert len(result["data"]["items"]) == 2

    def test_filter_by_os_type(self):
        from apps.job_mgmt.models import Target
        from apps.job_mgmt.nats_api import job_target_list

        Target.objects.create(name="web-01", ip="10.0.0.1", os_type="linux", team=[1])
        Target.objects.create(name="db-01", ip="10.0.0.2", os_type="windows", team=[1])

        result = job_target_list({"os_type": "linux"})
        assert result["data"]["count"] == 1
        assert result["data"]["items"][0]["os_type"] == "linux"

    def test_pagination(self):
        from apps.job_mgmt.models import Target
        from apps.job_mgmt.nats_api import job_target_list

        for i in range(5):
            Target.objects.create(name=f"node-{i}", ip=f"10.0.0.{i + 1}", os_type="linux", team=[1])

        result = job_target_list({"page": 1, "page_size": 2})
        assert result["data"]["count"] == 5
        assert len(result["data"]["items"]) == 2
