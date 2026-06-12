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


def test_execute_local_stream_without_optional_fields():
    ex = Executor("inst-1")
    with patch.object(ex.local_client, "run", return_value={"stdout": "ok"}) as mock_run:
        ex.execute_local_stream("echo hi", timeout=30)
    request_data = mock_run.call_args.args[1]
    assert request_data["stream_logs"] is True
    assert "shell" not in request_data
    assert "execution_id" not in request_data
    assert "stream_log_topic" not in request_data
