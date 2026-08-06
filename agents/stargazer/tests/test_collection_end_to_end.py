"""统一采集完整链路测试：HTTP → Redis → Runtime → Plugin → NATS。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import pytest_asyncio
import httpx
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError
from sanic import Sanic

import api.collect as collect_api
import api.monitor as monitor_api
from core.collection_application import (
    CollectionApplication,
    CollectionApplicationSettings,
)
from core.result_publisher import NatsResultPublisher
from core.target_collection_executor import (
    CollectOutcome,
    CollectOutcomeStatus,
    PreflightResult,
    PreflightStatus,
)


@pytest.fixture
def redis_socket(tmp_path):
    executable = shutil.which("redis-server")
    if executable is None:
        pytest.skip("redis-server is not installed")
    socket_path = Path("/tmp") / f"stargazer-e2e-{secrets.token_hex(6)}.sock"
    process = subprocess.Popen(
        [
            executable,
            "--save",
            "",
            "--appendonly",
            "no",
            "--port",
            "0",
            "--unixsocket",
            str(socket_path),
            "--unixsocketperm",
            "700",
            "--dir",
            str(tmp_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    probe = Redis(unix_socket_path=str(socket_path), db=13)
    try:
        for _attempt in range(100):
            try:
                if probe.ping():
                    break
            except (RedisConnectionError, OSError):
                time.sleep(0.01)
        else:
            pytest.fail("temporary redis-server did not start")
        yield socket_path
    finally:
        probe.close()
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        socket_path.unlink(missing_ok=True)


@pytest_asyncio.fixture
async def redis_client(redis_socket):
    client = AsyncRedis(
        unix_socket_path=str(redis_socket), db=13, decode_responses=True
    )
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


class ReachablePreflight:
    def __init__(self):
        self.targets = []

    async def check(self, target, request, *, timeout_seconds):
        self.targets.append(target)
        return PreflightResult(status=PreflightStatus.REACHABLE)


class RecordingPlugin:
    def __init__(self, *, rotate_credentials=False, family="configuration"):
        self.rotate_credentials = rotate_credentials
        self.family = family
        self.calls = []

    async def collect(self, target, credential, context):
        credential_id = str(credential.get("credential_id") or "")
        self.calls.append((target, credential_id, context.fence))
        if self.rotate_credentials and credential_id == "credential-bad":
            return CollectOutcome(
                status=CollectOutcomeStatus.AUTH_FAILED,
                error_code="authentication_failed",
            )
        value = (
            f'host_health{{host="{target}"}} 1'
            if self.family == "monitor"
            else f'mysql_info{{host="{target}"}} 1'
        )
        return CollectOutcome(status=CollectOutcomeStatus.SUCCESS, value=value)


class PluginFactory:
    def __init__(self, plugin):
        self.plugin = plugin

    def resolve(self, request):
        return self.plugin


def build_application(redis_client, plugin, published, scheduled, *, fail_once=False):
    attempts = {"count": 0}

    async def publish_metrics(ctx, value, params, task_id):
        attempts["count"] += 1
        if fail_once and attempts["count"] == 1:
            raise ConnectionError("NATS unavailable")
        published.append((task_id, value, params))

    def schedule(coroutine, *, name):
        task = asyncio.create_task(coroutine, name=name)
        scheduled.append(task)
        return task

    preflight = ReachablePreflight()
    application = CollectionApplication(
        redis_client=redis_client,
        schedule=schedule,
        owner_id="pod-e2e",
        settings=CollectionApplicationSettings(
            max_active_runs=2,
            max_active_targets=2,
            target_task_window=2,
            connect_timeout_seconds=1,
            plugin_timeout_seconds=1,
            lease_ttl_seconds=10,
            lease_heartbeat_seconds=1,
        ),
        plugin_factory=PluginFactory(plugin),
        preflight=preflight,
        publisher=NatsResultPublisher(metrics_publish=publish_metrics),
    )
    return application, preflight


def configuration_request(task_id):
    return {
            "x-task-id": task_id,
            "cmdbmodel_id": "mysql",
            "cmdbhosts": "10.10.24.1,10.10.24.2",
            "cmdbport": "3306",
            "cmdbcredential_count": "2",
            "cmdbcredential_0_credential_id": "credential-bad",
            "cmdbcredential_0_username": "bad-user",
            "cmdbcredential_0_password": "do-not-log-bad",
            "cmdbcredential_1_credential_id": "credential-good",
            "cmdbcredential_1_username": "collector",
            "cmdbcredential_1_password": "do-not-log-good",
        }


@asynccontextmanager
async def http_client(blueprint, name):
    app = Sanic(name)
    app.config.AUTO_EXTEND = False
    app.config.TOUCHUP = False
    app.blueprint(blueprint)
    app.asgi = True
    await app._startup()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://stargazer.test",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_configuration_http_to_redis_plugin_nats_and_completed_reentry(
    redis_client, monkeypatch
):
    published = []
    scheduled = []
    plugin = RecordingPlugin(rotate_credentials=True)
    application, preflight = build_application(
        redis_client, plugin, published, scheduled
    )
    monkeypatch.setattr(
        collect_api, "get_collection_application", lambda: application
    )

    async with http_client(collect_api.collect_router, "e2e-config-app") as client:
        accepted = await client.get(
            "/collect/collect_info",
            headers=configuration_request("e2e-config"),
        )
        await scheduled[0]
        completed = await client.get(
            "/collect/collect_info",
            headers=configuration_request("e2e-config"),
        )

    assert accepted.status_code == 202
    assert accepted.headers["x-task-status"] == "accepted"
    assert completed.status_code == 200
    assert completed.headers["x-task-status"] == "completed"
    assert len(scheduled) == 1
    assert preflight.targets == ["10.10.24.1", "10.10.24.2"]
    assert [call[1] for call in plugin.calls if call[0] == "10.10.24.1"] == [
        "credential-bad",
        "credential-good",
    ]
    assert [call[1] for call in plugin.calls if call[0] == "10.10.24.2"] == [
        "credential-bad",
        "credential-good",
    ]
    assert {entry[2]["collection_target"] for entry in published} == {
        "10.10.24.1",
        "10.10.24.2",
    }
    assert all(entry[2]["collection_fence"] == 1 for entry in published)
    assert all(len(entry[2]["collection_result_id"]) == 64 for entry in published)
    assert "do-not-log" not in str(published)


@pytest.mark.asyncio
async def test_publish_failure_reentry_reuses_pending_result_without_recollecting(
    redis_client, monkeypatch
):
    published = []
    scheduled = []
    plugin = RecordingPlugin()
    application, preflight = build_application(
        redis_client, plugin, published, scheduled, fail_once=True
    )
    monkeypatch.setattr(
        collect_api, "get_collection_application", lambda: application
    )
    headers = {
            "x-task-id": "e2e-pending",
            "cmdbmodel_id": "mysql",
            "cmdbhosts": "10.10.24.9",
            "cmdbcredential_id": "credential-good",
        }

    async with http_client(collect_api.collect_router, "e2e-pending-app") as client:
        first = await client.get("/collect/collect_info", headers=headers)
        await scheduled[0]
        second = await client.get("/collect/collect_info", headers=headers)
        await scheduled[1]
        completed = await client.get("/collect/collect_info", headers=headers)

    assert first.status_code == second.status_code == 202
    assert second.headers["x-fencing-token"] == "2"
    assert completed.status_code == 200
    assert preflight.targets == ["10.10.24.9"]
    assert plugin.calls == [("10.10.24.9", "credential-good", 1)]
    assert len(published) == 1
    assert published[0][2]["collection_fence"] == 2


@pytest.mark.asyncio
async def test_monitor_http_uses_the_same_runtime_and_result_pipeline(
    redis_client, monkeypatch
):
    published = []
    scheduled = []
    plugin = RecordingPlugin(family="monitor")
    application, preflight = build_application(
        redis_client, plugin, published, scheduled
    )
    monkeypatch.setattr(
        monitor_api, "get_collection_application", lambda: application
    )
    headers = {
            "x-task-id": "e2e-monitor",
            "username": "monitor-user",
            "password": "do-not-log-monitor",
            "host": "10.10.24.20",
            "instance_id": "vmware-20",
            "instance_type": "vmware",
            "collect_type": "monitor",
            "config_type": "manual",
        }

    async with http_client(monitor_api.monitor_router, "e2e-monitor-app") as client:
        accepted = await client.get(
            "/monitor/vmware/metrics?minutes=5", headers=headers
        )
        await scheduled[0]
        completed = await client.get(
            "/monitor/vmware/metrics?minutes=5", headers=headers
        )

    assert accepted.status_code == 202
    assert completed.status_code == 200
    assert completed.headers["x-task-status"] == "completed"
    assert preflight.targets == ["10.10.24.20"]
    assert plugin.calls == [("10.10.24.20", "credential-1", 1)]
    assert len(published) == 1
    assert published[0][2]["plugin_family"] == "monitor"
    assert "do-not-log-monitor" not in str(published)
