"""rpc.executor.Executor 转发契约补充测试。

每个方法把 instance_id + 组装后的 request_data 转发给对应子客户端的 run，
并传入正确的 _timeout（部分方法用 _resolve_rpc_timeout 加 grace）。
替换各子客户端的 run 为 patch.object 记录器，不触达真实 NATS。
"""
import pydantic.root_model  # noqa

from unittest.mock import patch

import pytest

from apps.rpc.executor import Executor, RPC_TIMEOUT_GRACE_SECONDS, _resolve_rpc_timeout

pytestmark = pytest.mark.unit


def test_resolve_rpc_timeout_加grace():
    assert _resolve_rpc_timeout(60) == 60 + RPC_TIMEOUT_GRACE_SECONDS
    assert _resolve_rpc_timeout(0) == RPC_TIMEOUT_GRACE_SECONDS


def test_health_check_默认5秒超时():
    ex = Executor("inst-1")
    with patch.object(ex.health_check_client, "run", return_value={"ok": True}) as run:
        out = ex.health_check()
    assert out == {"ok": True}
    args, kwargs = run.call_args
    assert args[0] == "inst-1"
    assert args[1] == {"execute_timeout": 5}
    assert kwargs["_timeout"] == 5


def test_execute_local_带shell():
    ex = Executor("inst-1")
    with patch.object(ex.local_client, "run", return_value={"stdout": "x"}) as run:
        ex.execute_local("ls", timeout=30, shell="bash")
    args, kwargs = run.call_args
    assert args[1] == {"command": "ls", "execute_timeout": 30, "shell": "bash"}
    assert kwargs["_timeout"] == 30


def test_execute_local_无shell不带shell字段():
    ex = Executor("inst-1")
    with patch.object(ex.local_client, "run", return_value={}) as run:
        ex.execute_local("pwd")
    request_data = run.call_args.args[1]
    assert "shell" not in request_data
    assert request_data["execute_timeout"] == 60


def test_execute_ssh_组装最小请求并加grace超时():
    ex = Executor("inst-1")
    with patch.object(ex.ssh_client, "run", return_value={"rc": 0}) as run:
        ex.execute_ssh("uptime", "10.0.0.1", "root", timeout=20)
    args, kwargs = run.call_args
    assert args[1] == {
        "command": "uptime", "host": "10.0.0.1", "port": 22, "user": "root", "execute_timeout": 20,
    }
    assert kwargs["_timeout"] == _resolve_rpc_timeout(20)


def test_execute_ssh_带密码与私钥():
    ex = Executor("inst-1")
    with patch.object(ex.ssh_client, "run", return_value={}) as run:
        ex.execute_ssh(
            "ls", "h", "u", password="pw", private_key="KEY", passphrase="pp",
            connection_test=True, port=2222,
        )
    rd = run.call_args.args[1]
    assert rd["password"] == "pw"
    assert rd["private_key"] == "KEY"
    assert rd["passphrase"] == "pp"
    assert rd["connection_test"] is True
    assert rd["port"] == 2222


def test_execute_ssh_fast_fail触发connection_test():
    ex = Executor("inst-1")
    with patch.object(ex.ssh_client, "run", return_value={}) as run:
        ex.execute_ssh("ls", "h", "u", fast_fail=True)
    assert run.call_args.args[1]["connection_test"] is True


def test_execute_ssh_stream_设置流字段():
    ex = Executor("inst-1")
    with patch.object(ex.ssh_client, "run", return_value={}) as run:
        ex.execute_ssh_stream(
            "tail", "h", "u", execution_id="e1", stream_log_topic="t1",
        )
    rd = run.call_args.args[1]
    assert rd["stream_logs"] is True
    assert rd["execution_id"] == "e1"
    assert rd["stream_log_topic"] == "t1"


def test_execute_ssh_stream_无可选不带流字段():
    ex = Executor("inst-1")
    with patch.object(ex.ssh_client, "run", return_value={}) as run:
        ex.execute_ssh_stream("tail", "h", "u")
    rd = run.call_args.args[1]
    assert rd["stream_logs"] is True
    assert "execution_id" not in rd
    assert "stream_log_topic" not in rd


def test_download_to_local_组装请求():
    ex = Executor("inst-1")
    with patch.object(ex.download_to_local_client, "run", return_value={}) as run:
        ex.download_to_local("bucket", "key", "f.txt", "/tmp/f", timeout=15, overwrite=False)
    args, kwargs = run.call_args
    assert args[1] == {
        "bucket_name": "bucket", "file_key": "key", "file_name": "f.txt",
        "target_path": "/tmp/f", "execute_timeout": 15, "overwrite": False,
    }
    assert kwargs["_timeout"] == 15


def test_download_to_remote_默认local_path与overwrite():
    ex = Executor("inst-1")
    with patch.object(ex.download_to_remote_client, "run", return_value={}) as run:
        ex.download_to_remote("b", "k", "f", "/remote", "h", "u")
    rd = run.call_args.args[1]
    assert rd["local_path"] == "/tmp"
    assert rd["overwrite"] is True
    assert rd["host"] == "h"
    assert rd["user"] == "u"
    assert run.call_args.kwargs["_timeout"] == _resolve_rpc_timeout(60)


def test_download_to_remote_fast_fail():
    ex = Executor("inst-1")
    with patch.object(ex.download_to_remote_client, "run", return_value={}) as run:
        ex.download_to_remote("b", "k", "f", "/r", "h", "u", fast_fail=True, private_key="K")
    rd = run.call_args.args[1]
    assert rd["fast_fail"] is True
    assert rd["private_key"] == "K"


def test_unzip_local_组装zip_path与dest_dir():
    ex = Executor("inst-1")
    with patch.object(ex.unzip_local_client, "run", return_value={}) as run:
        ex.unzip_local("/a.zip", "/out", timeout=10)
    args, kwargs = run.call_args
    assert args[1] == {"zip_path": "/a.zip", "dest_dir": "/out"}
    assert kwargs["_timeout"] == 10


def test_transfer_file_to_remote_组装请求并加grace():
    ex = Executor("inst-1")
    with patch.object(ex.transfer_file_to_remote_client, "run", return_value={}) as run:
        ex.transfer_file_to_remote("/src", "/dst", "h", "u", password="pw", timeout=40)
    args, kwargs = run.call_args
    rd = args[1]
    assert rd["source_path"] == "/src"
    assert rd["target_path"] == "/dst"
    assert rd["password"] == "pw"
    assert kwargs["_timeout"] == _resolve_rpc_timeout(40)
