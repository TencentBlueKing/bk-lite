"""有界执行一个 CollectionRun 中的全部目标采集。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from core.collection_runtime import CollectionRequest, RunLease
from core.collection_metrics import CollectionMetrics
from core.credential_policy import CredentialPolicy, InMemoryCredentialStateStore


class PreflightStatus(str, Enum):
    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PreflightResult:
    status: PreflightStatus
    error_code: str = ""
    detail: str = ""


class CollectOutcomeStatus(str, Enum):
    SUCCESS = "success"
    AUTH_FAILED = "auth_failed"
    RETRY_CREDENTIAL = "retry_credential"
    UNREACHABLE = "unreachable"
    FAILED = "failed"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class CollectOutcome:
    status: CollectOutcomeStatus
    value: Any = None
    error_code: str = ""
    detail: str = ""


@dataclass(frozen=True)
class TargetCollectionContext:
    task_id: str
    plugin_ref: str
    fence: int
    params: Mapping[str, Any]
    owner_id: str = ""


@dataclass(frozen=True)
class TargetCollectionResult:
    target: str
    status: str
    attempts: int
    credential_id: str = ""
    error_code: str = ""
    value: Any = None


@dataclass(frozen=True)
class RunSummary:
    total: int
    succeeded: int
    failed: int
    unreachable: int
    deferred: int
    skipped: int


@dataclass(frozen=True)
class TargetExecutorSettings:
    max_active_targets: int = 200
    target_task_window: int = 200
    connect_timeout_seconds: float = 5.0
    plugin_timeout_seconds: float = 60.0
    publish_guard_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_active_targets <= 0:
            raise ValueError("max_active_targets must be greater than zero")
        if self.target_task_window <= 0:
            raise ValueError("target_task_window must be greater than zero")
        if self.connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be greater than zero")
        if self.plugin_timeout_seconds <= 0:
            raise ValueError("plugin_timeout_seconds must be greater than zero")
        if self.publish_guard_seconds <= 0:
            raise ValueError("publish_guard_seconds must be greater than zero")


class PreflightProbe(Protocol):
    async def check(
        self,
        target: str,
        request: CollectionRequest,
        *,
        timeout_seconds: float,
    ) -> PreflightResult: ...


class CollectionPlugin(Protocol):
    async def collect(
        self,
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
    ) -> CollectOutcome: ...


class ResultPublisher(Protocol):
    async def publish(
        self,
        request: CollectionRequest,
        result: TargetCollectionResult,
        lease: RunLease,
    ) -> None: ...


class TargetCheckpointStore(Protocol):
    async def is_completed(
        self, *, task_id: str, plugin_ref: str, target: str
    ) -> bool: ...

    async def is_current(self, lease: RunLease) -> bool: ...

    async def load_pending(
        self, *, task_id: str, plugin_ref: str, target: str
    ) -> TargetCollectionResult | None: ...

    async def mark_publish_pending(
        self, *, plugin_ref: str, result: TargetCollectionResult, lease: RunLease
    ) -> bool: ...

    async def begin_publish(
        self, lease: RunLease, *, guard_seconds: float
    ) -> bool: ...

    async def mark_completed(
        self,
        *,
        plugin_ref: str,
        result: TargetCollectionResult,
        lease: RunLease,
    ) -> bool: ...


class NoopTargetCheckpointStore:
    async def is_completed(
        self, *, task_id: str, plugin_ref: str, target: str
    ) -> bool:
        return False

    async def is_current(self, lease: RunLease) -> bool:
        return True

    async def load_pending(self, *, task_id: str, plugin_ref: str, target: str):
        return None

    async def mark_publish_pending(self, *, plugin_ref, result, lease) -> bool:
        return True

    async def begin_publish(self, lease, *, guard_seconds: float) -> bool:
        return True

    async def mark_completed(
        self,
        *,
        plugin_ref: str,
        result: TargetCollectionResult,
        lease: RunLease,
    ) -> bool:
        return True


class TargetActivityTracker:
    def __init__(self) -> None:
        self.active = 0
        self.peak = 0
        self._lock = asyncio.Lock()

    async def enter(self) -> None:
        async with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)

    async def exit(self) -> None:
        async with self._lock:
            self.active = max(0, self.active - 1)


class TargetWorkerBudget:
    """跨运行限制已创建且未完成的目标 worker 协程数量。"""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        self._capacity = capacity
        self._available = capacity
        self._condition = asyncio.Condition()
        self.active = 0
        self.peak = 0

    async def reserve(self, desired: int) -> int:
        async with self._condition:
            while self._available <= 0:
                await self._condition.wait()
            reserved = min(max(1, desired), self._available)
            self._available -= reserved
            self.active += reserved
            self.peak = max(self.peak, self.active)
            return reserved

    async def release(self, count: int) -> None:
        async with self._condition:
            released = min(max(0, count), self.active)
            self.active -= released
            self._available = min(
                self._capacity, self._available + released
            )
            self._condition.notify_all()


class TargetCollectionExecutor:
    """以固定数量 worker 流式消费目标，避免为所有目标创建 Task。"""

    def __init__(
        self,
        *,
        preflight: PreflightProbe,
        plugin: CollectionPlugin,
        publisher: ResultPublisher,
        checkpoint_store: TargetCheckpointStore | None = None,
        credential_policy: CredentialPolicy | None = None,
        target_semaphore: asyncio.Semaphore | None = None,
        worker_budget: TargetWorkerBudget | None = None,
        activity_tracker: TargetActivityTracker | None = None,
        metrics: CollectionMetrics | None = None,
        settings: TargetExecutorSettings | None = None,
    ) -> None:
        self._preflight = preflight
        self._plugin = plugin
        self._publisher = publisher
        self._checkpoint_store = (
            checkpoint_store or NoopTargetCheckpointStore()
        )
        self._credential_policy = credential_policy or CredentialPolicy(
            store=InMemoryCredentialStateStore()
        )
        self._settings = settings or TargetExecutorSettings()
        self._target_semaphore = target_semaphore or asyncio.Semaphore(
            self._settings.max_active_targets
        )
        self._activity_tracker = activity_tracker or TargetActivityTracker()
        self._worker_budget = worker_budget or TargetWorkerBudget(
            self._settings.target_task_window
        )
        self._metrics = metrics or CollectionMetrics()

    async def execute(
        self, request: CollectionRequest, lease: RunLease
    ) -> RunSummary:
        targets = tuple(request.targets)
        results: list[TargetCollectionResult | None] = [None] * len(targets)
        skipped = 0
        next_index = 0
        iterator_lock = asyncio.Lock()

        async def worker() -> None:
            nonlocal next_index, skipped
            while True:
                async with iterator_lock:
                    if next_index >= len(targets):
                        return
                    index = next_index
                    next_index += 1
                if await self._checkpoint_store.is_completed(
                    task_id=request.task_id,
                    plugin_ref=request.plugin_ref,
                    target=targets[index],
                ):
                    skipped += 1
                    continue
                async with self._target_semaphore:
                    await self._activity_tracker.enter()
                    try:
                        result = await self._checkpoint_store.load_pending(
                            task_id=request.task_id,
                            plugin_ref=request.plugin_ref,
                            target=targets[index],
                        )
                        if result is None:
                            result = await self._execute_target(
                                request, targets[index], lease
                            )
                            if not await self._checkpoint_store.mark_publish_pending(
                                plugin_ref=request.plugin_ref,
                                result=result,
                                lease=lease,
                            ):
                                raise RuntimeError("lost run lease while saving pending result")
                    finally:
                        await self._activity_tracker.exit()
                results[index] = result
                if not await self._checkpoint_store.begin_publish(
                    lease, guard_seconds=self._settings.publish_guard_seconds
                ):
                    raise RuntimeError("lost run lease before result publish")
                try:
                    await self._publisher.publish(request, result, lease)
                except Exception:
                    self._metrics.increment("result_publish_failure_total")
                    raise
                if not await self._checkpoint_store.mark_completed(
                    plugin_ref=request.plugin_ref,
                    result=result,
                    lease=lease,
                ):
                    raise RuntimeError("lost run lease while saving checkpoint")

        desired_workers = min(
            len(targets), self._settings.target_task_window
        )
        worker_count = await self._worker_budget.reserve(desired_workers)
        worker_tasks = [
            asyncio.create_task(
                worker(),
                name=f"target-worker:{request.task_id}:{index}",
            )
            for index in range(worker_count)
        ]
        try:
            await asyncio.gather(*worker_tasks)
        except BaseException:
            for task in worker_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*worker_tasks, return_exceptions=True)
            raise
        finally:
            await self._worker_budget.release(worker_count)
        completed = tuple(result for result in results if result is not None)
        return RunSummary(
            total=len(targets),
            succeeded=sum(result.status == "success" for result in completed),
            failed=sum(result.status == "failed" for result in completed),
            unreachable=sum(
                result.status == "unreachable" for result in completed
            ),
            deferred=sum(result.status == "deferred" for result in completed),
            skipped=skipped,
        )

    async def _execute_target(
        self,
        request: CollectionRequest,
        target: str,
        lease: RunLease,
    ) -> TargetCollectionResult:
        preflight_started = time.monotonic()
        try:
            async with asyncio.timeout(
                self._settings.connect_timeout_seconds
            ):
                preflight = await self._preflight.check(
                    target,
                    request,
                    timeout_seconds=self._settings.connect_timeout_seconds,
                )
        except TimeoutError:
            preflight = PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="preflight_timeout",
            )
        finally:
            self._metrics.increment(
                "preflight_duration_seconds_total",
                time.monotonic() - preflight_started,
            )
            self._metrics.increment("preflight_total")

        if preflight.status == PreflightStatus.UNREACHABLE:
            self._metrics.increment("target_unreachable_total")
            return TargetCollectionResult(
                target=target,
                status="unreachable",
                attempts=0,
                error_code=preflight.error_code or "target_unreachable",
            )

        credentials = await self._credential_policy.eligible_credentials(
            request, target
        )
        if not credentials:
            self._metrics.increment("credential_cooldown_total")
            next_retry_at = await self._credential_policy.next_retry_at(
                request, target
            )
            return TargetCollectionResult(
                target=target,
                status="failed",
                attempts=0,
                error_code="no_valid_credential",
                value={"next_retry_at": next_retry_at},
            )
        context = TargetCollectionContext(
            task_id=request.task_id,
            plugin_ref=request.plugin_ref,
            fence=lease.fence,
            params=request.params,
            owner_id=lease.owner_id,
        )
        attempts = 0
        for credential in credentials:
            attempts += 1
            self._metrics.increment("credential_attempt_total")
            plugin_started = time.monotonic()
            try:
                async with asyncio.timeout(
                    self._settings.plugin_timeout_seconds
                ):
                    outcome = await self._plugin.collect(
                        target,
                        credential,
                        context,
                    )
            except TimeoutError:
                self._metrics.increment("plugin_timeout_total")
                outcome = CollectOutcome(
                    status=CollectOutcomeStatus.FAILED,
                    error_code="plugin_timeout",
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - 收敛插件异常为稳定结果
                outcome = CollectOutcome(
                    status=CollectOutcomeStatus.FAILED,
                    error_code="plugin_error",
                    detail=type(error).__name__,
                )
            finally:
                self._metrics.increment(
                    "plugin_duration_seconds_total",
                    time.monotonic() - plugin_started,
                )
                self._metrics.increment("plugin_total")

            credential_id = str(credential.get("credential_id") or "")
            if outcome.status == CollectOutcomeStatus.SUCCESS:
                await self._credential_policy.record_success(
                    request, target, credential
                )
                return TargetCollectionResult(
                    target=target,
                    status="success",
                    attempts=attempts,
                    credential_id=credential_id,
                    value=outcome.value,
                )
            if outcome.status == CollectOutcomeStatus.DEFERRED:
                return TargetCollectionResult(
                    target=target,
                    status="deferred",
                    attempts=attempts,
                    credential_id=credential_id,
                    value=outcome.value,
                )
            if outcome.status == CollectOutcomeStatus.AUTH_FAILED:
                await self._credential_policy.record_auth_failure(
                    request,
                    target,
                    credential,
                    error_code=outcome.error_code or "authentication_failed",
                )
                continue
            if outcome.status == CollectOutcomeStatus.RETRY_CREDENTIAL:
                continue
            if outcome.status == CollectOutcomeStatus.UNREACHABLE:
                return TargetCollectionResult(
                    target=target,
                    status="unreachable",
                    attempts=attempts,
                    error_code=outcome.error_code or "target_unreachable",
                )
            return TargetCollectionResult(
                target=target,
                status="failed",
                attempts=attempts,
                credential_id=credential_id,
                error_code=outcome.error_code or "collection_failed",
                value=outcome.value,
            )

        return TargetCollectionResult(
            target=target,
            status="failed",
            attempts=attempts,
            error_code="credentials_exhausted",
        )
