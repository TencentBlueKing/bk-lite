"""Job 采集完整链路：接入点本机、同云区域 NATS 节点、其余 IP 走 SSH。

IP 取自直连区域的真实节点：
- 172.18.0.30 接入点 fusion-collector-default
- 10.10.41.149、10.10.41.98 同区域且 NATS-Executor 在线
- 192.0.2.50 不在节点管理里，只能由接入点 SSH
"""

import asyncio
import json

import pytest
from core.collection.contracts import TargetExecutorSettings
from core.collection.executor import TargetCollectionExecutor
from core.collection.plugins import UnifiedPluginFactory
from core.collection.preflight import AsyncProtocolPreflight
from core.collection.runtime import CollectionRequest, RunLease
from plugins.script_executor import SSHPlugin

ACCESS_POINT_IP = "172.18.0.30"
ACCESS_POINT_ID = "8d41f0d8a12811f1a1920242ac120010"
LINUX_NODE_IP = "10.10.41.149"
LINUX_NODE_ID = "99db84ff4339493686899ef94cf48f34"
WINDOWS_NODE_IP = "10.10.41.98"
WINDOWS_NODE_ID = "62156872bd35483795253de3339189b9"
UNMANAGED_IP = "192.0.2.50"
CLOUD_REGION_ID = 1

NODES = {
    ACCESS_POINT_IP: {
        "id": ACCESS_POINT_ID,
        "ip": ACCESS_POINT_IP,
        "operating_system": "linux",
        "nats_executor_online": True,
    },
    LINUX_NODE_IP: {
        "id": LINUX_NODE_ID,
        "ip": LINUX_NODE_IP,
        "operating_system": "linux",
        "nats_executor_online": True,
    },
    WINDOWS_NODE_IP: {
        "id": WINDOWS_NODE_ID,
        "ip": WINDOWS_NODE_IP,
        "operating_system": "windows",
        "nats_executor_online": True,
    },
}


class RecordingPublisher:
    def __init__(self):
        self.results = []

    async def publish(self, request, result, lease):
        self.results.append(result)


class ScriptService:
    """配置插件真正调用的脚本执行器。"""

    def __init__(self, params):
        self.plugin = SSHPlugin({**params, "script_content": params.get("script_content") or "hostname"})

    async def probe(self):
        return await self.plugin.probe()

    async def collect(self):
        result = await self.plugin.list_all_resources()
        if result.get("success"):
            return 'host{collect_status="success"} 1'
        return 'host{collect_status="failed",collect_error="collection failed"} 1'


def _request(targets, *, ip_precheck, credentials):
    return CollectionRequest(
        task_id="job-chain",
        plugin_ref="host.config",
        targets=tuple(targets),
        credentials=tuple(credentials),
        params={
            "plugin_family": "configuration",
            "model_id": "host",
            "executor_type": "job",
            "collect_task_id": 91,
            "preflight_kind": "remote",
            "ip_precheck": ip_precheck,
            "port": 22,
            "node_id": ACCESS_POINT_ID,
            "executor_node_ip": ACCESS_POINT_IP,
            "cloud_region_id": CLOUD_REGION_ID,
        },
    )


def _install_edges(monkeypatch, nodes, *, refuse_hosts=()):
    lookups = []
    calls = []
    dials = []

    async def load(ips, **context):
        lookups.append({"ips": tuple(ips), **context})
        return [nodes[ip] for ip in ips if ip in nodes]

    async def nats_request(subject, payload=None, timeout=30.0):
        body = json.loads(payload)
        command = body["args"][0]
        calls.append(
            {
                "subject": subject,
                "host": command.get("host"),
                "password": command.get("password"),
                "command": command.get("command"),
            }
        )
        return {"success": True, "result": '{"hostname":"ok"}'}

    real_open_connection = asyncio.open_connection

    async def open_connection(host, port, **kwargs):
        if int(port) == 22:
            dials.append((host, port))
            if host in refuse_hosts:
                raise ConnectionRefusedError(host)

            class _Writer:
                def close(self):
                    return None

                async def wait_closed(self):
                    return None

            return object(), _Writer()
        return await real_open_connection(host, port, **kwargs)

    async def publish_marker(_request, _round_ts):
        return True

    monkeypatch.setattr("plugins.script_executor.nats_request", nats_request)
    monkeypatch.setattr("core.collection.preflight.asyncio.open_connection", open_connection)
    monkeypatch.setattr("core.collection.round_complete.publish_round_complete_marker", publish_marker)
    return load, calls, dials, lookups


async def _execute(monkeypatch, targets, *, ip_precheck, credentials, nodes=None, refuse_hosts=()):
    load, calls, dials, lookups = _install_edges(monkeypatch, nodes if nodes is not None else NODES, refuse_hosts=refuse_hosts)
    request = _request(targets, ip_precheck=ip_precheck, credentials=credentials)
    plugin = UnifiedPluginFactory(
        configuration_service_factory=ScriptService,
        configuration_node_info_loader=load,
    ).resolve(request)
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=AsyncProtocolPreflight(),
        access_probe=plugin,
        plugin=plugin,
        publisher=publisher,
        settings=TargetExecutorSettings(
            max_active_targets=len(targets),
            target_task_window=len(targets),
        ),
    )
    summary = await executor.execute(request, RunLease(request.task_id, request.digest, "pod-a", 1, 999999))
    await plugin.close()
    return summary, calls, dials, lookups


def _subjects_for(calls, command):
    return [item["subject"] for item in calls if item["command"] == command]


@pytest.mark.asyncio
async def test_job_run_uses_local_executor_for_access_point_and_same_region_nodes_and_ssh_for_other_ips(monkeypatch):
    summary, calls, dials, lookups = await _execute(
        monkeypatch,
        (ACCESS_POINT_IP, LINUX_NODE_IP, WINDOWS_NODE_IP, UNMANAGED_IP),
        ip_precheck=True,
        credentials=({"credential_id": "ssh-1", "username": "root", "password": "secret", "port": 22},),
    )

    assert summary.collection_succeeded == 4
    assert summary.unreachable == 0
    assert lookups[0]["cloud_region_id"] == CLOUD_REGION_ID
    assert set(_subjects_for(calls, "hostname")) == {
        f"local.execute.{ACCESS_POINT_ID}",
        f"local.execute.{LINUX_NODE_ID}",
        f"local.execute.{WINDOWS_NODE_ID}",
        f"ssh.execute.{ACCESS_POINT_ID}",
    }
    local_calls = [item for item in calls if item["subject"].startswith("local.execute.")]
    assert local_calls
    assert all(item["password"] in (None, "") and item["host"] in (None, "") for item in local_calls)
    ssh_collect = [item for item in calls if item["subject"].startswith("ssh.execute.") and item["command"] == "hostname"]
    assert ssh_collect
    assert all(item["host"] == UNMANAGED_IP and item["password"] == "secret" for item in ssh_collect)
    assert dials == [(UNMANAGED_IP, 22)]


@pytest.mark.asyncio
async def test_ip_precheck_does_not_dial_same_region_node_when_port_22_would_refuse(monkeypatch):
    summary, calls, dials, _lookups = await _execute(
        monkeypatch,
        (WINDOWS_NODE_IP,),
        ip_precheck=True,
        credentials=(),
        refuse_hosts={WINDOWS_NODE_IP},
    )

    assert summary.collection_succeeded == 1
    assert summary.unreachable == 0
    assert dials == []
    assert _subjects_for(calls, "hostname") == [f"local.execute.{WINDOWS_NODE_ID}"]
    assert all(item["password"] in (None, "") for item in calls)


@pytest.mark.asyncio
async def test_ip_precheck_stops_unmanaged_ip_when_ssh_port_refuses(monkeypatch):
    summary, calls, dials, _lookups = await _execute(
        monkeypatch,
        (UNMANAGED_IP,),
        ip_precheck=True,
        credentials=({"credential_id": "ssh-1", "username": "root", "password": "secret"},),
        refuse_hosts={UNMANAGED_IP},
    )

    assert summary.unreachable == 1
    assert summary.collection_succeeded == 0
    assert dials == [(UNMANAGED_IP, 22)]
    assert calls == []


@pytest.mark.asyncio
async def test_ip_precheck_off_collects_unmanaged_ip_over_ssh_without_dialing(monkeypatch):
    summary, calls, dials, _lookups = await _execute(
        monkeypatch,
        (UNMANAGED_IP,),
        ip_precheck=False,
        credentials=({"credential_id": "ssh-1", "username": "root", "password": "secret"},),
    )

    assert summary.collection_succeeded == 1
    assert dials == []
    assert _subjects_for(calls, "hostname") == [f"ssh.execute.{ACCESS_POINT_ID}"]


@pytest.mark.asyncio
async def test_same_region_node_without_running_executor_uses_ssh(monkeypatch):
    offline = {
        WINDOWS_NODE_IP: {
            "id": WINDOWS_NODE_ID,
            "ip": WINDOWS_NODE_IP,
            "operating_system": "windows",
            "nats_executor_online": False,
        }
    }
    summary, calls, dials, _lookups = await _execute(
        monkeypatch,
        (WINDOWS_NODE_IP,),
        ip_precheck=False,
        credentials=({"credential_id": "ssh-1", "username": "root", "password": "secret"},),
        nodes=offline,
    )

    assert summary.collection_succeeded == 1
    assert dials == []
    assert _subjects_for(calls, "hostname") == [f"ssh.execute.{ACCESS_POINT_ID}"]
    assert all(item["host"] == WINDOWS_NODE_IP for item in calls if item["command"] == "hostname")
