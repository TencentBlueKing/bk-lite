"""ExecutionTaskBaseService 单测（凭据 / 执行准备 / 状态 / 错误规整）"""

from unittest.mock import patch

import pytest

from apps.core.mixinx import EncryptMixin
from apps.job_mgmt.constants import CredentialSource, ExecutionStatus, ExecutorDriver, JobType, OSType, SSHCredentialType, TargetSource
from apps.job_mgmt.models import JobExecution, Target
from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService as Base

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _execution(**over):
    defaults = {"name": "e", "job_type": JobType.SCRIPT, "status": ExecutionStatus.PENDING, "team": [1]}
    defaults.update(over)
    return JobExecution.objects.create(**defaults)


def _target(**over):
    defaults = {
        "name": "t",
        "ip": "10.0.0.1",
        "os_type": OSType.LINUX,
        "driver": ExecutorDriver.ANSIBLE,
        "credential_source": CredentialSource.MANUAL,
        "ssh_user": "root",
        "ssh_credential_type": SSHCredentialType.PASSWORD,
        "ssh_password": "secret",
        "cloud_region_id": 1,
        "team": [1],
    }
    defaults.update(over)
    return Target.objects.create(**defaults)


class TestDecryptPassword:
    def test_none_returns_none(self):
        assert Base.decrypt_password(None) is None
        assert Base.decrypt_password("") is None

    def test_roundtrip(self):
        data = {"password": "topsecret"}
        EncryptMixin.encrypt_field("password", data)
        assert Base.decrypt_password(data["password"]) == "topsecret"


class TestPrepareExecution:
    def test_missing_execution_returns_none(self):
        svc = Base(999999, "t")
        execution, targets = svc.prepare_execution()
        assert execution is None and targets == []

    def test_cancelled_returns_none(self):
        ex = _execution(status=ExecutionStatus.CANCELLED, target_list=[{"target_id": 1}])
        svc = Base(ex.id, "t")
        execution, targets = svc.prepare_execution()
        assert execution is None

    def test_no_targets_marks_success(self):
        ex = _execution(target_list=[])
        svc = Base(ex.id, "t")
        execution, targets = svc.prepare_execution()
        assert execution is None
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.SUCCESS

    def test_running_returns_execution_and_targets(self):
        ex = _execution(target_list=[{"target_id": 1}])
        svc = Base(ex.id, "t")
        execution, targets = svc.prepare_execution()
        assert execution is not None
        assert targets == [{"target_id": 1}]
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.RUNNING


class TestStatusAndCancel:
    def test_update_status_with_finished_at(self):
        from django.utils import timezone

        ex = _execution()
        Base.update_execution_status(ex, ExecutionStatus.SUCCESS, finished_at=timezone.now())
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.SUCCESS and ex.finished_at is not None

    def test_is_cancelled_true(self):
        ex = _execution(status=ExecutionStatus.CANCELLED)
        assert Base.is_cancelled(ex.id) is True

    def test_is_cancelled_false(self):
        ex = _execution()
        assert Base.is_cancelled(ex.id) is False


class TestFinalizeExecution:
    def test_normal_marks_success_when_no_failures(self):
        ex = _execution(status=ExecutionStatus.RUNNING)
        with patch("apps.job_mgmt.services.execution_base_service.send_callback"):
            Base.finalize_execution(ex, "t", [{"status": ExecutionStatus.SUCCESS}])
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.SUCCESS
        assert ex.success_count == 1

    def test_normal_marks_failed_when_any_failure(self):
        ex = _execution(status=ExecutionStatus.RUNNING)
        with patch("apps.job_mgmt.services.execution_base_service.send_callback"):
            Base.finalize_execution(ex, "t", [{"status": ExecutionStatus.FAILED}])
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.FAILED

    def test_cancelled_keeps_cancelled_status(self):
        ex = _execution(status=ExecutionStatus.CANCELLED)
        with patch("apps.job_mgmt.services.execution_base_service.send_callback"):
            Base.finalize_execution(ex, "t", [{"status": ExecutionStatus.SUCCESS}])
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.CANCELLED


class TestAnsibleSelection:
    def test_should_use_ansible_non_manual_false(self):
        assert Base._should_use_ansible(TargetSource.NODE_MGMT, [{"target_id": 1}]) is False

    def test_should_use_ansible_no_ids_false(self):
        assert Base._should_use_ansible(TargetSource.MANUAL, [{}]) is False

    def test_should_use_ansible_true_for_ansible_driver(self):
        t = _target(driver=ExecutorDriver.ANSIBLE)
        assert Base._should_use_ansible(TargetSource.MANUAL, [{"target_id": t.id}]) is True

    def test_get_manual_targets(self):
        t = _target()
        assert [x.id for x in Base._get_manual_targets([{"target_id": t.id}])] == [t.id]
        assert Base._get_manual_targets([{}]) == []

    def test_contains_windows_manual_target(self):
        t = _target(os_type=OSType.WINDOWS, winrm_user="a", winrm_password="b")
        assert Base._contains_windows_manual_target([{"target_id": t.id}]) is True


class TestBuildHostCredentials:
    def test_linux_password(self):
        t = _target()
        creds = Base._build_host_credentials([t])
        assert creds[0]["connection"] == "ssh"
        assert creds[0]["password"] == "secret"

    def test_linux_key(self):
        t = _target(ssh_credential_type=SSHCredentialType.KEY)
        with patch.object(Base, "_read_ssh_key_file", staticmethod(lambda x: "PRIVATE")):
            creds = Base._build_host_credentials([t])
        assert creds[0]["private_key_content"] == "PRIVATE"

    def test_windows(self):
        t = _target(os_type=OSType.WINDOWS, winrm_user="adm", winrm_password="pw")
        creds = Base._build_host_credentials([t])
        assert creds[0]["connection"] == "winrm"

    def test_credential_mode_skipped(self):
        t = _target(credential_source=CredentialSource.CREDENTIAL, credential_id="c1")
        assert Base._build_host_credentials([t]) == []


class TestErrorFormatting:
    def test_format_error_with_keyword(self):
        msg = Base.format_error_message(ConnectionError("connection refused"))
        assert "connection" in msg or "refused" in msg

    def test_format_error_without_keyword_short(self):
        msg = Base.format_error_message(ValueError("oops"))
        assert "ValueError" in msg

    def test_format_error_long_truncated(self):
        msg = Base.format_error_message(ValueError("x" * 300))
        assert "ValueError" in msg

    @pytest.mark.parametrize(
        "exec_result,expect",
        [
            ({"stage": "tcp_connect", "error": "e"}, "不可达"),
            ({"stage": "ssh_dial", "category": "network", "error": "e"}, "网络"),
            ({"stage": "ssh_dial", "category": "auth", "error": "e"}, "认证失败"),
            ({"stage": "legacy_retry", "category": "compatibility", "error": "e"}, "兼容性"),
            ({"stage": "session_create", "error": "e"}, "会话创建"),
            ({"stage": "command_run", "category": "remote_timeout", "error": "e"}, "超时"),
            ({"stage": "command_run", "category": "remote_exit", "error": "e"}, "执行失败"),
            ({"code": "timeout", "error": "e"}, "超时"),
        ],
    )
    def test_normalize_executor_error_branches(self, exec_result, expect):
        assert expect in Base.normalize_executor_error(exec_result, "默认")

    def test_normalize_executor_error_plain_message(self):
        assert Base.normalize_executor_error("just a message") == "just a message"

    def test_normalize_executor_error_default(self):
        assert Base.normalize_executor_error(123, "默认失败") == "默认失败"
