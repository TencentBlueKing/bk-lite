import json
from pathlib import Path

import pytest
from plugins.inputs.custom_script.collector import CustomScriptCollector, parse_records, render_script
from plugins.script_executor import SSHPlugin

# 来自已创建任务 23（host）和 24（nginx）的非敏感契约。
TASK_SCRIPTS = {
    23: {
        "plugin_id": "custom_host_scan",
        "content": '#!/bin/bash\necho \'[{"inst_name":"demo-host"}]\'\n# edited\n',
        "shell": "bash",
        "os_type": "linux",
        "version": 2,
    },
    24: {
        "plugin_id": "custom_nginx_scan",
        "content": '#!/bin/bash\necho \'[{"inst_name":"demo-nginx"}]\'\n',
        "shell": "bash",
        "os_type": "linux",
        "version": 1,
    },
}


def test_render_script_injects_business_credential_placeholder():
    rendered = render_script("echo {{credential.db_password}}", {"db_password": "s3cret", "password": "transport"})
    assert rendered == "echo s3cret"


def test_parse_records_drops_missing_inst_name_and_nested_values():
    records = parse_records('[{"inst_name":"a","port":"1","labels":{"x":1}},{"port":"2"}]')
    assert records == [{"inst_name": "a", "port": "1"}]


def test_ssh_plugin_uses_injected_script_content(monkeypatch):
    plugin = SSHPlugin(
        {
            "node_id": "node-1",
            "host": "10.0.0.8",
            "script_content": "echo {{bk_host_innerip}}",
            "shell": "bash",
            "model_id": "host",
            "execute_timeout": 90,
        }
    )
    assert plugin.execute_timeout == 90
    assert plugin._read_script() == "echo 10.0.0.8"
    assert plugin._get_shell_type() == "bash"


@pytest.mark.asyncio
async def test_prepare_injects_script_once(monkeypatch):
    from core.collection.plugins import ConfigurationCollectionPlugin
    from core.collection.runtime import CollectionRequest

    calls = []

    async def fake_fetch(task_id):
        calls.append(task_id)
        return {"content": "echo ok", "shell": "bash", "os_type": "linux", "plugin_id": "custom_host_scan"}

    monkeypatch.setattr("plugins.inputs.custom_script.collector.fetch_custom_script", fake_fetch)
    plugin = ConfigurationCollectionPlugin(service_factory=lambda params: params)
    request = CollectionRequest(
        task_id="run-1",
        plugin_ref="custom_script.config",
        targets=("10.0.0.1",),
        params={"plugin_name": "custom_script_info", "collect_task_id": 7, "executor_type": "protocol"},
    )
    await plugin.prepare(request)
    await plugin.prepare(request)
    assert calls == [7]
    assert request.params["script_content"] == "echo ok"
    assert request.params["custom_plugin_id"] == "custom_host_scan"


@pytest.mark.asyncio
async def test_created_tasks_follow_stargazer_fetch_and_execute(monkeypatch):
    from core.collection.plugins import ConfigurationCollectionPlugin
    from core.collection.runtime import CollectionRequest

    calls = []

    async def fake_nats(subject, payload, timeout):
        body = json.loads(payload)
        task_id = body["args"][0]["collect_task_id"]
        calls.append((subject, task_id))
        assert subject.endswith(".cmdb_get_custom_script")
        return {"success": True, "result": TASK_SCRIPTS[task_id]}

    executed = []

    async def fake_execute(self, need_raw=False):
        executed.append(self.script_content)
        inst_name = "demo-host" if "demo-host" in self.script_content else "demo-nginx"
        return {"success": True, "result": json.dumps([{"inst_name": inst_name}])}

    monkeypatch.setattr("core.infra.nats_utils.nats_request", fake_nats)
    monkeypatch.setattr(SSHPlugin, "list_all_resources", fake_execute)

    for task_id, expected in TASK_SCRIPTS.items():
        plugin = ConfigurationCollectionPlugin(service_factory=lambda params: params)
        request = CollectionRequest(
            task_id=f"run-{task_id}",
            plugin_ref="custom_script.config",
            targets=("10.0.0.8",),
            params={
                "plugin_name": "custom_script_info",
                "collect_task_id": task_id,
                "executor_type": "job",
                "model_id": "host" if task_id == 23 else "nginx",
                "node_id": "8d41f0d8a12811f1a1920242ac120010",
                "host": "10.0.0.8",
                "username": "root",
                "timeout": 120,
            },
        )
        await plugin.prepare(request)
        await plugin.prepare(request)
        assert request.params["custom_plugin_id"] == expected["plugin_id"]
        assert request.params["shell"] == expected["shell"]
        collector = CustomScriptCollector(dict(request.params))
        result = await collector.list_all_resources()
        assert result["success"] is True
        assert result["result"][expected["plugin_id"]] == [{"inst_name": "demo-host" if task_id == 23 else "demo-nginx"}]

    assert [task_id for _subject, task_id in calls] == [23, 24]
    assert executed[0].endswith("# edited\n")


@pytest.mark.asyncio
async def test_windows_bat_uses_cmd_script_type(monkeypatch):
    captured = {}

    async def fake_adhoc(**kwargs):
        captured.update(kwargs)
        return {"success": True, "result": [{"stdout": '[{"inst_name":"win-1"}]'}]}

    monkeypatch.setattr("plugins.inputs.custom_script.collector.ansible_adhoc", fake_adhoc)
    collector = CustomScriptCollector(
        {
            "custom_plugin_id": "custom_win_scan",
            "os_type": "windows",
            "shell": "bat",
            "script_content": "echo hello",
            "node_id": "node-1",
            "host": "10.0.0.9",
            "username": "administrator",
            "password": "secret",
            "timeout": 90,
        }
    )
    result = await collector.list_all_resources()
    assert result["result"]["custom_win_scan"] == [{"inst_name": "win-1"}]
    assert captured["module"] == "win_shell"
    assert captured["stream_remote_type"] == "bat"
    assert captured["module_args"] == "echo hello"


@pytest.mark.asyncio
async def test_windows_reads_stdout_from_host_keyed_ansible_result(monkeypatch):
    async def fake_adhoc(**kwargs):
        return {
            "success": True,
            "result": {"10.0.0.9": {"rc": 0, "stdout": '[{"inst_name":"win-dict"}]'}},
        }

    monkeypatch.setattr("plugins.inputs.custom_script.collector.ansible_adhoc", fake_adhoc)
    collector = CustomScriptCollector(
        {
            "custom_plugin_id": "custom_win_scan",
            "os_type": "windows",
            "shell": "powershell",
            "script_content": "Write-Output ok",
            "node_id": "node-1",
            "host": "10.0.0.9",
            "username": "administrator",
            "password": "secret",
            "timeout": 90,
        }
    )
    result = await collector.list_all_resources()
    assert result["result"]["custom_win_scan"] == [{"inst_name": "win-dict"}]


def _params_from_dispatched_headers(headers):
    """与 api/collect.py 一样，只消费 cmdb 前缀和 Telegraf tags。"""
    params = {key.split("cmdb", 1)[-1]: value for key, value in headers.items() if key.startswith("cmdb")}
    params["tags"] = {
        "instance_id": headers.get("instance_id"),
        "instance_type": headers.get("instance_type"),
        "collect_type": headers.get("collect_type"),
        "config_type": headers.get("config_type"),
    }
    return params


@pytest.mark.asyncio
async def test_dispatched_headers_drive_stargazer_collection(monkeypatch):
    from core.collection.plugins import ConfigurationCollectionPlugin
    from core.collection.request_builder import build_collection_request

    fixture = json.loads((Path(__file__).parent / "fixtures" / "custom_script_dispatched_headers.json").read_text())
    calls = []
    executed = []

    async def fake_nats(subject, payload, timeout):
        task_id = json.loads(payload)["args"][0]["collect_task_id"]
        calls.append(int(task_id))
        assert subject.endswith(".cmdb_get_custom_script")
        return {"success": True, "result": TASK_SCRIPTS[int(task_id)]}

    async def fake_execute(self, need_raw=False):
        executed.append(self.script_content)
        inst_name = "demo-host" if "demo-host" in self.script_content else "demo-nginx"
        return {"success": True, "result": json.dumps([{"inst_name": inst_name}])}

    monkeypatch.setattr("core.infra.nats_utils.nats_request", fake_nats)
    monkeypatch.setattr(SSHPlugin, "list_all_resources", fake_execute)

    for task_id, headers in fixture.items():
        rendered = json.dumps(headers)
        assert "#!/bin/bash" not in rendered
        assert "biz-secret" not in rendered
        params = _params_from_dispatched_headers(headers)
        request = build_collection_request(task_id=params["collect_task_id"], params=params)
        assert request.plugin_ref == "custom_script.config"
        assert request.targets == ("10.0.0.8",)
        assert request.params["plugin_name"] == "custom_script_info"
        assert request.params["model_id"] in {"host", "nginx"}
        plugin = ConfigurationCollectionPlugin(service_factory=lambda params: params)
        await plugin.prepare(request)
        target_params = dict(request.params)
        if request.credentials:
            target_params.update(request.credentials[0])
        target_params["host"] = request.targets[0]
        result = await CustomScriptCollector(target_params).list_all_resources()
        plugin_id = headers["cmdbcustom_plugin_id"]
        assert result["result"][plugin_id][0]["inst_name"] in {"demo-host", "demo-nginx"}
        assert target_params["ssh_password"].startswith("${PASSWORD_ssh_password_cmdb_")

    assert calls == [23, 24]
    assert executed[0].endswith("# edited\n")


@pytest.mark.asyncio
async def test_custom_script_service_loads_custom_collector_and_encodes_metric(monkeypatch):
    from service.collection_service import CollectionService
    from tasks.utils.nats_helper import convert_structured_metrics_to_influx

    params = {
        "plugin_name": "custom_script_info",
        "model_id": "host",
        "executor_type": "job",
        "os_type": "linux",
        "shell": "sh",
        "custom_plugin_id": "custom_host_linux_scan",
        "script_content": 'echo \'[{"inst_name":"demo-host-v2"}]\'',
        "collect_task_id": "25",
        "host": "10.0.0.8",
        "node_id": "node-1",
        "username": "root",
        "password": "secret",
        "port": "22",
        "timeout": "120",
        "_runtime_structured_metrics": True,
    }

    factory = await CollectionService.prepare(params)
    collector = factory.executor_config.get_collector_info()
    assert collector["class"] == "CustomScriptCollector"
    assert collector["module"] == "plugins.inputs.custom_script.collector"

    async def fake_execute(self, need_raw=False):
        assert "demo-host-v2" in self.script_content
        assert self.model_id == "host"
        return {"success": True, "result": '[{"inst_name":"demo-host-v2"}]'}

    monkeypatch.setattr(SSHPlugin, "list_all_resources", fake_execute)
    payload = await factory(params).collect()

    assert payload.data["custom_host_linux_scan"][0]["inst_name"] == "demo-host-v2"
    assert "host" not in payload.data
    lines = convert_structured_metrics_to_influx(payload, {"plugin_name": "custom_script_info", "instance_id": "cmdb_25"})
    rendered = "\n".join(lines)
    assert "custom_host_linux_scan_info" in rendered
    assert "host_info" not in rendered
    assert "demo-host-v2" in rendered


@pytest.mark.asyncio
async def test_builtin_host_service_still_loads_host_collector():
    from service.collection_service import CollectionService

    factory = await CollectionService.prepare(
        {
            "plugin_name": "host_info",
            "model_id": "host",
            "executor_type": "job",
        }
    )

    assert factory.executor_config.get_collector_info()["class"] == "HostInfo"
