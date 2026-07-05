# -*- coding: utf-8 -*-
"""vm_ssh.py 单测（fake paramiko client）"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.collect_fixtures.vm_ssh import VMSSH  # noqa: E402


class _FakeExec:
    """模拟 paramiko exec_command 返回的 (stdin, stdout, stderr) 三元组。"""
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", exit_code: int = 0):
        self.stdin = MagicMock()
        _stdout = MagicMock()
        _stdout.read.return_value = stdout
        _stdout.channel.recv_exit_status.return_value = exit_code
        self.stdout = _stdout
        _stderr = MagicMock()
        _stderr.read.return_value = stderr
        self.stderr = _stderr
        self.exit_code = exit_code


def _fake_ssh_result(stdout: str = "", stderr: str = "", exit_code: int = 0, exec_time: float = 0.1):
    """构造一个与 stargazer SSHResult 接口兼容的 MagicMock。"""
    from dataclasses import dataclass

    @dataclass
    class SSHResult:
        stdout: str
        stderr: str
        exit_status: int
        exec_time: float

    return SSHResult(stdout=stdout, stderr=stderr, exit_status=exit_code, exec_time=exec_time)


def test_vm_ssh_connects_with_password():
    """connect 应该用给定的 host/port/user/password 调用底层 SSHClient.connect。"""
    with patch("tests.collect_fixtures.vm_ssh._SSHClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        ssh = VMSSH(host="127.0.0.1", port=12222, user="root", password="testpw")
        ssh.connect()

        mock_cls.assert_called_once_with(timeout=30)
        # connect 应该被调用,传 password 登录
        assert mock_client.connect.called
        # 兼容两种 kwargs:host= 或 hostname=
        call_kwargs = mock_client.connect.call_args.kwargs
        # 关键字段都要传对
        assert call_kwargs["password"] == "testpw"
        assert call_kwargs["username"] == "root"
        assert call_kwargs["port"] == 12222


def test_vm_ssh_exec_returns_dict():
    """exec 返回 dict {stdout, stderr, exit_code}。"""
    with patch("tests.collect_fixtures.vm_ssh._SSHClient") as mock_cls:
        mock_client = MagicMock()
        # stargazer SSHClient.execute_command 返回 SSHResult dataclass
        mock_client.execute_command.return_value = _fake_ssh_result(
            stdout="hello\n", stderr="", exit_code=0
        )
        mock_cls.return_value = mock_client

        ssh = VMSSH(host="127.0.0.1", port=12222, user="root", password="x")
        ssh.connect()
        result = ssh.exec("echo hello")

        assert result["stdout"] == "hello\n"
        assert result["stderr"] == ""
        assert result["exit_code"] == 0


def test_vm_ssh_exec_raises_on_nonzero_exit_when_check_true():
    with patch("tests.collect_fixtures.vm_ssh._SSHClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.execute_command.return_value = _fake_ssh_result(
            stdout="", stderr="boom", exit_code=1
        )
        mock_cls.return_value = mock_client

        ssh = VMSSH(host="127.0.0.1", port=12222, user="root", password="x")
        ssh.connect()
        with pytest.raises(RuntimeError, match=r"SSH cmd failed.*exit=1"):
            ssh.exec("false", check=True)


def test_vm_ssh_exec_with_check_false_does_not_raise():
    with patch("tests.collect_fixtures.vm_ssh._SSHClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.execute_command.return_value = _fake_ssh_result(
            stdout="", stderr="warn", exit_code=2
        )
        mock_cls.return_value = mock_client

        ssh = VMSSH(host="127.0.0.1", port=12222, user="root", password="x")
        ssh.connect()
        result = ssh.exec("grep nonexistent", check=False)
        assert result["exit_code"] == 2


def test_vm_ssh_close():
    with patch("tests.collect_fixtures.vm_ssh._SSHClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        ssh = VMSSH(host="127.0.0.1", port=12222, user="root", password="x")
        ssh.connect()
        ssh.close()

        mock_client.close.assert_called_once()


def test_vm_ssh_exec_without_connect_raises():
    """未 connect 直接 exec 应该报 RuntimeError。"""
    ssh = VMSSH(host="127.0.0.1", port=22, user="root", password="x")
    with pytest.raises(RuntimeError, match="not connected"):
        ssh.exec("ls")


def test_vm_ssh_connect_does_not_pass_unknown_kwargs():
    """回归测试：VMSSH.connect 不应传 _SSHClient.connect 不接受的 kwargs。

    真实场景:v2-Task 7 真实跑 nginx 时 paramiko 报 TypeError 因为传了 allow_agent/look_for_keys。
    此处用 stub class 强制真实签名检查(MagicMock 会接受任意 kwargs,抓不到 bug)。
    """
    class _StubSSHClient:
        def __init__(self, timeout=30, known_hosts_file=None):
            self.timeout = timeout
            self.connected_with = None
        def connect(self, host, username, password=None, port=22, key_filename=None):
            self.connected_with = {"host": host, "username": username, "password": password, "port": port}
        def close(self):
            pass
        def execute_command(self, command, timeout=None):
            return ("", "", 0, 0.1)

    with patch("tests.collect_fixtures.vm_ssh._SSHClient", _StubSSHClient):
        ssh = VMSSH(host="127.0.0.1", port=12222, user="root", password="testpw")
        ssh.connect()

    # 如果 VMSSH 之前传了 allow_agent/look_for_keys,_StubSSHClient.connect 会抛 TypeError
    # 这里通过就说明 VMSSH.connect 只传了合法 kwargs
    assert ssh._client.connected_with["host"] == "127.0.0.1"
    assert ssh._client.connected_with["port"] == 12222
    assert ssh._client.connected_with["password"] == "testpw"
