import asyncio
import builtins
import json
import time
from pathlib import Path

import pytest

import plugins.script_executor as script_executor_module
from core.collection.contracts import AccessProbeStatus
from core.plugin.executor import PluginExecutor
from core.plugin.yaml_reader import ExecutorConfig
from plugins.inputs.config_file.config_file_info import ConfigFileInfo
from plugins.inputs.mysql.mysql_info import MysqlInfo
from plugins.inputs.postgresql.postgresql_info import PostgresqlInfo
from plugins.script_executor import SSHPlugin
from tasks.collectors.host_collector import HostCollector


async def _heartbeat_during(awaitable, minimum_ticks: int = 5):
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        result = await awaitable
    finally:
        heartbeat_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await heartbeat_task

    assert ticks >= minimum_ticks, "event_loop_stalled"
    return result


def _delay_file_reads(monkeypatch, target_path: Path) -> None:
    real_open = builtins.open

    def delayed_open(file, *args, **kwargs):
        if Path(file) == target_path:
            time.sleep(0.05)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", delayed_open)


@pytest.mark.asyncio
async def test_ssh_script_loading_does_not_stall_event_loop(
    tmp_path, monkeypatch
):
    script_path = tmp_path / "collect.sh"
    script_path.write_text("echo ok", encoding="utf-8")
    _delay_file_reads(monkeypatch, script_path)

    plugin = SSHPlugin(
        {
            "node_id": "node-1",
            "host": "10.0.0.1",
            "script_path": str(script_path),
            "model_id": "host",
        }
    )

    async def fake_nats_request(*_args, **_kwargs):
        return {"success": True, "result": "{}"}

    monkeypatch.setattr(script_executor_module, "nats_request", fake_nats_request)

    result = await _heartbeat_during(plugin.list_all_resources())

    assert result == {"success": True, "result": {"host": [{}]}}


@pytest.mark.asyncio
async def test_ssh_probe_accepts_empty_port_header(monkeypatch):
    captured = {}

    async def accepted(subject, *, payload, timeout):
        request = json.loads(payload.decode())
        captured["subject"] = subject
        captured["port"] = request["args"][0]["port"]
        captured["timeout"] = timeout
        return {"success": True, "result": ""}

    monkeypatch.setattr(script_executor_module, "nats_request", accepted)
    plugin = SSHPlugin(
        {
            "node_id": "node-1",
            "host": "10.10.41.149",
            "script_path": "must-not-be-read.sh",
            "model_id": "host",
            "username": "collector",
            "password": "secret",
            "port": "",
            "timeout": "",
        }
    )

    result = await plugin.probe()

    assert result.status == AccessProbeStatus.READY
    assert captured["port"] == 22
    assert captured["timeout"] == 5.0
    assert captured["subject"] == "ssh.execute.node-1"


@pytest.mark.asyncio
async def test_ssh_plugin_accepts_ansible_node_id_alias():
    plugin = SSHPlugin(
        {
            "ansible_node_id": "node-alias",
            "host": "10.10.41.149",
            "script_path": "must-not-be-read.sh",
            "port": None,
        }
    )
    assert plugin.node_id == "node-alias"
    assert plugin.port == 22


@pytest.mark.asyncio
async def test_ssh_probe_uses_remote_noop_and_classifies_auth_failure(monkeypatch):
    async def rejected(_subject, *, payload, timeout):
        request = json.loads(payload.decode())
        args = request["args"][0]
        assert args["command"] == "true"
        assert args["connection_test"] is True
        assert timeout == 5
        return {"success": False, "error": "Permission denied (publickey,password)"}

    monkeypatch.setattr(script_executor_module, "nats_request", rejected)
    plugin = SSHPlugin(
        {
            "node_id": "node-1",
            "host": "10.0.0.8",
            "script_path": "must-not-be-read.sh",
            "model_id": "host",
            "username": "collector",
            "password": "secret",
            "timeout": 5,
        }
    )

    result = await plugin.probe()

    assert result.status == AccessProbeStatus.AUTH_FAILED
    assert result.error_code == "authentication_failed"
    assert "secret" not in result.detail


@pytest.mark.asyncio
async def test_job_executor_prepares_ssh_adapter_before_probe(monkeypatch):
    async def accepted(_subject, *, payload, timeout):
        request = json.loads(payload.decode())
        assert request["args"][0]["command"] == "true"
        return {"success": True, "result": ""}

    monkeypatch.setattr(script_executor_module, "nats_request", accepted)
    executor = PluginExecutor(
        "host",
        ExecutorConfig(
            executor_type="job",
            config={
                "timeout": 60,
                "scripts": {"linux": "plugins/shell/host.sh"},
                "default_script": "linux",
            },
            plugin_config={"metadata": {}},
        ),
        {
            "node_id": "node-1",
            "host": "10.0.0.8",
            "model_id": "host",
            "username": "collector",
            "password": "secret",
            "timeout": 5,
        },
    )

    result = await executor.probe()

    assert result.status == AccessProbeStatus.READY


@pytest.mark.asyncio
async def test_config_file_script_loading_does_not_stall_event_loop(
    tmp_path, monkeypatch
):
    script_path = tmp_path / "config-file.sh"
    script_path.write_text("cat '{{config_file_path}}'", encoding="utf-8")
    _delay_file_reads(monkeypatch, script_path)

    plugin = ConfigFileInfo(
        {
            "node_id": "node-1",
            "host": "10.0.0.1",
            "script_path": str(script_path),
            "model_id": "config_file",
            "config_file_path": "/etc/app.conf",
        }
    )

    async def fake_nats_request(*_args, **_kwargs):
        return {"success": True, "result": '{"status":"success"}'}

    monkeypatch.setattr("core.infra.nats_utils.nats_request", fake_nats_request)

    result = await _heartbeat_during(plugin.list_all_resources())

    assert result["success"] is True
    assert result["result"]["status"] == "success"
    assert result["result"]["file_name"] == "app.conf"


@pytest.mark.asyncio
async def test_host_collection_preparation_and_formatting_do_not_stall_event_loop(
    monkeypatch,
):
    collector = HostCollector(
        {
            "host": "10.0.0.1",
            "os_type": "linux",
            "username": "root",
            "password": "secret",
            "ansible_node_id": "node-1",
            "metrics_modules": "cpu",
            "execute_timeout": 5,
            "callback_timestamp": 1700000000000,
        }
    )

    real_open = builtins.open

    def delayed_host_script_open(file, *args, **kwargs):
        if "tasks/collectors/scripts" in str(file):
            time.sleep(0.03)
        return real_open(file, *args, **kwargs)

    async def fake_adhoc(**_kwargs):
        return {
            "success": True,
            "result": json.dumps(
                {"cpu": {"usage_percent": 12.5, "core_count": 4}}
            ),
        }

    monkeypatch.setattr(builtins, "open", delayed_host_script_open)
    monkeypatch.setattr("core.infra.ansible_rpc.ansible_adhoc", fake_adhoc)

    result = await _heartbeat_during(collector.collect(), minimum_ticks=10)

    assert (
        'host_cpu_usage_percent{instance_id="10.0.0.1",os_type="linux"} '
        "12.5 1700000000000"
    ) in result


@pytest.mark.asyncio
async def test_mysql_credential_probe_does_not_stall_event_loop(monkeypatch):
    class Cursor:
        def execute(self, query):
            if query != "SHOW GLOBAL VARIABLES LIKE 'version'":
                raise AssertionError("probe used a non-minimal capability query")

        def fetchall(self):
            return [{"Variable_name": "version", "Value": "8.0.36"}]

        def close(self):
            return None

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            return None

    def connect(**_kwargs):
        time.sleep(0.05)
        return Connection()

    monkeypatch.setattr("plugins.inputs.mysql.mysql_info.pymysql.connect", connect)
    plugin = MysqlInfo(
        {
            "host": "10.0.0.8",
            "port": 3306,
            "user": "collector",
            "password": "secret",
            "timeout": 5,
        }
    )

    result = await _heartbeat_during(plugin.probe())

    assert result.status == AccessProbeStatus.READY
    assert result.evidence == {"server_version": "8.0.36"}


@pytest.mark.asyncio
async def test_mysql_probe_returns_stable_auth_failure_without_secret(monkeypatch):
    import pymysql

    def rejected(**_kwargs):
        raise pymysql.err.OperationalError(
            1045, "Access denied for password secret-do-not-return"
        )

    monkeypatch.setattr(
        "plugins.inputs.mysql.mysql_info.pymysql.connect", rejected
    )
    plugin = MysqlInfo(
        {
            "host": "10.0.0.8",
            "user": "collector",
            "password": "secret-do-not-return",
            "timeout": 5,
        }
    )

    result = await plugin.probe()

    assert result.status == AccessProbeStatus.AUTH_FAILED
    assert result.error_code == "authentication_failed"
    assert "secret-do-not-return" not in result.detail


@pytest.mark.asyncio
async def test_postgresql_credential_probe_does_not_stall_event_loop(monkeypatch):
    class Cursor:
        def execute(self, query):
            if query != "SHOW server_version":
                raise AssertionError("probe used a non-minimal capability query")

        def fetchall(self):
            return [{"server_version": "16.2"}]

        def close(self):
            return None

    class Connection:
        def cursor(self, **_kwargs):
            return Cursor()

        def close(self):
            return None

    def connect(**_kwargs):
        time.sleep(0.05)
        return Connection()

    monkeypatch.setattr(
        "plugins.inputs.postgresql.postgresql_info.psycopg2.connect", connect
    )
    plugin = PostgresqlInfo(
        {
            "host": "10.0.0.9",
            "port": 5432,
            "user": "collector",
            "password": "secret",
            "timeout": 5,
        }
    )

    result = await _heartbeat_during(plugin.probe())

    assert result.status == AccessProbeStatus.READY
    assert result.evidence == {"server_version": "16.2"}
