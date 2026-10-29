import json
from types import SimpleNamespace

import api.collect as collect_api
import pytest
from core.collection.enums import WorkloadClass
from core.collection.runtime import Submission, SubmissionStatus
from core.scan.orchestrator import ScanDiscoverRequest


class Application:
    def __init__(self):
        self.payloads = []

    async def submit_scan(self, payload):
        self.payloads.append(payload)
        request = ScanDiscoverRequest.from_payload(payload)
        assert request.workload_class is WorkloadClass.SCAN
        return Submission(
            task_id=f"scan:{payload.get('execution_id')}",
            status=SubmissionStatus.ACCEPTED,
            fence=1,
            summary={"target_count": 3, "workload_class": WorkloadClass.SCAN.value},
        )


def _request(payload):
    async def receive_body():
        return None

    return SimpleNamespace(
        method="POST",
        path="/api/collect/scan_discover",
        json=payload,
        receive_body=receive_body,
        headers={},
    )


@pytest.mark.asyncio
async def test_scan_discover_http_uses_scan_workload(monkeypatch):
    app = Application()
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: app)
    payload = {
        "execution_id": 42,
        "ip_ranges": [{"begin": "10.0.1.1", "end": "10.0.1.3"}],
        "port_fingerprints": [{"port": 3306, "target_type": "mysql"}],
    }
    result = await collect_api.scan_discover(_request(payload))
    assert result.status == 202
    assert result.headers["x-task-status"] == SubmissionStatus.ACCEPTED.value
    assert result.headers["x-target-count"] == "3"
    assert result.headers["x-workload-class"] == WorkloadClass.SCAN.value
    assert app.payloads[0]["execution_id"] == 42


@pytest.mark.asyncio
async def test_collect_info_stays_configuration(monkeypatch):
    class CollectApp:
        def __init__(self):
            self.requests = []

        async def submit(self, request):
            self.requests.append(request)
            return Submission(task_id=request.task_id, status=SubmissionStatus.ACCEPTED, fence=1)

    app = CollectApp()
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: app)
    request = SimpleNamespace(
        method="GET",
        path="/api/collect/collect_info",
        query_string="",
        headers={"cmdbplugin_name": "mysql_info", "cmdbhosts": "10.0.1.1", "cmdbmodel_id": "mysql"},
    )
    await collect_api._submit_collection_run(
        request,
        {"model_id": "mysql", "hosts": "10.0.1.1", "plugin_name": "mysql_info"},
        "mysql",
    )
    assert app.requests[0].workload_class is WorkloadClass.CONFIGURATION


@pytest.mark.asyncio
async def test_collect_scan_plugin_reuses_mysql_info(monkeypatch):
    from types import SimpleNamespace

    from core.scan.collect_plugin import collect_scan_plugin

    captured = {}

    class FakeService:
        def __init__(self, params):
            captured["params"] = params

        async def collect(self):
            return SimpleNamespace(error="", data={"mysql": [{"version": "8.0"}]})

    monkeypatch.setattr("service.collection_service.CollectionService", FakeService)
    result = await collect_scan_plugin(
        {"host": "10.0.1.8", "port": 3306, "target_type": "mysql"},
        [{"credential_id": "cred-db", "username": "u"}],
    )
    assert result["success"] is True
    assert result["snapshot"]["version"] == "8.0"
    assert captured["params"]["plugin_name"] == "mysql_info"
    assert captured["params"]["executor_type"] == "protocol"
    assert captured["params"]["user"] == "u"


@pytest.mark.asyncio
async def test_list_scan_processes_skips_agent_placeholder():
    from core.scan.process_list import list_scan_processes

    lines = await list_scan_processes("10.0.1.8", {"pool": [{"credential_id": "agent"}]})
    assert lines == []


@pytest.mark.asyncio
async def test_list_scan_processes_agent_uses_local_execute(monkeypatch):
    from core.scan.process_list import list_scan_processes

    captured = {}

    async def fake_load_node_infos(ips, *, collect_task_id=None, cloud_region_id=None, timeout_seconds=10.0):
        captured["lookup"] = {
            "ips": list(ips),
            "collect_task_id": collect_task_id,
            "cloud_region_id": cloud_region_id,
        }
        del timeout_seconds
        return [{"id": "node-9", "ip": "10.0.1.8", "operating_system": "linux"}]

    async def fake_nats_request(subject, payload, timeout=30.0):
        captured["subject"] = subject
        del payload, timeout
        return {"success": True, "result": "/usr/sbin/mysqld\n"}

    monkeypatch.setattr("service.node_info_loader.load_node_infos", fake_load_node_infos)
    monkeypatch.setattr("core.infra.nats_utils.nats_request", fake_nats_request)

    lines = await list_scan_processes(
        "10.0.1.8",
        {
            "pool": [{"credential_id": "agent"}],
            "execution_id": 44,
            "cloud_region": {"id": 1},
        },
    )
    assert lines == ["/usr/sbin/mysqld"]
    assert captured["lookup"]["collect_task_id"] == 44
    assert captured["subject"] == "local.execute.node-9"


@pytest.mark.asyncio
async def test_list_scan_processes_prefers_agent_over_ssh(monkeypatch):
    from core.scan.process_list import list_scan_processes

    captured = {}

    async def fake_load_node_infos(ips, *, collect_task_id=None, cloud_region_id=None, timeout_seconds=10.0):
        del ips, collect_task_id, cloud_region_id, timeout_seconds
        return [{"id": "node-147", "ip": "10.11.27.147", "operating_system": "linux"}]

    async def fake_nats_request(subject, payload, timeout=30.0):
        captured["subject"] = subject
        del payload, timeout
        return {"success": True, "result": "redis-server *:6379\n"}

    def boom(*args, **kwargs):
        del args, kwargs
        raise AssertionError("SSH must not run when the host is a managed agent")

    monkeypatch.setattr("service.node_info_loader.load_node_infos", fake_load_node_infos)
    monkeypatch.setattr("core.infra.nats_utils.nats_request", fake_nats_request)
    monkeypatch.setattr("core.infra.ssh_client.SSHClient", boom)

    lines = await list_scan_processes(
        "10.11.27.147",
        {
            "pool": [{"credential_id": "cred-ssh", "username": "root", "password": "secret", "port": "22"}],
            "execution_id": 42,
            "cloud_region": {"id": 1},
        },
        access_point=[{"id": "ap-1"}],
    )
    assert lines == ["redis-server *:6379"]
    assert captured["subject"] == "local.execute.node-147"


@pytest.mark.asyncio
async def test_list_scan_processes_falls_back_to_access_point_ssh(monkeypatch):
    from core.scan.process_list import list_scan_processes

    captured = {}

    async def fake_load_node_infos(ips, *, collect_task_id=None, cloud_region_id=None, timeout_seconds=10.0):
        del ips, collect_task_id, cloud_region_id, timeout_seconds
        return []

    async def fake_nats_request(subject, payload, timeout=30.0):
        captured["subject"] = subject
        captured["command"] = json.loads(payload.decode())["args"][0]["command"]
        del timeout
        return {"success": True, "result": "/usr/sbin/nginx\n"}

    monkeypatch.setattr("service.node_info_loader.load_node_infos", fake_load_node_infos)
    monkeypatch.setattr("core.infra.nats_utils.nats_request", fake_nats_request)

    lines = await list_scan_processes(
        "10.0.1.9",
        {
            "pool": [{"credential_id": "cred-ssh", "username": "root", "password": "secret", "port": "22"}],
            "execution_id": 42,
        },
        access_point=[{"id": "ap-1"}],
    )
    assert lines == ["/usr/sbin/nginx"]
    assert captured["subject"] == "ssh.execute.ap-1"
    assert captured["command"] == "ps -eo args --no-headers"
