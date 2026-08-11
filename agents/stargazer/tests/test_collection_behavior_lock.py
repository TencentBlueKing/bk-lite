"""锁定采集运行时公开契约与关键状态机行为，供后续重构对照。"""

from __future__ import annotations

import pytest

from core.collection.runtime import CollectionRequest, RunLease
from core.collection.contracts import (
    AccessProbeResult,
    AccessProbeStatus,
    CollectOutcome,
    CollectOutcomeStatus,
    PreflightResult,
    PreflightStatus,
    TargetExecutorSettings,
)
from core.collection.executor import (
    TargetCollectionExecutor,
)


class ReachablePreflight:
    async def check(self, target, request, *, timeout_seconds, plan=None):
        return PreflightResult(status=PreflightStatus.REACHABLE)


class RecordingPublisher:
    def __init__(self):
        self.results = []

    async def publish(self, request, result, lease):
        self.results.append(result)


class CollectPlugin:
    def __init__(self):
        self.calls = []

    async def collect(self, target, credential, context):
        self.calls.append(credential.get("credential_id"))
        return CollectOutcome(
            status=CollectOutcomeStatus.SUCCESS, value={"ok": True}
        )


class NotSupportedThenCollectProbe:
    async def probe(self, target, credential, context, *, timeout_seconds):
        return AccessProbeResult(status=AccessProbeStatus.NOT_SUPPORTED)


@pytest.mark.asyncio
async def test_not_supported_probe_still_runs_collect():
    """无廉价 probe 语义：NOT_SUPPORTED 不得跳过正式采集。"""
    plugin = CollectPlugin()
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=NotSupportedThenCollectProbe(),
        plugin=plugin,
        publisher=publisher,
        settings=TargetExecutorSettings(
            max_active_targets=1, target_task_window=1
        ),
    )
    request = CollectionRequest(
        task_id="lock-not-supported",
        plugin_ref="mysql.config",
        targets=("10.0.0.1",),
        credentials=({"credential_id": "c1"},),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.succeeded == 1
    assert plugin.calls == ["c1"]
    assert publisher.results[0].status == "success"


@pytest.mark.asyncio
async def test_no_access_probe_means_direct_collect():
    """access_probe=None 时 CredentialAttempt 直接 collect。"""
    plugin = CollectPlugin()
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=None,
        plugin=plugin,
        publisher=publisher,
        settings=TargetExecutorSettings(
            max_active_targets=1, target_task_window=1
        ),
    )
    request = CollectionRequest(
        task_id="lock-no-probe",
        plugin_ref="host.config",
        targets=("10.0.0.2",),
        credentials=({"credential_id": "c1"},),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.succeeded == 1
    assert plugin.calls == ["c1"]


def test_public_contract_enums_stable():
    """公开枚举取值稳定，搬迁到 collection_contracts 后不得漂移。"""
    assert PreflightStatus.REACHABLE.value == "reachable"
    assert PreflightStatus.UNREACHABLE.value == "unreachable"
    assert PreflightStatus.UNKNOWN.value == "unknown"
    assert AccessProbeStatus.NOT_SUPPORTED.value == "not_supported"
    assert AccessProbeStatus.READY.value == "ready"
    assert CollectOutcomeStatus.DEFERRED.value == "deferred"
    assert CollectOutcomeStatus.SUCCESS.value == "success"


def test_collection_result_id_is_stable_and_shared():
    from core.collection.contracts import build_collection_result_id

    first = build_collection_result_id(
        task_id="t1", plugin_ref="mysql.config", target="10.0.0.1", fence=3
    )
    second = build_collection_result_id(
        task_id="t1", plugin_ref="mysql.config", target="10.0.0.1", fence=3
    )
    other = build_collection_result_id(
        task_id="t1", plugin_ref="mysql.config", target="10.0.0.1", fence=4
    )
    assert first == second
    assert len(first) == 64
    assert first != other
    assert first.startswith(first[:24])  # host remote callback_task_id 前缀同源
