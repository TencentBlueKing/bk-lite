"""ScriptExecutionRunner 单测（merge_script_with_params 纯函数 + 执行分支）"""

from unittest.mock import patch

import pytest

from apps.job_mgmt.constants import DangerousLevel, ExecutionStatus, JobType, ScriptType, TargetSource
from apps.job_mgmt.models import DangerousRule, JobExecution
from apps.job_mgmt.services.script_execution_runner import ScriptExecutionRunner

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

EXEC_PATH = "apps.job_mgmt.services.script_execution_runner.Executor"
PUB_PATH = "apps.job_mgmt.services.script_execution_runner.publish_done_sentinel"


class TestMergeScriptWithParams:
    def _runner(self):
        return ScriptExecutionRunner(1)

    def test_empty_params_returns_content(self):
        assert self._runner().merge_script_with_params("echo", "", ScriptType.SHELL) == "echo"

    def test_shell_injects_positional(self):
        out = self._runner().merge_script_with_params("echo $1", "'a' 'b'", ScriptType.SHELL)
        assert out.startswith("set -- ") and "echo $1" in out

    def test_python_injects_argv(self):
        out = self._runner().merge_script_with_params("print(1)", "'a'", ScriptType.PYTHON)
        assert "_sys.argv" in out

    def test_powershell_injects_args(self):
        out = self._runner().merge_script_with_params("echo", "'a'", ScriptType.POWERSHELL)
        assert "$args = @(" in out

    def test_bat_unchanged(self):
        assert self._runner().merge_script_with_params("echo", "'a'", ScriptType.BAT) == "echo"


def _execution(**over):
    defaults = {
        "name": "s",
        "job_type": JobType.SCRIPT,
        "status": ExecutionStatus.RUNNING,
        "script_content": "echo hi",
        "script_type": "shell",
        "target_source": TargetSource.NODE_MGMT,
        "target_list": [{"node_id": "n1", "name": "h", "ip": "1.1.1.1"}],
        "team": [1],
    }
    defaults.update(over)
    return JobExecution.objects.create(**defaults)


class TestDangerousCommand:
    def test_blocks_and_publishes(self):
        DangerousRule.objects.create(name="no-rm", pattern="rm -rf", level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[])
        ex = _execution(script_content="rm -rf /")
        with patch(PUB_PATH) as pub:
            blocked = ScriptExecutionRunner(ex.id)._handle_dangerous_command(ex, ex.target_list)
        assert blocked is True
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.FAILED
        pub.assert_called()

    def test_safe_command_returns_false(self):
        ex = _execution()
        assert ScriptExecutionRunner(ex.id)._handle_dangerous_command(ex, ex.target_list) is False


class TestRunViaAnsibleIfNeeded:
    def test_node_mgmt_returns_false(self):
        ex = _execution()
        assert ScriptExecutionRunner(ex.id)._run_via_ansible_if_needed(ex, ex.target_list, "echo") is False

    def test_ansible_success(self):
        from apps.job_mgmt.constants import CredentialSource, ExecutorDriver, OSType, SSHCredentialType
        from apps.job_mgmt.models import Target

        t = Target.objects.create(
            name="t",
            ip="10.0.0.1",
            os_type=OSType.LINUX,
            driver=ExecutorDriver.ANSIBLE,
            credential_source=CredentialSource.MANUAL,
            ssh_user="root",
            ssh_credential_type=SSHCredentialType.PASSWORD,
            ssh_password="pw",
            cloud_region_id=1,
            team=[1],
        )
        ex = _execution(target_source=TargetSource.MANUAL, target_list=[{"target_id": t.id}])
        with patch.object(ScriptExecutionRunner, "_execute_script_via_ansible") as mexec:
            handled = ScriptExecutionRunner(ex.id)._run_via_ansible_if_needed(ex, [{"target_id": t.id}], "echo")
        assert handled is True
        mexec.assert_called_once()

    def test_ansible_exception_marks_failed(self):
        from apps.job_mgmt.constants import CredentialSource, ExecutorDriver, OSType, SSHCredentialType
        from apps.job_mgmt.models import Target

        t = Target.objects.create(
            name="t",
            ip="10.0.0.1",
            os_type=OSType.LINUX,
            driver=ExecutorDriver.ANSIBLE,
            credential_source=CredentialSource.MANUAL,
            ssh_user="root",
            ssh_credential_type=SSHCredentialType.PASSWORD,
            ssh_password="pw",
            cloud_region_id=1,
            team=[1],
        )
        ex = _execution(target_source=TargetSource.MANUAL, target_list=[{"target_id": t.id}])
        with patch.object(ScriptExecutionRunner, "_execute_script_via_ansible", side_effect=RuntimeError("boom")), patch(PUB_PATH):
            handled = ScriptExecutionRunner(ex.id)._run_via_ansible_if_needed(ex, [{"target_id": t.id}], "echo")
        assert handled is True
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.FAILED


class TestExecuteScriptOnTarget:
    def test_cancelled_skips(self):
        ex = _execution(status=ExecutionStatus.CANCELLED)
        result = ScriptExecutionRunner(ex.id).execute_script_on_target(
            {"node_id": "n1", "name": "h", "ip": "1.1.1.1"}, TargetSource.NODE_MGMT, "echo", "shell", 60, ex.id
        )
        assert result["status"] == ExecutionStatus.CANCELLED

    def test_node_mgmt_str_result_success(self):
        ex = _execution()
        with patch(EXEC_PATH) as MExec:
            MExec.return_value.execute_local_stream.return_value = "done output"
            result = ScriptExecutionRunner(ex.id).execute_script_on_target(
                {"node_id": "n1", "name": "h", "ip": "1.1.1.1"}, TargetSource.NODE_MGMT, "echo", "shell", 60, ex.id
            )
        assert result["status"] == ExecutionStatus.SUCCESS and result["stdout"] == "done output"

    def test_node_mgmt_dict_failed(self):
        ex = _execution()
        with patch(EXEC_PATH) as MExec:
            MExec.return_value.execute_local_stream.return_value = {"stdout": "x", "exit_code": 1, "stderr": "err"}
            result = ScriptExecutionRunner(ex.id).execute_script_on_target(
                {"node_id": "n1", "name": "h", "ip": "1.1.1.1"}, TargetSource.NODE_MGMT, "echo", "shell", 60, ex.id
            )
        assert result["status"] == ExecutionStatus.FAILED

    def test_node_mgmt_dict_timeout(self):
        ex = _execution()
        with patch(EXEC_PATH) as MExec:
            MExec.return_value.execute_local_stream.return_value = {"code": "timeout", "result": "x"}
            result = ScriptExecutionRunner(ex.id).execute_script_on_target(
                {"node_id": "n1", "name": "h", "ip": "1.1.1.1"}, TargetSource.NODE_MGMT, "echo", "shell", 60, ex.id
            )
        assert result["status"] == ExecutionStatus.TIMEOUT

    def test_manual_missing_creds_marks_failed(self):
        ex = _execution(target_source=TargetSource.MANUAL, target_list=[{"target_id": 999999}])
        with patch.object(ScriptExecutionRunner, "get_ssh_credentials", return_value={}):
            result = ScriptExecutionRunner(ex.id).execute_script_on_target(
                {"target_id": 999999, "name": "h", "ip": "1.1.1.1"}, TargetSource.MANUAL, "echo", "shell", 60, ex.id
            )
        assert result["status"] == ExecutionStatus.FAILED
