import asyncio

import pytest

from core.collection.runtime import CollectionRequest, RunLease
from core.collection.metrics import CollectionMetrics
from core.collection.credential_policy import CredentialPolicy, InMemoryCredentialStateStore
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
    TargetWorkerBudget,
)


class UnreachablePreflight:
    async def check(self, target, request, *, timeout_seconds, plan=None):
        return PreflightResult(
            status=PreflightStatus.UNREACHABLE,
            error_code="tcp_connect_failed",
        )


class RecordingPlugin:
    def __init__(self):
        self.calls = []

    async def collect(self, target, credential, context):
        self.calls.append((target, credential, context))
        return CollectOutcome(status=CollectOutcomeStatus.SUCCESS, value={"ok": True})


class RecordingPublisher:
    def __init__(self):
        self.results = []

    async def publish(self, request, result, lease):
        self.results.append((request, result, lease))


class ReachablePreflight:
    async def check(self, target, request, *, timeout_seconds, plan=None):
        return PreflightResult(status=PreflightStatus.REACHABLE)


class CredentialProtocolProbe:
    async def probe(
        self, target, credential, context, *, timeout_seconds
    ):
        if credential["credential_id"] == "credential-1":
            return AccessProbeResult(
                status=AccessProbeStatus.AUTH_FAILED,
                error_code="authentication_failed",
            )
        return AccessProbeResult(status=AccessProbeStatus.READY)


class NoResponseThenReadyProbe:
    async def probe(
        self, target, credential, context, *, timeout_seconds
    ):
        if credential["credential_id"] == "credential-1":
            return AccessProbeResult(
                status=AccessProbeStatus.NO_RESPONSE,
                error_code="protocol_probe_no_response",
            )
        return AccessProbeResult(status=AccessProbeStatus.READY)


class AlwaysNoResponseProbe:
    async def probe(self, target, credential, context, *, timeout_seconds):
        return AccessProbeResult(
            status=AccessProbeStatus.NO_RESPONSE,
            error_code="protocol_no_response",
        )


class TargetUnreachableAccessProbe:
    async def probe(
        self, target, credential, context, *, timeout_seconds
    ):
        return AccessProbeResult(
            status=AccessProbeStatus.TARGET_UNREACHABLE,
            error_code="target_unreachable",
        )


class MustNotCollectPlugin:
    async def collect(self, target, credential, context):
        raise AssertionError("formal collection must not run")


class BrokenAccessProbe:
    async def probe(
        self, target, credential, context, *, timeout_seconds
    ):
        raise RuntimeError("secret-do-not-publish")


class TimeoutThenReadyAccessProbe:
    async def probe(
        self, target, credential, context, *, timeout_seconds
    ):
        if credential["credential_id"] == "credential-1":
            await asyncio.sleep(60)
        return AccessProbeResult(status=AccessProbeStatus.READY)


class FixedAccessProbe:
    def __init__(self, status, error_code):
        self.status = status
        self.error_code = error_code

    async def probe(
        self, target, credential, context, *, timeout_seconds
    ):
        return AccessProbeResult(
            status=self.status,
            error_code=self.error_code,
        )


class RejectsUnverifiedCredentialPlugin:
    async def collect(self, target, credential, context):
        if credential["credential_id"] != "credential-2":
            raise AssertionError("formal collection used an unverified credential")
        return CollectOutcome(
            status=CollectOutcomeStatus.SUCCESS,
            value={"version": "8.0"},
        )


class BrokenAccessProbe:
    async def probe(
        self, target, credential, context, *, timeout_seconds
    ):
        raise RuntimeError("secret-do-not-publish")


class TimeoutThenReadyAccessProbe:
    async def probe(
        self, target, credential, context, *, timeout_seconds
    ):
        if credential["credential_id"] == "credential-1":
            await asyncio.sleep(60)
        return AccessProbeResult(status=AccessProbeStatus.READY)


class FixedAccessProbe:
    def __init__(self, status, error_code):
        self.status = status
        self.error_code = error_code

    async def probe(
        self, target, credential, context, *, timeout_seconds
    ):
        return AccessProbeResult(
            status=self.status,
            error_code=self.error_code,
        )


class RejectsUnverifiedCredentialPlugin:
    async def collect(self, target, credential, context):
        if credential["credential_id"] != "credential-2":
            raise AssertionError("formal collection used an unverified credential")
        return CollectOutcome(
            status=CollectOutcomeStatus.SUCCESS,
            value={"version": "8.0"},
        )


class ScriptedPlugin:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def collect(self, target, credential, context):
        self.calls.append((target, credential["credential_id"]))
        return self.outcomes.pop(0)


@pytest.mark.asyncio
async def test_unreachable_target_is_filtered_before_any_credential_attempt():
    plugin = RecordingPlugin()
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=UnreachablePreflight(),
        plugin=plugin,
        publisher=publisher,
        settings=TargetExecutorSettings(
            max_active_targets=4,
            target_task_window=4,
            connect_timeout_seconds=5,
            plugin_timeout_seconds=60,
        ),
    )
    request = CollectionRequest(
        task_id="collect-unreachable",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=(
            {"credential_id": "credential-1"},
            {"credential_id": "credential-2"},
        ),
        params={"model_id": "mysql", "port": 3306},
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.total == 1
    assert summary.unreachable == 1
    assert summary.succeeded == 0
    assert plugin.calls == []
    assert len(publisher.results) == 1
    assert publisher.results[0][1].status == "unreachable"
    assert publisher.results[0][1].attempts == 0


@pytest.mark.asyncio
async def test_credentials_rotate_inside_target_and_success_gets_affinity():
    plugin = ScriptedPlugin(
        [
            CollectOutcome(
                status=CollectOutcomeStatus.AUTH_FAILED,
                error_code="unauthorized",
            ),
            CollectOutcome(
                status=CollectOutcomeStatus.SUCCESS,
                value={"version": "8.0"},
            ),
        ]
    )
    publisher = RecordingPublisher()
    credential_policy = CredentialPolicy(store=InMemoryCredentialStateStore())
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=plugin,
        publisher=publisher,
        credential_policy=credential_policy,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="collect-rotate",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=(
            {"credential_id": "credential-1"},
            {"credential_id": "credential-2"},
            {"credential_id": "credential-3"},
        ),
        params={"scope_id": "tenant-a", "credential_set_version": "v1"},
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.succeeded == 1
    assert plugin.calls == [
        ("10.10.24.1", "credential-1"),
        ("10.10.24.1", "credential-2"),
    ]
    assert publisher.results[0][1].credential_id == "credential-2"
    assert publisher.results[0][1].attempts == 2
    eligible = await credential_policy.eligible_credentials(
        request, "10.10.24.1"
    )
    assert [item["credential_id"] for item in eligible] == [
        "credential-2",
        "credential-3",
    ]


@pytest.mark.asyncio
async def test_credential_protocol_probe_runs_before_formal_collection():
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=CredentialProtocolProbe(),
        plugin=RejectsUnverifiedCredentialPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(
            max_active_targets=1,
            target_task_window=1,
            connect_timeout_seconds=5,
            plugin_timeout_seconds=60,
        ),
    )
    request = CollectionRequest(
        task_id="collect-after-credential-probe",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=(
            {"credential_id": "credential-1"},
            {"credential_id": "credential-2"},
        ),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.succeeded == 1
    assert publisher.results[0][1].credential_id == "credential-2"
    assert publisher.results[0][1].attempts == 2


@pytest.mark.asyncio
async def test_protocol_no_response_rotates_without_freezing_credential():
    publisher = RecordingPublisher()
    credential_policy = CredentialPolicy(store=InMemoryCredentialStateStore())
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=NoResponseThenReadyProbe(),
        plugin=RejectsUnverifiedCredentialPlugin(),
        publisher=publisher,
        credential_policy=credential_policy,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="collect-after-no-response",
        plugin_ref="snmp.config",
        targets=("10.10.24.1",),
        credentials=(
            {"credential_id": "credential-1"},
            {"credential_id": "credential-2"},
        ),
        params={"scope_id": "tenant-a", "credential_set_version": "v1"},
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)
    eligible = await credential_policy.eligible_credentials(
        request, "10.10.24.1"
    )

    assert summary.succeeded == 1
    assert [item["credential_id"] for item in eligible] == [
        "credential-2",
        "credential-1",
    ]


@pytest.mark.asyncio
async def test_protocol_no_response_stops_after_default_attempt_limit():
    publisher = RecordingPublisher()
    probe = AlwaysNoResponseProbe()
    plugin = RecordingPlugin()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=probe,
        plugin=plugin,
        publisher=publisher,
        settings=TargetExecutorSettings(
            max_active_targets=1,
            target_task_window=1,
            max_no_response_attempts=3,
        ),
    )
    request = CollectionRequest(
        task_id="collect-no-response-limit",
        plugin_ref="snmp.config",
        targets=("10.10.24.1",),
        credentials=tuple(
            {"credential_id": f"credential-{index}"} for index in range(1, 6)
        ),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.failed == 1
    assert publisher.results[0][1].attempts == 3
    assert publisher.results[0][1].error_code == "no_response_attempt_limit"
    assert plugin.calls == []


@pytest.mark.asyncio
async def test_access_probe_target_unreachable_stops_credential_rotation():
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=TargetUnreachableAccessProbe(),
        plugin=MustNotCollectPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="collect-protocol-unreachable",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=(
            {"credential_id": "credential-1"},
            {"credential_id": "credential-2"},
        ),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.unreachable == 1
    assert publisher.results[0][1].status == "unreachable"
    assert publisher.results[0][1].attempts == 1
    assert publisher.results[0][1].error_code == "target_unreachable"


@pytest.mark.asyncio
async def test_access_probe_failure_logs_target_and_credential_id(monkeypatch):
    logged = []

    def capture(message, *args):
        logged.append(message % args if args else message)

    monkeypatch.setattr(
        "core.collection.executor.logger.info", capture
    )
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=TargetUnreachableAccessProbe(),
        plugin=MustNotCollectPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="probe-log",
        plugin_ref="network.config",
        targets=("10.10.69.240",),
        credentials=({"credential_id": "cred-snmp-1", "community": "secret-community"},),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    await executor.execute(request, lease)

    assert any("event=target_unreachable" in item for item in logged)
    assert any("target=10.10.69.240" in item for item in logged)
    assert any("credential_id=cred-snmp-1" in item for item in logged)
    assert not any("secret-community" in item for item in logged)


@pytest.mark.asyncio
async def test_access_probe_exception_fails_only_current_target():
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=BrokenAccessProbe(),
        plugin=MustNotCollectPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="collect-broken-probe",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "credential-1"},),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.failed == 1
    assert publisher.results[0][1].error_code == "access_probe_error"
    assert "secret-do-not-publish" not in publisher.results[0][1].error_code


@pytest.mark.asyncio
async def test_access_probe_timeout_rotates_to_next_credential():
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=TimeoutThenReadyAccessProbe(),
        plugin=RejectsUnverifiedCredentialPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(
            max_active_targets=1,
            target_task_window=1,
            connect_timeout_seconds=0.01,
            plugin_timeout_seconds=1,
        ),
    )
    request = CollectionRequest(
        task_id="collect-probe-timeout",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=(
            {"credential_id": "credential-1"},
            {"credential_id": "credential-2"},
        ),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.succeeded == 1
    assert publisher.results[0][1].credential_id == "credential-2"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("probe_status", "error_code", "result_status"),
    [
        (AccessProbeStatus.SERVICE_UNAVAILABLE, "service_unavailable", "failed"),
        (
            AccessProbeStatus.TLS_VALIDATION_FAILED,
            "tls_validation_failed",
            "failed",
        ),
        (AccessProbeStatus.PROTOCOL_MISMATCH, "protocol_mismatch", "failed"),
        (AccessProbeStatus.MISCONFIGURED, "probe_misconfigured", "failed"),
        (AccessProbeStatus.RATE_LIMITED, "rate_limited", "deferred"),
    ],
)
async def test_target_scoped_access_probe_result_stops_credential_rotation(
    probe_status, error_code, result_status
):
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=FixedAccessProbe(probe_status, error_code),
        plugin=MustNotCollectPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id=f"collect-{error_code}",
        plugin_ref="http.config",
        targets=("api.example.test",),
        credentials=(
            {"credential_id": "credential-1"},
            {"credential_id": "credential-2"},
        ),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    await executor.execute(request, lease)

    result = publisher.results[0][1]
    assert result.status == result_status
    assert result.attempts == 1
    assert result.error_code == error_code


@pytest.mark.asyncio
async def test_capability_denied_probe_cools_credential_without_collecting():
    publisher = RecordingPublisher()
    credential_policy = CredentialPolicy(
        store=InMemoryCredentialStateStore(),
        jitter=lambda _start, _end: 0,
    )
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=FixedAccessProbe(
            AccessProbeStatus.CAPABILITY_DENIED,
            "capability_denied",
        ),
        plugin=MustNotCollectPlugin(),
        publisher=publisher,
        credential_policy=credential_policy,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="collect-capability-denied",
        plugin_ref="postgresql.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "credential-1"},),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.failed == 1
    assert publisher.results[0][1].error_code == "credentials_exhausted"
    assert await credential_policy.eligible_credentials(
        request, "10.10.24.1"
    ) == ()


@pytest.mark.asyncio
async def test_access_probe_metrics_are_exposed_by_collection_metrics():
    metrics = CollectionMetrics()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=CredentialProtocolProbe(),
        plugin=RejectsUnverifiedCredentialPlugin(),
        publisher=RecordingPublisher(),
        metrics=metrics,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="collect-probe-metrics",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "credential-2"},),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    await executor.execute(request, lease)

    snapshot = metrics.snapshot()
    assert snapshot["access_probe_total"] == 1
    assert snapshot["access_probe_duration_seconds_total"] >= 0


@pytest.mark.asyncio
async def test_target_without_matching_credential_has_stable_error():
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=MustNotCollectPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="collect-no-matching-credential",
        plugin_ref="network.config",
        targets=("10.10.69.245",),
        credentials=(
            {
                "credential_id": "credential-247",
                "target_host": "10.10.69.247",
            },
        ),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.failed == 1
    assert publisher.results[0][1].attempts == 0
    assert publisher.results[0][1].error_code == "no_matching_credential"


@pytest.mark.asyncio
async def test_without_access_probe_collect_is_the_credential_attempt():
    plugin = RecordingPlugin()
    publisher = RecordingPublisher()
    request = CollectionRequest(
        task_id="collect-no-probe",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "credential-1"},),
    )
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=None,
        plugin=plugin,
        publisher=publisher,
        settings=TargetExecutorSettings(
            max_active_targets=1, target_task_window=1
        ),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.succeeded == 1
    assert [call[0] for call in plugin.calls] == ["10.10.24.1"]
    assert publisher.results[0][1].status == "success"


@pytest.mark.asyncio
async def test_all_targets_are_collected_each_cycle():
    plugin = RecordingPlugin()
    publisher = RecordingPublisher()
    request = CollectionRequest(
        task_id="collect-resume",
        plugin_ref="mysql.config",
        targets=("10.10.24.1", "10.10.24.2"),
        credentials=({"credential_id": "credential-1"},),
    )
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=plugin,
        publisher=publisher,
        settings=TargetExecutorSettings(max_active_targets=2, target_task_window=2),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-b",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert [call[0] for call in plugin.calls] == ["10.10.24.1", "10.10.24.2"]
    assert [entry[1].target for entry in publisher.results] == [
        "10.10.24.1",
        "10.10.24.2",
    ]
    assert summary.total == 2
    assert summary.skipped == 0
    assert summary.succeeded == 2


@pytest.mark.asyncio
async def test_thin_lease_publishes_without_checkpoint_store():
    """薄租约不再接受 checkpoint_store；发布不依赖 fencing 拦截。"""
    plugin = RecordingPlugin()
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=plugin,
        publisher=publisher,
    )
    request = CollectionRequest(
        task_id="collect-stale",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "credential-1"},),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.succeeded == 1
    assert len(publisher.results) == 1


@pytest.mark.asyncio
async def test_publish_failure_retries_once_then_fails_without_recollect():
    plugin = RecordingPlugin()
    publish_calls = {"count": 0}

    class FailingPublisher:
        async def publish(self, request, result, lease):
            publish_calls["count"] += 1
            raise ConnectionError("nats unavailable")

    request = CollectionRequest(
        task_id="collect-publish-retry",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "c1"},),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=plugin,
        publisher=FailingPublisher(),
        settings=TargetExecutorSettings(
            max_active_targets=1,
            target_task_window=1,
            publish_max_attempts=2,
        ),
    )
    with pytest.raises(ConnectionError):
        await executor.execute(request, lease)

    assert len(plugin.calls) == 1
    assert publish_calls["count"] == 2


@pytest.mark.asyncio
async def test_publish_succeeds_on_second_attempt():
    plugin = RecordingPlugin()
    publisher = RecordingPublisher()
    publish_calls = {"count": 0}

    class FlakyPublisher:
        async def publish(self, request, result, lease):
            publish_calls["count"] += 1
            if publish_calls["count"] == 1:
                raise ConnectionError("nats unavailable")
            await publisher.publish(request, result, lease)

    request = CollectionRequest(
        task_id="collect-publish-flaky",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "c1"},),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=plugin,
        publisher=FlakyPublisher(),
        settings=TargetExecutorSettings(
            max_active_targets=1,
            target_task_window=1,
            publish_max_attempts=2,
        ),
    )
    summary = await executor.execute(request, lease)

    assert summary.succeeded == 1
    assert len(plugin.calls) == 1
    assert publish_calls["count"] == 2
    assert len(publisher.results) == 1


@pytest.mark.asyncio
async def test_multiple_runs_share_the_same_pod_target_limit():
    active = 0
    peak = 0

    class SlowPlugin:
        async def collect(self, target, credential, context):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return CollectOutcome(status=CollectOutcomeStatus.SUCCESS)

    shared_gate = asyncio.Semaphore(2)
    settings = TargetExecutorSettings(
        max_active_targets=2, target_task_window=4
    )
    executors = [
        TargetCollectionExecutor(
            preflight=ReachablePreflight(),
            plugin=SlowPlugin(),
            publisher=RecordingPublisher(),
            target_semaphore=shared_gate,
            settings=settings,
        )
        for _ in range(2)
    ]

    async def run(index):
        request = CollectionRequest(
            task_id=f"collect-shared-{index}",
            plugin_ref="mysql.config",
            targets=tuple(f"10.10.{index}.{item}" for item in range(1, 5)),
            credentials=({"credential_id": "credential-1"},),
        )
        lease = RunLease(
            task_id=request.task_id,
            request_digest=request.digest,
            owner_id="pod-a",
            fence=1,
            expires_at=999999,
        )
        await executors[index].execute(request, lease)

    await asyncio.gather(run(0), run(1))

    assert peak == 2


@pytest.mark.asyncio
async def test_multiple_runs_share_one_global_target_task_window():
    release = asyncio.Event()
    budget = TargetWorkerBudget(3)

    class BlockingPlugin:
        async def collect(self, target, credential, context):
            await release.wait()
            return CollectOutcome(status=CollectOutcomeStatus.SUCCESS)

    executors = [
        TargetCollectionExecutor(
            preflight=ReachablePreflight(),
            plugin=BlockingPlugin(),
            publisher=RecordingPublisher(),
            worker_budget=budget,
            settings=TargetExecutorSettings(
                max_active_targets=4, target_task_window=4
            ),
        )
        for _ in range(2)
    ]

    async def run(index):
        request = CollectionRequest(
            task_id=f"window-{index}",
            plugin_ref="mysql.config",
            targets=tuple(f"10.20.{index}.{item}" for item in range(1, 5)),
        )
        lease = RunLease(
            task_id=request.task_id,
            request_digest=request.digest,
            owner_id="pod-a",
            fence=1,
            expires_at=999999,
        )
        await executors[index].execute(request, lease)

    tasks = [asyncio.create_task(run(index)) for index in range(2)]
    await asyncio.sleep(0.02)

    assert budget.active == 3
    assert budget.peak == 3

    release.set()
    await asyncio.gather(*tasks)
    assert budget.active == 0


@pytest.mark.asyncio
async def test_worker_failure_cancels_siblings_before_releasing_budget():
    cancelled = asyncio.Event()
    budget = TargetWorkerBudget(2)

    class FailingPreflight:
        async def check(self, target, request, *, timeout_seconds, plan=None):
            if target.endswith("1"):
                raise RuntimeError("probe failed")
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    executor = TargetCollectionExecutor(
        preflight=FailingPreflight(),
        plugin=RecordingPlugin(),
        publisher=RecordingPublisher(),
        worker_budget=budget,
        settings=TargetExecutorSettings(
            max_active_targets=2, target_task_window=2
        ),
    )
    request = CollectionRequest(
        task_id="worker-cancel",
        plugin_ref="mysql.config",
        targets=("10.10.24.1", "10.10.24.2"),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    with pytest.raises(RuntimeError, match="probe failed"):
        await executor.execute(request, lease)

    assert cancelled.is_set()
    assert budget.active == 0


class BrokenCredentialStore(InMemoryCredentialStateStore):
    async def load_target_state(self, scope, credential_ids):
        raise ConnectionError("Too many connections")


@pytest.mark.asyncio
async def test_credential_state_redis_error_fails_only_that_target():
    plugin = RecordingPlugin()
    publisher = RecordingPublisher()
    metrics = CollectionMetrics()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=plugin,
        publisher=publisher,
        credential_policy=CredentialPolicy(store=BrokenCredentialStore()),
        metrics=metrics,
        settings=TargetExecutorSettings(max_active_targets=2, target_task_window=2),
    )
    request = CollectionRequest(
        task_id="credential-state-unavailable",
        plugin_ref="mysql.config",
        targets=("10.10.24.1", "10.10.24.2"),
        credentials=({"credential_id": "credential-1"},),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert summary.total == 2
    assert summary.failed == 2
    assert summary.succeeded == 0
    assert plugin.calls == []
    assert [result[1].error_code for result in publisher.results] == [
        "credential_state_unavailable",
        "credential_state_unavailable",
    ]
    assert metrics.snapshot()["credential_state_redis_error_total"] == 2
