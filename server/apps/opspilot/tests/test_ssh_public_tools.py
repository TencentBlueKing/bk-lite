"""SSH/SFTP 公开工具的连接、执行与传输契约。"""

import stat
from types import SimpleNamespace as NS
from unittest.mock import patch

import pydantic.root_model  # noqa: F401
import pytest

from apps.opspilot.metis.llm.tools.ssh import (
    batch,
    connection,
    execute,
    transfer,
    utils as ssh_utils,
)


pytestmark = pytest.mark.unit


class ExternalChannel:
    def __init__(self, exit_code):
        self.exit_code = exit_code

    def recv_exit_status(self):
        return self.exit_code


class ExternalStream:
    def __init__(self, content=b"", exit_code=0):
        self.content = content
        self.channel = ExternalChannel(exit_code)
        self.written = ""
        self.closed = False

    def read(self):
        return self.content

    def write(self, content):
        self.written += content

    def close(self):
        self.closed = True


class ExternalSFTP:
    def __init__(self):
        self.puts = []
        self.gets = []
        self.removed = []
        self.created = []
        self.closed = False

    def stat(self, path):
        if path in {"/", "/var"}:
            return NS()
        raise IOError(path)

    def mkdir(self, path):
        self.created.append(path)

    def put(self, local_path, remote_path):
        self.puts.append((local_path, remote_path))

    def get(self, remote_path, local_path):
        self.gets.append((remote_path, local_path))
        with open(local_path, "wb") as target:
            target.write(b"remote diagnostics")

    def listdir_attr(self, _remote_path):
        return [
            NS(
                filename="app.log",
                st_size=1024,
                st_mode=stat.S_IFREG | 0o640,
                st_mtime=1710000000,
            ),
            NS(
                filename="archive",
                st_size=0,
                st_mode=stat.S_IFDIR | 0o750,
                st_mtime=1710000001,
            ),
            NS(
                filename=".hidden",
                st_size=2,
                st_mode=stat.S_IFREG | 0o600,
                st_mtime=1710000002,
            ),
        ]

    def remove(self, remote_path):
        self.removed.append(remote_path)

    def close(self):
        self.closed = True


class ExternalSSHClient:
    instances = []

    def __init__(self):
        self.connect_params = None
        self.commands = []
        self.policy = None
        self.closed = False
        self.sftp = ExternalSFTP()
        self.__class__.instances.append(self)

    def set_missing_host_key_policy(self, policy):
        self.policy = policy

    def connect(self, **params):
        self.connect_params = params

    def get_transport(self):
        return NS(remote_version="SSH-2.0-OpenSSH_9.6")

    def exec_command(self, command, timeout=None):
        self.commands.append((command, timeout))
        outputs = {
            "hostname": b"db-01\n",
            "cat /etc/os-release 2>/dev/null || uname -s": b"Alpine Linux\n",
            "uname -r": b"6.6.1\n",
            "uname -m": b"x86_64\n",
        }
        stdout = ExternalStream(outputs.get(command, b"healthy\n"))
        stderr = ExternalStream()
        stdin = ExternalStream()
        self.last_stdin = stdin
        return stdin, stdout, stderr

    def open_sftp(self):
        return self.sftp

    def close(self):
        self.closed = True


@pytest.fixture
def ssh_runtime():
    ExternalSSHClient.instances = []
    with patch.object(
        connection.paramiko,
        "SSHClient",
        ExternalSSHClient,
    ):
        yield


def test_create_ssh_client_uses_password_without_key_discovery(ssh_runtime):
    client = connection.create_ssh_client(
        host=" db.example.com ",
        username=" ops ",
        password="secret",
        port=2222,
        timeout=9,
    )

    assert client.connect_params == {
        "hostname": "db.example.com",
        "username": "ops",
        "port": 2222,
        "timeout": 9,
        "look_for_keys": False,
        "password": "secret",
    }


def test_connection_and_server_info_tools_close_client(ssh_runtime):
    connected = connection.test_ssh_connection.invoke(
        {
            "host": "db.example.com",
            "username": "ops",
            "password": "secret",
            "port": 2222,
        }
    )
    info = connection.get_ssh_server_info.invoke(
        {
            "host": "db.example.com",
            "username": "ops",
            "password": "secret",
        }
    )

    assert connected["success"] is True
    assert connected["server_info"]["banner"] == "SSH-2.0-OpenSSH_9.6"
    assert info == {
        "hostname": "db-01",
        "os_info": "Alpine Linux",
        "kernel": "6.6.1",
        "architecture": "x86_64",
        "ssh_banner": "SSH-2.0-OpenSSH_9.6",
    }
    assert all(client.closed for client in ExternalSSHClient.instances)


def test_execute_command_builds_environment_and_working_directory(
    ssh_runtime,
):
    result = execute.ssh_execute_command.invoke(
        {
            "host": "db.example.com",
            "username": "ops",
            "password": "secret",
            "command": "systemctl is-active postgres",
            "working_directory": "/srv/app",
            "environment": {"ENV": "prod", "TRACE": "1"},
        }
    )

    assert result["success"] is True
    assert result["stdout"] == "healthy"
    assert result["exit_code"] == 0
    assert ExternalSSHClient.instances[0].commands[0][0] == (
        "export ENV=prod; export TRACE=1; "
        "cd /srv/app && systemctl is-active postgres"
    )
    assert ExternalSSHClient.instances[0].closed is True


def test_execute_script_streams_content_to_interpreter(ssh_runtime):
    result = execute.ssh_execute_script.invoke(
        {
            "host": "db.example.com",
            "username": "ops",
            "password": "secret",
            "script_content": "set -e\nhostname\n",
            "interpreter": "/bin/sh",
        }
    )

    client = ExternalSSHClient.instances[0]
    assert result["success"] is True
    assert result["command"] == "<script via /bin/sh>"
    assert client.commands == [("/bin/sh", 60)]
    assert client.last_stdin.written == "set -e\nhostname\n"
    assert client.last_stdin.closed is True


def test_upload_and_download_files_report_real_local_sizes(
    ssh_runtime,
    tmp_path,
):
    source = tmp_path / "config.yml"
    source.write_bytes(b"mode: production\n")
    target = tmp_path / "downloads" / "diagnostics.txt"

    uploaded = transfer.upload_file.invoke(
        {
            "host": "db.example.com",
            "username": "ops",
            "password": "secret",
            "local_path": str(source),
            "remote_path": "/var/app/config.yml",
        }
    )
    downloaded = transfer.download_file.invoke(
        {
            "host": "db.example.com",
            "username": "ops",
            "password": "secret",
            "remote_path": "/var/log/app.log",
            "local_path": str(target),
        }
    )

    upload_client, download_client = ExternalSSHClient.instances
    assert uploaded["bytes_transferred"] == len(b"mode: production\n")
    assert uploaded["file_size"] == "17.00 B"
    assert upload_client.sftp.created == ["/var/app"]
    assert upload_client.sftp.puts == [
        (str(source), "/var/app/config.yml")
    ]
    assert downloaded["bytes_transferred"] == len(b"remote diagnostics")
    assert target.read_bytes() == b"remote diagnostics"
    assert upload_client.sftp.closed is True
    assert download_client.sftp.closed is True


def test_list_and_delete_remote_files_preserve_metadata_and_hide_dotfiles(
    ssh_runtime,
):
    listing = transfer.list_remote_directory.invoke(
        {
            "host": "db.example.com",
            "username": "ops",
            "password": "secret",
            "remote_path": "/var/log",
        }
    )
    deleted = transfer.delete_remote_file.invoke(
        {
            "host": "db.example.com",
            "username": "ops",
            "password": "secret",
            "remote_path": "/var/log/old.log",
        }
    )

    list_client, delete_client = ExternalSSHClient.instances
    assert listing["total_items"] == 2
    assert listing["files"][0]["name"] == "app.log"
    assert listing["files"][0]["size"] == "1.00 KB"
    assert listing["directories"][0]["permissions"] == "drwxr-x---"
    assert deleted["success"] is True
    assert delete_client.sftp.removed == ["/var/log/old.log"]
    assert list_client.closed is True
    assert delete_client.closed is True


def test_batch_execute_commands_invokes_public_ssh_tool_for_each_host(
    ssh_runtime,
):
    result = batch.batch_execute_commands.invoke(
        {
            "hosts": ["db-01.example.com", "db-02.example.com"],
            "username": "ops",
            "password": "secret",
            "command": "hostname",
            "max_workers": 2,
        }
    )

    assert result["total"] == 2
    assert result["success_count"] == 2
    assert result["failed_count"] == 0
    assert set(result["summary"]["successful_hosts"]) == {
        "db-01.example.com",
        "db-02.example.com",
    }


def test_batch_upload_and_availability_invoke_public_tools(
    ssh_runtime,
    tmp_path,
):
    source = tmp_path / "agent.conf"
    source.write_text("enabled=true\n")
    hosts = ["node-01.example.com", "node-02.example.com"]

    uploaded = batch.batch_upload_files.invoke(
        {
            "hosts": hosts,
            "username": "ops",
            "password": "secret",
            "local_path": str(source),
            "remote_path": "/etc/agent.conf",
            "max_workers": 2,
        }
    )
    available = batch.check_hosts_availability.invoke(
        {
            "hosts": hosts,
            "username": "ops",
            "password": "secret",
            "max_workers": 2,
        }
    )

    assert uploaded["success_count"] == 2
    assert set(uploaded["summary"]["successful_hosts"]) == set(hosts)
    assert available["available_count"] == 2
    assert available["unavailable_count"] == 0
    assert set(available["available_hosts"]) == set(hosts)


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        (
            "ssh://ops@db.example.com:2222/var/log/app.log",
            {
                "host": "db.example.com",
                "username": "ops",
                "port": 2222,
                "path": "/var/log/app.log",
            },
        ),
        (
            "ops@db.example.com",
            {
                "host": "db.example.com",
                "username": "ops",
                "port": 22,
                "path": None,
            },
        ),
        (
            "db.example.com",
            {
                "host": "db.example.com",
                "username": None,
                "port": 22,
                "path": None,
            },
        ),
    ],
)
def test_ssh_uri_parser_supports_operational_address_forms(uri, expected):
    assert ssh_utils.parse_ssh_uri(uri) == expected


def test_ssh_runtime_config_and_validation_contract():
    assert ssh_utils.prepare_ssh_config(
        {
            "configurable": {
                "ssh_timeout": 8,
                "ssh_port": 2222,
                "ssh_key_path": "/keys/ops",
            }
        }
    ) == {
        "timeout": 8,
        "port": 2222,
        "key_path": "/keys/ops",
        "look_for_keys": True,
    }
    assert ssh_utils.format_command_output(" ok \n", " warning ", 1) == {
        "stdout": "ok",
        "stderr": "warning",
        "exit_code": 1,
        "success": False,
    }
    with pytest.raises(ValueError, match="主机地址不能为空"):
        ssh_utils.validate_host_params("", "ops")
    with pytest.raises(ValueError, match="主机地址格式无效"):
        ssh_utils.validate_host_params("-oProxyCommand=evil", "ops")
