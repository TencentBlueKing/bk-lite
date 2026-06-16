# server/apps/job_mgmt/tests/test_script_runner_streaming.py
from unittest.mock import MagicMock, patch

import pytest

from apps.job_mgmt.constants import ExecutionStatus, ScriptType, TargetSource
from apps.job_mgmt.services.script_execution_runner import ScriptExecutionRunner

pytestmark = pytest.mark.unit


def _runner():
    return ScriptExecutionRunner(execution_id=99)


def test_ssh_branch_calls_execute_ssh_stream_with_topic():
    runner = _runner()
    target = {"target_id": 5, "name": "host1", "ip": "1.2.3.4"}
    fake_exec = MagicMock()
    fake_exec.execute_ssh_stream.return_value = {"stdout": "hi", "stderr": "", "exit_code": 0}

    with patch("apps.job_mgmt.services.script_execution_runner.Executor", return_value=fake_exec), \
         patch.object(ScriptExecutionRunner, "is_cancelled", return_value=False), \
         patch.object(ScriptExecutionRunner, "get_ssh_credentials", return_value={
             "node_id": "region-1", "host": "1.2.3.4", "username": "root",
             "password": "p", "private_key": None, "port": 22,
         }):
        result = runner.execute_script_on_target(
            target, TargetSource.MANUAL, "echo hi", ScriptType.SHELL, 60, 99
        )

    assert fake_exec.execute_ssh_stream.called
    kwargs = fake_exec.execute_ssh_stream.call_args.kwargs
    assert kwargs["stream_log_topic"] == "job.stream.99.5"
    assert kwargs["execution_id"] == "99"
    assert result["status"] == ExecutionStatus.SUCCESS


def test_crlf_script_normalized_to_lf_for_shell():
    """Windows 粘贴的 CRLF shell 脚本应转成 LF，避免 Linux bash 报 $'\\r' 语法错误。"""
    runner = _runner()
    target = {"node_id": "n7", "name": "h1", "ip": "1.2.3.4"}
    fake_exec = MagicMock()
    fake_exec.execute_local_stream.return_value = {"stdout": "", "stderr": "", "exit_code": 0}
    crlf = "#!/bin/bash\r\necho hi\r\nfor i in 1 2; do echo $i; done\r\n"

    with patch("apps.job_mgmt.services.script_execution_runner.Executor", return_value=fake_exec), \
         patch.object(ScriptExecutionRunner, "is_cancelled", return_value=False):
        runner.execute_script_on_target(target, TargetSource.NODE_MGMT, crlf, ScriptType.SHELL, 60, 99)

    sent = fake_exec.execute_local_stream.call_args.args[0]
    assert "\r" not in sent
    assert "for i in 1 2; do echo $i; done" in sent


def test_crlf_preserved_for_windows_bat():
    """Windows 原生脚本(bat)保留 CRLF，不做规范化。"""
    runner = _runner()
    target = {"node_id": "n7", "name": "h1", "ip": "1.2.3.4"}
    fake_exec = MagicMock()
    fake_exec.execute_local_stream.return_value = {"stdout": "", "stderr": "", "exit_code": 0}

    with patch("apps.job_mgmt.services.script_execution_runner.Executor", return_value=fake_exec), \
         patch.object(ScriptExecutionRunner, "is_cancelled", return_value=False):
        runner.execute_script_on_target(target, TargetSource.NODE_MGMT, "echo hi\r\n", ScriptType.BAT, 60, 99)

    sent = fake_exec.execute_local_stream.call_args.args[0]
    assert "\r\n" in sent


def test_local_branch_calls_execute_local_stream_with_topic():
    runner = _runner()
    target = {"node_id": "node-7", "name": "h1", "ip": "1.2.3.4"}
    fake_exec = MagicMock()
    fake_exec.execute_local_stream.return_value = {"stdout": "hi", "stderr": "", "exit_code": 0}

    with patch("apps.job_mgmt.services.script_execution_runner.Executor", return_value=fake_exec), \
         patch.object(ScriptExecutionRunner, "is_cancelled", return_value=False):
        result = runner.execute_script_on_target(
            target, TargetSource.NODE_MGMT, "echo hi", ScriptType.SHELL, 60, 99
        )

    assert fake_exec.execute_local_stream.called
    kwargs = fake_exec.execute_local_stream.call_args.kwargs
    assert kwargs["stream_log_topic"] == "job.stream.99.node-7"
    assert kwargs["execution_id"] == "99"
    assert result["status"] == ExecutionStatus.SUCCESS


def test_sidecar_publishes_done_sentinel_per_target():
    runner = _runner()
    execution = MagicMock()
    execution.id = 99
    execution.target_source = TargetSource.MANUAL
    execution.script_type = ScriptType.SHELL
    execution.timeout = 60
    target_list = [{"target_id": 5, "name": "h1", "ip": "1.1.1.1"}]

    with patch.object(ScriptExecutionRunner, "execute_script_on_target", return_value={
            "target_key": "5", "name": "h1", "status": ExecutionStatus.SUCCESS}), \
         patch.object(ScriptExecutionRunner, "is_cancelled", return_value=False), \
         patch("apps.job_mgmt.services.script_execution_runner.publish_done_sentinel") as mock_done:
        runner._run_via_sidecar(execution, target_list, "echo hi")

    mock_done.assert_called_once_with(99, "5", ExecutionStatus.SUCCESS)


def test_dangerous_command_publishes_done_for_all_targets():
    runner = _runner()
    execution = MagicMock()
    execution.id = 99
    execution.script_content = "rm -rf /"
    execution.team = [1]
    target_list = [
        {"target_id": 5, "name": "h1", "ip": "1.1.1.1"},
        {"node_id": "n7", "name": "h2", "ip": "2.2.2.2"},
    ]
    check = MagicMock()
    check.can_execute = False
    check.forbidden = [{"rule_name": "rm-rf"}]

    with patch("apps.job_mgmt.services.script_execution_runner.DangerousChecker.check_command", return_value=check), \
         patch("apps.job_mgmt.services.script_execution_runner.publish_done_sentinel") as mock_done:
        handled = runner._handle_dangerous_command(execution, target_list)

    assert handled is True
    done_targets = {c.args[1] for c in mock_done.call_args_list}
    assert done_targets == {"5", "n7"}
    for c in mock_done.call_args_list:
        assert c.args[2] == ExecutionStatus.FAILED


def test_ansible_windows_reject_publishes_done_for_all_targets():
    runner = _runner()
    execution = MagicMock()
    execution.id = 99
    execution.target_source = TargetSource.MANUAL
    target_list = [
        {"target_id": 5, "name": "h1", "ip": "1.1.1.1"},
        {"target_id": 6, "name": "h2", "ip": "2.2.2.2"},
    ]
    with patch.object(ScriptExecutionRunner, "_contains_windows_manual_target", return_value=True), \
         patch.object(ScriptExecutionRunner, "_should_use_ansible", return_value=False), \
         patch("apps.job_mgmt.services.script_execution_runner.publish_done_sentinel") as mock_done:
        handled = runner._run_via_ansible_if_needed(execution, target_list, "echo hi")

    assert handled is True
    done_targets = {c.args[1] for c in mock_done.call_args_list}
    assert done_targets == {"5", "6"}
    assert all(c.args[2] == ExecutionStatus.FAILED for c in mock_done.call_args_list)


def test_ansible_submit_failure_publishes_done_for_all_targets():
    runner = _runner()
    execution = MagicMock()
    execution.id = 99
    execution.target_source = TargetSource.MANUAL
    execution.script_type = ScriptType.SHELL
    target_list = [{"target_id": 5, "name": "h1", "ip": "1.1.1.1"}]
    with patch.object(ScriptExecutionRunner, "_contains_windows_manual_target", return_value=False), \
         patch.object(ScriptExecutionRunner, "_should_use_ansible", return_value=True), \
         patch.object(ScriptExecutionRunner, "_execute_script_via_ansible", side_effect=RuntimeError("boom")), \
         patch("apps.job_mgmt.services.script_execution_runner.publish_done_sentinel") as mock_done:
        handled = runner._run_via_ansible_if_needed(execution, target_list, "echo hi")

    assert handled is True
    mock_done.assert_called_once_with(99, "5", ExecutionStatus.FAILED)


def test_publish_cancelled_sentinels_only_for_unsentineled():
    """已发过哨兵的目标跳过；未发过的补发 CANCELLED（spec §8）。"""
    runner = _runner()
    target_list = [
        {"target_id": 5, "name": "h1"},
        {"node_id": "n7", "name": "h2"},
    ]
    sentineled = {"5"}
    with patch("apps.job_mgmt.services.script_execution_runner.publish_done_sentinel") as mock_done:
        runner._publish_cancelled_sentinels(99, target_list, sentineled)

    mock_done.assert_called_once_with(99, "n7", ExecutionStatus.CANCELLED)
    assert sentineled == {"5", "n7"}


def test_sidecar_invokes_cancelled_sweep_when_cancelled():
    """取消时，_run_via_sidecar 在收尾对未产出结果的目标补发 CANCELLED。"""
    runner = _runner()
    execution = MagicMock()
    execution.id = 99
    execution.target_source = TargetSource.MANUAL
    execution.script_type = ScriptType.SHELL
    execution.timeout = 60
    target_list = [{"target_id": 5, "name": "h1", "ip": "1.1.1.1"}]

    with patch.object(ScriptExecutionRunner, "execute_script_on_target", return_value={
            "target_key": "5", "name": "h1", "status": ExecutionStatus.SUCCESS}), \
         patch.object(ScriptExecutionRunner, "is_cancelled", return_value=True), \
         patch("apps.job_mgmt.services.script_execution_runner.publish_done_sentinel"), \
         patch.object(ScriptExecutionRunner, "_publish_cancelled_sentinels") as mock_sweep:
        runner._run_via_sidecar(execution, target_list, "echo hi")

    mock_sweep.assert_called_once()
    args = mock_sweep.call_args.args
    assert args[0] == 99
    assert args[1] == target_list
    assert "5" in args[2]
