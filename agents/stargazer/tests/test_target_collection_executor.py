import asyncio

import pytest
from core.collection.contracts import (
    AccessProbeResult,
    AccessProbeStatus,
    CollectOutcome,
    CollectOutcomeStatus,
    PreflightResult,
    PreflightStatus,
    TargetExecutorSettings,
)
from core.collection.credential_policy import CredentialPolicy, InMemoryCredentialStateStore
from core.collection.executor import TargetCollectionExecutor, TargetWorkerBudget
from core.collection.metrics import CollectionMetrics
from core.collection.result_publisher import BufferedResultPublisher
from core.collection.runtime import CollectionRequest, RunLease


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


class OneTargetFailingPublisher:
    def __init__(self, failed_target):
        self.failed_target = failed_target
        self.targets = []

    async def publish(self, request, result, lease):
        self.targets.append(result.target)
        if result.target == self.failed_target:
            raise TimeoutError("nats flush timed out")


class DefinitelyNotPublishedError(ConnectionError):
    delivery_detected = False


class RecordingReadyAccessProbe:
    def __init__(self):
        self.calls = []

    async def probe(self, target, credential, context, *, timeout_seconds):
        self.calls.append((target, credential, context, timeout_seconds))
        return AccessProbeResult(status=AccessProbeStatus.READY)


class ReachablePreflight:
    async def check(self, target, request, *, timeout_seconds, plan=None):
        return PreflightResult(status=PreflightStatus.REACHABLE)


class RecordingReachablePreflight:
    def __init__(self):
        self.calls = []

    async def check(self, target, request, *, timeout_seconds, plan=None):
        self.calls.append((target, request, timeout_seconds))
        return PreflightResult(status=PreflightStatus.REACHABLE)


class PinnedReachablePreflight:
    async def check(self, target, request, *, timeout_seconds, plan=None):
        return PreflightResult(status=PreflightStatus.REACHABLE, connect_host="10.0.0.8")


class FirstTargetBrokenPreflight:
    async def check(self, target, request, *, timeout_seconds, plan=None):
        if target == "10.10.24.1":
            raise RuntimeError("unexpected target failure")
        return PreflightResult(status=PreflightStatus.REACHABLE)


@pytest.mark.asyncio
async def test_disabled_reachability_keeps_security_preflight_but_skips_all_access_probes():
    preflight = RecordingReachablePreflight()
    access_probe = RecordingReadyAccessProbe()
    plugin = RecordingPlugin()
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=preflight,
        access_probe=access_probe,
        plugin=plugin,
        publisher=publisher,
        settings=TargetExecutorSettings(
            max_active_targets=1,
            target_task_window=1,
            access_probe_enabled=False,
        ),
    )
    request = CollectionRequest(
        task_id="preflight-disabled",
        plugin_ref="network.config",
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
    assert len(preflight.calls) == 1
    assert access_probe.calls == []
    assert len(plugin.calls) == 1


@pytest.mark.asyncio
async def test_one_target_publish_failure_does_not_cancel_remaining_targets():
    publisher = OneTargetFailingPublisher("10.10.24.2")
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=RecordingPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(
            max_active_targets=1,
            target_task_window=1,
            publish_max_attempts=2,
        ),
    )
    request = CollectionRequest(
        task_id="publish-isolated",
        plugin_ref="network.config",
        targets=("10.10.24.1", "10.10.24.2", "10.10.24.3"),
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

    assert publisher.targets == [
        "10.10.24.1",
        "10.10.24.2",
        "10.10.24.3",
    ]
    assert summary.collection_succeeded == 3
    assert summary.publish_succeeded == 2
    assert summary.publish_failed == 0
    assert summary.publish_unknown == 1
    assert summary.has_errors is True


@pytest.mark.asyncio
async def test_unexpected_target_failure_is_reported_without_cancelling_run():
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=FirstTargetBrokenPreflight(),
        plugin=RecordingPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="target-error-isolated",
        plugin_ref="network.config",
        targets=("10.10.24.1", "10.10.24.2"),
        credentials=({"credential_id": "credential-1"},),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    summary = await executor.execute(request, lease)

    assert summary.collection_failed == 1
    assert summary.collection_succeeded == 1
    assert [item[1].target for item in publisher.results] == [
        "10.10.24.1",
        "10.10.24.2",
    ]
    assert publisher.results[0][1].error_code == "target_execution_error"


@pytest.mark.asyncio
async def test_slow_publish_does_not_hold_target_collection_window():
    release = asyncio.Event()

    class SlowDelegate:
        async def publish_batch(self, items):
            await release.wait()

    plugin = RecordingPlugin()
    publisher = BufferedResultPublisher(SlowDelegate(), capacity=2, batch_size=2, flush_interval_seconds=0.01)
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=plugin,
        publisher=publisher,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="publish-does-not-hold-target-window",
        plugin_ref="network.config",
        targets=("10.10.24.1", "10.10.24.2"),
        credentials=({"credential_id": "credential-1"},),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    run = asyncio.create_task(executor.execute(request, lease))
    for _ in range(100):
        if len(plugin.calls) == 2:
            break
        await asyncio.sleep(0.001)

    assert len(plugin.calls) == 2
    assert run.done() is False
    release.set()
    summary = await run
    assert summary.publish_succeeded == 2
    await publisher.shutdown()


class CredentialProtocolProbe:
    async def probe(self, target, credential, context, *, timeout_seconds):
        if credential["credential_id"] == "credential-1":
            return AccessProbeResult(
                status=AccessProbeStatus.AUTH_FAILED,
                error_code="authentication_failed",
            )
        return AccessProbeResult(status=AccessProbeStatus.READY)


class NoResponseThenReadyProbe:
    async def probe(self, target, credential, context, *, timeout_seconds):
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
    async def probe(self, target, credential, context, *, timeout_seconds):
        return AccessProbeResult(
            status=AccessProbeStatus.TARGET_UNREACHABLE,
            error_code="target_unreachable",
        )


class MustNotCollectPlugin:
    async def collect(self, target, credential, context):
        raise AssertionError("formal collection must not run")


class BrokenAccessProbe:
    async def probe(self, target, credential, context, *, timeout_seconds):
        raise RuntimeError("secret-do-not-publish")


class TimeoutThenReadyAccessProbe:
    async def probe(self, target, credential, context, *, timeout_seconds):
        if credential["credential_id"] == "credential-1":
            await asyncio.sleep(60)
        return AccessProbeResult(status=AccessProbeStatus.READY)


class FixedAccessProbe:
    def __init__(self, status, error_code):
        self.status = status
        self.error_code = error_code

    async def probe(self, target, credential, context, *, timeout_seconds):
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
async def test_preflight_pinned_host_is_forwarded_only_in_internal_context():
    plugin = RecordingPlugin()
    executor = TargetCollectionExecutor(
        preflight=PinnedReachablePreflight(),
        plugin=plugin,
        publisher=RecordingPublisher(),
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="pinned-connect-host",
        plugin_ref="mysql.config",
        targets=("db.trusted.example",),
        credentials=({"credential_id": "credential-1"},),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    await executor.execute(request, lease)

    assert plugin.calls[0][2].params["_validated_connect_host"] == "10.0.0.8"
    assert "_validated_connect_host" not in request.params


@pytest.mark.asyncio
async def test_credentials_rotate_inside_target_and_success_gets_affinity():
    plugin = ScriptedPlugin(
        [
            CollectOutcome(
                status=CollectOutcomeStatus.AUTH_FAILED,
                error_code="unauthorized",
            ),
            CollectOutcome(
                status=CollectOutcomeStatus.AUTH_FAILED,
                error_code="authentication_failed",
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
        ("10.10.24.1", "credential-3"),
    ]
    assert publisher.results[0][1].credential_id == "credential-3"
    assert publisher.results[0][1].attempts == 3
    assert [(failure.credential_id, failure.error_code) for failure in publisher.results[0][1].credential_failures] == [
        ("credential-1", "unauthorized"),
        ("credential-2", "authentication_failed"),
    ]
    eligible = await credential_policy.eligible_credentials(request, "10.10.24.1")
    assert [item["credential_id"] for item in eligible] == [
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
    eligible = await credential_policy.eligible_credentials(request, "10.10.24.1")

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
        credentials=tuple({"credential_id": f"credential-{index}"} for index in range(1, 6)),
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
    assert publisher.results[0][1].credential_id == "credential-1"
    assert publisher.results[0][1].error_code == "target_unreachable"


@pytest.mark.asyncio
async def test_collect_unreachable_keeps_selected_credential_identity():
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=ScriptedPlugin(
            [
                CollectOutcome(
                    status=CollectOutcomeStatus.UNREACHABLE,
                    error_code="target_unreachable",
                )
            ]
        ),
        publisher=publisher,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="collect-unreachable-after-selection",
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

    assert summary.unreachable == 1
    assert publisher.results[0][1].credential_id == "credential-1"


@pytest.mark.asyncio
async def test_access_probe_failure_logs_target_and_credential_id(monkeypatch):
    logged = []

    def capture(message, *args):
        logged.append(message % args if args else message)

    monkeypatch.setattr("core.collection.executor.logger.info", capture)
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
async def test_target_scoped_access_probe_result_stops_credential_rotation(probe_status, error_code, result_status):
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
    assert [(failure.credential_id, failure.error_code) for failure in publisher.results[0][1].credential_failures] == [
        ("credential-1", "capability_denied")
    ]
    assert await credential_policy.eligible_credentials(request, "10.10.24.1") == ()


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
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
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
async def test_unknown_publish_failure_is_not_retried_or_recollected():
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
    summary = await executor.execute(request, lease)

    assert len(plugin.calls) == 1
    assert publish_calls["count"] == 1
    assert summary.publish_unknown == 1
    assert summary.has_errors is True


@pytest.mark.asyncio
async def test_publish_succeeds_on_second_attempt():
    plugin = RecordingPlugin()
    publisher = RecordingPublisher()
    publish_calls = {"count": 0}

    class FlakyPublisher:
        async def publish(self, request, result, lease):
            publish_calls["count"] += 1
            if publish_calls["count"] == 1:
                raise DefinitelyNotPublishedError("nats unavailable")
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
async def test_publish_retry_shares_one_end_to_end_deadline():
    plugin = RecordingPlugin()
    publish_started = None

    class SlowRetryPublisher:
        def __init__(self):
            self.calls = 0

        async def publish(self, request, result, lease):
            nonlocal publish_started
            self.calls += 1
            if publish_started is None:
                publish_started = asyncio.get_running_loop().time()
            await asyncio.sleep(0.035)
            if self.calls == 1:
                raise DefinitelyNotPublishedError("not delivered")

    publisher = SlowRetryPublisher()
    metrics = CollectionMetrics()
    request = CollectionRequest(
        task_id="collect-publish-one-deadline",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "c1"},),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=plugin,
        publisher=publisher,
        metrics=metrics,
        settings=TargetExecutorSettings(
            max_active_targets=1,
            target_task_window=1,
            publish_guard_seconds=0.05,
            publish_max_attempts=2,
        ),
    )

    summary = await executor.execute(request, lease)
    elapsed = asyncio.get_running_loop().time() - publish_started

    assert publisher.calls == 2
    assert elapsed < 0.065
    assert summary.publish_unknown == 1
    assert metrics.snapshot()["publish_timeout_total"] == 1


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
    settings = TargetExecutorSettings(max_active_targets=2, target_task_window=4)
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
            settings=TargetExecutorSettings(max_active_targets=4, target_task_window=4),
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
async def test_target_failure_keeps_siblings_running_and_releases_budget_after_run():
    sibling_started = asyncio.Event()
    release_sibling = asyncio.Event()
    budget = TargetWorkerBudget(2)

    class FailingPreflight:
        async def check(self, target, request, *, timeout_seconds, plan=None):
            if target.endswith("1"):
                raise RuntimeError("probe failed")
            sibling_started.set()
            await release_sibling.wait()
            return PreflightResult(status=PreflightStatus.REACHABLE)

    executor = TargetCollectionExecutor(
        preflight=FailingPreflight(),
        plugin=RecordingPlugin(),
        publisher=RecordingPublisher(),
        worker_budget=budget,
        settings=TargetExecutorSettings(max_active_targets=2, target_task_window=2),
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

    run = asyncio.create_task(executor.execute(request, lease))
    await sibling_started.wait()
    assert run.done() is False
    release_sibling.set()
    summary = await run

    assert summary.collection_failed == 1
    assert summary.collection_succeeded == 1
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
