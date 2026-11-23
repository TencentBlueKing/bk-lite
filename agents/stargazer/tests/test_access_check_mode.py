"""连通性测试停在 probe，正式采集仍在 probe 通过后采集。"""

from __future__ import annotations

import time

import pytest
from core.collection.contracts import (
    AccessProbeResult,
    AccessProbeStatus,
    CollectOutcome,
    CollectOutcomeStatus,
    PreflightResult,
    PreflightStatus,
    TargetCollectionContext,
    TargetExecutorSettings,
)
from core.collection.credential_policy import CredentialPolicy, InMemoryCredentialStateStore
from core.collection.enums import FailureStage
from core.collection.execution_plan import ExecutionPlan
from core.collection.metrics import CollectionMetrics
from core.collection.plugins import ConfigurationCollectionPlugin
from core.collection.runtime import CollectionRequest, RunLease
from core.collection.target_attempt import TargetAttemptRunner


class _Preflight:
    def __init__(self, status):
        self.status = status
        self.calls = 0

    async def check(self, target, request, *, timeout_seconds):
        self.calls += 1
        return PreflightResult(
            status=self.status,
            error_code="tcp_connection_refused",
            failed_stage=FailureStage.IP_PRECHECK,
        )


class _Plugin:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.probes = []
        self.collects = []

    async def probe(self, target, credential, context, *, timeout_seconds):
        self.probes.append(credential["credential_id"])
        status = self.statuses.pop(0)
        return AccessProbeResult(status=status, error_code=status.value)

    async def collect(self, target, credential, context):
        self.collects.append(credential["credential_id"])
        return CollectOutcome(status=CollectOutcomeStatus.SUCCESS, value="inventory")


def _request(*, purpose, preflight_kind="tcp", model_id="mysql"):
    return CollectionRequest(
        task_id="task-1",
        plugin_ref="mysql.config",
        targets=("10.0.0.8",),
        credentials=(
            {"credential_id": "credential-1", "username": "one", "password": "secret-one"},
            {"credential_id": "credential-2", "username": "two", "password": "secret-two"},
        ),
        params={
            "run_purpose": purpose,
            "model_id": model_id,
            "preflight_kind": preflight_kind,
            "ip_precheck": True,
        },
    )


def _runner(preflight, plugin, store):
    return TargetAttemptRunner(
        preflight=preflight,
        access_probe=plugin,
        plugin=plugin,
        credential_policy=CredentialPolicy(store=store),
        settings=TargetExecutorSettings(),
        plan=ExecutionPlan(
            preflight_timeout_seconds=1,
            probe_timeout_seconds=1,
            collection_timeout_seconds=1,
            publish_timeout_seconds=1,
            execution_mode="sync",
            capacity_group="default",
        ),
        metrics=CollectionMetrics(),
    )


def _lease():
    return RunLease(
        task_id="task-1",
        request_digest="digest",
        owner_id="test",
        fence=1,
        expires_at=time.time() + 60,
    )


@pytest.mark.asyncio
async def test_access_check_stops_after_probe_and_keeps_testing_other_credentials():
    plugin = _Plugin([AccessProbeStatus.READY, AccessProbeStatus.AUTH_FAILED])
    store = InMemoryCredentialStateStore()
    runner = _runner(_Preflight(PreflightStatus.REACHABLE), plugin, store)

    result = await runner.run(_request(purpose="access_check"), "10.0.0.8", _lease())

    assert plugin.collects == []
    assert plugin.probes == ["credential-1", "credential-2"]
    assert [row.conclusion for row in result.access_rows] == ["credential_ok", "credential_rejected"]
    assert "secret-one" not in repr(result.access_rows)
    assert await store.get_failure(runner._credential_policy._scope(_request(purpose="access_check"), "10.0.0.8"), "credential-2") is None


@pytest.mark.asyncio
async def test_access_check_preflight_failure_does_not_call_probe():
    plugin = _Plugin([AccessProbeStatus.READY, AccessProbeStatus.READY])
    runner = _runner(_Preflight(PreflightStatus.UNREACHABLE), plugin, InMemoryCredentialStateStore())

    result = await runner.run(_request(purpose="access_check"), "10.0.0.8", _lease())

    assert plugin.probes == []
    assert plugin.collects == []
    assert [(row.credential_id, row.conclusion, row.attempted) for row in result.access_rows] == [
        ("credential-1", "network_unreachable", False),
        ("credential-2", "not_tested", False),
    ]


@pytest.mark.asyncio
async def test_access_check_without_probe_does_not_collect():
    plugin = _Plugin([AccessProbeStatus.NOT_SUPPORTED, AccessProbeStatus.NOT_SUPPORTED])
    runner = _runner(_Preflight(PreflightStatus.REACHABLE), plugin, InMemoryCredentialStateStore())

    result = await runner.run(_request(purpose="access_check"), "10.0.0.8", _lease())

    assert plugin.collects == []
    assert [row.conclusion for row in result.access_rows] == ["unsupported", "unsupported"]


@pytest.mark.asyncio
async def test_access_check_cloud_transport_failure_does_not_skip_the_next_credential():
    plugin = _Plugin([AccessProbeStatus.TARGET_UNREACHABLE, AccessProbeStatus.READY])
    runner = _runner(_Preflight(PreflightStatus.REACHABLE), plugin, InMemoryCredentialStateStore())

    result = await runner.run(
        _request(purpose="access_check", preflight_kind="cloud", model_id="qcloud"),
        "account",
        _lease(),
    )

    assert plugin.collects == []
    assert [row.conclusion for row in result.access_rows] == ["network_unreachable", "credential_ok"]


@pytest.mark.asyncio
async def test_configuration_plugin_probe_does_not_collect():
    calls = []

    class _Service:
        async def probe(self):
            calls.append("probe")
            return AccessProbeResult(status=AccessProbeStatus.READY)

        async def collect(self):
            calls.append("collect")

    plugin = ConfigurationCollectionPlugin(lambda _params: _Service())
    result = await plugin.probe(
        "10.0.0.8",
        {"credential_id": "credential-1"},
        TargetCollectionContext(
            task_id="task-1",
            plugin_ref="mysql.config",
            fence=1,
            params={"model_id": "mysql"},
        ),
        timeout_seconds=1,
    )

    assert result.status == AccessProbeStatus.READY
    assert calls == ["probe"]


@pytest.mark.asyncio
async def test_collect_mode_still_collects_after_ready_probe():
    plugin = _Plugin([AccessProbeStatus.READY])
    runner = _runner(_Preflight(PreflightStatus.REACHABLE), plugin, InMemoryCredentialStateStore())

    result = await runner.run(_request(purpose="collect"), "10.0.0.8", _lease())

    assert plugin.collects == ["credential-1"]
    assert result.status == "success"
    assert result.access_rows == ()
