"""NATS 开放接口单元测试"""

from datetime import timedelta
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

    def test_dispatch_failure_marks_execution_failed(self):
        from apps.job_mgmt.constants import ExecutionStatus
        from apps.job_mgmt.models import JobExecution
        from apps.job_mgmt.nats_api import job_script_execute

        with patch("apps.job_mgmt.services.dangerous_checker.DangerousChecker.check_command") as mock_check, patch(
            "apps.job_mgmt.nats_api.execute_script_task.delay", side_effect=ConnectionError("broker unavailable")
        ):
            mock_check.return_value = MagicMock(can_execute=True, forbidden=[])
            result = job_script_execute(self._valid_data(name="dispatch-failed-script"))

        assert result == {"result": False, "message": "任务调度服务暂不可用，请稍后重试"}
        execution = JobExecution.objects.get(name="dispatch-failed-script")
        assert execution.status == ExecutionStatus.FAILED
        assert execution.celery_task_id == ""

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

    def test_normalize_crlf_on_persist(self):
        """NATS 入口入库前规范化;worker 兜底不依赖。"""
        from apps.job_mgmt.models import JobExecution
        from apps.job_mgmt.nats_api import job_script_execute

        data = {
            "name": "crlf-nats",
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "n1", "name": "h1", "ip": "1.1.1.1", "os": "linux", "cloud_region_id": "r1"}],
            "script_type": "shell",
            "script_content": "echo a\r\necho b\r\n",
            "team": [1],
            "timeout": 60,
        }
        with patch("apps.job_mgmt.services.dangerous_checker.DangerousChecker.check_command") as mock_check, patch(
            "apps.job_mgmt.nats_api.execute_script_task.delay", return_value=MagicMock(id="task-1")
        ):
            mock_result = MagicMock()
            mock_result.can_execute = True
            mock_result.forbidden = []
            mock_check.return_value = mock_result
            result = job_script_execute(data)
        assert result["result"] is True
        e = JobExecution.objects.get(name="crlf-nats")
        assert "\r" not in e.script_content
        assert e.script_content.startswith("echo a\necho b")

    def test_bat_keeps_crlf_on_persist(self):
        from apps.job_mgmt.models import JobExecution
        from apps.job_mgmt.nats_api import job_script_execute

        crlf = "@echo off\r\nset x=1\r\n"
        data = {
            "name": "bat-nats",
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "n1", "name": "h1", "ip": "1.1.1.1", "os": "linux", "cloud_region_id": "r1"}],
            "script_type": "bat",
            "script_content": crlf,
            "team": [1],
        }
        with patch("apps.job_mgmt.services.dangerous_checker.DangerousChecker.check_command") as mock_check, patch(
            "apps.job_mgmt.nats_api.execute_script_task.delay", return_value=MagicMock(id="task-1")
        ):
            mock_result = MagicMock()
            mock_result.can_execute = True
            mock_result.forbidden = []
            mock_check.return_value = mock_result
            result = job_script_execute(data)
        assert result["result"] is True
        e = JobExecution.objects.get(name="bat-nats")
        assert "\r" in e.script_content

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
    def test_legacy_entry_can_be_disabled_and_reenabled_without_side_effects(self, monkeypatch):
        from apps.job_mgmt.models import JobExecution
        from apps.job_mgmt.nats_api import job_file_distribute

        monkeypatch.setenv("JOB_FILE_DISTRIBUTE_NATS_ENABLED", "0")
        result = job_file_distribute({"name": "disabled-legacy"})

        assert result["result"] is False
        assert "OpenAPI" in result["message"]
        assert not JobExecution.objects.filter(name="disabled-legacy").exists()

        monkeypatch.setenv("JOB_FILE_DISTRIBUTE_NATS_ENABLED", "1")
        result = job_file_distribute({})
        assert result["result"] is False
        assert "name" in result["message"]

    def test_dispatch_failure_marks_execution_failed(self):
        from django.utils import timezone

        from apps.job_mgmt.constants import ExecutionStatus
        from apps.job_mgmt.models import DistributionFile, JobExecution
        from apps.job_mgmt.nats_api import job_file_distribute

        DistributionFile.objects.create(
            original_name="package.tar.gz",
            file_key="job-files/package.tar.gz",
            expire_at=timezone.now() + timedelta(days=1),
            team=1,
        )
        data = {
            "name": "dispatch-failed-file",
            "file_keys": ["job-files/package.tar.gz"],
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "n1", "name": "h1", "ip": "1.1.1.1", "os": "linux", "cloud_region_id": "r1"}],
            "target_path": "/tmp/",
            "team": [1],
            "actor": {"user": "forged", "domain": "evil.example"},
        }
        with patch("apps.job_mgmt.services.dangerous_checker.DangerousChecker.check_path") as mock_check, patch(
            "apps.job_mgmt.nats_api.distribute_files_task.delay", side_effect=ConnectionError("broker unavailable")
        ):
            mock_check.return_value = MagicMock(can_execute=True, forbidden=[])
            result = job_file_distribute(data)

        assert result == {"result": False, "message": "任务调度服务暂不可用，请稍后重试"}
        execution = JobExecution.objects.get(name="dispatch-failed-file")
        assert execution.status == ExecutionStatus.FAILED
        assert execution.celery_task_id == ""
        assert execution.created_by == "api"
        assert execution.executor_user == "api"
        assert execution.domain == "domain.com"

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

    @pytest.mark.parametrize("file_team", [1, None])
    def test_unauthorized_file_is_rejected(self, file_team):
        from django.utils import timezone

        from apps.job_mgmt.models import DistributionFile, JobExecution
        from apps.job_mgmt.nats_api import job_file_distribute

        DistributionFile.objects.create(
            original_name="team-a-package.tar.gz",
            file_key="job-files/team-a-package.tar.gz",
            expire_at=timezone.now() + timedelta(days=1),
            team=file_team,
        )
        data = {
            "name": "cross-team-file",
            "file_keys": ["job-files/team-a-package.tar.gz"],
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "n1", "name": "h1", "ip": "1.1.1.1", "os": "linux", "cloud_region_id": "r1"}],
            "target_path": "/tmp/",
            "team": [2],
        }

        with patch("apps.job_mgmt.services.dangerous_checker.DangerousChecker.check_path") as mock_check, patch(
            "apps.job_mgmt.nats_api.distribute_files_task.delay"
        ) as mock_delay:
            mock_check.return_value = MagicMock(can_execute=True, forbidden=[])
            mock_delay.return_value.id = "must-not-dispatch"
            result = job_file_distribute(data)

        assert result["result"] is False
        assert "无权" in result["message"]
        assert not JobExecution.objects.filter(name="cross-team-file").exists()
        mock_delay.assert_not_called()


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

        result = job_detail_query({"task_id": 99999, "team": [1]})
        assert result["result"] is False
        assert "不存在" in result["message"]

    def test_missing_task_id(self):
        from apps.job_mgmt.nats_api import job_detail_query

        result = job_detail_query({"team": [1]})
        assert result["result"] is False

    def test_without_team_returns_limited_safe_metadata(self):
        from apps.job_mgmt.models import JobExecution
        from apps.job_mgmt.nats_api import job_detail_query

        execution = JobExecution.objects.create(name="legacy", script_content="echo secret", execution_results=[{"stdout": "secret"}], team=[1])
        result = job_detail_query({"task_id": execution.id})
        assert result["result"] is True
        assert result["data"]["detail_limited"] is True
        assert result["data"]["requires_team"] is True
        assert "script_content" not in result["data"]
        assert "execution_results" not in result["data"]


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


@pytest.mark.unit
@pytest.mark.django_db
class TestJobTargetListV2:
    @pytest.fixture(autouse=True)
    def enable_v2(self, monkeypatch):
        monkeypatch.setenv("JOB_TARGET_LIST_V2_ENABLED", "true")

    def test_requires_caller_token(self):
        from apps.job_mgmt.nats_api import job_target_list_v2

        assert job_target_list_v2({}) == {"result": False, "message": "caller_token 不能为空"}

    def test_is_disabled_until_projection_is_reconciled(self, monkeypatch):
        from apps.job_mgmt.nats_api import job_target_list_v2

        monkeypatch.delenv("JOB_TARGET_LIST_V2_ENABLED")
        caller = MagicMock(group_list=[1])
        with patch("apps.job_mgmt.nats_api._verify_token", return_value=caller):
            assert job_target_list_v2({"caller_token": "valid"}) == {
                "result": False,
                "message": "job_target_list_v2 尚未启用",
            }

    def test_rejects_invalid_page_size_and_cursor(self, monkeypatch):
        from apps.job_mgmt.nats_api import job_target_list_v2

        caller = MagicMock(group_list=[1])
        with patch("apps.job_mgmt.nats_api._verify_token", return_value=caller):
            assert job_target_list_v2({"caller_token": "valid", "page_size": -1}) == {
                "result": False,
                "message": "page_size 范围为 1-100",
            }
            assert job_target_list_v2({"caller_token": "valid", "page_size": 101}) == {
                "result": False,
                "message": "page_size 范围为 1-100",
            }
            assert job_target_list_v2({"caller_token": "valid", "cursor": 0}) == {
                "result": False,
                "message": "cursor 必须为大于 0 的整数",
            }
            for invalid in (True, 1.5):
                assert job_target_list_v2({"caller_token": "valid", "page_size": invalid}) == {
                    "result": False,
                    "message": "page_size 参数非法",
                }
                assert job_target_list_v2({"caller_token": "valid", "cursor": invalid}) == {
                    "result": False,
                    "message": "cursor 必须为大于 0 的整数",
                }
            monkeypatch.setenv("JOB_TARGET_LIST_V2_MAX_PAGE_SIZE", "2")
            assert job_target_list_v2({"caller_token": "valid", "page_size": 3}) == {
                "result": False,
                "message": "page_size 范围为 1-2",
            }
            for invalid_max in ("invalid", "0", "101", "1000"):
                monkeypatch.setenv("JOB_TARGET_LIST_V2_MAX_PAGE_SIZE", invalid_max)
                assert job_target_list_v2({"caller_token": "valid", "page_size": 100})["result"] is True
                assert job_target_list_v2({"caller_token": "valid", "page_size": 101}) == {
                    "result": False,
                    "message": "page_size 范围为 1-100",
                }

    def test_returns_bounded_team_scoped_keyset_pages(self, django_assert_num_queries):
        from apps.job_mgmt.models import Target
        from apps.job_mgmt.nats_api import job_target_list_v2

        Target.objects.create(name="foreign", ip="10.0.1.1", os_type="linux", team=[2])
        owned = [Target.objects.create(name=f"owned-{index}", ip=f"10.0.0.{index}", os_type="linux", team=[1]) for index in range(1, 6)]

        caller = MagicMock(group_list=[{"id": 1, "name": "team-one"}])
        with patch("apps.job_mgmt.nats_api._verify_token", return_value=caller):
            with django_assert_num_queries(2):
                first = job_target_list_v2({"caller_token": "valid", "page_size": 2})
                second = job_target_list_v2({"caller_token": "valid", "page_size": 2, "cursor": first["data"]["next_cursor"]})

        assert first["result"] is True
        assert "count" not in first["data"]
        assert [item["target_id"] for item in first["data"]["items"]] == [owned[4].id, owned[3].id]
        assert first["data"]["has_more"] is True
        assert first["data"]["next_cursor"] == owned[3].id
        assert [item["target_id"] for item in second["data"]["items"]] == [owned[2].id, owned[1].id]
        assert {item["target_id"] for item in first["data"]["items"]}.isdisjoint(item["target_id"] for item in second["data"]["items"])

    def test_sparse_team_page_never_exposes_foreign_cursor(self, django_assert_num_queries):
        from apps.job_mgmt.models import Target
        from apps.job_mgmt.nats_api import job_target_list_v2

        owned = [Target.objects.create(name=f"owned-{index}", ip=f"10.0.0.{index}", os_type="linux", team=[1]) for index in range(1, 3)]
        foreign = [Target.objects.create(name=f"foreign-{index}", ip=f"10.0.1.{index}", os_type="linux", team=[2]) for index in range(1, 4)]

        caller = MagicMock(group_list=[1])
        with patch("apps.job_mgmt.nats_api._verify_token", return_value=caller):
            with django_assert_num_queries(1):
                first = job_target_list_v2({"caller_token": "valid", "page_size": 1})
            with django_assert_num_queries(1):
                second = job_target_list_v2({"caller_token": "valid", "page_size": 1, "cursor": first["data"]["next_cursor"]})

        foreign_ids = {target.id for target in foreign}
        assert [item["target_id"] for item in first["data"]["items"]] == [owned[1].id]
        assert first["data"]["next_cursor"] == owned[1].id
        assert first["data"]["next_cursor"] not in foreign_ids
        assert [item["target_id"] for item in second["data"]["items"]] == [owned[0].id]
        assert second["data"]["next_cursor"] is None
        assert second["data"]["has_more"] is False

    def test_target_save_keeps_indexed_team_projection_in_sync(self):
        from apps.job_mgmt.models import Target, TargetTeamMembership

        target = Target.objects.create(name="owned", ip="10.0.0.1", os_type="linux", team=[1, "2", 2, "invalid"])
        assert set(TargetTeamMembership.objects.filter(target=target).values_list("team_id", flat=True)) == {1, 2}

        target.team = [{"id": 3}, 4]
        target.save(update_fields=["team"])
        assert set(TargetTeamMembership.objects.filter(target=target).values_list("team_id", flat=True)) == {3, 4}

    def test_target_and_projection_roll_back_together(self):
        from apps.job_mgmt.models import Target

        target = Target.objects.create(name="owned", ip="10.0.0.1", os_type="linux", team=[1])
        target.team = [2]
        with patch("apps.job_mgmt.models.target._replace_target_team_memberships", side_effect=RuntimeError("sync failed")):
            with pytest.raises(RuntimeError, match="sync failed"):
                target.save(update_fields=["team"])

        target.refresh_from_db()
        assert target.team == [1]

    def test_queryset_and_bulk_team_writes_keep_projection_in_sync(self):
        from apps.job_mgmt.models import Target, TargetTeamMembership

        target = Target.objects.create(name="one", ip="10.0.0.1", os_type="linux", team=[1])
        Target.objects.filter(id=target.id).update(team=[2])
        assert set(TargetTeamMembership.objects.filter(target=target).values_list("team_id", flat=True)) == {2}

        created = Target.objects.bulk_create([Target(name="two", ip="10.0.0.2", os_type="linux", team=[3])])[0]
        assert set(TargetTeamMembership.objects.filter(target=created).values_list("team_id", flat=True)) == {3}

        created.team = [4]
        Target.objects.bulk_update([created], ["team"])
        assert set(TargetTeamMembership.objects.filter(target=created).values_list("team_id", flat=True)) == {4}

    def test_projection_has_team_target_composite_index(self):
        from apps.job_mgmt.models import TargetTeamMembership

        assert any(index.fields == ["team_id", "target"] for index in TargetTeamMembership._meta.indexes)

    def test_projection_reconciliation_is_repeatable(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        from apps.job_mgmt.models import Target, TargetTeamMembership

        target = Target.objects.create(name="owned", ip="10.0.0.1", os_type="linux", team=[1])
        TargetTeamMembership.objects.filter(target=target).delete()

        with pytest.raises(CommandError, match="1 个目标"):
            call_command("reconcile_target_team_memberships", check=True)
        call_command("reconcile_target_team_memberships", apply=True)
        call_command("reconcile_target_team_memberships", check=True)
        assert set(TargetTeamMembership.objects.filter(target=target).values_list("team_id", flat=True)) == {1}

    def test_real_token_page_uses_one_auth_and_one_target_query(self, django_assert_num_queries):
        import os

        import jwt

        from apps.job_mgmt.models import Target
        from apps.job_mgmt.nats_api import job_target_list_v2
        from apps.system_mgmt.models import User
        from apps.system_mgmt.nats.common import _build_jwt_payload

        user = User.objects.create(
            username="target-list-v2",
            display_name="Target List V2",
            email="target-list-v2@example.invalid",
            password="unused",
            group_list=[{"id": 1, "name": "team-one"}],
        )
        target = Target.objects.create(name="owned", ip="10.0.0.1", os_type="linux", team=[1])
        token = jwt.encode(_build_jwt_payload(user.id), key=os.environ["SECRET_KEY"], algorithm="HS256")

        with django_assert_num_queries(2):
            result = job_target_list_v2({"caller_token": token, "page_size": 1})

        assert [item["target_id"] for item in result["data"]["items"]] == [target.id]

    def test_empty_page_has_no_resume_cursor(self):
        from apps.job_mgmt.nats_api import job_target_list_v2

        caller = MagicMock(group_list=[1])
        with patch("apps.job_mgmt.nats_api._verify_token", return_value=caller):
            result = job_target_list_v2({"caller_token": "valid"})

        assert result == {
            "result": True,
            "data": {"items": [], "next_cursor": None, "has_more": False},
        }
