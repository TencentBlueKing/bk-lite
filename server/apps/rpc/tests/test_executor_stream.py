"""Executor.execute_local_stream 流式本地执行 RPC 单测。"""
from unittest.mock import patch

import pytest

from apps.rpc.executor import Executor
from apps.rpc.ansible import AnsibleExecutor

pytestmark = pytest.mark.unit


def test_ansible_adhoc_forwards_stream_fields():
    ex = AnsibleExecutor("inst-1")
    with patch.object(ex.adhoc_client, "run", return_value={"accepted": True}) as mock_run:
        ex.adhoc(
            host_credentials=[{"host": "1.1.1.1", "user": "root"}],
            module="shell",
            module_args="echo hi",
            task_id="99",
            stream_log_topic="job.stream.99.ansible",
            execution_id="99",
        )
    request_data = mock_run.call_args.args[1]
    assert request_data["stream_log_topic"] == "job.stream.99.ansible"
    assert request_data["execution_id"] == "99"


def test_ansible_adhoc_omits_stream_fields_when_absent():
    ex = AnsibleExecutor("inst-1")
    with patch.object(ex.adhoc_client, "run", return_value={"accepted": True}) as mock_run:
        ex.adhoc(host_credentials=[{"host": "1.1.1.1", "user": "root"}], module="ping")
    request_data = mock_run.call_args.args[1]
    assert "stream_log_topic" not in request_data
    assert "execution_id" not in request_data


def test_execute_local_stream_sets_stream_fields():
    ex = Executor("inst-1")
    with patch.object(ex.local_client, "run", return_value={"stdout": "ok"}) as mock_run:
        ex.execute_local_stream(
            "echo hi",
            timeout=30,
            shell="bash",
            execution_id="99",
            stream_log_topic="job.stream.99.n7",
        )
    args, kwargs = mock_run.call_args
    instance_id, request_data = args[0], args[1]
    assert instance_id == "inst-1"
    assert request_data["command"] == "echo hi"
    assert request_data["shell"] == "bash"
    assert request_data["stream_logs"] is True
    assert request_data["execution_id"] == "99"
    assert request_data["stream_log_topic"] == "job.stream.99.n7"


def test_execute_local_forwards_environment_variables():
    ex = Executor("inst-1")
    with patch.object(ex.local_client, "run", return_value={"stdout": "ok"}) as mock_run:
        ex.execute_local(
            "telegraf --once",
            timeout=30,
            shell="bash",
            env={"BK_LITE_PREFLIGHT_SECRET": "secret"},
        )
    request_data = mock_run.call_args.args[1]
    assert request_data["env"] == {"BK_LITE_PREFLIGHT_SECRET": "secret"}


def test_execute_local_stream_without_optional_fields():
    ex = Executor("inst-1")
    with patch.object(ex.local_client, "run", return_value={"stdout": "ok"}) as mock_run:
        ex.execute_local_stream("echo hi", timeout=30)
    request_data = mock_run.call_args.args[1]
    assert request_data["stream_logs"] is True
    assert "shell" not in request_data
    assert "execution_id" not in request_data
    assert "stream_log_topic" not in request_data


def test_execute_ssh_stream_all_optional_fields():
    ex = Executor("inst-1")
    with patch.object(ex.ssh_client, "run", return_value={"stdout": "ok"}) as mock_run:
        ex.execute_ssh_stream(
            "echo hi",
            host="10.0.0.1",
            username="root",
            password="pwd",
            private_key="PEM",
            passphrase="ph",
            timeout=45,
            port=2222,
            execution_id="e1",
            stream_log_topic="job.stream.e1",
            fast_fail=True,
        )
    args, kwargs = mock_run.call_args
    instance_id, request_data = args[0], args[1]
    assert instance_id == "inst-1"
    assert request_data["command"] == "echo hi"
    assert request_data["host"] == "10.0.0.1"
    assert request_data["port"] == 2222
    assert request_data["user"] == "root"
    assert request_data["stream_logs"] is True
    assert request_data["password"] == "pwd"
    assert request_data["private_key"] == "PEM"
    assert request_data["passphrase"] == "ph"
    assert request_data["execution_id"] == "e1"
    assert request_data["stream_log_topic"] == "job.stream.e1"
    # fast_fail 映射为 connection_test=True
    assert request_data["connection_test"] is True


def test_execute_ssh_stream_omits_optional_fields():
    ex = Executor("inst-1")
    with patch.object(ex.ssh_client, "run", return_value={"stdout": "ok"}) as mock_run:
        ex.execute_ssh_stream("echo hi", host="h", username="u")
    request_data = mock_run.call_args.args[1]
    assert request_data["port"] == 22
    assert "password" not in request_data
    assert "private_key" not in request_data
    assert "passphrase" not in request_data
    assert "execution_id" not in request_data
    assert "stream_log_topic" not in request_data
    assert "connection_test" not in request_data


def test_download_to_remote_optional_fields():
    ex = Executor("inst-1")
    with patch.object(ex.download_to_remote_client, "run", return_value={"ok": True}) as mock_run:
        ex.download_to_remote(
            bucket_name="b",
            file_key="k",
            file_name="f",
            target_path="/tmp",
            host="10.0.0.2",
            username="root",
            password="pwd",
            private_key="PEM",
            passphrase="ph",
            fast_fail=True,
        )
    request_data = mock_run.call_args.args[1]
    assert request_data["password"] == "pwd"
    assert request_data["private_key"] == "PEM"
    assert request_data["passphrase"] == "ph"
    assert request_data["fast_fail"] is True


def test_transfer_file_to_remote_optional_fields():
    ex = Executor("inst-1")
    with patch.object(ex.transfer_file_to_remote_client, "run", return_value={"ok": True}) as mock_run:
        ex.transfer_file_to_remote(
            source_path="/src",
            target_path="/dst",
            host="10.0.0.3",
            username="root",
            password="pwd",
            private_key="PEM",
            passphrase="ph",
        )
    args = mock_run.call_args.args
    assert args[0] == "inst-1"
    request_data = args[1]
    assert request_data["source_path"] == "/src"
    assert request_data["target_path"] == "/dst"
    assert request_data["password"] == "pwd"
    assert request_data["private_key"] == "PEM"
    assert request_data["passphrase"] == "ph"
