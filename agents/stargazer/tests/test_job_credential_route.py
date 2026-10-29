"""JOB 执行路由由目标 Agent 信息决定，不能把空账号等同于 Agent 已就绪。"""
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
