"""有界执行一个 CollectionRun 中的全部目标采集。"""

from __future__ import annotations

import asyncio
import time
from collections import Counter

from core.collection.capacity import TargetActivityTracker, TargetWorkerBudget, unlimited_target_gate
from core.collection.contracts import (
    AccessProbe,
    AccessProbeResult,
    AccessProbeStatus,
    CollectionPlugin,
    CollectOutcome,
    CollectOutcomeStatus,
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
from core.collection.enums import FailureStage, WorkloadClass
from core.collection.execution_plan import ExecutionPlan
from core.collection.metrics import CollectionMetrics
from core.collection.result_delivery import PendingPublish, ResultDeliveryCoordinator
from core.collection.result_publisher import ImmediateResultPublishQueue
from core.collection.runtime import CollectionRequest, RunLease
from core.collection.scheduler import CollectionScheduler
from core.collection.target_attempt import TargetAttemptRunner, request_instance_id
from core.logger import logger, safe_exception_info, safe_log_value
from core.plugin.error_logging import PluginExceptionLogBudget

_FAILURE_SUMMARY_SAMPLE_LIMIT = 3
_FAILURE_SUMMARY_CODE_LIMIT = 8

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
        self._publisher = publisher if callable(getattr(publisher, "enqueue", None)) else ImmediateResultPublishQueue(publisher)
        self._settings = settings or TargetExecutorSettings()
        self._plan = plan or ExecutionPlan(
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
        self._target_attempt_runner = TargetAttemptRunner(
            preflight=preflight,
            access_probe=access_probe,
            plugin=plugin,
            credential_policy=credential_policy or CredentialPolicy(store=InMemoryCredentialStateStore()),
            settings=self._settings,
            plan=self._plan,
            metrics=self._metrics,
        )

    # fmt: off
    async def execute(  # noqa: C901
        self, request: CollectionRequest, lease: RunLease
    ) -> RunSummary:
        # fmt: on
        from core.collection.round_complete import new_round_ts

        run_started_at = time.monotonic()
        round_ts = new_round_ts()
        targets = request.targets
        instance_id = request_instance_id(request)
        results: dict[int, TargetCollectionResult] = {}
        publish_statuses: dict[int, str] = {}
        publish_error_codes: dict[int, str] = {}
        active_targets: set[str] = set()
        progress_completed = 0
        progress_step = max(1, (len(targets) + 9) // 10)
        skipped = 0
        delivery = ResultDeliveryCoordinator(
            publisher=self._publisher,
            settings=self._settings,
            metrics=self._metrics,
            request=request,
            lease=lease,
            log_identity=_request_log_identity(request, instance_id),
            failure_log_limit=_FAILURE_SUMMARY_SAMPLE_LIMIT,
        )
        plugin_exception_log_budget = PluginExceptionLogBudget(
            limit=_FAILURE_SUMMARY_SAMPLE_LIMIT
        )

        async def execute_index(index: int) -> PendingPublish:
            nonlocal progress_completed
            target = targets[index]
            target_started_at = time.monotonic()
            # 目标槽位只覆盖目标执行与进入发布路径；发布异常在目标内隔离。
            try:
                async with self._target_semaphore:
                    await self._activity_tracker.enter()
                    target_started_at = time.monotonic()
                    active_targets.add(target)
                    logger.debug(
                        "event=target_collection_started instance_id=%s "
                        "plugin_ref=%s plugin_name=%s model_id=%s target=%s",
                        safe_log_value(instance_id),
                        safe_log_value(request.plugin_ref),
                        safe_log_value(request.params.get("plugin_name") or "-"),
                        safe_log_value(request.params.get("model_id") or "-"),
                        safe_log_value(target, max_length=255),
                    )
                    try:
                        result = await self._target_attempt_runner.run(
                            request,
                            target,
                            lease,
                            plugin_exception_log_budget=plugin_exception_log_budget,
                        )
                        if result.status == "success" and _is_snmp_plugin(
                            plugin_ref=request.plugin_ref,
                            plugin_name=request.params.get("plugin_name"),
                        ):
                            duration_ms = round((time.monotonic() - target_started_at) * 1000, 2)
                            logger.debug(
                                "event=target_collection_succeeded %s "
                                "plugin_ref=%s plugin_name=%s model_id=%s target=%s "
                                "credential_id=%s duration_ms=%s | SNMP采集成功 IP=%s 耗时=%sms",
                                _request_log_identity(request, instance_id),
                                safe_log_value(request.plugin_ref),
                                safe_log_value(request.params.get("plugin_name") or "-"),
                                safe_log_value(request.params.get("model_id") or "-"),
                                safe_log_value(target, max_length=255),
                                safe_log_value(result.credential_id or "-"),
                                duration_ms,
                                safe_log_value(target, max_length=255),
                                duration_ms,
                            )
                    finally:
                        active_targets.discard(target)
                        await self._activity_tracker.exit()
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - 单目标框架异常不得取消 Run
                self._metrics.increment("target_execution_error_total")
                if plugin_exception_log_budget.claim():
                    logger.error(
                        "event=target_execution_failed task_id=%s plugin_ref=%s "
                        "model_id=%s target=%s failed_stage=framework error_type=%s",
                        safe_log_value(request.task_id),
                        safe_log_value(request.plugin_ref),
                        safe_log_value(request.params.get("model_id") or "-"),
                        safe_log_value(targets[index], max_length=255),
                        type(error).__name__,
                        exc_info=safe_exception_info(error),
                    )
                result = TargetCollectionResult(
                    target=target,
                    status="failed",
                    attempts=0,
                    error_code="target_execution_error",
                    failed_stage=FailureStage.FRAMEWORK,
                )
            self._metrics.increment(
                f"execution_mode_{self._plan.execution_mode}_{result.status}_total"
            )
            self._metrics.increment(
                f"capacity_group_{self._plan.capacity_group}_{result.status}_total"
            )
            progress_completed += 1
            if (
                progress_completed == 1
                or progress_completed == len(targets)
                or progress_completed % progress_step == 0
            ):
                active_samples = (
                    ",".join(
                        safe_log_value(item, max_length=255)
                        for item in sorted(active_targets)[:5]
                    )
                    or "-"
                )
                logger.info(
                    "event=collection_progress instance_id=%s "
                    "plugin_ref=%s plugin_name=%s model_id=%s | "
                    "采集进度 已完成=%s/%s 当前采集=%s 待处理=%s "
                    "最近完成=%s 最近结果=%s 当前目标样本=%s",
                    safe_log_value(instance_id),
                    safe_log_value(request.plugin_ref),
                    safe_log_value(request.params.get("plugin_name") or "-"),
                    safe_log_value(request.params.get("model_id") or "-"),
                    progress_completed,
                    len(targets),
                    self._activity_tracker.active,
                    max(0, len(targets) - progress_completed),
                    safe_log_value(targets[index], max_length=255),
                    _target_status_zh(result.status),
                    active_samples,
                )
            return await delivery.enqueue(index, result)

        if self._scheduler is not None:
            workload_class = (
                WorkloadClass.NETWORK_TOPOLOGY
                if self._plan.capacity_group == "network_topology"
                else request.workload_class
            )
            scheduled = await self._scheduler.execute(
                f"{request.task_id}:{lease.fence}",
                range(len(targets)),
                execute_index,
                workload=workload_class,
                capacity_group=self._plan.capacity_group,
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
            desired_workers = (
                max(1, len(targets))
                if window <= 0
                else (min(len(targets), window) if targets else 1)
            )
            worker_count = await self._worker_budget.reserve(desired_workers)
            pending_publishes = []
            worker_tasks = [
                asyncio.create_task(
                    worker(),
                    name=f"target-worker:{safe_log_value(request.task_id)}:{index}",
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
            index, publish_status, publish_error_code = await delivery.finish(pending)
            publish_statuses[index] = publish_status
            publish_error_codes[index] = publish_error_code
        completed = tuple(results.values())
        for status in publish_statuses.values():
            self._metrics.increment(f"publish_{status}_total")
            if status == "succeeded":
                self._metrics.increment("publish_confirmed_total")
            elif status == "unknown":
                self._metrics.increment("publish_delivery_unknown_total")
            elif status == "failed":
                self._metrics.increment("publish_retryable_failed_total")
        summary = RunSummary(
            total=len(targets),
            collection_succeeded=sum(
                result.status == "success" for result in completed
            ),
            collection_failed=sum(result.status == "failed" for result in completed),
            unreachable=sum(result.status == "unreachable" for result in completed),
            deferred=sum(result.status == "deferred" for result in completed),
            skipped=skipped,
            publish_succeeded=sum(
                status == "succeeded" for status in publish_statuses.values()
            ),
            publish_not_applicable=sum(
                status == "not_applicable" for status in publish_statuses.values()
            ),
            publish_failed=sum(
                status == "failed" for status in publish_statuses.values()
            ),
            publish_unknown=sum(
                status == "unknown" for status in publish_statuses.values()
            ),
            publish_event_failed=sum(
                status == "event_failed" for status in publish_statuses.values()
            ),
            publish_permanent_failed=sum(
                status == "permanent_failed" for status in publish_statuses.values()
            ),
        )
        failures = tuple(result for result in completed if result.status in {"failed", "unreachable"})
        failure_counts = Counter(result.error_code or result.status for result in failures)
        failure_codes = _bounded_failure_counts(failure_counts)
        failure_samples = ",".join(
            "%s|%s|%s"
            % (
                safe_log_value(result.target, max_length=255),
                safe_log_value(_failure_stage_name(result)),
                safe_log_value(result.error_code or result.status),
            )
            for result in failures[:_FAILURE_SUMMARY_SAMPLE_LIMIT]
        ) or "-"
        if failures:
            logger.info(
                "event=collection_failure_samples %s plugin_ref=%s model_id=%s "
                "sample_count=%s total_failures=%s samples=%s",
                _request_log_identity(request, instance_id),
                safe_log_value(request.plugin_ref),
                safe_log_value(request.params.get("model_id") or "-"),
                min(len(failures), _FAILURE_SUMMARY_SAMPLE_LIMIT),
                len(failures),
                failure_samples,
            )
        publish_failures = tuple(
            (index, status, publish_error_codes.get(index) or status)
            for index, status in publish_statuses.items()
            if status not in {"succeeded", "not_applicable"}
        )
        publish_failure_counts = Counter(error_code for _index, _status, error_code in publish_failures)
        publish_failure_codes = (
            ",".join(
                f"{safe_log_value(code)}:{count}"
                for code, count in sorted(publish_failure_counts.items())
            )
            or "-"
        )
        publish_failure_samples = ",".join(
            f"{safe_log_value(targets[index], max_length=255)}|{safe_log_value(error_code)}"
            for index, _status, error_code in publish_failures[:_FAILURE_SUMMARY_SAMPLE_LIMIT]
        ) or "-"
        log_summary = (
            logger.warning
            if failures
            or summary.publish_failed
            or summary.publish_unknown
            or summary.publish_event_failed
            or summary.publish_permanent_failed
            else logger.info
        )
        log_summary(
            "event=collection_run_summary %s plugin_ref=%s model_id=%s "
            "| 任务汇总 总目标=%s 采集成功=%s 采集失败=%s 不可达=%s 延后处理=%s 跳过=%s "
            "发布成功=%s 无需发布=%s 发布失败=%s 发布状态未知=%s 发布事件失败=%s 发布永久失败=%s "
            "总耗时=%sms 失败类型=%s 失败样本=%s 发布失败类型=%s 发布失败样本=%s",
            _request_log_identity(request, instance_id),
            safe_log_value(request.plugin_ref),
            safe_log_value(request.params.get("model_id") or "-"),
            summary.total,
            summary.collection_succeeded,
            summary.collection_failed,
            summary.unreachable,
            summary.deferred,
            summary.skipped,
            summary.publish_succeeded,
            summary.publish_not_applicable,
            summary.publish_failed,
            summary.publish_unknown,
            summary.publish_event_failed,
            summary.publish_permanent_failed,
            round((time.monotonic() - run_started_at) * 1000, 2),
            failure_codes,
            failure_samples,
            publish_failure_codes,
            publish_failure_samples,
        )
        from core.collection.round_complete import is_complete_round

        publish_clean = is_complete_round(summary)
        if publish_clean:
            from core.collection.round_complete import publish_round_complete_marker

            await publish_round_complete_marker(request, round_ts)
        else:
            logger.info(
                "event=round_complete_marker_skipped %s reason=publish_incomplete "
                "round_ts=%s publish_failed=%s publish_unknown=%s "
                "publish_event_failed=%s publish_permanent_failed=%s",
                _request_log_identity(request, instance_id),
                round_ts,
                summary.publish_failed,
                summary.publish_unknown,
                summary.publish_event_failed,
                summary.publish_permanent_failed,
            )
        return summary


def _request_log_identity(request: CollectionRequest, instance_id: str) -> str:
    if instance_id != "-":
        return f"instance_id={safe_log_value(instance_id)}"
    return f"task_id={safe_log_value(request.task_id)}"


def _bounded_failure_counts(failure_counts: Counter) -> str:
    ordered = sorted(
        failure_counts.items(),
        key=lambda item: (-item[1], str(item[0])),
    )
    visible = ordered[:_FAILURE_SUMMARY_CODE_LIMIT]
    rendered = [f"{safe_log_value(code)}:{count}" for code, count in visible]
    other_count = sum(count for _code, count in ordered[_FAILURE_SUMMARY_CODE_LIMIT:])
    if other_count:
        rendered.append(f"other:{other_count}")
    return ",".join(rendered) or "-"


def _failure_stage_name(result: TargetCollectionResult) -> str:
    if result.failed_stage is not None:
        return result.failed_stage.value
    error_code = result.error_code or result.status
    if result.status == "unreachable" and result.attempts == 0:
        return "preflight"
    if error_code.startswith("access_probe_") or error_code in {
        "protocol_no_response",
        "no_response_attempt_limit",
        "target_unreachable",
    }:
        return "access_probe"
    if error_code in {
        "authentication_failed",
        "credential_state_unavailable",
        "credentials_exhausted",
        "no_matching_credential",
        "no_valid_credential",
    }:
        return "credential"
    return "collection"


def _target_status_zh(status: str) -> str:
    return {
        "success": "成功",
        "failed": "失败",
        "unreachable": "不可达",
        "deferred": "延后处理",
    }.get(str(status), str(status))


def _is_snmp_plugin(*, plugin_ref: object, plugin_name: object) -> bool:
    return str(plugin_name or "") == "snmp_facts" or str(plugin_ref or "") == "network.config"
