"""JOB 执行路由由目标 Agent 信息决定，不能把空账号等同于 Agent 已就绪。"""
import json
import logging

import pytest
from plugins.script_executor import SSHPlugin


@pytest.mark.asyncio
async def test_local_executor_timeout_falls_back_to_ssh_when_credential_exists(monkeypatch):
    calls = []

    async def request(subject, payload=None, timeout=10.0):
        calls.append(subject)
        if subject.startswith("local.execute."):
            raise TimeoutError("nats executor unavailable")
        return {"success": True, "result": "{}"}

    monkeypatch.setattr("plugins.script_executor.nats_request", request)
    plugin = SSHPlugin(
        {
            "node_id": "access-point",
            "host": "192.0.2.20",
            "script_content": "echo ok",
            "username": "root",
            "password": "secret",
            "model_id": "host",
            "node_info": {"id": "node-20", "operating_system": "linux"},
        }
    )

    result = await plugin.list_all_resources()

    assert result["success"] is True
    assert calls == ["local.execute.node-20", "ssh.execute.access-point"]


@pytest.mark.asyncio
async def test_local_executor_timeout_without_credential_does_not_call_ssh(monkeypatch):
    calls = []

    async def request(subject, payload=None, timeout=10.0):
        calls.append(subject)
        raise TimeoutError("nats executor unavailable")

    monkeypatch.setattr("plugins.script_executor.nats_request", request)
    plugin = SSHPlugin(
        {
            "node_id": "access-point",
            "host": "192.0.2.20",
            "script_content": "echo ok",
            "model_id": "host",
            "node_info": {"id": "node-20", "operating_system": "linux"},
        }
    )

    result = await plugin.list_all_resources()

    assert result["success"] is False
    assert calls == ["local.execute.node-20"]


@pytest.mark.parametrize("username,password", [(None, None), ("", ""), ("test-user", "test-password")])
@pytest.mark.parametrize("node_info", [{}, {"id": "test-agent"}])
def test_job_credentials_do_not_decide_agent_route(username, password, node_info):
    plugin = SSHPlugin(
        {
            "node_id": "test-access-point",
            "host": "192.0.2.10",
            "script_path": "test.sh",
            "username": username,
            "password": password,
            "node_info": node_info,
        }
    )
    params = plugin._build_exec_params("true")
    if node_info:
        assert params["shell"] == "bash"
        assert "host" not in params
        assert "password" not in params
    else:
        assert params["host"] == "192.0.2.10"
        assert params["username"] == username
        assert params["password"] == password
        assert params["connection_test"] is True
        assert "shell" not in params


@pytest.mark.parametrize("collector_name", ["ssh", "config_file"])
@pytest.mark.parametrize(
    "authentication",
    [
        {"username": "test-user", "password": "test-password"},
        {"username": "test-user", "private_key": "test-private-key", "passphrase": "test-passphrase"},
    ],
)
def test_job_vault_fields_reach_actual_executor_request(collector_name, authentication):
    from plugins.inputs.config_file.config_file_info import ConfigFileInfo

    collector = SSHPlugin if collector_name == "ssh" else ConfigFileInfo
    plugin = collector(
        {
            "node_id": "test-access-point",
            "host": "192.0.2.10",
            "script_path": "test.sh",
            "port": 2222,
            **authentication,
        }
    )
    request = plugin._build_exec_params("true")
    assert all(request[key] == value for key, value in authentication.items())
    assert request["port"] == 2222
    assert request["host"] == "192.0.2.10"
    if "private_key" in authentication:
        assert not request["password"]
    else:
        assert "private_key" not in request


def test_redis_local_execution_injects_rediscli_auth_without_putting_it_on_the_command():
    plugin = SSHPlugin(
        {
            "node_id": "access-point",
            "host": "10.209.0.13",
            "script_content": "redis-cli PING",
            "username": "root",
            "password": "ssh-secret",
            "service_password": "redis-secret",
            "model_id": "redis",
            "node_info": {"id": "node-13", "operating_system": "linux"},
        }
    )

    params = plugin._build_exec_params("redis-cli PING")

    assert params["shell"] == "sh"
    assert params["env"] == {"REDISCLI_AUTH": "redis-secret"}
    assert "REDIS_USER" not in params["env"]
    assert "password" not in params
    assert "redis-secret" not in params["command"]


@pytest.mark.parametrize(
    "password",
    ["", "   ", "${PASSWORD_password_cmdb_42}"],
)
def test_redis_local_execution_skips_blank_or_unexpanded_password(password):
    plugin = SSHPlugin(
        {
            "node_id": "access-point",
            "host": "10.209.0.13",
            "script_content": "redis-cli PING",
            "service_password": password,
            "model_id": "redis",
            "node_info": {"id": "node-13"},
        }
    )

    assert "env" not in plugin._build_exec_params("redis-cli PING")


def test_non_redis_local_execution_does_not_receive_rediscli_auth():
    plugin = SSHPlugin(
        {
            "node_id": "access-point",
            "host": "10.209.0.13",
            "script_path": "host_discover.sh",
            "password": "ssh-secret",
            "model_id": "host",
            "node_info": {"id": "node-13"},
        }
    )

    params = plugin._build_exec_params("true")

    assert "env" not in params
    assert "password" not in params


@pytest.mark.asyncio
async def test_redis_local_execute_payload_carries_rediscli_auth(monkeypatch):
    captured = {}

    async def request(subject, payload=None, timeout=10.0):
        captured["subject"] = subject
        captured["payload"] = json.loads(payload)
        return {"success": True, "result": "{}"}

    monkeypatch.setattr("plugins.script_executor.nats_request", request)
    plugin = SSHPlugin(
        {
            "node_id": "access-point",
            "host": "10.209.0.13",
            "script_content": "echo ok",
            "password": "ssh-secret",
            "service_password": "redis-secret",
            "model_id": "redis",
            "node_info": {"id": "node-13", "operating_system": "linux"},
        }
    )

    result = await plugin.list_all_resources()

    args = captured["payload"]["args"][0]
    assert result["success"] is True
    assert captured["subject"] == "local.execute.node-13"
    assert args["env"]["REDISCLI_AUTH"] == "redis-secret"
    assert "REDIS_USER" not in args["env"]
    assert "redis-secret" not in args["command"]
    assert "ssh-secret" not in args["command"]
    assert "password" not in args


def test_ssh_password_is_not_the_redis_service_secret():
    plugin = SSHPlugin(
        {
            "node_id": "access-point",
            "host": "10.209.0.13",
            "script_content": "redis-cli PING",
            "username": "root",
            "password": "ssh-secret",
            "model_id": "redis",
            "node_info": {"id": "node-13"},
        }
    )

    assert "env" not in plugin._build_exec_params("redis-cli PING")


def test_redis_acl_username_is_separate_from_the_ssh_account():
    plugin = SSHPlugin(
        {
            "node_id": "access-point",
            "host": "10.209.0.13",
            "script_content": "redis-cli PING",
            "username": "root",
            "password": "ssh-secret",
            "service_username": "reader",
            "service_password": "redis-secret",
            "model_id": "redis",
        }
    )

    params = plugin._build_exec_params("redis-cli PING")

    assert params["user"] == "root"
    assert params["password"] == "ssh-secret"
    assert params["env"] == {"REDISCLI_AUTH": "redis-secret", "REDIS_USER": "reader"}
    assert "redis-secret" not in params["command"]


@pytest.mark.asyncio
async def test_execution_debug_log_does_not_contain_the_service_secret(monkeypatch, caplog):
    secret = "SENTINEL_SERVICE_SECRET_MUST_NOT_LOG"

    async def request(subject, payload=None, timeout=10.0):
        return {"success": True, "result": "{}"}

    test_logger = logging.getLogger("test.stargazer.service_credential")
    monkeypatch.setattr("plugins.script_executor.nats_request", request)
    monkeypatch.setattr("plugins.script_executor.logger", test_logger)
    plugin = SSHPlugin(
        {
            "node_id": "access-point",
            "host": "10.209.0.13",
            "script_content": "echo ok",
            "username": "root",
            "password": "ssh-secret",
            "service_password": secret,
            "model_id": "redis",
            "collection_task_id": "task-42",
        }
    )

    with caplog.at_level(logging.DEBUG, logger=test_logger.name):
        await plugin.list_all_resources()

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in joined
    assert "echo ok" in joined or "event=ssh_script_execute" in joined


@pytest.mark.asyncio
async def test_redis_ssh_execute_payload_carries_service_env(monkeypatch):
    captured = {}

    async def request(subject, payload=None, timeout=10.0):
        captured["subject"] = subject
        captured["payload"] = json.loads(payload)
        return {"success": True, "result": "{}"}

    monkeypatch.setattr("plugins.script_executor.nats_request", request)
    plugin = SSHPlugin(
        {
            "node_id": "access-point",
            "host": "10.209.0.13",
            "script_content": "echo ok",
            "username": "root",
            "password": "ssh-secret",
            "service_password": "redis-secret",
            "model_id": "redis",
        }
    )

    await plugin.list_all_resources()

    args = captured["payload"]["args"][0]
    assert captured["subject"] == "ssh.execute.access-point"
    assert args["env"]["REDISCLI_AUTH"] == "redis-secret"
    assert args["password"] == "ssh-secret"
    assert "redis-secret" not in args["command"]


@pytest.mark.parametrize(
    ("username", "password", "auth_source", "expected"),
    [
        ("", "mongo-secret", "admin", None),
        ("reader", "", "admin", None),
        ("reader", "mongo-secret", "", {"MONGO_USER": "reader", "MONGO_PASSWORD": "mongo-secret", "MONGO_AUTH_DB": "admin"}),
        ("reader", "mongo-secret", "appdb", {"MONGO_USER": "reader", "MONGO_PASSWORD": "mongo-secret", "MONGO_AUTH_DB": "appdb"}),
    ],
)
def test_mongodb_service_credential_is_injected_only_as_a_pair(username, password, auth_source, expected):
    plugin = SSHPlugin(
        {
            "node_id": "access-point",
            "host": "10.209.0.13",
            "script_content": "echo mongo",
            "username": "root",
            "password": "ssh-secret",
            "service_username": username,
            "service_password": password,
            "auth_source": auth_source,
            "model_id": "mongodb",
            "node_info": {"id": "node-13"},
        }
    )

    params = plugin._build_exec_params("echo mongo")

    if expected is None:
        assert "env" not in params
    else:
        assert params["env"] == expected
    assert "mongo-secret" not in params["command"]
