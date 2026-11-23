"""作业在最后一次组装连接时读取系统凭据，只将登录字段交给对应的执行器。"""

import logging
from unittest.mock import patch

import pytest

from apps.job_mgmt.constants import CredentialSource, ExecutionStatus, ExecutorDriver, JobType, OSType, ScriptType, TargetSource
from apps.job_mgmt.models import JobExecution, Playbook, Target
from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService
from apps.job_mgmt.services.file_distribution_runner import FileDistributionRunner
from apps.job_mgmt.services.playbook_execution import PlaybookExecution
from apps.job_mgmt.services.script_execution_runner import ScriptExecutionRunner
from apps.system_mgmt.models import Group
from apps.system_mgmt.services.credential_service import create_credential, seed_builtin_types, set_disabled, update_credential

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

KEY = "runner-private-key-sentinel"
PASSPHRASE = "runner-passphrase-sentinel"
PASSWORD = "runner-windows-password-sentinel"


@pytest.fixture
def team():
    seed_builtin_types()
    return Group.objects.create(name="vault-runner-team").id


def _target(team, *, os_type=OSType.LINUX, driver=ExecutorDriver.ANSIBLE, region=7):
    actor = {"username": "creator", "domain": "example.test", "current_team": team, "group_list": [team]}
    protocol = "winrm" if os_type == OSType.WINDOWS else "ssh"
    fields = (
        {"username": "vault-user", "password": PASSWORD}
        if protocol == "winrm"
        else {
            "username": "vault-user",
            "auth_method": "key",
            "private_key": KEY,
            "passphrase": PASSPHRASE,
        }
    )
    credential = create_credential({"name": "vault", "type": protocol, "group_id": team, "fields": fields}, actor=actor)
    target = Target.objects.create(
        name="remote",
        ip="192.0.2.16",
        os_type=os_type,
        driver=driver,
        node_id="executor",
        cloud_region_id=region,
        ssh_port=2222,
        ssh_user="old",
        ssh_password="never-use",
        winrm_user="old-win",
        winrm_password="never-use",
        winrm_scheme="http",
        winrm_port=5985,
        winrm_transport="ntlm",
        winrm_cert_validation=False,
        credential_source=CredentialSource.CREDENTIAL,
        credential_id=credential.credential_id,
        team=[team],
    )
    return target, actor


def _execution(team, targets, job_type=JobType.SCRIPT, **kwargs):
    return JobExecution.objects.create(
        name="scheduled vault run",
        job_type=job_type,
        team=[team],
        enforce_scheduled_team_boundary=True,
        script_type=ScriptType.SHELL,
        script_content="echo done",
        target_source=TargetSource.MANUAL,
        target_list=[{"target_id": target.id, "ip": target.ip} for target in targets],
        **kwargs,
    )


def _assert_no_secrets(value):
    for secret in (KEY, PASSPHRASE, PASSWORD, "never-use"):
        assert secret not in str(value)


def test_sidecar_scripts_and_linux_file_distribution_forward_key_passphrase(team, caplog):
    target, _ = _target(team, driver=ExecutorDriver.SIDECAR)
    execution = _execution(team, [target])
    with patch("apps.job_mgmt.services.script_execution_runner.Executor") as executor:
        executor.return_value.execute_ssh_stream.return_value = {"stdout": "done", "exit_code": 0}
        result = ScriptExecutionRunner(execution.id).execute_script_on_target(
            execution.target_list[0],
            TargetSource.MANUAL,
            "echo done",
            ScriptType.SHELL,
            30,
            execution.id,
            execution,
        )
    call = executor.return_value.execute_ssh_stream.call_args.kwargs
    assert result["status"] == ExecutionStatus.SUCCESS
    assert (call["username"], call["private_key"], call["passphrase"], call["password"], call["port"]) == ("vault-user", KEY, PASSPHRASE, None, 2222)
    _assert_no_secrets(result)

    with patch("apps.job_mgmt.services.file_distribution_runner.Executor") as executor:
        executor.return_value.download_to_remote.return_value = {"success": True, "result": "Warning: remote host key added"}
        response = FileDistributionRunner(execution.id).download_to_manual_target({"name": "file"}, target.id, "/tmp", 30, True, execution=execution)
    assert response == {"success": True}
    call = executor.return_value.download_to_remote.call_args.kwargs
    assert call["with_status"] is True
    assert (call["username"], call["private_key"], call["passphrase"], call["password"], call["port"]) == ("vault-user", KEY, PASSPHRASE, None, 2222)
    execution.refresh_from_db()
    _assert_no_secrets([execution.execution_results, execution.target_list, caplog.text])


@pytest.mark.parametrize("auth_method", ["password", "key"])
def test_ansible_script_mixes_vault_and_local_login_using_latest_fields(team, auth_method):
    target, actor = _target(team)
    if auth_method == "password":
        update_credential(target.credential_id, {"fields": {"username": "vault-user", "auth_method": "password", "password": PASSWORD}}, actor=actor)
    manual = Target.objects.create(name="manual", ip="192.0.2.17", team=[team], cloud_region_id=7, ssh_user="local-user", ssh_password="local-secret")
    execution = _execution(team, [manual, target])
    with patch.object(ExecutionTaskBaseService, "_get_ansible_node", return_value="node"), patch(
        "apps.job_mgmt.services.execution_base_service.AnsibleExecutor"
    ) as executor:
        ExecutionTaskBaseService._execute_script_via_ansible(execution, execution.target_list, "echo done", ScriptType.SHELL)
    payload = {row["host"]: row for row in executor.return_value.adhoc.call_args.kwargs["host_credentials"]}
    assert payload[manual.ip]["user"] == "local-user"
    assert payload[manual.ip]["password"] == "local-secret"
    expected = {"host": target.ip, "connection": "ssh", "user": "vault-user", "port": 2222}
    if auth_method == "password":
        expected["password"] = PASSWORD
    else:
        expected.update(private_key_content=KEY, private_key_passphrase=PASSPHRASE)
    assert payload[target.ip] == expected
    execution.refresh_from_db()
    _assert_no_secrets([execution.execution_results, execution.target_list, execution.credential_actor])


def test_winrm_playbook_and_files_use_target_transport_and_vault_login(team, caplog):
    target, _ = _target(team, os_type=OSType.WINDOWS)
    playbook = Playbook.objects.create(name="vault-book", team=[team])
    execution = _execution(team, [target], JobType.PLAYBOOK, playbook=playbook)
    expected = dict(
        host=target.ip,
        port=5985,
        connection="winrm",
        user="vault-user",
        password=PASSWORD,
        winrm_scheme="http",
        winrm_transport="ntlm",
        winrm_cert_validation=False,
    )
    with patch.object(ExecutionTaskBaseService, "_get_ansible_node", return_value="win-node"), patch(
        "apps.job_mgmt.services.playbook_execution.AnsibleExecutor"
    ) as executor:
        executor.return_value.playbook.return_value = {"server_debug": PASSWORD}
        PlaybookExecution(execution.id).run()
    assert executor.return_value.playbook.call_args.kwargs["host_credentials"] == [expected]
    with patch.object(ExecutionTaskBaseService, "_get_ansible_node", return_value="win-node"), patch(
        "apps.job_mgmt.services.file_distribution_runner.AnsibleExecutor"
    ) as executor:
        executor.return_value.task_query.return_value = {"status": "success", "result": {"success": True}}
        response = FileDistributionRunner(execution.id).download_to_manual_target({"name": "f"}, target.id, "C:\\data", 30, True, execution=execution)
    assert response["success"]
    assert executor.return_value.playbook.call_args.kwargs["host_credentials"] == [expected]
    _assert_no_secrets(caplog.text)


@pytest.mark.parametrize("job_type", [JobType.SCRIPT, JobType.PLAYBOOK])
@pytest.mark.parametrize("reason", ["disabled", "regions", "drivers"])
def test_ansible_batch_fails_all_targets_before_dispatch(team, job_type, reason):
    first, actor = _target(team)
    second, _ = _target(
        team, region=8 if reason == "regions" else 7, driver=ExecutorDriver.SIDECAR if reason == "drivers" else ExecutorDriver.ANSIBLE
    )
    if reason == "disabled":
        set_disabled(second.credential_id, True, actor=actor)
    execution = _execution(team, [first, second], job_type, playbook=Playbook.objects.create(name="book", team=[team]))
    with patch.object(ExecutionTaskBaseService, "_get_ansible_node", return_value="node"), patch(
        "apps.job_mgmt.services.execution_base_service.AnsibleExecutor"
    ) as script_rpc, patch("apps.job_mgmt.services.playbook_execution.AnsibleExecutor") as book_rpc, patch(
        "apps.job_mgmt.services.script_execution_runner.ensure_stream_sync"
    ), patch(
        "apps.job_mgmt.services.script_execution_runner.publish_done_sentinel"
    ):
        runner = ScriptExecutionRunner if job_type == JobType.SCRIPT else PlaybookExecution
        runner(execution.id).run()
    script_rpc.assert_not_called()
    book_rpc.assert_not_called()
    execution.refresh_from_db()
    expected_reason = {"disabled": "停用", "regions": "云区域", "drivers": "执行驱动"}[reason]
    assert execution.status == ExecutionStatus.FAILED
    assert execution.failed_count == 2
    assert {r["target_key"] for r in execution.execution_results} == {str(first.id), str(second.id)}
    assert all(r["status"] == ExecutionStatus.FAILED and expected_reason in r["error_message"] for r in execution.execution_results)
    _assert_no_secrets(execution.execution_results)


def test_exception_log_preserves_one_traceback_without_credentials(caplog):
    runner = ScriptExecutionRunner(1024)
    caplog.set_level(logging.ERROR, logger="job")
    private_text = PASSPHRASE
    error = ValueError(private_text)
    try:
        raise error
    except ValueError as exc:
        runner._log_execution_failure("execute_script", exc)
    records = [record for record in caplog.records if record.exc_info]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=job_execution_failed execution_id=%s failed_stage=%s error_type=%s"
    assert record.args == (1024, "execute_script", "ValueError")
    assert record.getMessage() == "event=job_execution_failed execution_id=1024 failed_stage=execute_script error_type=ValueError"
    assert record.exc_info[2] is error.__traceback__
    assert str(error) == private_text
    _assert_no_secrets(logging.Formatter().format(record))


@pytest.mark.parametrize("entry", ["sidecar", "ansible", "playbook", "linux_file", "windows_file"])
def test_executor_exception_cannot_echo_login_material_to_job_or_logs(team, caplog, entry):
    target, _ = _target(
        team,
        driver=ExecutorDriver.SIDECAR if entry in ("sidecar", "linux_file") else ExecutorDriver.ANSIBLE,
        os_type=OSType.WINDOWS if entry == "windows_file" else OSType.LINUX,
    )
    execution = _execution(team, [target], playbook=Playbook.objects.create(name="test", team=[team]))
    error = RuntimeError(PASSWORD)
    target_info = execution.target_list[0]
    with patch.object(ExecutionTaskBaseService, "_get_ansible_node", return_value="node"), patch(
        "apps.job_mgmt.services.script_execution_runner.Executor"
    ) as sidecar, patch("apps.job_mgmt.services.execution_base_service.AnsibleExecutor") as ansible, patch(
        "apps.job_mgmt.services.playbook_execution.AnsibleExecutor"
    ) as playbook, patch(
        "apps.job_mgmt.services.file_distribution_runner.Executor"
    ) as file_ssh, patch(
        "apps.job_mgmt.services.file_distribution_runner.AnsibleExecutor"
    ) as file_winrm, patch(
        "apps.job_mgmt.services.script_execution_runner.ensure_stream_sync"
    ), patch(
        "apps.job_mgmt.services.script_execution_runner.publish_done_sentinel"
    ):
        sidecar.return_value.execute_ssh_stream.side_effect = error
        ansible.return_value.adhoc.side_effect = error
        playbook.return_value.playbook.side_effect = error
        file_ssh.return_value.download_to_remote.side_effect = error
        file_winrm.return_value.playbook.side_effect = error

        if entry.endswith("_file"):
            result = FileDistributionRunner(execution.id).distribute_file_to_target(
                target_info, TargetSource.MANUAL, [{"name": "f"}], "/tmp", 30, execution=execution
            )
        elif entry == "sidecar":
            result = ScriptExecutionRunner(execution.id).execute_script_on_target(
                target_info, TargetSource.MANUAL, "echo", "shell", 30, execution.id, execution
            )
        else:
            runner_type = PlaybookExecution if entry == "playbook" else ScriptExecutionRunner
            runner_type(execution.id).run()
            execution.refresh_from_db()
            result = execution.execution_results[0]
    assert error.__traceback__ is not None
    assert result["status"] == ExecutionStatus.FAILED and "凭据执行请求失败" in result["error_message"]
    if entry in ("ansible", "playbook"):
        assert execution.failed_count == 1
    _assert_no_secrets([result, execution.execution_results, caplog.text])


def test_remote_auth_rejection_is_a_failure_even_without_exit_code(team, caplog):
    target, _ = _target(team, driver=ExecutorDriver.SIDECAR)
    execution = _execution(team, [target])
    with patch("apps.job_mgmt.services.script_execution_runner.Executor") as executor:
        executor.return_value.execute_ssh_stream.return_value = {"stage": "ssh_dial", "success": False, "error": PASSPHRASE, "result": KEY}
        result = ScriptExecutionRunner(execution.id).execute_script_on_target(
            execution.target_list[0], TargetSource.MANUAL, "echo", "shell", 30, execution.id, execution
        )
    assert result["status"] == ExecutionStatus.FAILED
    assert result["exit_code"] == 1
    assert result["stdout"] == "" and result["stderr"] == "执行器连接失败"
    _assert_no_secrets([result, caplog.text])
