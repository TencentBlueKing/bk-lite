"""ExecutionService 单测（C4）

验证从 view 下沉的对象校验、危险检测逻辑：

- 目标 / 文件 / 脚本 / Playbook 不存在或团队不匹配 → 抛 :class:`ExecutionAuthorizationError`
  并携带正确的 HTTP 状态码（400 / 403）；
- 危险命令 / 路径检出 → 抛错并附带规则名称。
"""

from unittest.mock import patch

import pytest

from apps.job_mgmt.constants import CredentialSource, ExecutionStatus, JobType, OSType, TargetSource, TriggerSource
from apps.job_mgmt.models import DistributionFile, JobExecution, Playbook, Script, Target
from apps.job_mgmt.services.execution_service import ExecutionAuthorizationError, ExecutionDispatchError, ExecutionService


def _make_target(team, **kwargs):
    defaults = {
        "name": "t1",
        "ip": "10.0.0.1",
        "os_type": OSType.LINUX,
        "credential_source": CredentialSource.MANUAL,
        "ssh_user": "root",
        "team": team,
    }
    defaults.update(kwargs)
    return Target.objects.create(**defaults)


@pytest.fixture
def authorized_teams():
    return {1, 2}


@pytest.mark.unit
@pytest.mark.django_db
class TestValidateManualTargets:
    def test_empty_target_list_returns_empty(self, authorized_teams):
        result = ExecutionService.validate_manual_targets([], authorized_teams)
        assert result == []

    def test_targets_without_target_id_are_ignored(self, authorized_teams):
        """node_mgmt 来源的目标可能没有 target_id，函数应跳过校验"""
        result = ExecutionService.validate_manual_targets([{"node_id": "n1"}, {"name": "x"}], authorized_teams)
        assert result == []

    def test_missing_target_raises_400(self, authorized_teams):
        with pytest.raises(ExecutionAuthorizationError) as exc:
            ExecutionService.validate_manual_targets([{"target_id": 999_999}], authorized_teams)
        assert exc.value.status_code == 400
        assert "不存在" in exc.value.message

    def test_target_outside_authorized_team_raises_403(self, authorized_teams):
        t = _make_target(team=[99])
        with pytest.raises(ExecutionAuthorizationError) as exc:
            ExecutionService.validate_manual_targets([{"target_id": t.id}], authorized_teams, error_label="分发")
        assert exc.value.status_code == 403
        assert "分发" in exc.value.message

    def test_authorized_target_passes(self, authorized_teams):
        t = _make_target(team=[1])
        result = ExecutionService.validate_manual_targets([{"target_id": t.id}], authorized_teams)
        assert [tg.id for tg in result] == [t.id]

    def test_superuser_bypasses_team_check(self):
        """authorized_team_ids=None 表示超管，应放行所有团队"""
        t = _make_target(team=[999])
        result = ExecutionService.validate_manual_targets([{"target_id": t.id}], authorized_team_ids=None)
        assert [tg.id for tg in result] == [t.id]


@pytest.mark.unit
@pytest.mark.django_db
class TestValidateDistributionFiles:
    def _make_file(self, team, **kwargs):
        from datetime import timedelta

        from django.utils import timezone

        defaults = {
            "original_name": "f.tar",
            "file_key": "job-files/x",
            "expire_at": timezone.now() + timedelta(days=7),
            "team": team,
        }
        defaults.update(kwargs)
        return DistributionFile.objects.create(**defaults)

    def test_missing_file_raises_400(self, authorized_teams):
        with pytest.raises(ExecutionAuthorizationError) as exc:
            ExecutionService.validate_distribution_files([999_999], authorized_teams)
        assert exc.value.status_code == 400
        assert "不存在" in exc.value.message

    def test_file_outside_authorized_team_raises_403(self, authorized_teams):
        f = self._make_file(team=99)
        with pytest.raises(ExecutionAuthorizationError) as exc:
            ExecutionService.validate_distribution_files([f.id], authorized_teams)
        assert exc.value.status_code == 403
        assert "分发" in exc.value.message

    def test_authorized_file_passes(self, authorized_teams):
        f = self._make_file(team=1)
        result = ExecutionService.validate_distribution_files([f.id], authorized_teams)
        assert [df.id for df in result] == [f.id]


@pytest.mark.unit
@pytest.mark.django_db
class TestFetchAuthorizedScriptAndPlaybook:
    def test_script_not_found_raises_403(self, authorized_teams):
        with pytest.raises(ExecutionAuthorizationError) as exc:
            ExecutionService.fetch_authorized_script(999_999, authorized_teams)
        assert exc.value.status_code == 403

    def test_script_outside_team_raises_403(self, authorized_teams):
        s = Script.objects.create(name="s", content="echo", team=[99])
        with pytest.raises(ExecutionAuthorizationError) as exc:
            ExecutionService.fetch_authorized_script(s.id, authorized_teams)
        assert exc.value.status_code == 403

    def test_script_authorized_returns_instance(self, authorized_teams):
        s = Script.objects.create(name="s", content="echo", team=[1])
        result = ExecutionService.fetch_authorized_script(s.id, authorized_teams)
        assert result.id == s.id

    def test_playbook_outside_team_raises_403(self, authorized_teams):
        p = Playbook.objects.create(name="p", version="v1.0.0", team=[99])
        with pytest.raises(ExecutionAuthorizationError) as exc:
            ExecutionService.fetch_authorized_playbook(p.id, authorized_teams)
        assert exc.value.status_code == 403

    def test_playbook_authorized_returns_instance(self, authorized_teams):
        p = Playbook.objects.create(name="p", version="v1.0.0", team=[1])
        result = ExecutionService.fetch_authorized_playbook(p.id, authorized_teams)
        assert result.id == p.id


@pytest.mark.unit
class TestDangerousChecks:
    def test_dangerous_command_blocked_raises_400_with_rules(self):
        check_result = type("R", (), {"can_execute": False, "forbidden": [{"rule_name": "rm -rf /"}]})()
        with patch("apps.job_mgmt.services.execution_service.DangerousChecker.check_command", return_value=check_result):
            with pytest.raises(ExecutionAuthorizationError) as exc:
                ExecutionService.check_dangerous_command("rm -rf /", team=[1])
        assert exc.value.status_code == 400
        assert "rm -rf /" in exc.value.message
        assert "高危命令" in exc.value.message

    def test_dangerous_command_allowed_passes(self):
        check_result = type("R", (), {"can_execute": True, "forbidden": []})()
        with patch("apps.job_mgmt.services.execution_service.DangerousChecker.check_command", return_value=check_result):
            ExecutionService.check_dangerous_command("echo ok", team=[1])

    def test_dangerous_path_blocked_raises_400(self):
        check_result = type("R", (), {"can_execute": False, "forbidden": [{"rule_name": "/etc"}]})()
        with patch("apps.job_mgmt.services.execution_service.DangerousChecker.check_path", return_value=check_result):
            with pytest.raises(ExecutionAuthorizationError) as exc:
                ExecutionService.check_dangerous_path("/etc/passwd", team=[1])
        assert exc.value.status_code == 400
        assert "高危路径" in exc.value.message

    def test_dangerous_path_allowed_passes(self):
        check_result = type("R", (), {"can_execute": True, "forbidden": []})()
        with patch("apps.job_mgmt.services.execution_service.DangerousChecker.check_path", return_value=check_result):
            ExecutionService.check_dangerous_path("/tmp/x", team=[1])


@pytest.mark.unit
@pytest.mark.django_db
class TestBuildFilesInfo:
    def test_maps_distribution_file_to_payload_dict(self):
        from datetime import timedelta

        from django.utils import timezone

        df = DistributionFile.objects.create(
            original_name="a.bin",
            file_key="job-files/a",
            expire_at=timezone.now() + timedelta(days=7),
            team=1,
        )
        result = ExecutionService.build_files_info([df])
        assert result == [{"name": "a.bin", "file_key": "job-files/a"}]


# create_* 方法会派发任务；用 patch 绕开真实 Celery，仅断言派发被调用 / 失败处理
DISPATCH_PATH = "apps.job_mgmt.services.celery_dispatch.dispatch_celery_task"


@pytest.mark.unit
@pytest.mark.django_db
class TestCreateQuickExecution:
    def test_script_content_mode_creates_and_dispatches(self):
        with patch(DISPATCH_PATH, return_value="celery-1") as dispatch:
            execution = ExecutionService.create_quick_execution(
                data={
                    "name": "临时脚本",
                    "target_source": TargetSource.NODE_MGMT,
                    "target_list": [{"node_id": "n1"}],
                    "script_content": "echo hi",
                    "script_type": "shell",
                },
                team=[1],
                authorized_team_ids={1},
                username="alice",
                timeout_explicit=False,
            )
        assert execution.pk is not None
        assert execution.job_type == JobType.SCRIPT
        assert execution.script_content == "echo hi"
        assert execution.executor_user == "alice"
        assert execution.total_count == 1
        dispatch.assert_called_once()

    def test_script_library_mode_uses_script_timeout_when_not_explicit(self):
        script = Script.objects.create(name="s", content="echo lib", script_type="shell", team=[1], timeout=999)
        with patch(DISPATCH_PATH, return_value="celery-1"):
            execution = ExecutionService.create_quick_execution(
                data={
                    "name": "库脚本",
                    "target_source": TargetSource.NODE_MGMT,
                    "target_list": [{"node_id": "n1"}],
                    "script_id": script.id,
                },
                team=[1],
                authorized_team_ids={1},
                username="alice",
                timeout_explicit=False,
            )
        assert execution.script_id == script.id
        assert execution.script_content == "echo lib"
        assert execution.timeout == 999

    def test_explicit_timeout_overrides_script_default(self):
        script = Script.objects.create(name="s", content="echo", script_type="shell", team=[1], timeout=999)
        with patch(DISPATCH_PATH, return_value="celery-1"):
            execution = ExecutionService.create_quick_execution(
                data={
                    "name": "x",
                    "target_source": TargetSource.NODE_MGMT,
                    "target_list": [{"node_id": "n1"}],
                    "script_id": script.id,
                    "timeout": 30,
                },
                team=[1],
                authorized_team_ids={1},
                username="alice",
                timeout_explicit=True,
            )
        assert execution.timeout == 30

    def test_playbook_mode_creates_playbook_execution(self):
        playbook = Playbook.objects.create(name="p", version="v1.0.0", team=[1])
        with patch(DISPATCH_PATH, return_value="celery-1"):
            execution = ExecutionService.create_quick_execution(
                data={
                    "name": "pb",
                    "target_source": TargetSource.NODE_MGMT,
                    "target_list": [{"node_id": "n1"}],
                    "playbook_id": playbook.id,
                    "params": [],
                },
                team=[1],
                authorized_team_ids={1},
                username="alice",
                timeout_explicit=False,
            )
        assert execution.job_type == JobType.PLAYBOOK
        assert execution.playbook_id == playbook.id
        assert execution.playbook_version == "v1.0.0"

    def test_unauthorized_script_raises_403_before_create(self):
        script = Script.objects.create(name="s", content="echo", script_type="shell", team=[99])
        with patch(DISPATCH_PATH) as dispatch:
            with pytest.raises(ExecutionAuthorizationError) as exc:
                ExecutionService.create_quick_execution(
                    data={
                        "name": "x",
                        "target_source": TargetSource.NODE_MGMT,
                        "target_list": [{"node_id": "n1"}],
                        "script_id": script.id,
                    },
                    team=[1],
                    authorized_team_ids={1},
                    username="alice",
                    timeout_explicit=False,
                )
        assert exc.value.status_code == 403
        dispatch.assert_not_called()
        assert JobExecution.objects.count() == 0

    def test_dispatch_failure_raises_503(self):
        with patch(DISPATCH_PATH, return_value=None):
            with pytest.raises(ExecutionDispatchError) as exc:
                ExecutionService.create_quick_execution(
                    data={
                        "name": "x",
                        "target_source": TargetSource.NODE_MGMT,
                        "target_list": [{"node_id": "n1"}],
                        "script_content": "echo",
                        "script_type": "shell",
                    },
                    team=[1],
                    authorized_team_ids={1},
                    username="alice",
                    timeout_explicit=False,
                )
        assert exc.value.status_code == 503


@pytest.mark.unit
@pytest.mark.django_db
class TestCreateFileDistribution:
    def _make_file(self, team=1):
        from datetime import timedelta

        from django.utils import timezone

        return DistributionFile.objects.create(
            original_name="f.tar",
            file_key="job-files/f",
            expire_at=timezone.now() + timedelta(days=7),
            team=team,
        )

    def test_creates_file_distribution_execution(self):
        f = self._make_file(team=1)
        with patch(DISPATCH_PATH, return_value="celery-1") as dispatch:
            execution = ExecutionService.create_file_distribution(
                data={
                    "name": "分发",
                    "target_source": TargetSource.NODE_MGMT,
                    "target_list": [{"node_id": "n1"}],
                    "target_path": "/tmp/app",
                    "file_ids": [f.id],
                },
                team=[1],
                authorized_team_ids={1},
                username="bob",
            )
        assert execution.job_type == JobType.FILE_DISTRIBUTION
        assert execution.target_path == "/tmp/app"
        assert execution.files == [{"name": "f.tar", "file_key": "job-files/f"}]
        dispatch.assert_called_once()

    def test_unauthorized_file_raises_403(self):
        f = self._make_file(team=99)
        with patch(DISPATCH_PATH) as dispatch:
            with pytest.raises(ExecutionAuthorizationError) as exc:
                ExecutionService.create_file_distribution(
                    data={
                        "name": "x",
                        "target_source": TargetSource.NODE_MGMT,
                        "target_list": [{"node_id": "n1"}],
                        "target_path": "/tmp",
                        "file_ids": [f.id],
                    },
                    team=[1],
                    authorized_team_ids={1},
                    username="bob",
                )
        assert exc.value.status_code == 403
        dispatch.assert_not_called()


@pytest.mark.unit
@pytest.mark.django_db
class TestCreateReExecution:
    def _make_original(self, **kwargs):
        defaults = {
            "name": "orig",
            "job_type": JobType.SCRIPT,
            "status": ExecutionStatus.SUCCESS,
            "script_content": "echo",
            "script_type": "shell",
            "target_list": [{"node_id": "n1"}],
            "team": [1],
        }
        defaults.update(kwargs)
        return JobExecution.objects.create(**defaults)

    def test_empty_target_list_raises_400(self):
        original = self._make_original(target_list=[])
        with patch(DISPATCH_PATH):
            with pytest.raises(ExecutionAuthorizationError) as exc:
                ExecutionService.create_re_execution(original=original, username="bob", authorized_team_ids={1})
        assert exc.value.status_code == 400

    def test_script_re_execution_sets_manual_trigger(self):
        original = self._make_original()
        with patch(DISPATCH_PATH, return_value="celery-1"):
            execution = ExecutionService.create_re_execution(original=original, username="bob", authorized_team_ids={1})
        assert execution.id != original.id
        assert execution.trigger_source == TriggerSource.MANUAL
        assert execution.job_type == JobType.SCRIPT
        assert execution.script_content == "echo"

    def test_re_execution_normalizes_legacy_crlf(self):
        """re_execute 复制历史 script_content 时规范化,防止历史脏数据传递。"""
        original = self._make_original(
            script_content="echo a\r\necho b\r\n",
            script_type="shell",
        )
        with patch(DISPATCH_PATH, return_value="celery-1"):
            execution = ExecutionService.create_re_execution(original=original, username="bob", authorized_team_ids={1})
        # 新副本不含 CR
        assert "\r" not in execution.script_content
        assert execution.script_content.startswith("echo a\necho b")

    def test_re_execution_bat_preserves_crlf(self):
        crlf = "@echo off\r\nset x=1\r\n"
        original = self._make_original(script_content=crlf, script_type="bat")
        with patch(DISPATCH_PATH, return_value="celery-1"):
            execution = ExecutionService.create_re_execution(original=original, username="bob", authorized_team_ids={1})
        # bat 保留 CRLF
        assert "\r" in execution.script_content

    def test_playbook_re_execution_without_playbook_raises_400(self):
        original = self._make_original(job_type=JobType.PLAYBOOK, playbook=None)
        with patch(DISPATCH_PATH):
            with pytest.raises(ExecutionAuthorizationError) as exc:
                ExecutionService.create_re_execution(original=original, username="bob", authorized_team_ids={1})
        assert exc.value.status_code == 400

    # ---------- #3403：团队归属校验 ---------- #
    def test_cross_team_raises_403_before_create(self):
        original = self._make_original(team=[1])
        with patch(DISPATCH_PATH) as dispatch:
            with pytest.raises(ExecutionAuthorizationError) as exc:
                ExecutionService.create_re_execution(original=original, username="bob", authorized_team_ids={99})
        assert exc.value.status_code == 403
        dispatch.assert_not_called()
        # 越权时不得创建新执行（库中仅剩原始那 1 条）
        assert JobExecution.objects.count() == 1

    def test_superuser_bypasses_team_check(self):
        original = self._make_original(team=[999])
        with patch(DISPATCH_PATH, return_value="celery-1"):
            execution = ExecutionService.create_re_execution(original=original, username="bob", authorized_team_ids=None)
        assert execution.trigger_source == TriggerSource.MANUAL

    def test_referenced_script_cross_team_raises_403(self):
        script = Script.objects.create(name="s", content="echo", script_type="shell", team=[99])
        original = self._make_original(team=[1], script=script)
        with patch(DISPATCH_PATH) as dispatch:
            with pytest.raises(ExecutionAuthorizationError) as exc:
                ExecutionService.create_re_execution(original=original, username="bob", authorized_team_ids={1})
        assert exc.value.status_code == 403
        dispatch.assert_not_called()

    def test_referenced_playbook_cross_team_raises_403(self):
        playbook = Playbook.objects.create(name="p", version="v1.0.0", team=[99])
        original = self._make_original(team=[1], job_type=JobType.PLAYBOOK, playbook=playbook)
        with patch(DISPATCH_PATH) as dispatch:
            with pytest.raises(ExecutionAuthorizationError) as exc:
                ExecutionService.create_re_execution(original=original, username="bob", authorized_team_ids={1})
        assert exc.value.status_code == 403
        dispatch.assert_not_called()
