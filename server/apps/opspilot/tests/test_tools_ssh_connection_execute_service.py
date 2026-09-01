"""SSH 连接/执行/批量：mock paramiko 与底层命令，断言成功/失败汇总。"""
from unittest.mock import MagicMock, patch

import paramiko
import pytest

from apps.opspilot.metis.llm.tools.ssh import batch as batch_mod
from apps.opspilot.metis.llm.tools.ssh import connection as conn
from apps.opspilot.metis.llm.tools.ssh import execute as exe
from apps.opspilot.metis.llm.tools.ssh.utils import format_command_output, prepare_ssh_config, validate_host_params

pytestmark = pytest.mark.unit


def test_validate_host_and_prepare_config():
    with pytest.raises(ValueError):
        validate_host_params("", "root")
    with pytest.raises(ValueError):
        validate_host_params("10.0.0.1", "")
    validate_host_params("10.0.0.1", "root")
    cfg = prepare_ssh_config({"configurable": {"ssh_timeout": 5, "ssh_port": 2222}})
    assert cfg["timeout"] == 5
    assert cfg["port"] == 2222


def test_format_command_output_success_and_failure():
    ok = format_command_output("hello\n", "", 0)
    assert ok["success"] is True
    assert ok["stdout"] == "hello"
    bad = format_command_output("", "denied", 1)
    assert bad["success"] is False
    assert bad["exit_code"] == 1


def test_create_ssh_client_uses_password_and_maps_auth_error():
    client = MagicMock()
    with patch("apps.opspilot.metis.llm.tools.ssh.connection.paramiko.SSHClient", return_value=client):
        out = conn.create_ssh_client("10.0.0.1", "root", password="p")
    assert out is client
    client.connect.assert_called_once()
    assert client.connect.call_args.kwargs["password"] == "p"
    client.connect.side_effect = paramiko.AuthenticationException("bad")
    with patch("apps.opspilot.metis.llm.tools.ssh.connection.paramiko.SSHClient", return_value=client):
        with pytest.raises(paramiko.AuthenticationException, match="SSH认证失败"):
            conn.create_ssh_client("10.0.0.1", "root", password="p")


def test_test_ssh_connection_success_and_failure():
    client = MagicMock()
    transport = MagicMock(remote_version="OpenSSH_9")
    client.get_transport.return_value = transport
    with patch.object(conn, "create_ssh_client", return_value=client):
        out = conn.test_ssh_connection.invoke({"host": "10.0.0.1", "username": "root", "password": "p"})
    assert out["success"] is True
    assert out["server_info"]["banner"] == "OpenSSH_9"
    client.close.assert_called_once()
    with patch.object(conn, "create_ssh_client", side_effect=RuntimeError("down")):
        failed = conn.test_ssh_connection.invoke({"host": "10.0.0.1", "username": "root", "password": "p"})
    assert failed["success"] is False
    assert "down" in failed["error"]


def _ssh_streams(stdout="ok\n", stderr="", exit_code=0):
    stdout_obj = MagicMock()
    stdout_obj.read.return_value = stdout.encode()
    stdout_obj.channel.recv_exit_status.return_value = exit_code
    stderr_obj = MagicMock()
    stderr_obj.read.return_value = stderr.encode()
    return MagicMock(), stdout_obj, stderr_obj


def test_ssh_execute_command_cwd_env_and_error():
    client = MagicMock()
    client.exec_command.return_value = _ssh_streams("done", "", 0)
    with patch.object(exe, "create_ssh_client", return_value=client):
        out = exe.ssh_execute_command.invoke(
            {
                "host": "10.0.0.1",
                "username": "root",
                "password": "p",
                "command": "ls",
                "working_directory": "/tmp",
                "environment": {"A": "1"},
            }
        )
    assert out["success"] is True
    cmd = client.exec_command.call_args.args[0]
    assert "cd /tmp" in cmd
    assert "export A=1" in cmd
    with patch.object(exe, "create_ssh_client", side_effect=RuntimeError("refused")):
        failed = exe.ssh_execute_command.invoke({"host": "10.0.0.1", "username": "root", "password": "p", "command": "ls"})
    assert failed["success"] is False
    assert failed["exit_code"] == -1


def test_batch_execute_rejects_empty_and_summarizes():
    with pytest.raises(ValueError, match="主机列表不能为空"):
        batch_mod.batch_execute_commands.func(hosts=[], username="root", command="uptime")
    command_tool = MagicMock()
    command_tool.invoke.side_effect = lambda payload, config=None: {
        "success": payload["host"] != "bad",
        "stdout": "ok",
    }
    with patch.object(batch_mod, "ssh_execute_command", command_tool):
        out = batch_mod.batch_execute_commands.func(
            hosts=["good", "bad"],
            username="root",
            command="uptime",
            password="p",
        )
    assert out["total"] == 2
    assert out["success_count"] == 1
    assert out["failed_count"] == 1
    assert "good" in out["summary"]["successful_hosts"]
    assert "bad" in out["summary"]["failed_hosts"]
