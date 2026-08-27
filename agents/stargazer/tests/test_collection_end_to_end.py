"""统一采集完整链路测试：HTTP → Redis → Runtime → Plugin → NATS。"""

from __future__ import annotations

import asyncio
import json
import os
import resource
import secrets
import shutil
import subprocess
import sys
import time
import traceback
import tracemalloc
from contextlib import asynccontextmanager
from pathlib import Path

import api.collect as collect_api
import api.health as health_api
import api.monitor as monitor_api
import httpx
import pytest
import pytest_asyncio
from core.collection.application import CollectionApplication, CollectionApplicationSettings
from core.collection.contracts import AccessProbeResult, AccessProbeStatus, CollectOutcome, CollectOutcomeStatus, PreflightResult, PreflightStatus
from core.collection.execution_plan import ExecutionPlan
from core.collection.result_publisher import NatsResultPublisher
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError
from sanic import Sanic


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
    client = AsyncRedis(unix_socket_path=str(redis_socket), db=13, decode_responses=True)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


class ReachablePreflight:
    def __init__(self):
        self.targets = []

    async def check(self, target, request, *, timeout_seconds, plan=None):
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
        value = f'host_health{{host="{target}"}} 1' if self.family == "monitor" else f'mysql_info{{host="{target}"}} 1'
        return CollectOutcome(status=CollectOutcomeStatus.SUCCESS, value=value)


class ClosableRecordingPlugin(RecordingPlugin):
    def __init__(self):
        super().__init__()
        self.prepare_calls = 0
        self.prepared = False
        self.close_calls = 0

    async def prepare(self, request):
        assert request.targets == ("10.10.24.1", "10.10.24.2")
        self.prepare_calls += 1
        self.prepared = True

    async def collect(self, target, credential, context):
        assert self.prepared
        return await super().collect(target, credential, context)

    async def close(self):
        self.close_calls += 1


class FailingClosePlugin(ClosableRecordingPlugin):
    def __init__(self, secret):
        super().__init__()
        self.secret = secret

    async def close(self):
        self.close_calls += 1
        raise RuntimeError("password=" + self.secret)


class PluginFactory:
    def __init__(self, plugin):
        self.plugin = plugin

    def resolve(self, request):
        return self.plugin


class CredentialProbePlugin:
    def __init__(self):
        self.collected_credentials = []

    async def probe(self, target, credential, context, *, timeout_seconds):
        if credential["credential_id"] == "credential-bad":
            return AccessProbeResult(
                status=AccessProbeStatus.AUTH_FAILED,
                error_code="authentication_failed",
            )
        return AccessProbeResult(status=AccessProbeStatus.READY)

    async def collect(self, target, credential, context):
        if credential["credential_id"] != "credential-good":
            raise AssertionError("unverified credential reached collection")
        self.collected_credentials.append((target, credential["credential_id"]))
        return CollectOutcome(
            status=CollectOutcomeStatus.SUCCESS,
            value=f'mysql_info{{host="{target}"}} 1',
        )


class TimeoutSnmpPlugin:
    """模拟无响应 SNMP 设备；community 只校验、不记录。"""

    def __init__(self, expected_community):
        self.expected_community = expected_community
        self.active = 0
        self.peak = 0
        self.calls = 0
        self.credential_mismatches = 0

    async def collect(self, target, credential, context):
        self.calls += 1
        if not (
            credential.get("version") == "v2"
            and credential.get("community") == self.expected_community
            and int(credential.get("snmp_port") or 0) == 161
        ):
            self.credential_mismatches += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            # 必须超过运行时的 5 秒上限，由 asyncio.timeout 取消等待。
            await asyncio.sleep(60)
        finally:
            self.active -= 1


class TimeoutHostPlugin:
    """模拟主机 SSH/Job CredentialAttempt：校验 mock 凭据后打满外层采集超时。"""

    supports_access_probe = False

    def __init__(self, *, expected_username: str, expected_password: str):
        self.expected_username = expected_username
        self.expected_password = expected_password
        self.active = 0
        self.peak = 0
        self.calls = 0
        self.credential_mismatches = 0

    async def collect(self, target, credential, context):
        self.calls += 1
        if not (
            str(credential.get("username") or "") == self.expected_username
            and str(credential.get("password") or "") == self.expected_password
            and int(credential.get("port") or 22) == 22
        ):
            self.credential_mismatches += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            # 必须超过运行时的 5 秒上限，由 asyncio.timeout 取消等待。
            await asyncio.sleep(60)
        finally:
            self.active -= 1


class MixedRealSnmpPlugin:
    """只对显式授权目标调用真实 SNMP，其余目标模拟 5 秒无响应。"""

    def __init__(self, real_targets):
        from plugins.inputs.network.snmp_facts import SnmpFacts

        self.real_targets = {str(item["host"]): dict(item) for item in real_targets}
        self.snmp_factory = SnmpFacts
        self.active = 0
        self.peak = 0
        self.calls = 0
        self.mock_calls = 0
        self.credential_mismatches = 0
        self.real_results = {}

    async def collect(self, target, credential, context):
        self.calls += 1
        expected = self.real_targets.get(target)
        if expected is None:
            self.mock_calls += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                await asyncio.sleep(5)
            finally:
                self.active -= 1
            return CollectOutcome(
                status=CollectOutcomeStatus.FAILED,
                error_code="mock_snmp_timeout",
            )

        if str(credential.get("target_host") or "") != target:
            self.credential_mismatches += 1
            return CollectOutcome(status=CollectOutcomeStatus.RETRY_CREDENTIAL)

        self.active += 1
        self.peak = max(self.peak, self.active)
        started = time.monotonic()
        params = {
            key: credential[key]
            for key in (
                "version",
                "community",
                "snmp_port",
                "timeout",
                "retries",
            )
            if key in credential
        }
        params["host"] = target
        try:
            response = await self.snmp_factory(params).list_all_resources()
        finally:
            self.active -= 1
        payload = response.get("result") or {}
        succeeded = response.get("success") is True
        self.real_results[target] = {
            "success": succeeded,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "system_records": len(payload.get("network_system") or []),
            "interface_records": len(payload.get("network_interfaces") or []),
            "error_code": "" if succeeded else "snmp_collection_failed",
        }
        return CollectOutcome(
            status=(CollectOutcomeStatus.SUCCESS if succeeded else CollectOutcomeStatus.FAILED),
            value=("snmp_collection_success 1\n" if succeeded else None),
            error_code="" if succeeded else "real_snmp_failed",
        )


def _max_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def build_application(redis_client, plugin, published, scheduled, *, fail_once=False):
    attempts = {"count": 0}

    async def publish_metrics(ctx, value, params, task_id):
        attempts["count"] += 1
        if fail_once and attempts["count"] == 1:
            error = ConnectionError("NATS unavailable before publish")
            error.delivery_detected = False
            raise error
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
            network_topology_max_active_targets=1,
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


class FixedFiveSecondPlanResolver:
    def resolve(self, _request):
        return ExecutionPlan(
            preflight_timeout_seconds=15,
            probe_timeout_seconds=15,
            collection_timeout_seconds=5,
            publish_timeout_seconds=30,
            execution_mode="async",
            capacity_group="default",
        )


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
async def test_configuration_http_to_redis_plugin_nats_and_next_cycle_resubmit(redis_client, monkeypatch):
    published = []
    scheduled = []
    plugin = RecordingPlugin(rotate_credentials=True)
    application, preflight = build_application(redis_client, plugin, published, scheduled)
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: application)

    async with http_client(collect_api.collect_router, "e2e-config-app") as client:
        accepted = await client.get(
            "/collect/collect_info",
            headers=configuration_request("e2e-config"),
        )
        await scheduled[0]
        next_cycle = await client.get(
            "/collect/collect_info",
            headers=configuration_request("e2e-config"),
        )

    assert accepted.status_code == 202
    assert accepted.headers["x-task-status"] == "accepted"
    assert next_cycle.status_code == 202
    assert next_cycle.headers["x-task-status"] == "accepted"
    assert len(scheduled) == 2
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
    await scheduled[1]


@pytest.mark.asyncio
async def test_collection_run_closes_run_scoped_plugin(redis_client, monkeypatch):
    published = []
    scheduled = []
    plugin = ClosableRecordingPlugin()
    application, _preflight = build_application(redis_client, plugin, published, scheduled)
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: application)

    async with http_client(collect_api.collect_router, "e2e-plugin-close-app") as client:
        accepted = await client.get(
            "/collect/collect_info",
            headers=configuration_request("e2e-plugin-close"),
        )
        await scheduled[0]

    assert accepted.status_code == 202
    assert plugin.prepare_calls == 1
    assert plugin.close_calls == 1


@pytest.mark.asyncio
async def test_plugin_close_failure_keeps_run_result_and_logs_safe_traceback(redis_client, monkeypatch):
    published = []
    scheduled = []
    log_calls = []
    plugin = FailingClosePlugin("plugin-close-secret-sentinel")
    application, _preflight = build_application(redis_client, plugin, published, scheduled)
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: application)
    monkeypatch.setattr(
        "core.collection.application.logger.exception",
        lambda message, *args, **kwargs: log_calls.append((message, args, kwargs)),
    )

    async with http_client(collect_api.collect_router, "e2e-plugin-close-failure-app") as client:
        accepted = await client.get(
            "/collect/collect_info",
            headers=configuration_request("e2e-plugin-close-failure"),
        )
        await scheduled[0]

    assert accepted.status_code == 202
    assert plugin.close_calls == 1
    assert len(log_calls) == 1
    message, args, kwargs = log_calls[0]
    formatted = (message % args) + "\n" + "".join(traceback.format_exception(*kwargs["exc_info"]))
    assert "failed_stage=plugin_close" in formatted
    assert "error_type=PluginCloseFailure" in formatted
    assert "test_collection_end_to_end.py" in formatted
    assert "in close" in formatted
    assert "plugin-close-secret-sentinel" not in formatted


@pytest.mark.asyncio
async def test_http_chain_uses_credential_protocol_probe_before_collection(redis_client, monkeypatch):
    published = []
    scheduled = []
    plugin = CredentialProbePlugin()
    application, _preflight = build_application(redis_client, plugin, published, scheduled)
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: application)
    headers = configuration_request("e2e-credential-probe")
    headers["cmdbip_precheck"] = "true"

    async with http_client(collect_api.collect_router, "e2e-credential-probe-app") as client:
        accepted = await client.get(
            "/collect/collect_info",
            headers=headers,
        )
        await scheduled[0]

    assert accepted.status_code == 202
    assert plugin.collected_credentials == [
        ("10.10.24.1", "credential-good"),
        ("10.10.24.2", "credential-good"),
    ]
    assert len(published) == 2
    assert all(entry[2]["collection_fence"] == 1 for entry in published)
    assert all(len(entry[2]["collection_result_id"]) == 64 for entry in published)
    assert "do-not-log" not in str(published)


@pytest.mark.asyncio
async def test_publish_transient_failure_retries_once_without_recollecting(redis_client, monkeypatch):
    published = []
    scheduled = []
    plugin = RecordingPlugin()
    application, preflight = build_application(redis_client, plugin, published, scheduled, fail_once=True)
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: application)
    headers = {
        "x-task-id": "e2e-publish-retry",
        "cmdbmodel_id": "mysql",
        "cmdbhosts": "10.10.24.9",
        "cmdbcredential_id": "credential-good",
    }

    async with http_client(collect_api.collect_router, "e2e-publish-retry-app") as client:
        first = await client.get("/collect/collect_info", headers=headers)
        await scheduled[0]
        next_cycle = await client.get("/collect/collect_info", headers=headers)

    assert first.status_code == 202
    assert next_cycle.status_code == 202
    assert preflight.targets == ["10.10.24.9"]
    assert plugin.calls == [("10.10.24.9", "credential-good", 1)]
    assert len(published) == 1
    await scheduled[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route_name", "path"),
    [
        ("vmware", "/monitor/vmware/metrics"),
        ("qcloud", "/monitor/qcloud/metrics"),
        ("oceanstor", "/monitor/oceanstor/metrics"),
        ("windows-wmi", "/monitor/windows/wmi/metrics"),
        ("host", "/monitor/host/metrics"),
    ],
)
async def test_monitor_auth_enforce_rejects_every_route_before_submit(
    monkeypatch,
    route_name,
    path,
):
    monkeypatch.setenv("STARGAZER_MONITOR_AUTH_MODE", "enforce")
    monkeypatch.setenv("STARGAZER_MONITOR_AUTH_TOKEN", "current-token")

    def fail_if_runtime_is_requested():
        pytest.fail("unauthenticated request reached collection runtime")

    monkeypatch.setattr(
        monitor_api,
        "get_collection_application",
        fail_if_runtime_is_requested,
    )

    async with http_client(
        monitor_api.monitor_router,
        f"e2e-monitor-auth-{route_name}-app",
    ) as client:
        rejected = await client.get(path)

    assert rejected.status_code == 401
    assert rejected.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_monitor_auth_enforce_does_not_affect_other_blueprints(
    redis_client,
    monkeypatch,
):
    published = []
    scheduled = []
    application, _preflight = build_application(
        redis_client,
        RecordingPlugin(),
        published,
        scheduled,
    )
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: application)
    monkeypatch.setenv("STARGAZER_MONITOR_AUTH_MODE", "enforce")
    monkeypatch.setenv("STARGAZER_MONITOR_AUTH_TOKEN", "current-token")
    app = Sanic("e2e-monitor-auth-blueprint-scope-app")
    app.config.AUTO_EXTEND = False
    app.config.TOUCHUP = False
    app.blueprint(
        [
            monitor_api.monitor_router,
            collect_api.collect_router,
            health_api.health_router,
        ]
    )
    app.asgi = True
    await app._startup()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://stargazer.test",
    ) as client:
        assert (await client.get("/monitor/host/metrics")).status_code == 401
        assert (await client.get("/health/")).status_code == 200
        accepted = await client.get(
            "/collect/collect_info",
            headers=configuration_request("e2e-auth-blueprint-scope"),
        )

    assert accepted.status_code == 202
    assert len(scheduled) == 1
    await scheduled[0]


@pytest.mark.asyncio
async def test_monitor_http_uses_the_same_runtime_and_result_pipeline(redis_client, monkeypatch):
    published = []
    scheduled = []
    plugin = RecordingPlugin(family="monitor")
    application, preflight = build_application(redis_client, plugin, published, scheduled)
    monkeypatch.setattr(monitor_api, "get_collection_application", lambda: application)
    monkeypatch.delenv("STARGAZER_MONITOR_AUTH_MODE", raising=False)
    monkeypatch.delenv("STARGAZER_MONITOR_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("STARGAZER_MONITOR_AUTH_PREVIOUS_TOKEN", raising=False)
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
        accepted = await client.get("/monitor/vmware/metrics?minutes=5", headers=headers)
        await scheduled[0]
        monkeypatch.setenv("STARGAZER_MONITOR_AUTH_MODE", "enforce")
        monkeypatch.setenv("STARGAZER_MONITOR_AUTH_TOKEN", "current-token")
        next_cycle = await client.get(
            "/monitor/vmware/metrics?minutes=5",
            headers={**headers, "Authorization": "Bearer current-token"},
        )

    assert accepted.status_code == 202
    assert next_cycle.status_code == 202
    assert next_cycle.headers["x-task-status"] == "accepted"
    assert preflight.targets == ["10.10.24.20"]
    assert plugin.calls == [("10.10.24.20", "credential-1", 1)]
    assert len(published) == 1
    assert published[0][2]["plugin_family"] == "monitor"
    assert "do-not-log-monitor" not in str(published)
    await scheduled[1]


@pytest.mark.asyncio
async def test_snmp_256_target_timeout_load_through_http_redis_runtime_and_nats(redis_client, monkeypatch):
    """最坏情况：256 个 SNMP 目标全部在 5 秒超时，验证两批有界执行。"""
    target_prefix = os.getenv("STARGAZER_SNMP_TEST_PREFIX", "10.10.69")
    community = os.getenv("STARGAZER_SNMP_TEST_COMMUNITY", "mock-snmp-community")
    targets = tuple(f"{target_prefix}.{index}" for index in range(256))
    plugin = TimeoutSnmpPlugin(community)
    published = 0

    async def publish_metrics(_ctx, _value, _params, _task_id):
        nonlocal published
        published += 1

    app = Sanic("e2e-snmp-load-app")
    app.config.AUTO_EXTEND = False
    app.config.TOUCHUP = False
    app.blueprint(collect_api.collect_router)
    app.asgi = True
    await app._startup()
    application = CollectionApplication(
        redis_client=redis_client,
        schedule=app.add_task,
        owner_id="pod-snmp-load",
        settings=CollectionApplicationSettings(
            max_active_runs=1,
            max_active_targets=200,
            target_task_window=200,
            connect_timeout_seconds=5,
            plugin_timeout_seconds=5,
            lease_ttl_seconds=30,
            lease_heartbeat_seconds=1,
            shutdown_grace_seconds=1,
            run_deadline_seconds=20,
        ),
        plugin_factory=PluginFactory(plugin),
        publisher=NatsResultPublisher(metrics_publish=publish_metrics),
        execution_plan_resolver=FixedFiveSecondPlanResolver(),
    )
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: application)

    stop_monitor = asyncio.Event()
    lag_samples = []
    peak_tasks = 0

    async def monitor_loop():
        nonlocal peak_tasks
        interval = 0.01
        expected = time.monotonic() + interval
        while not stop_monitor.is_set():
            await asyncio.sleep(interval)
            now = time.monotonic()
            lag_samples.append(max(0.0, now - expected))
            expected = now + interval
            peak_tasks = max(peak_tasks, len(asyncio.all_tasks()))

    monitor_task = asyncio.create_task(monitor_loop())
    tracing_was_active = tracemalloc.is_tracing()
    if not tracing_was_active:
        tracemalloc.start()
    tracemalloc.reset_peak()
    rss_before = _max_rss_bytes()
    redis_memory_before = await redis_client.info("memory")
    cpu_started = time.process_time()
    wall_started = time.monotonic()
    headers = {
        "x-task-id": "e2e-snmp-256-timeout",
        "cmdbmodel_id": "network",
        "cmdbexecutor_type": "protocol",
        "cmdbhosts": ",".join(targets),
        "cmdbcredential_count": "1",
        "cmdbcredential_0_credential_id": "snmp-v2-mock",
        "cmdbcredential_0_version": "v2",
        "cmdbcredential_0_community": community,
        "cmdbcredential_0_snmp_port": "161",
    }

    finished = False
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://stargazer.test",
        ) as client:
            accepted = await client.get("/collect/collect_info", headers=headers)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                stats = await application.stats()
                if stats["active_runs"] == 0 and published == 256:
                    finished = True
                    break
                await asyncio.sleep(0.25)
    finally:
        wall_seconds = time.monotonic() - wall_started
        cpu_seconds = time.process_time() - cpu_started
        _current_bytes, python_peak_bytes = tracemalloc.get_traced_memory()
        if not tracing_was_active:
            tracemalloc.stop()
        stop_monitor.set()
        await monitor_task
        await application.shutdown()

    assert accepted.status_code == 202
    assert accepted.headers["x-target-count"] == "256"
    assert finished is True
    assert plugin.calls == 256
    assert plugin.credential_mismatches == 0
    assert plugin.peak == 200
    assert published == 256
    assert 9.5 <= wall_seconds < 20
    assert max(lag_samples, default=0) < 0.2

    redis_memory = await redis_client.info("memory")
    stats = await application.stats()
    assert stats["active_runs"] == 0
    assert stats["active_targets"] == 0
    assert stats["target_worker_tasks"] == 0
    report = {
        "targets": 256,
        "credentials": 1,
        "snmp_version": "v2",
        "snmp_port": 161,
        "community": "***",
        "timeout_seconds": 5,
        "target_concurrency": 200,
        "wall_seconds": round(wall_seconds, 3),
        "cpu_seconds": round(cpu_seconds, 3),
        "process_cpu_percent_of_one_core": round(cpu_seconds / wall_seconds * 100, 2),
        "process_max_rss_bytes": _max_rss_bytes(),
        "process_max_rss_delta_bytes": max(0, _max_rss_bytes() - rss_before),
        "python_traced_peak_bytes": python_peak_bytes,
        "redis_used_memory_bytes": int(redis_memory["used_memory"]),
        "redis_used_memory_delta_bytes": max(
            0,
            int(redis_memory["used_memory"]) - int(redis_memory_before["used_memory"]),
        ),
        "redis_used_memory_peak_bytes": int(redis_memory["used_memory_peak"]),
        "peak_asyncio_tasks": peak_tasks,
        "peak_plugin_io": plugin.peak,
        "event_loop_lag_max_seconds": round(max(lag_samples, default=0), 6),
        "event_loop_lag_samples": len(lag_samples),
        "published_results": published,
        "plugin_timeout_total": int(stats["plugin_timeout_total"]),
        "active_runs_after_completion": stats["active_runs"],
        "active_targets_after_completion": stats["active_targets"],
        "target_worker_tasks_after_completion": stats["target_worker_tasks"],
        "expected_failed_targets": 256,
        "expected_succeeded_targets": 0,
    }
    print("SNMP_E2E_LOAD_RESULT=" + json.dumps(report, sort_keys=True))


@pytest.mark.asyncio
async def test_host_150_target_timeout_load_through_http_redis_runtime_and_nats(redis_client, monkeypatch):
    """主机采集压测：10.10.41.0–149（150）全部 mock 凭据，外层 5s 超时。"""
    target_prefix = os.getenv("STARGAZER_HOST_TEST_PREFIX", "10.10.41")
    username = os.getenv("STARGAZER_HOST_TEST_USERNAME", "mock-host-user")
    password = os.getenv("STARGAZER_HOST_TEST_PASSWORD", "mock-host-secret")
    target_count = int(os.getenv("STARGAZER_HOST_TEST_COUNT", "150"))
    targets = tuple(f"{target_prefix}.{index}" for index in range(target_count))
    plugin = TimeoutHostPlugin(expected_username=username, expected_password=password)
    published = 0

    async def publish_metrics(_ctx, _value, _params, _task_id):
        nonlocal published
        published += 1

    app = Sanic("e2e-host-load-app")
    app.config.AUTO_EXTEND = False
    app.config.TOUCHUP = False
    app.blueprint(collect_api.collect_router)
    app.asgi = True
    await app._startup()
    application = CollectionApplication(
        redis_client=redis_client,
        schedule=app.add_task,
        owner_id="pod-host-load",
        settings=CollectionApplicationSettings(
            max_active_runs=1,
            max_active_targets=200,
            target_task_window=200,
            connect_timeout_seconds=5,
            plugin_timeout_seconds=5,
            lease_ttl_seconds=30,
            lease_heartbeat_seconds=1,
            shutdown_grace_seconds=1,
            run_deadline_seconds=20,
        ),
        plugin_factory=PluginFactory(plugin),
        # 压测聚焦 CredentialAttempt/有界并发；不把本机 NATS Responder 可用性算进结果
        preflight=ReachablePreflight(),
        publisher=NatsResultPublisher(metrics_publish=publish_metrics),
        execution_plan_resolver=FixedFiveSecondPlanResolver(),
    )
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: application)

    stop_monitor = asyncio.Event()
    lag_samples = []
    peak_tasks = 0

    async def monitor_loop():
        nonlocal peak_tasks
        interval = 0.01
        expected = time.monotonic() + interval
        while not stop_monitor.is_set():
            await asyncio.sleep(interval)
            now = time.monotonic()
            lag_samples.append(max(0.0, now - expected))
            expected = now + interval
            peak_tasks = max(peak_tasks, len(asyncio.all_tasks()))

    monitor_task = asyncio.create_task(monitor_loop())
    tracing_was_active = tracemalloc.is_tracing()
    if not tracing_was_active:
        tracemalloc.start()
    tracemalloc.reset_peak()
    rss_before = _max_rss_bytes()
    redis_memory_before = await redis_client.info("memory")
    cpu_started = time.process_time()
    wall_started = time.monotonic()
    headers = {
        "x-task-id": "e2e-host-150-timeout",
        "cmdbmodel_id": "host",
        "cmdbexecutor_type": "job",
        "cmdbhosts": ",".join(targets),
        "cmdbcredential_count": "1",
        "cmdbcredential_0_credential_id": "host-ssh-mock",
        "cmdbcredential_0_username": username,
        "cmdbcredential_0_password": password,
        "cmdbcredential_0_port": "22",
    }

    finished = False
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://stargazer.test",
        ) as client:
            accepted = await client.get("/collect/collect_info", headers=headers)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                stats = await application.stats()
                if stats["active_runs"] == 0 and published == target_count:
                    finished = True
                    break
                await asyncio.sleep(0.25)
    finally:
        wall_seconds = time.monotonic() - wall_started
        cpu_seconds = time.process_time() - cpu_started
        _current_bytes, python_peak_bytes = tracemalloc.get_traced_memory()
        if not tracing_was_active:
            tracemalloc.stop()
        stop_monitor.set()
        await monitor_task
        await application.shutdown()

    assert accepted.status_code == 202
    assert accepted.headers["x-target-count"] == str(target_count)
    assert finished is True
    assert plugin.calls == target_count
    assert plugin.credential_mismatches == 0
    assert plugin.peak == min(target_count, 200)
    assert published == target_count
    assert 4.5 <= wall_seconds < 15
    assert max(lag_samples, default=0) < 0.2

    redis_memory = await redis_client.info("memory")
    stats = await application.stats()
    assert stats["active_runs"] == 0
    assert stats["active_targets"] == 0
    assert stats["target_worker_tasks"] == 0
    sorted_lag_samples = sorted(lag_samples)

    def lag_percentile(fraction):
        if not sorted_lag_samples:
            return 0
        index = round((len(sorted_lag_samples) - 1) * fraction)
        return sorted_lag_samples[index]

    report = {
        "targets": target_count,
        "target_range": f"{target_prefix}.0-{target_count - 1}",
        "credentials": 1,
        "protocol": "host-ssh-job-mock",
        "username": "***",
        "password": "***",
        "port": 22,
        "timeout_seconds": 5,
        "target_concurrency": 200,
        "wall_seconds": round(wall_seconds, 3),
        "cpu_seconds": round(cpu_seconds, 3),
        "process_cpu_percent_of_one_core": round(cpu_seconds / wall_seconds * 100, 2),
        "process_max_rss_bytes": _max_rss_bytes(),
        "process_max_rss_delta_bytes": max(0, _max_rss_bytes() - rss_before),
        "python_traced_peak_bytes": python_peak_bytes,
        "redis_used_memory_bytes": int(redis_memory["used_memory"]),
        "redis_used_memory_delta_bytes": max(
            0,
            int(redis_memory["used_memory"]) - int(redis_memory_before["used_memory"]),
        ),
        "redis_used_memory_peak_bytes": int(redis_memory["used_memory_peak"]),
        "peak_asyncio_tasks": peak_tasks,
        "peak_plugin_io": plugin.peak,
        "event_loop_lag_max_seconds": round(max(lag_samples, default=0), 6),
        "event_loop_lag_p95_seconds": round(lag_percentile(0.95), 6),
        "event_loop_lag_p99_seconds": round(lag_percentile(0.99), 6),
        "event_loop_lag_samples": len(lag_samples),
        "published_results": published,
        "plugin_timeout_total": int(stats["plugin_timeout_total"]),
        "credential_mismatch_attempts": plugin.credential_mismatches,
        "active_runs_after_completion": stats["active_runs"],
        "active_targets_after_completion": stats["active_targets"],
        "target_worker_tasks_after_completion": stats["target_worker_tasks"],
        "expected_failed_targets": target_count,
        "expected_succeeded_targets": 0,
    }
    print("HOST_E2E_LOAD_RESULT=" + json.dumps(report, sort_keys=True))


@pytest.mark.asyncio
async def test_snmp_mixed_real_targets_and_mock_subnet_through_full_runtime(redis_client, monkeypatch):
    raw_real_targets = os.getenv("STARGAZER_SNMP_REAL_TARGETS_JSON", "")
    if not raw_real_targets:
        pytest.skip("STARGAZER_SNMP_REAL_TARGETS_JSON is not configured")
    real_targets = json.loads(raw_real_targets)
    target_prefix = os.getenv("STARGAZER_SNMP_TEST_PREFIX", "192.0.2")
    targets = tuple(f"{target_prefix}.{index}" for index in range(256))
    assert {str(item["host"]) for item in real_targets}.issubset(targets)
    plugin = MixedRealSnmpPlugin(real_targets)
    published = 0

    async def publish_metrics(_ctx, _value, _params, _task_id):
        nonlocal published
        published += 1

    app = Sanic("e2e-snmp-mixed-load-app")
    app.config.AUTO_EXTEND = False
    app.config.TOUCHUP = False
    app.blueprint(collect_api.collect_router)
    app.asgi = True
    await app._startup()
    application = CollectionApplication(
        redis_client=redis_client,
        schedule=app.add_task,
        owner_id="pod-snmp-mixed-load",
        settings=CollectionApplicationSettings(
            max_active_runs=1,
            max_active_targets=200,
            target_task_window=200,
            connect_timeout_seconds=5,
            # 允许真实目标保留 timeout=20/retries=3；外层只作安全兜底。
            plugin_timeout_seconds=30,
            lease_ttl_seconds=60,
            lease_heartbeat_seconds=1,
            shutdown_grace_seconds=1,
            run_deadline_seconds=40,
        ),
        plugin_factory=PluginFactory(plugin),
        publisher=NatsResultPublisher(metrics_publish=publish_metrics),
    )
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: application)

    stop_monitor = asyncio.Event()
    lag_samples = []
    peak_tasks = 0

    async def monitor_loop():
        nonlocal peak_tasks
        interval = 0.01
        expected = time.monotonic() + interval
        while not stop_monitor.is_set():
            await asyncio.sleep(interval)
            now = time.monotonic()
            lag_samples.append(max(0.0, now - expected))
            expected = now + interval
            peak_tasks = max(peak_tasks, len(asyncio.all_tasks()))

    monitor_task = asyncio.create_task(monitor_loop())
    tracing_was_active = tracemalloc.is_tracing()
    if not tracing_was_active:
        tracemalloc.start()
    tracemalloc.reset_peak()
    rss_before = _max_rss_bytes()
    redis_memory_before = await redis_client.info("memory")
    cpu_started = time.process_time()
    wall_started = time.monotonic()
    headers = {
        "x-task-id": "e2e-snmp-256-mixed-real",
        "cmdbmodel_id": "network",
        "cmdbexecutor_type": "protocol",
        "cmdbhosts": ",".join(targets),
        "cmdbcredential_count": str(len(real_targets) + 1),
    }
    for index, credential in enumerate(real_targets):
        headers.update(
            {
                f"cmdbcredential_{index}_credential_id": f"snmp-real-{index + 1}",
                f"cmdbcredential_{index}_target_host": str(credential["host"]),
                f"cmdbcredential_{index}_version": str(credential["version"]),
                f"cmdbcredential_{index}_community": str(credential["community"]),
                f"cmdbcredential_{index}_snmp_port": str(credential["snmp_port"]),
            }
        )
        if "timeout" in credential:
            headers[f"cmdbcredential_{index}_timeout"] = str(credential["timeout"])
        if "retries" in credential:
            headers[f"cmdbcredential_{index}_retries"] = str(credential["retries"])
    mock_index = len(real_targets)
    headers.update(
        {
            f"cmdbcredential_{mock_index}_credential_id": "snmp-mock-shared",
            f"cmdbcredential_{mock_index}_version": "v2",
            f"cmdbcredential_{mock_index}_community": "mock-only",
            f"cmdbcredential_{mock_index}_snmp_port": "161",
        }
    )

    finished = False
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://stargazer.test",
        ) as client:
            accepted = await client.get("/collect/collect_info", headers=headers)
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                stats = await application.stats()
                if stats["active_runs"] == 0 and published == 256:
                    finished = True
                    break
                await asyncio.sleep(0.25)
    finally:
        wall_seconds = time.monotonic() - wall_started
        cpu_seconds = time.process_time() - cpu_started
        _current_bytes, python_peak_bytes = tracemalloc.get_traced_memory()
        if not tracing_was_active:
            tracemalloc.stop()
        stop_monitor.set()
        await monitor_task
        await application.shutdown()

    assert accepted.status_code == 202
    assert accepted.headers["x-target-count"] == "256"
    assert finished is True
    assert plugin.mock_calls == 252
    assert set(plugin.real_results) == {str(item["host"]) for item in real_targets}
    assert plugin.peak == 200
    assert published == 256

    redis_memory = await redis_client.info("memory")
    stats = await application.stats()
    assert stats["active_runs"] == 0
    assert stats["active_targets"] == 0
    assert stats["target_worker_tasks"] == 0
    sorted_lag_samples = sorted(lag_samples)

    def lag_percentile(fraction):
        if not sorted_lag_samples:
            return 0
        index = round((len(sorted_lag_samples) - 1) * fraction)
        return sorted_lag_samples[index]

    report = {
        "targets": 256,
        "real_targets": len(real_targets),
        "mock_targets": 252,
        "credentials": len(real_targets),
        "communities": "***",
        "mock_timeout_seconds": 5,
        "runtime_safety_timeout_seconds": 30,
        "target_concurrency": 200,
        "wall_seconds": round(wall_seconds, 3),
        "cpu_seconds": round(cpu_seconds, 3),
        "process_cpu_percent_of_one_core": round(cpu_seconds / wall_seconds * 100, 2),
        "process_max_rss_bytes": _max_rss_bytes(),
        "process_max_rss_delta_bytes": max(0, _max_rss_bytes() - rss_before),
        "python_traced_peak_bytes": python_peak_bytes,
        "redis_used_memory_bytes": int(redis_memory["used_memory"]),
        "redis_used_memory_delta_bytes": max(
            0,
            int(redis_memory["used_memory"]) - int(redis_memory_before["used_memory"]),
        ),
        "redis_used_memory_peak_bytes": int(redis_memory["used_memory_peak"]),
        "peak_asyncio_tasks": peak_tasks,
        "peak_plugin_io": plugin.peak,
        "event_loop_lag_max_seconds": round(max(lag_samples, default=0), 6),
        "event_loop_lag_p95_seconds": round(lag_percentile(0.95), 6),
        "event_loop_lag_p99_seconds": round(lag_percentile(0.99), 6),
        "event_loop_lag_samples": len(lag_samples),
        "published_results": published,
        "credential_mismatch_attempts": plugin.credential_mismatches,
        "real_results": plugin.real_results,
        "active_runs_after_completion": stats["active_runs"],
        "active_targets_after_completion": stats["active_targets"],
        "target_worker_tasks_after_completion": stats["target_worker_tasks"],
        "real_succeeded": sum(1 for item in plugin.real_results.values() if item.get("success")),
        "real_failed": sum(1 for item in plugin.real_results.values() if not item.get("success")),
        "mock_calls": plugin.mock_calls,
    }
    print("SNMP_MIXED_LOAD_RESULT=" + json.dumps(report, sort_keys=True))
    assert max(lag_samples, default=0) < 0.2
