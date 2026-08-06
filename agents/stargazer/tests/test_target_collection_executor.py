import asyncio

import pytest

from core.collection_runtime import CollectionRequest, RunLease
from core.credential_policy import CredentialPolicy, InMemoryCredentialStateStore
from core.target_collection_executor import (
    CollectOutcome,
    CollectOutcomeStatus,
    PreflightResult,
    PreflightStatus,
    TargetCollectionExecutor,
    TargetExecutorSettings,
    TargetWorkerBudget,
)


class UnreachablePreflight:
    async def check(self, target, request, *, timeout_seconds):
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
    async def check(self, target, request, *, timeout_seconds):
        return PreflightResult(status=PreflightStatus.REACHABLE)


class RecordingCheckpointStore:
    def __init__(self, *, completed=(), current=True):
        self.completed = set(completed)
        self.current = current
        self.saved = []
        self.pending = {}

    async def is_completed(self, *, task_id, plugin_ref, target):
        return (task_id, plugin_ref, target) in self.completed

    async def is_current(self, lease):
        return self.current

    async def load_pending(self, *, task_id, plugin_ref, target):
        return self.pending.get((task_id, plugin_ref, target))

    async def mark_publish_pending(self, *, plugin_ref, result, lease):
        if not self.current:
            return False
        self.pending[(lease.task_id, plugin_ref, result.target)] = result
        return True

    async def begin_publish(self, lease, *, guard_seconds):
        return self.current

    async def mark_completed(self, *, plugin_ref, result, lease):
        self.saved.append((plugin_ref, result, lease))
        self.pending.pop((lease.task_id, plugin_ref, result.target), None)
        return self.current


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
        "credential-1",
        "credential-3",
    ]


@pytest.mark.asyncio
async def test_completed_target_is_skipped_during_takeover():
    plugin = RecordingPlugin()
    publisher = RecordingPublisher()
    request = CollectionRequest(
        task_id="collect-resume",
        plugin_ref="mysql.config",
        targets=("10.10.24.1", "10.10.24.2"),
        credentials=({"credential_id": "credential-1"},),
    )
    checkpoint_store = RecordingCheckpointStore(
        completed={(request.task_id, request.plugin_ref, "10.10.24.1")}
    )
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=plugin,
        publisher=publisher,
        checkpoint_store=checkpoint_store,
        settings=TargetExecutorSettings(max_active_targets=2, target_task_window=2),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-b",
        fence=2,
        expires_at=999999,
    )

    summary = await executor.execute(request, lease)

    assert [call[0] for call in plugin.calls] == ["10.10.24.2"]
    assert [entry[1].target for entry in publisher.results] == ["10.10.24.2"]
    assert [entry[1].target for entry in checkpoint_store.saved] == [
        "10.10.24.2"
    ]
    assert summary.total == 2
    assert summary.skipped == 1


@pytest.mark.asyncio
async def test_lost_lease_does_not_publish_or_checkpoint_result():
    plugin = RecordingPlugin()
    publisher = RecordingPublisher()
    checkpoint_store = RecordingCheckpointStore(current=False)
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=plugin,
        publisher=publisher,
        checkpoint_store=checkpoint_store,
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

    with pytest.raises(RuntimeError, match="lost run lease"):
        await executor.execute(request, lease)

    assert publisher.results == []
    assert checkpoint_store.saved == []


@pytest.mark.asyncio
async def test_publish_failure_keeps_pending_result_for_retry_without_recollect():
    plugin = RecordingPlugin()
    checkpoints = RecordingCheckpointStore()

    class FailingPublisher:
        async def publish(self, request, result, lease):
            raise ConnectionError("nats unavailable")

    request = CollectionRequest(
        task_id="collect-pending", plugin_ref="mysql.config",
        targets=("10.10.24.1",), credentials=({"credential_id": "c1"},),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)
    first = TargetCollectionExecutor(
        preflight=ReachablePreflight(), plugin=plugin,
        publisher=FailingPublisher(), checkpoint_store=checkpoints,
    )
    with pytest.raises(ConnectionError):
        await first.execute(request, lease)

    publisher = RecordingPublisher()
    retry = TargetCollectionExecutor(
        preflight=ReachablePreflight(), plugin=plugin,
        publisher=publisher, checkpoint_store=checkpoints,
    )
    await retry.execute(request, lease)

    assert len(plugin.calls) == 1
    assert len(publisher.results) == 1
    assert checkpoints.saved[0][1].target == "10.10.24.1"


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
        async def check(self, target, request, *, timeout_seconds):
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
