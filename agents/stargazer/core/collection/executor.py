"""有界执行一个 CollectionRun 中的全部目标采集。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace

from core.collection.contracts import (
    AccessProbe,
    AccessProbeResult,
    AccessProbeStatus,
    CollectionPlugin,
    CollectOutcome,
    CollectOutcomeStatus,
    CredentialFailureResult,
    PreflightProbe,
    PreflightResult,
    PreflightStatus,
    ResultPublisher,
    RunSummary,
    TargetCollectionContext,
    TargetCollectionResult,
    TargetExecutorSettings,
)
from core.collection.credential_policy import CredentialPolicy, InMemoryCredentialStateStore
from core.collection.execution_plan import ExecutionPlan
from core.collection.metrics import CollectionMetrics
from core.collection.result_publisher import FuturePublishReceipt, ImmediateResultPublishQueue
from core.collection.runtime import CollectionRequest, RunLease
from core.collection.scheduler import CollectionScheduler
from core.infra.redis_client import is_credential_state_redis_error
from core.logger import logger

# 兼容旧 import：执行器专属符号仍由此导出；领域类型请优先 from core.collection.contracts
__all__ = [
    "AccessProbe",
    "AccessProbeResult",
    "AccessProbeStatus",
    "CollectOutcome",
    "CollectOutcomeStatus",
    "CollectionPlugin",
    "PreflightProbe",
    "PreflightResult",
    "PreflightStatus",
    "ResultPublisher",
    "RunSummary",
    "TargetActivityTracker",
    "TargetCollectionContext",
    "TargetCollectionExecutor",
    "TargetCollectionResult",
    "TargetExecutorSettings",
    "TargetWorkerBudget",
]


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
    """跨运行限制已创建且未完成的目标 worker 协程数量。

    capacity=0 表示不限制（按 desired 全量发放）。
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 0:
            raise ValueError("capacity must be >= 0 (0 means unlimited)")
        self._unlimited = capacity == 0
        self._capacity = capacity
        self._available = 0 if self._unlimited else capacity
        self._condition = asyncio.Condition()
        self.active = 0
        self.peak = 0

    async def reserve(self, desired: int) -> int:
        async with self._condition:
            wanted = max(1, desired)
            if self._unlimited:
                self.active += wanted
                self.peak = max(self.peak, self.active)
                return wanted
            while self._available <= 0:
                await self._condition.wait()
            reserved = min(wanted, self._available)
            self._available -= reserved
            self.active += reserved
            self.peak = max(self.peak, self.active)
            return reserved

    async def release(self, count: int) -> None:
        async with self._condition:
            released = min(max(0, count), self.active)
            self.active -= released
            if not self._unlimited:
                self._available = min(self._capacity, self._available + released)
            self._condition.notify_all()


class _UnlimitedTargetGate:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def unlimited_target_gate() -> _UnlimitedTargetGate:
    return _UnlimitedTargetGate()


@dataclass(frozen=True)
class _PendingPublish:
    index: int
    result: TargetCollectionResult
    receipt: object
    started_at: float
    deadline: float


class TargetCollectionExecutor:
    """以固定数量 worker 流式消费目标，避免为所有目标创建 Task。"""

    def __init__(
        self,
        *,
        preflight: PreflightProbe,
        access_probe: AccessProbe | None = None,
        plugin: CollectionPlugin,
        publisher: ResultPublisher,
        credential_policy: CredentialPolicy | None = None,
        target_semaphore: asyncio.Semaphore | None = None,
        worker_budget: TargetWorkerBudget | None = None,
        activity_tracker: TargetActivityTracker | None = None,
        metrics: CollectionMetrics | None = None,
        settings: TargetExecutorSettings | None = None,
        plan: ExecutionPlan | None = None,
        scheduler: CollectionScheduler | None = None,
    ) -> None:
        self._preflight = preflight
        # None = 无廉价 AccessProbe，CredentialAttempt 直接 collect
        self._access_probe = access_probe
        self._plugin = plugin
        self._publisher = publisher if callable(getattr(publisher, "enqueue", None)) else ImmediateResultPublishQueue(publisher)
        self._credential_policy = credential_policy or CredentialPolicy(store=InMemoryCredentialStateStore())
        self._settings = settings or TargetExecutorSettings()
        self._plan = plan or ExecutionPlan(
            preflight_enabled=self._settings.access_probe_enabled,
            preflight_timeout_seconds=self._settings.connect_timeout_seconds,
            probe_timeout_seconds=self._settings.connect_timeout_seconds,
            collection_timeout_seconds=self._settings.plugin_timeout_seconds,
            publish_timeout_seconds=self._settings.publish_guard_seconds,
            execution_mode="sync",
            capacity_group="default",
        )
        if target_semaphore is not None:
            self._target_semaphore = target_semaphore
        elif scheduler is not None:
            # 全局调度器是生产路径的唯一目标准入；避免重复 semaphore 形成双重容量语义。
            self._target_semaphore = unlimited_target_gate()
        elif self._settings.max_active_targets <= 0:
            self._target_semaphore = unlimited_target_gate()
        else:
            self._target_semaphore = asyncio.Semaphore(self._settings.max_active_targets)
        self._activity_tracker = activity_tracker or TargetActivityTracker()
        self._worker_budget = worker_budget or TargetWorkerBudget(self._settings.target_task_window)
        self._metrics = metrics or CollectionMetrics()
        self._scheduler = scheduler

    async def execute(self, request: CollectionRequest, lease: RunLease) -> RunSummary:
        targets = request.targets
        results: dict[int, TargetCollectionResult] = {}
        publish_statuses: dict[int, str] = {}
        skipped = 0

        async def execute_index(index: int) -> _PendingPublish:
            # 目标槽位只覆盖目标执行与进入发布路径；发布异常在目标内隔离。
            try:
                async with self._target_semaphore:
                    await self._activity_tracker.enter()
                    try:
                        result = await self._execute_target(request, targets[index], lease)
                    finally:
                        await self._activity_tracker.exit()
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - 单目标框架异常不得取消 Run
                self._metrics.increment("target_execution_error_total")
                logger.error(
                    "event=target_execution_failed task_id=%s target=%s " "error_type=%s",
                    request.task_id,
                    targets[index],
                    type(error).__name__,
                )
                result = TargetCollectionResult(
                    target=targets[index],
                    status="failed",
                    attempts=0,
                    error_code="target_execution_error",
                )
            self._metrics.increment(f"execution_mode_{self._plan.execution_mode}_{result.status}_total")
            self._metrics.increment(f"capacity_group_{self._plan.capacity_group}_{result.status}_total")
            return await self._enqueue_publish(index, request, result, lease)

        async def finish_publish(pending: _PendingPublish) -> tuple[int, str]:
            current = pending
            publish_status = "failed"
            for attempt in range(self._settings.publish_max_attempts):
                try:
                    async with asyncio.timeout_at(current.deadline):
                        await current.receipt.wait()
                    self._metrics.observe(
                        "publish_duration_seconds",
                        asyncio.get_running_loop().time() - current.started_at,
                    )
                    return current.index, "succeeded"
                except Exception as error:  # noqa: BLE001 - 单目标有限重试
                    if isinstance(error, TimeoutError) and asyncio.get_running_loop().time() >= current.deadline:
                        self._metrics.increment("publish_timeout_total")
                    self._metrics.observe(
                        "publish_duration_seconds",
                        asyncio.get_running_loop().time() - current.started_at,
                    )
                    self._metrics.increment("result_publish_failure_total")
                    if bool(getattr(error, "delivery_detected", True)):
                        publish_status = "unknown"
                        break
                    if attempt + 1 < self._settings.publish_max_attempts:
                        self._metrics.increment("result_publish_retry_total")
                        current = await self._enqueue_publish(
                            current.index,
                            request,
                            current.result,
                            lease,
                            started_at=current.started_at,
                            deadline=current.deadline,
                        )
                        continue
                    publish_status = "failed"
                    break
            logger.warning(
                "event=result_publish_%s task_id=%s target=%s",
                publish_status,
                request.task_id,
                current.result.target,
            )
            return current.index, publish_status

        if self._scheduler is not None:
            scheduled = await self._scheduler.execute(
                f"{request.task_id}:{lease.fence}",
                range(len(targets)),
                execute_index,
            )
            pending_publishes = scheduled
            for pending in scheduled:
                results[pending.index] = pending.result
        else:
            next_index = 0
            iterator_lock = asyncio.Lock()

            async def worker() -> None:
                nonlocal next_index
                while True:
                    async with iterator_lock:
                        if next_index >= len(targets):
                            return
                        index = next_index
                        next_index += 1
                    pending = await execute_index(index)
                    results[pending.index] = pending.result
                    pending_publishes.append(pending)

            window = self._settings.target_task_window
            desired_workers = max(1, len(targets)) if window <= 0 else (min(len(targets), window) if targets else 1)
            worker_count = await self._worker_budget.reserve(desired_workers)
            pending_publishes = []
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
        for pending in pending_publishes:
            index, publish_status = await finish_publish(pending)
            publish_statuses[index] = publish_status
        completed = tuple(results.values())
        for status in publish_statuses.values():
            self._metrics.increment(f"publish_{status}_total")
        return RunSummary(
            total=len(targets),
            collection_succeeded=sum(result.status == "success" for result in completed),
            collection_failed=sum(result.status == "failed" for result in completed),
            unreachable=sum(result.status == "unreachable" for result in completed),
            deferred=sum(result.status == "deferred" for result in completed),
            skipped=skipped,
            publish_succeeded=sum(status == "succeeded" for status in publish_statuses.values()),
            publish_failed=sum(status == "failed" for status in publish_statuses.values()),
            publish_unknown=sum(status == "unknown" for status in publish_statuses.values()),
        )

    async def _enqueue_publish(
        self,
        index: int,
        request: CollectionRequest,
        result: TargetCollectionResult,
        lease: RunLease,
        *,
        started_at: float | None = None,
        deadline: float | None = None,
    ) -> _PendingPublish:
        loop = asyncio.get_running_loop()
        attempt_started_at = loop.time()
        started_at = attempt_started_at if started_at is None else started_at
        deadline = started_at + self._plan.publish_timeout_seconds if deadline is None else deadline
        try:
            async with asyncio.timeout_at(deadline):
                receipt = await self._publisher.enqueue(request, result, lease)
        except Exception as error:  # noqa: BLE001 - 交由统一发布重试处理
            completion = loop.create_future()
            completion.set_exception(error)
            receipt = FuturePublishReceipt(completion)
        self._metrics.observe("publish_enqueue_duration_seconds", loop.time() - attempt_started_at)
        return _PendingPublish(
            index=index,
            result=result,
            receipt=receipt,
            started_at=started_at,
            deadline=deadline,
        )

    async def _execute_target(
        self,
        request: CollectionRequest,
        target: str,
        lease: RunLease,
    ) -> TargetCollectionResult:
        preflight = await self._run_preflight(request, target)
        if preflight.status == PreflightStatus.UNREACHABLE:
            self._metrics.increment("target_unreachable_total")
            error_code = preflight.error_code or "target_unreachable"
            logger.info(
                "🚫 event=target_unreachable task_id=%s target=%s " "reason=%s detail=%s",
                request.task_id,
                target,
                error_code,
                preflight.detail or "-",
            )
            return TargetCollectionResult(
                target=target,
                status="unreachable",
                attempts=0,
                error_code=error_code,
            )

        credentials = await self._load_eligible_credentials(request, target)
        if credentials is None:
            return TargetCollectionResult(
                target=target,
                status="failed",
                attempts=0,
                error_code="credential_state_unavailable",
            )
        if not credentials:
            return await self._no_credential_result(request, target)

        context_params = dict(request.params)
        if preflight.connect_host:
            context_params["_validated_connect_host"] = preflight.connect_host
        context = TargetCollectionContext(
            task_id=request.task_id,
            plugin_ref=request.plugin_ref,
            fence=lease.fence,
            params=context_params,
            owner_id=lease.owner_id,
            attempt_id=lease.attempt_id,
        )
        return await self._run_credential_attempts(request, target, credentials, context)

    async def _load_eligible_credentials(self, request: CollectionRequest, target: str):
        try:
            return await self._credential_policy.eligible_credentials(request, target)
        except Exception as exc:  # noqa: BLE001 - 凭据状态失败隔离为单目标
            if not is_credential_state_redis_error(exc):
                raise
            self._metrics.increment("credential_state_redis_error_total")
            logger.warning(
                "event=credential_state_unavailable task_id=%s target=%s " "error_type=%s detail=%s",
                request.task_id,
                target,
                type(exc).__name__,
                str(exc)[:200] or "-",
            )
            return None

    async def _safe_record_success(
        self,
        request: CollectionRequest,
        target: str,
        credential,
    ) -> None:
        try:
            await self._credential_policy.record_success(request, target, credential)
        except Exception as exc:  # noqa: BLE001 - 写亲和失败不阻断成功结果
            if not is_credential_state_redis_error(exc):
                raise
            self._metrics.increment("credential_state_redis_error_total")
            logger.warning(
                "event=credential_success_persist_failed task_id=%s target=%s " "error_type=%s",
                request.task_id,
                target,
                type(exc).__name__,
            )

    async def _safe_record_auth_failure(
        self,
        request: CollectionRequest,
        target: str,
        credential,
        *,
        error_code: str,
    ) -> None:
        try:
            await self._credential_policy.record_auth_failure(
                request,
                target,
                credential,
                error_code=error_code,
            )
        except Exception as exc:  # noqa: BLE001 - 写冷冻失败不阻断轮换
            if not is_credential_state_redis_error(exc):
                raise
            self._metrics.increment("credential_state_redis_error_total")
            logger.warning(
                "event=credential_failure_persist_failed task_id=%s target=%s " "error_type=%s",
                request.task_id,
                target,
                type(exc).__name__,
            )

    async def _run_preflight(self, request: CollectionRequest, target: str) -> PreflightResult:
        preflight_started = time.monotonic()
        try:
            async with asyncio.timeout(self._plan.preflight_timeout_seconds):
                return await self._preflight.check(
                    target,
                    request,
                    timeout_seconds=self._plan.preflight_timeout_seconds,
                )
        except TimeoutError:
            self._metrics.increment("preflight_timeout_total")
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="preflight_timeout",
            )
        finally:
            duration = time.monotonic() - preflight_started
            self._metrics.increment(
                "preflight_duration_seconds_total",
                duration,
            )
            self._metrics.observe("preflight_duration_seconds", duration)
            self._metrics.increment("preflight_total")

    async def _no_credential_result(self, request: CollectionRequest, target: str) -> TargetCollectionResult:
        self._metrics.increment("credential_cooldown_total")
        next_retry_at = None
        try:
            next_retry_at = await self._credential_policy.next_retry_at(request, target)
        except Exception as exc:  # noqa: BLE001 - 读冷冻时间失败不影响结果
            if not is_credential_state_redis_error(exc):
                raise
            self._metrics.increment("credential_state_redis_error_total")
        has_matching_credential = bool(self._credential_policy.matching_credentials(request, target))
        error_code = "no_valid_credential" if has_matching_credential else "no_matching_credential"
        logger.info(
            "🚫 event=target_no_credential task_id=%s target=%s error_code=%s " "next_retry_at=%s",
            request.task_id,
            target,
            error_code,
            next_retry_at,
        )
        return TargetCollectionResult(
            target=target,
            status="failed",
            attempts=0,
            error_code=error_code,
            value={"next_retry_at": next_retry_at},
        )

    async def _run_credential_attempts(
        self,
        request: CollectionRequest,
        target: str,
        credentials,
        context: TargetCollectionContext,
    ) -> TargetCollectionResult:
        attempts = 0
        no_response_attempts = 0
        credential_failures = []
        for credential in credentials:
            attempts += 1
            self._metrics.increment("credential_attempt_total")
            credential_id = str(credential.get("credential_id") or "")

            access = await self._run_access_probe(target, credential, context, attempts)
            if isinstance(access, TargetCollectionResult):
                return replace(access, credential_failures=tuple(credential_failures))

            probe_decision = await self._apply_access_probe(
                request,
                target,
                credential,
                access,
                attempts=attempts,
                no_response_attempts=no_response_attempts,
            )
            if probe_decision.credential_failure:
                credential_failures.append(probe_decision.credential_failure)
            if probe_decision.action == "return":
                return replace(
                    probe_decision.result,
                    credential_failures=tuple(credential_failures),
                )
            if probe_decision.action == "continue":
                no_response_attempts = probe_decision.no_response_attempts
                continue
            no_response_attempts = probe_decision.no_response_attempts

            outcome = await self._run_collect(target, credential, context)
            collect_decision = await self._apply_collect_outcome(
                request,
                target,
                credential,
                outcome,
                attempts=attempts,
                credential_id=credential_id,
            )
            if collect_decision.credential_failure:
                credential_failures.append(collect_decision.credential_failure)
            if collect_decision.action == "return":
                return replace(
                    collect_decision.result,
                    credential_failures=tuple(credential_failures),
                )
            # continue → 下一凭据

        logger.info(
            "🚫 event=credentials_exhausted task_id=%s target=%s attempts=%s",
            request.task_id,
            target,
            attempts,
        )
        return TargetCollectionResult(
            target=target,
            status="failed",
            attempts=attempts,
            error_code="credentials_exhausted",
            credential_failures=tuple(credential_failures),
        )

    async def _run_access_probe(
        self,
        target: str,
        credential,
        context: TargetCollectionContext,
        attempts: int,
    ) -> AccessProbeResult | TargetCollectionResult:
        if not self._plan.preflight_enabled or self._access_probe is None:
            return AccessProbeResult(status=AccessProbeStatus.NOT_SUPPORTED)

        access_probe_started = time.monotonic()
        try:
            async with asyncio.timeout(self._plan.probe_timeout_seconds):
                return await self._access_probe.probe(
                    target,
                    credential,
                    context,
                    timeout_seconds=self._plan.probe_timeout_seconds,
                )
        except TimeoutError:
            self._metrics.increment("access_probe_timeout_total")
            self._metrics.increment("probe_timeout_total")
            return AccessProbeResult(
                status=AccessProbeStatus.NO_RESPONSE,
                error_code="access_probe_timeout",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 不把 Adapter 异常正文写入结果
            self._metrics.increment("access_probe_error_total")
            credential_id = str(credential.get("credential_id") or "")
            # 只记异常类型与短消息，便于排障；凭据值不应出现在异常文本中
            logger.info(
                "🚫 event=access_probe_failed task_id=%s target=%s "
                "credential_id=%s probe_status=error error_code=access_probe_error "
                "error_type=%s error=%s",
                context.task_id,
                target,
                credential_id or "-",
                type(exc).__name__,
                str(exc)[:200] or "-",
            )
            return TargetCollectionResult(
                target=target,
                status="failed",
                attempts=attempts,
                credential_id=credential_id,
                error_code="access_probe_error",
            )
        finally:
            duration = time.monotonic() - access_probe_started
            self._metrics.increment(
                "access_probe_duration_seconds_total",
                duration,
            )
            self._metrics.observe("access_probe_duration_seconds", duration)
            self._metrics.increment("access_probe_total")

    async def _apply_access_probe(
        self,
        request: CollectionRequest,
        target: str,
        credential,
        access: AccessProbeResult,
        *,
        attempts: int,
        no_response_attempts: int,
    ):
        credential_id = str(credential.get("credential_id") or "")
        if access.status == AccessProbeStatus.NOT_SUPPORTED:
            return _AttemptDecision(action="collect", no_response_attempts=no_response_attempts)
        if access.status in {
            AccessProbeStatus.AUTH_FAILED,
            AccessProbeStatus.CAPABILITY_DENIED,
        }:
            error_code = access.error_code or access.status.value
            await self._safe_record_auth_failure(
                request,
                target,
                credential,
                error_code=error_code,
            )
            logger.info(
                "🚫 event=access_probe_failed task_id=%s target=%s " "credential_id=%s probe_status=%s error_code=%s action=rotate",
                request.task_id,
                target,
                credential_id or "-",
                access.status.value,
                error_code,
            )
            return _AttemptDecision(
                action="continue",
                no_response_attempts=no_response_attempts,
                credential_failure=CredentialFailureResult(
                    credential_id=credential_id,
                    error_code=error_code,
                ),
            )
        if access.status == AccessProbeStatus.NO_RESPONSE:
            no_response_attempts += 1
            logger.info(
                "🚫 event=access_probe_failed task_id=%s target=%s " "credential_id=%s probe_status=%s error_code=%s " "no_response_attempts=%s",
                request.task_id,
                target,
                credential_id or "-",
                access.status.value,
                access.error_code or access.status.value,
                no_response_attempts,
            )
            limit = self._settings.max_no_response_attempts
            if limit and no_response_attempts >= limit:
                return _AttemptDecision(
                    action="return",
                    result=TargetCollectionResult(
                        target=target,
                        status="failed",
                        attempts=attempts,
                        credential_id=credential_id,
                        error_code="no_response_attempt_limit",
                    ),
                    no_response_attempts=no_response_attempts,
                )
            return _AttemptDecision(action="continue", no_response_attempts=no_response_attempts)
        if access.status == AccessProbeStatus.TARGET_UNREACHABLE:
            logger.info(
                "🚫 event=target_unreachable task_id=%s target=%s " "credential_id=%s reason=%s",
                request.task_id,
                target,
                credential_id or "-",
                access.error_code or "target_unreachable",
            )
            return _AttemptDecision(
                action="return",
                result=TargetCollectionResult(
                    target=target,
                    status="unreachable",
                    attempts=attempts,
                    credential_id=credential_id,
                    error_code=access.error_code or "target_unreachable",
                ),
                no_response_attempts=no_response_attempts,
            )
        if access.status == AccessProbeStatus.RATE_LIMITED:
            logger.info(
                "🚫 event=access_probe_failed task_id=%s target=%s " "credential_id=%s probe_status=%s error_code=%s action=defer",
                request.task_id,
                target,
                credential_id or "-",
                access.status.value,
                access.error_code or "rate_limited",
            )
            return _AttemptDecision(
                action="return",
                result=TargetCollectionResult(
                    target=target,
                    status="deferred",
                    attempts=attempts,
                    credential_id=credential_id,
                    error_code=access.error_code or "rate_limited",
                ),
                no_response_attempts=no_response_attempts,
            )
        if access.status in {
            AccessProbeStatus.SERVICE_UNAVAILABLE,
            AccessProbeStatus.TLS_VALIDATION_FAILED,
            AccessProbeStatus.PROTOCOL_MISMATCH,
            AccessProbeStatus.MISCONFIGURED,
        }:
            logger.info(
                "🚫 event=access_probe_failed task_id=%s target=%s " "credential_id=%s probe_status=%s error_code=%s action=stop",
                request.task_id,
                target,
                credential_id or "-",
                access.status.value,
                access.error_code or access.status.value,
            )
            return _AttemptDecision(
                action="return",
                result=TargetCollectionResult(
                    target=target,
                    status="failed",
                    attempts=attempts,
                    credential_id=credential_id,
                    error_code=access.error_code or access.status.value,
                ),
                no_response_attempts=no_response_attempts,
            )
        if access.status != AccessProbeStatus.READY:
            logger.info(
                "🚫 event=access_probe_failed task_id=%s target=%s " "credential_id=%s probe_status=%s error_code=access_probe_misconfigured",
                request.task_id,
                target,
                credential_id or "-",
                access.status.value,
            )
            return _AttemptDecision(
                action="return",
                result=TargetCollectionResult(
                    target=target,
                    status="failed",
                    attempts=attempts,
                    credential_id=credential_id,
                    error_code="access_probe_misconfigured",
                ),
                no_response_attempts=no_response_attempts,
            )
        return _AttemptDecision(action="collect", no_response_attempts=no_response_attempts)

    async def _run_collect(
        self,
        target: str,
        credential,
        context: TargetCollectionContext,
    ) -> CollectOutcome:
        plugin_started = time.monotonic()
        mode = self._plan.execution_mode
        group = self._plan.capacity_group
        self._metrics.increment(f"execution_mode_{mode}_total")
        self._metrics.increment(f"capacity_group_{group}_total")
        if mode == "sync":
            self._metrics.add_gauge("sync_calls_in_flight", 1)
        try:
            async with asyncio.timeout(self._plan.collection_timeout_seconds):
                return await self._plugin.collect(
                    target,
                    credential,
                    context,
                )
        except TimeoutError:
            self._metrics.increment("plugin_timeout_total")
            self._metrics.increment("collection_timeout_total")
            self._metrics.increment(f"execution_mode_{mode}_timeout_total")
            self._metrics.increment(f"capacity_group_{group}_timeout_total")
            return CollectOutcome(
                status=CollectOutcomeStatus.FAILED,
                error_code="plugin_timeout",
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - 收敛插件异常为稳定结果
            return CollectOutcome(
                status=CollectOutcomeStatus.FAILED,
                error_code="plugin_error",
                detail=type(error).__name__,
            )
        finally:
            if mode == "sync":
                self._metrics.add_gauge("sync_calls_in_flight", -1)
            duration = time.monotonic() - plugin_started
            self._metrics.increment(
                "plugin_duration_seconds_total",
                duration,
            )
            self._metrics.observe("plugin_duration_seconds", duration)
            self._metrics.observe(f"execution_mode_{mode}_duration_seconds", duration)
            self._metrics.observe(f"capacity_group_{group}_duration_seconds", duration)
            self._metrics.increment("plugin_total")

    async def _apply_collect_outcome(
        self,
        request: CollectionRequest,
        target: str,
        credential,
        outcome: CollectOutcome,
        *,
        attempts: int,
        credential_id: str,
    ):
        if outcome.status == CollectOutcomeStatus.SUCCESS:
            await self._safe_record_success(request, target, credential)
            return _AttemptDecision(
                action="return",
                result=TargetCollectionResult(
                    target=target,
                    status="success",
                    attempts=attempts,
                    credential_id=credential_id,
                    value=outcome.value,
                ),
            )
        if outcome.status == CollectOutcomeStatus.DEFERRED:
            return _AttemptDecision(
                action="return",
                result=TargetCollectionResult(
                    target=target,
                    status="deferred",
                    attempts=attempts,
                    credential_id=credential_id,
                    value=outcome.value,
                ),
            )
        if outcome.status == CollectOutcomeStatus.AUTH_FAILED:
            error_code = outcome.error_code or "authentication_failed"
            await self._safe_record_auth_failure(
                request,
                target,
                credential,
                error_code=error_code,
            )
            return _AttemptDecision(
                action="continue",
                credential_failure=CredentialFailureResult(
                    credential_id=credential_id,
                    error_code=error_code,
                ),
            )
        if outcome.status == CollectOutcomeStatus.RETRY_CREDENTIAL:
            return _AttemptDecision(action="continue")
        if outcome.status == CollectOutcomeStatus.UNREACHABLE:
            return _AttemptDecision(
                action="return",
                result=TargetCollectionResult(
                    target=target,
                    status="unreachable",
                    attempts=attempts,
                    credential_id=credential_id,
                    error_code=outcome.error_code or "target_unreachable",
                ),
            )
        return _AttemptDecision(
            action="return",
            result=TargetCollectionResult(
                target=target,
                status="failed",
                attempts=attempts,
                credential_id=credential_id,
                error_code=outcome.error_code or "collection_failed",
                value=outcome.value,
            ),
        )


@dataclass(frozen=True)
class _AttemptDecision:
    action: str  # collect | continue | return
    result: TargetCollectionResult | None = None
    no_response_attempts: int = 0
    credential_failure: CredentialFailureResult | None = None
