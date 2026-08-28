import asyncio
import traceback

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
from core.collection.enums import FailureStage
from core.collection.execution_plan import ExecutionPlan
from core.collection.executor import TargetCollectionExecutor, TargetWorkerBudget
from core.collection.metrics import CollectionMetrics
from core.collection.plugins import UnifiedPluginFactory
from core.collection.result_publisher import BufferedResultPublisher, NatsResultPublisher
from core.collection.runtime import CollectionRequest, RunLease
from tasks.utils import metrics_helper


class UnreachablePreflight:
    async def check(self, target, request, *, timeout_seconds, plan=None):
        return PreflightResult(
            status=PreflightStatus.UNREACHABLE,
            error_code="tcp_connect_failed",
        )


class OutboundRejectedPreflight:
    async def check(self, target, request, *, timeout_seconds, plan=None):
        return PreflightResult(
            status=PreflightStatus.UNREACHABLE,
            error_code="outbound_target_rejected",
            failed_stage=FailureStage.OUTBOUND_POLICY,
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
    def __init__(self):
        self.error = None

    async def check(self, target, request, *, timeout_seconds, plan=None):
        if target == "10.10.24.1":
            secret = "target-" + "framework-secret-sentinel"
            try:
                raise RuntimeError("password=" + secret)
            except RuntimeError as error:
                self.error = error
                raise
        return PreflightResult(status=PreflightStatus.REACHABLE)


@pytest.mark.asyncio
async def test_job_node_info_loads_after_preflight_before_probe_and_collect_service():
    order = []

    class OrderedPreflight:
        async def check(self, target, request, *, timeout_seconds, plan=None):
            order.append("preflight")
            return PreflightResult(
                status=PreflightStatus.REACHABLE,
                connect_host=target,
            )

    async def load(ips, **_context):
        order.append("node_info")
        return [{"id": "node-1", "ip": ips[0], "operating_system": "linux"}]

    class Service:
        def __init__(self, params):
            assert params["node_info"]["id"] == "node-1"
            order.append("service")

        async def probe(self):
            order.append("probe")
            return AccessProbeResult(status=AccessProbeStatus.READY)

        async def collect(self):
            order.append("collect")
            return 'host{collect_status="success"} 1'

    request = CollectionRequest(
        task_id="job-node-info-order",
        plugin_ref="host.config",
        targets=("10.0.0.1",),
        credentials=({"credential_id": "credential-1"},),
        params={
            "plugin_family": "configuration",
            "model_id": "host",
            "executor_type": "job",
            "collect_task_id": 91,
            "ip_precheck": True,
        },
    )
    plugin = UnifiedPluginFactory(
        configuration_service_factory=Service,
        configuration_node_info_loader=load,
    ).resolve(request)
    executor = TargetCollectionExecutor(
        preflight=OrderedPreflight(),
        access_probe=plugin,
        plugin=plugin,
        publisher=RecordingPublisher(),
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    summary = await executor.execute(request, lease)
    await plugin.close()

    assert summary.collection_succeeded == 1
    assert order == [
        "preflight",
        "node_info",
        "service",
        "probe",
        "service",
        "collect",
    ]


@pytest.mark.asyncio
async def test_all_preflight_failures_do_not_start_job_node_info_lookup():
    async def unexpected_load(*_args, **_kwargs):
        raise AssertionError("node info lookup must wait for an eligible target")

    request = CollectionRequest(
        task_id="job-no-eligible-target",
        plugin_ref="host.config",
        targets=("10.0.0.1", "10.0.0.2"),
        credentials=({"credential_id": "credential-1"},),
        params={
            "plugin_family": "configuration",
            "model_id": "host",
            "executor_type": "job",
            "collect_task_id": 91,
        },
    )
    plugin = UnifiedPluginFactory(
        configuration_service_factory=lambda params: params,
        configuration_node_info_loader=unexpected_load,
    ).resolve(request)
    executor = TargetCollectionExecutor(
        preflight=UnreachablePreflight(),
        access_probe=plugin,
        plugin=plugin,
        publisher=RecordingPublisher(),
        settings=TargetExecutorSettings(max_active_targets=2, target_task_window=2),
    )

    summary = await executor.execute(
        request,
        RunLease(request.task_id, request.digest, "pod-a", 1, 999999),
    )
    await plugin.close()

    assert summary.unreachable == 2


@pytest.mark.asyncio
async def test_preflight_failure_detail_logs_include_every_failed_target(monkeypatch):
    logged = []

    def capture(message, *args):
        logged.append(message % args if args else message)

    monkeypatch.setattr("core.collection.executor.logger.warning", capture)
    executor = TargetCollectionExecutor(
        preflight=UnreachablePreflight(),
        plugin=RecordingPlugin(),
        publisher=RecordingPublisher(),
        settings=TargetExecutorSettings(max_active_targets=25, target_task_window=25),
    )
    request = CollectionRequest(
        task_id="bounded-failure-logs",
        plugin_ref="network.config",
        targets=tuple(f"10.10.69.{index}" for index in range(25)),
        credentials=(),
        params={"model_id": "network"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    summary = await executor.execute(request, lease)

    target_details = [item for item in logged if "event=target_collection_failed" in item]
    run_summaries = [item for item in logged if "event=collection_run_summary" in item]
    assert summary.unreachable == 25
    assert len(target_details) == 25
    assert all("plugin_ref=network.config" in item for item in target_details)
    assert all("model_id=network" in item for item in target_details)
    assert all("stage=preflight" in item for item in target_details)
    assert all("failed_stage=preflight" in item for item in target_details)
    assert all("error_type=TargetCollectionFailure" in item for item in target_details)
    assert len(run_summaries) == 1
    assert "任务汇总" in run_summaries[0]
    assert "不可达=25" in run_summaries[0]


@pytest.mark.asyncio
async def test_ip_precheck_failure_logs_each_ip_with_stable_safe_template(monkeypatch):
    warning_calls = []
    monkeypatch.setattr(
        "core.collection.executor.logger.warning",
        lambda message, *args: warning_calls.append((message, args)),
    )
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=UnreachablePreflight(),
        plugin=RecordingPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(max_active_targets=2, target_task_window=2),
    )
    request = CollectionRequest(
        task_id="ip-precheck-log",
        plugin_ref="network.config",
        targets=("10.10.69.21\r\nforged=true", "10.10.69.22"),
        credentials=(
            {
                "credential_id": "credential-1",
                "password": "precheck-secret-sentinel",
            },
        ),
        params={"model_id": "network", "ip_precheck": True},
    )

    summary = await executor.execute(
        request,
        RunLease(request.task_id, request.digest, "pod-a", 1, 999999),
    )

    precheck_calls = [item for item in warning_calls if item[0].startswith("event=ip_precheck_failed")]
    expected_template = "event=ip_precheck_failed task_id=%s target=%s " "failed_stage=ip_precheck error_type=%s"
    assert precheck_calls == [
        (
            expected_template,
            ("ip-precheck-log", "10.10.69.21\\r\\nforged=true", "tcp_connect_failed"),
        ),
        (expected_template, ("ip-precheck-log", "10.10.69.22", "tcp_connect_failed")),
    ]
    rendered = [template % args for template, args in precheck_calls]
    assert all("precheck-secret-sentinel" not in message for message in rendered)
    all_rendered = [template % args for template, args in warning_calls]
    assert all("precheck-secret-sentinel" not in message for message in all_rendered)
    assert summary.unreachable == 2
    assert [result.error_code for _, result, _ in publisher.results] == [
        "tcp_connect_failed",
        "tcp_connect_failed",
    ]
    assert publisher.results[0][1].target == "10.10.69.21\r\nforged=true"


@pytest.mark.asyncio
async def test_outbound_policy_rejection_is_not_logged_as_ip_precheck_failure(monkeypatch):
    warning_calls = []
    monkeypatch.setattr(
        "core.collection.executor.logger.warning",
        lambda message, *args: warning_calls.append((message, args)),
    )
    executor = TargetCollectionExecutor(
        preflight=OutboundRejectedPreflight(),
        plugin=RecordingPlugin(),
        publisher=RecordingPublisher(),
    )
    request = CollectionRequest(
        task_id="outbound-policy-log",
        plugin_ref="network.config",
        targets=("127.0.0.1",),
        credentials=({"credential_id": "credential-1"},),
        params={"model_id": "network", "ip_precheck": True},
    )

    summary = await executor.execute(
        request,
        RunLease(request.task_id, request.digest, "pod-a", 1, 999999),
    )

    rendered = [template % args for template, args in warning_calls]
    assert summary.unreachable == 1
    assert not any("event=ip_precheck_failed" in message for message in rendered)
    assert any("stage=outbound_policy" in message for message in rendered)


@pytest.mark.asyncio
async def test_plugin_failure_has_central_searchable_log_without_secret(monkeypatch):
    warning_logs = []
    error_logs = []

    def capture_warning(message, *args):
        warning_logs.append(message % args if args else message)

    def capture_error(message, *args):
        error_logs.append(message % args if args else message)

    class BrokenPlugin:
        async def collect(self, target, credential, context):
            raise RuntimeError("password=must-not-be-logged")

    monkeypatch.setattr("core.collection.executor.logger.warning", capture_warning)
    monkeypatch.setattr("core.collection.executor.logger.error", capture_error)
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=BrokenPlugin(),
        publisher=RecordingPublisher(),
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="vmware-plugin-failure-log",
        plugin_ref="vmware_vc.config",
        targets=("10.10.16.254",),
        credentials=({"credential_id": "credential-1", "password": "secret"},),
        params={"model_id": "vmware_vc"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    summary = await executor.execute(request, lease)

    failures = [item for item in warning_logs if "event=collection_run_summary" in item]
    call_chains = [item for item in error_logs if "event=plugin_exception" in item]
    assert summary.failed == 1
    assert len(failures) == 1
    assert "task_id=vmware-plugin-failure-log" in failures[0]
    assert "instance_id=" not in failures[0]
    assert "plugin_ref=vmware_vc.config" in failures[0]
    assert "model_id=vmware_vc" in failures[0]
    assert "失败类型=plugin_error:1" in failures[0]
    assert "失败样本=10.10.16.254|credential-1|plugin_error|RuntimeError" in failures[0]
    assert "must-not-be-logged" not in failures[0]
    assert "secret" not in failures[0]
    assert len(call_chains) == 1
    assert "task_id=vmware-plugin-failure-log" in call_chains[0]
    assert "plugin_ref=vmware_vc.config" in call_chains[0]
    assert "model_id=vmware_vc" in call_chains[0]
    assert "target=10.10.16.254" in call_chains[0]
    assert "error_type=RuntimeError" in call_chains[0]
    assert ":collect" in call_chains[0]
    assert "must-not-be-logged" not in call_chains[0]
    assert "secret" not in call_chains[0]


@pytest.mark.asyncio
async def test_plugin_exception_call_chains_include_every_failed_target(monkeypatch):
    error_logs = []

    def capture_error(message, *args):
        error_logs.append(message % args if args else message)

    class BrokenPlugin:
        async def collect(self, target, credential, context):
            raise RuntimeError(f"SNMP authorization failure for {target}")

    monkeypatch.setattr("core.collection.executor.logger.error", capture_error)
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=BrokenPlugin(),
        publisher=RecordingPublisher(),
        settings=TargetExecutorSettings(max_active_targets=10, target_task_window=10),
    )
    request = CollectionRequest(
        task_id="bounded-plugin-call-chains",
        plugin_ref="network.config",
        targets=tuple(f"10.10.69.{index}" for index in range(10)),
        credentials=({"credential_id": "credential-1", "community": "secret"},),
        params={"model_id": "network", "plugin_name": "snmp_facts"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    summary = await executor.execute(request, lease)

    call_chains = [item for item in error_logs if "event=plugin_exception" in item]
    assert summary.failed == 10
    assert len(call_chains) == 10
    assert all("plugin_name=snmp_facts" in item for item in call_chains)
    assert all("error_message=SNMP authorization failure" in item for item in call_chains)
    assert {item.split("target=", 1)[1].split(" ", 1)[0] for item in call_chains} == {f"10.10.69.{index}" for index in range(10)}


@pytest.mark.asyncio
async def test_late_plugin_exception_keeps_target_context(monkeypatch):
    error_logs = []

    def capture_error(message, *args):
        error_logs.append(message % args if args else message)

    class LateBrokenPlugin:
        async def collect(self, target, credential, context):
            if target.endswith(".9"):
                raise RuntimeError("late SNMP decoder failure")
            return CollectOutcome(status=CollectOutcomeStatus.SUCCESS, value={"ok": True})

    monkeypatch.setattr("core.collection.executor.logger.error", capture_error)
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=LateBrokenPlugin(),
        publisher=RecordingPublisher(),
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="late-plugin-call-chain",
        plugin_ref="network.config",
        targets=tuple(f"10.10.69.{index}" for index in range(10)),
        credentials=({"credential_id": "credential-1"},),
        params={"model_id": "network", "plugin_name": "snmp_facts"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    summary = await executor.execute(request, lease)

    call_chains = [item for item in error_logs if "event=plugin_exception" in item]
    assert summary.failed == 1
    assert len(call_chains) == 1
    assert "target=10.10.69.9" in call_chains[0]
    assert "error_message=late SNMP decoder failure" in call_chains[0]


@pytest.mark.asyncio
async def test_plugin_failure_detail_logs_include_every_failed_target(monkeypatch):
    logged = []

    def capture(message, *args):
        logged.append(message % args if args else message)

    class FailingPlugin:
        async def collect(self, target, credential, context):
            return CollectOutcome(
                status=CollectOutcomeStatus.FAILED,
                error_code="plugin_timeout",
            )

    monkeypatch.setattr("core.collection.executor.logger.warning", capture)
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=FailingPlugin(),
        publisher=RecordingPublisher(),
        settings=TargetExecutorSettings(max_active_targets=25, target_task_window=25),
    )
    request = CollectionRequest(
        task_id="bounded-plugin-failure-logs",
        plugin_ref="network.config",
        targets=tuple(f"10.10.69.{index}" for index in range(25)),
        credentials=({"credential_id": "credential-1"},),
        params={"model_id": "network"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    summary = await executor.execute(request, lease)

    target_failures = [item for item in logged if "event=target_collection_failed" in item]
    failures = [item for item in logged if "event=collection_run_summary" in item]
    assert summary.failed == 25
    assert len(target_failures) == 25
    assert {item.split("target=", 1)[1].split(" ", 1)[0] for item in target_failures} == {f"10.10.69.{index}" for index in range(25)}
    assert len(failures) == 1
    assert "采集失败=25" in failures[0]
    assert "失败类型=plugin_timeout:25" in failures[0]
    assert failures[0].count("|credential-1|plugin_timeout|") == 3


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
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="preflight-disabled",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "credential-1"},),
        params={"ip_precheck": False},
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
async def test_unexpected_target_failure_owns_safe_traceback_without_cancelling_run(monkeypatch):
    error_calls = []
    monkeypatch.setattr(
        "core.collection.executor.logger.error",
        lambda message, *args, **kwargs: error_calls.append((message, args, kwargs)),
    )
    publisher = RecordingPublisher()
    preflight = FirstTargetBrokenPreflight()
    executor = TargetCollectionExecutor(
        preflight=preflight,
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
    assert len(error_calls) == 1
    template, args, kwargs = error_calls[0]
    assert template.startswith("event=target_execution_failed")
    assert "failed_stage=framework" in template
    assert args[-1] == "RuntimeError"
    assert kwargs["exc_info"][2] is preflight.error.__traceback__
    formatted = "".join(traceback.format_exception(*kwargs["exc_info"]))
    assert "test_target_collection_executor.py" in formatted
    assert "in check" in formatted
    assert "target-framework-secret-sentinel" not in formatted
    assert str(preflight.error) == "password=target-framework-secret-sentinel"


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
        params={"model_id": "mysql", "port": 3306, "ip_precheck": True},
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
        params={
            "scope_id": "tenant-a",
            "credential_set_version": "v1",
            "ip_precheck": True,
        },
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
        params={"ip_precheck": True},
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
        params={
            "scope_id": "tenant-a",
            "credential_set_version": "v1",
            "ip_precheck": True,
        },
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
        params={"ip_precheck": True},
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
async def test_single_snmp_no_response_is_visible_as_timeout_without_plugin_traceback(monkeypatch):
    warning_logs = []
    error_logs = []

    def capture_warning(message, *args):
        warning_logs.append(message % args if args else message)

    def capture_error(message, *args):
        error_logs.append(message % args if args else message)

    monkeypatch.setattr("core.collection.executor.logger.warning", capture_warning)
    monkeypatch.setattr("core.collection.executor.logger.error", capture_error)
    publisher = RecordingPublisher()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        access_probe=AlwaysNoResponseProbe(),
        plugin=MustNotCollectPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(
            max_active_targets=1,
            target_task_window=1,
            connect_timeout_seconds=10,
        ),
    )
    request = CollectionRequest(
        task_id="snmp-timeout-visible",
        plugin_ref="network.config",
        targets=("10.10.69.245",),
        credentials=({"credential_id": "credential-1"},),
        params={
            "model_id": "network",
            "plugin_name": "snmp_facts",
            "ip_precheck": True,
        },
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    summary = await executor.execute(request, lease)

    assert summary.failed == 1
    assert publisher.results[0][1].error_code == "protocol_no_response"
    target_failures = [item for item in warning_logs if "event=target_collection_failed" in item]
    run_summaries = [item for item in warning_logs if "event=collection_run_summary" in item]
    assert len(target_failures) == 1
    assert "stage=access_probe" in target_failures[0]
    assert "reason=timeout" in target_failures[0]
    assert "timeout_seconds=10" in target_failures[0]
    assert "target=10.10.69.245" in target_failures[0]
    assert "失败类型=protocol_no_response:1" in run_summaries[0]
    assert not any("event=plugin_exception" in item for item in error_logs)


@pytest.mark.asyncio
async def test_collection_info_is_bounded_and_target_details_are_debug(monkeypatch):
    info_logs = []
    debug_logs = []

    def capture_info(message, *args):
        info_logs.append(message % args if args else message)

    def capture_debug(message, *args):
        debug_logs.append(message % args if args else message)

    monkeypatch.setattr("core.collection.executor.logger.info", capture_info)
    monkeypatch.setattr("core.collection.executor.logger.debug", capture_debug)
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=RecordingPlugin(),
        publisher=RecordingPublisher(),
        settings=TargetExecutorSettings(max_active_targets=5, target_task_window=5),
    )
    request = CollectionRequest(
        task_id="bounded-progress",
        plugin_ref="network.config",
        targets=tuple(f"10.10.70.{index}" for index in range(25)),
        credentials=({"credential_id": "credential-1"},),
        params={
            "model_id": "network",
            "plugin_name": "snmp_facts",
            "instance_id": "cmdb-network-1",
        },
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    await executor.execute(request, lease)

    progress = [item for item in info_logs if "event=collection_progress" in item]
    summaries = [item for item in info_logs if "event=collection_run_summary" in item]
    assert 2 <= len(progress) <= 12
    assert len(summaries) == 1
    assert not any("event=target_collection_started" in item for item in info_logs)
    assert not any("event=target_collection_succeeded" in item for item in info_logs)
    assert "plugin_ref=network.config" in progress[0]
    assert "plugin_name=snmp_facts" in progress[0]
    assert "instance_id=cmdb-network-1" in progress[0]
    assert "采集进度" in progress[0]
    assert "已完成=" in progress[0]
    assert "当前目标样本=" in progress[0]
    assert "已完成=25/25" in progress[-1]
    assert "最近结果=成功" in progress[-1]
    starts = [item for item in debug_logs if "event=target_collection_started" in item]
    successes = [item for item in debug_logs if "event=target_collection_succeeded" in item]
    assert len(starts) == 25
    assert all("plugin_name=snmp_facts" in item for item in starts)
    assert all("target=" in item for item in starts)
    assert len(successes) == 25
    assert all("SNMP采集成功" in item for item in successes)
    assert all("task_id=" not in item for item in successes)
    assert all("instance_id=cmdb-network-1" in item for item in successes)
    assert all("credential_id=credential-1" in item for item in successes)
    assert all("耗时=" in item for item in successes)


@pytest.mark.asyncio
async def test_publish_failures_are_sampled_and_aggregated(monkeypatch):
    warning_logs = []

    def capture_warning(message, *args):
        warning_logs.append(message % args if args else message)

    class BlockingEnqueuePublisher:
        async def enqueue(self, request, result, lease):
            await asyncio.sleep(60)

    monkeypatch.setattr("core.collection.executor.logger.warning", capture_warning)
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=RecordingPlugin(),
        publisher=BlockingEnqueuePublisher(),
        settings=TargetExecutorSettings(
            max_active_targets=10,
            target_task_window=10,
            publish_queue_timeout_seconds=0.001,
            publish_total_timeout_seconds=1,
            publish_max_attempts=2,
        ),
    )
    request = CollectionRequest(
        task_id="publish-timeout-sampled",
        plugin_ref="network.config",
        targets=tuple(f"10.10.71.{index}" for index in range(10)),
        credentials=({"credential_id": "credential-1"},),
        params={"model_id": "network", "instance_id": "cmdb-network-2"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    summary = await executor.execute(request, lease)

    publish_failures = [item for item in warning_logs if "event=result_publish_failed" in item]
    old_terminal = [item for item in warning_logs if "event=result_publish_terminal" in item]
    run_summaries = [item for item in warning_logs if "event=collection_run_summary" in item]
    assert summary.publish_failed == 10
    assert len(publish_failures) == 3
    assert old_terminal == []
    assert all("phase=enqueue" in item for item in publish_failures)
    assert all("reason=publish_queue_timeout" in item for item in publish_failures)
    assert all("timeout_seconds=0.001" in item for item in publish_failures)
    assert all("instance_id=cmdb-network-2" in item for item in publish_failures)
    assert all("task_id=" not in item for item in publish_failures)
    assert "instance_id=cmdb-network-2" in run_summaries[0]
    assert "task_id=" not in run_summaries[0]
    assert "发布失败类型=publish_queue_timeout:10" in run_summaries[0]
    assert run_summaries[0].count("|publish_queue_timeout") == 3


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
        params={"ip_precheck": True},
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
    assert publisher.results[0][1].failed_stage == FailureStage.ACCESS_PROBE


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
    assert publisher.results[0][1].failed_stage == FailureStage.COLLECTION


@pytest.mark.asyncio
async def test_access_probe_failure_logs_target_and_credential_id(monkeypatch):
    logged = []

    def capture(message, *args):
        logged.append(message % args if args else message)

    monkeypatch.setattr("core.collection.executor.logger.warning", capture)
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
        params={"ip_precheck": True},
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=1,
        expires_at=999999,
    )

    await executor.execute(request, lease)

    assert any("event=collection_run_summary" in item for item in logged)
    assert any("失败类型=target_unreachable:1" in item for item in logged)
    assert any("失败样本=10.10.69.240|cred-snmp-1|target_unreachable|-" in item for item in logged)
    assert not any("secret-community" in item for item in logged)


@pytest.mark.asyncio
async def test_access_probe_exception_fails_only_current_target(monkeypatch):
    error_logs = []

    def capture_error(message, *args):
        error_logs.append(message % args if args else message)

    monkeypatch.setattr("core.collection.executor.logger.error", capture_error)
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
        params={
            "model_id": "mysql",
            "plugin_name": "mysql_info",
            "ip_precheck": True,
        },
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
    assert len(error_logs) == 1
    assert "event=plugin_exception" in error_logs[0]
    assert "plugin_ref=mysql.config" in error_logs[0]
    assert "plugin_name=mysql_info" in error_logs[0]
    assert ":probe" in error_logs[0]
    assert "secret-do-not-publish" not in error_logs[0]


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
        params={"ip_precheck": True},
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
        params={"ip_precheck": True},
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
        params={"ip_precheck": True},
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
        params={"ip_precheck": True},
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
    assert snapshot["target_started_to_probe_seconds_p99"] >= 0
    assert snapshot["target_started_to_collect_seconds_p99"] >= 0


@pytest.mark.asyncio
async def test_collection_timeout_records_bounded_overshoot():
    class NeverCompletesPlugin:
        async def collect(self, target, credential, context):
            await asyncio.sleep(60)

    metrics = CollectionMetrics()
    publisher = RecordingPublisher()
    plan = ExecutionPlan(
        preflight_timeout_seconds=1,
        probe_timeout_seconds=1,
        collection_timeout_seconds=0.02,
        publish_timeout_seconds=1,
        execution_mode="async",
        capacity_group="snmp",
    )
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=NeverCompletesPlugin(),
        publisher=publisher,
        metrics=metrics,
        plan=plan,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )
    request = CollectionRequest(
        task_id="collect-timeout-overshoot",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "credential-1"},),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    await executor.execute(request, lease)

    snapshot = metrics.snapshot()
    assert publisher.results[0][1].error_code == "plugin_timeout"
    assert 0 <= snapshot["timeout_overshoot_seconds_p99"] < 0.1


@pytest.mark.asyncio
async def test_target_without_matching_credential_has_stable_error(monkeypatch):
    warning_logs = []
    monkeypatch.setattr(
        "core.collection.executor.logger.warning",
        lambda message, *args: warning_logs.append(message % args if args else message),
    )
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
    target_failures = [item for item in warning_logs if "event=target_collection_failed" in item]
    assert len(target_failures) == 1
    assert "target=10.10.69.245" in target_failures[0]
    assert "stage=credential" in target_failures[0]
    assert "error_code=no_matching_credential" in target_failures[0]


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
async def test_result_event_failure_does_not_turn_confirmed_nats_publish_into_unknown():
    async def publish_metrics_batch(entries):
        return {entry[2]["collection_result_id"]: None for entry in entries}

    async def fail_result_event(_event):
        raise ConnectionError("redis unavailable")

    publisher = BufferedResultPublisher(
        NatsResultPublisher(
            metrics_publish_batch=publish_metrics_batch,
            result_event_sink=fail_result_event,
        ),
        capacity=1,
        batch_size=1,
        flush_interval_seconds=0.01,
    )
    request = CollectionRequest(
        task_id="collect-event-failure",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "c1"},),
        params={"plugin_family": "configuration", "model_id": "network"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=RecordingPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1),
    )

    summary = await executor.execute(request, lease)
    await publisher.shutdown()

    assert summary.publish_event_failed == 1
    assert summary.publish_unknown == 0
    assert summary.has_errors is True


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
            publish_queue_timeout_seconds=0.05,
            publish_total_timeout_seconds=0.05,
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
async def test_total_timeout_cancels_queued_result_without_false_unknown_or_late_delivery():
    release = asyncio.Event()
    delivered = []

    class BlockingBatchDelegate:
        async def publish_batch(self, items):
            delivered.extend(item[1].target for item in items)
            await release.wait()

    publisher = BufferedResultPublisher(
        BlockingBatchDelegate(),
        capacity=2,
        batch_size=1,
        flush_interval_seconds=0.01,
    )
    request = CollectionRequest(
        task_id="collect-queued-total-timeout",
        plugin_ref="network.config",
        targets=("10.10.24.1", "10.10.24.2"),
        credentials=({"credential_id": "c1"},),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999, attempt_id="attempt-a")
    metrics = CollectionMetrics()
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=RecordingPlugin(),
        publisher=publisher,
        metrics=metrics,
        settings=TargetExecutorSettings(
            max_active_targets=2,
            target_task_window=2,
            publish_queue_timeout_seconds=0.1,
            publish_total_timeout_seconds=0.02,
            publish_max_attempts=1,
        ),
    )

    summary = await executor.execute(request, lease)
    release.set()
    await publisher.shutdown()

    assert summary.publish_unknown == 1
    assert summary.publish_failed == 1
    assert delivered == ["10.10.24.1"]
    assert metrics.snapshot()["publish_queue_residence_seconds_p99"] > 0


@pytest.mark.asyncio
async def test_safe_publish_retry_reuses_identical_encoded_error_payload(monkeypatch):
    payloads = []
    clock = iter((1000.0, 2000.0, 3000.0))
    monkeypatch.setattr(metrics_helper.time, "time", lambda: next(clock, 3000.0))

    async def publish_metrics_batch(entries):
        payloads.append(entries[0][1])
        result_id = entries[0][2]["collection_result_id"]
        if len(payloads) == 1:
            return {result_id: DefinitelyNotPublishedError("connection unavailable")}
        return {result_id: None}

    class FailingCollectionPlugin:
        async def collect(self, target, credential, context):
            return CollectOutcome(status=CollectOutcomeStatus.FAILED, error_code="collection_failed")

    publisher = BufferedResultPublisher(
        NatsResultPublisher(metrics_publish_batch=publish_metrics_batch),
        capacity=1,
        batch_size=1,
    )
    request = CollectionRequest(
        task_id="collect-stable-retry-payload",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "c1"},),
        params={"plugin_family": "configuration", "model_id": "network"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999, attempt_id="attempt-a")
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=FailingCollectionPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(max_active_targets=1, target_task_window=1, publish_max_attempts=2),
    )

    summary = await executor.execute(request, lease)
    await publisher.shutdown()

    assert summary.publish_succeeded == 1
    assert payloads[0] == payloads[1]


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
