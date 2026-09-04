"""单次采集运行的结果入队、确认与有限重试。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from core.collection.contracts import (
    PublishOutcome,
    PublishStatus,
    ResultPublisher,
    TargetCollectionResult,
    TargetExecutorSettings,
    has_publishable_metrics,
)
from core.collection.metrics import CollectionMetrics
from core.collection.result_publisher import SCAN_CREDENTIAL_RESULT_SUBJECT, FuturePublishReceipt
from core.collection.runtime import CollectionRequest, RunLease
from core.logger import logger, safe_log_value


@dataclass(frozen=True)
class PendingPublish:
    """已进入发布队列、等待最终确认的目标结果。"""

    index: int
    result: TargetCollectionResult | None
    receipt: object | None
    started_at: float
    deadline: float
    delivery_required: bool = True
    target: str = ""


class BoundedResultDeliveryObserver:
    """发布子系统内以固定 worker/队列观察 PubAck，不把 payload 交回 Run 汇总。"""

    def __init__(
        self,
        delivery,
        *,
        worker_count: int = 4,
        queue_capacity: int = 160,
    ) -> None:
        if worker_count <= 0:
            raise ValueError("worker_count must be greater than zero")
        if queue_capacity <= 0:
            raise ValueError("queue_capacity must be greater than zero")
        self._delivery = delivery
        self._worker_count = int(worker_count)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_capacity)
        self._workers: list[asyncio.Task] = []

    async def observe(
        self,
        pending: PendingPublish,
        *,
        target: str,
        on_terminal: Callable[[int, str, str, str, Exception | None], None],
    ) -> None:
        self._ensure_workers()
        await self._queue.put((pending, target, on_terminal))

    async def drain(self) -> None:
        workers = tuple(self._workers)
        if not workers:
            return
        await self._queue.join()
        for _worker in workers:
            await self._queue.put(None)
        await asyncio.gather(*workers)
        self._workers.clear()

    async def abort(self) -> None:
        workers = tuple(self._workers)
        for worker in workers:
            if not worker.done():
                worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        self._workers.clear()
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                return

    def _ensure_workers(self) -> None:
        if self._workers:
            return
        self._workers = [
            asyncio.create_task(
                self._worker(),
                name=f"result-delivery-observer:{index}",
            )
            for index in range(self._worker_count)
        ]

    async def _worker(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                if item is None:
                    return
                pending, target, on_terminal = item
                try:
                    index, status, error_code = await self._delivery.finish(pending)
                except asyncio.CancelledError:
                    raise
                except Exception as error:  # Run 边界通过 callback 接管异常身份
                    on_terminal(pending.index, target, "", "", error)
                else:
                    on_terminal(index, target, status, error_code, None)
            finally:
                self._queue.task_done()


class ResultDeliveryCoordinator:
    """隐藏单次 Run 的发布超时、重试和失败采样策略。"""

    def __init__(
        self,
        *,
        publisher: ResultPublisher,
        settings: TargetExecutorSettings,
        metrics: CollectionMetrics,
        request: CollectionRequest,
        lease: RunLease,
        log_identity: str,
        failure_log_limit: int,
    ) -> None:
        self._publisher = publisher
        self._settings = settings
        self._metrics = metrics
        self._request = request
        self._lease = lease
        self._log_identity = log_identity
        self._failure_log_limit = failure_log_limit
        self._failure_log_count = 0

    async def enqueue(
        self,
        index: int,
        result: TargetCollectionResult,
        *,
        started_at: float | None = None,
        deadline: float | None = None,
        payload_permit=None,
    ) -> PendingPublish:
        loop = asyncio.get_running_loop()
        if result.publish_timestamp_ms <= 0:
            result = replace(result, publish_timestamp_ms=int(time.time() * 1000))
        attempt_started_at = loop.time()
        started_at = attempt_started_at if started_at is None else started_at
        deadline = started_at + self._settings.publish_total_timeout_seconds if deadline is None else deadline
        if not _requires_delivery(self._request, result):
            if payload_permit is not None:
                payload_permit.release()
            self._metrics.increment("result_delivery_not_applicable_total")
            return PendingPublish(
                index=index,
                result=result,
                receipt=None,
                started_at=started_at,
                deadline=deadline,
                delivery_required=False,
                target=result.target,
            )
        queue_deadline = min(
            deadline,
            attempt_started_at + self._settings.publish_queue_timeout_seconds,
        )
        try:
            async with asyncio.timeout_at(queue_deadline):
                enqueue_options = {"deadline": deadline}
                if payload_permit is not None:
                    enqueue_options["payload_permit"] = payload_permit
                receipt = await self._publisher.enqueue(self._request, result, self._lease, **enqueue_options)
        except Exception as error:  # noqa: BLE001 - 统一交给 finish 的有限重试
            if payload_permit is not None:
                payload_permit.release()
            completion = loop.create_future()
            if isinstance(error, TimeoutError):
                self._metrics.increment("publish_queue_timeout_total")
                completion.set_result(
                    PublishOutcome(
                        status=PublishStatus.RETRYABLE_FAILED,
                        error_code="publish_queue_timeout",
                    )
                )
            else:
                completion.set_exception(error)
            manages_retries_for = getattr(self._publisher, "manages_retries_for", None)
            receipt = FuturePublishReceipt(
                completion,
                retries_managed=bool(manages_retries_for(self._request) if callable(manages_retries_for) else False),
            )
        self._metrics.observe(
            "publish_enqueue_duration_seconds",
            loop.time() - attempt_started_at,
        )
        return PendingPublish(
            index=index,
            result=result,
            receipt=receipt,
            started_at=started_at,
            deadline=deadline,
            target=result.target,
        )

    async def finish(self, pending: PendingPublish) -> tuple[int, str, str]:
        if not pending.delivery_required:
            return pending.index, "not_applicable", ""
        current = pending
        publish_status = "failed"
        error_code = ""
        attempts = 0
        for attempt in range(self._settings.publish_max_attempts):
            attempts = attempt + 1
            try:
                async with asyncio.timeout_at(current.deadline):
                    outcome = await current.receipt.wait()
                self._observe_receipt(current)
                if outcome is None or outcome.status == PublishStatus.CONFIRMED:
                    return current.index, "succeeded", ""
                if outcome.status == PublishStatus.EVENT_FAILED:
                    publish_status = "event_failed"
                    error_code = outcome.error_code
                    break
                if outcome.status == PublishStatus.PERMANENT_FAILED:
                    publish_status = "permanent_failed"
                    error_code = outcome.error_code
                    break
                if outcome.status == PublishStatus.DELIVERY_UNKNOWN:
                    publish_status = "unknown"
                    error_code = outcome.error_code
                    break
                error_code = outcome.error_code or "publish_retryable_failed"
                if bool(getattr(current.receipt, "retries_managed", False)):
                    publish_status = "failed"
                    break
            except Exception as error:  # noqa: BLE001 - 单目标发布有限重试
                self._observe_queue_residence(current)
                error_code = type(error).__name__
                if isinstance(error, TimeoutError) and asyncio.get_running_loop().time() >= current.deadline:
                    self._metrics.increment("publish_timeout_total")
                    cancel_if_unattempted = getattr(
                        current.receipt,
                        "cancel_if_unattempted",
                        None,
                    )
                    if callable(cancel_if_unattempted) and cancel_if_unattempted():
                        publish_status = "failed"
                        error_code = "publish_total_timeout_before_delivery"
                        break
                self._observe_duration(current)
                self._metrics.increment("result_publish_failure_total")
                if bool(getattr(error, "delivery_detected", True)):
                    publish_status = "unknown"
                    break
            if attempt + 1 < self._settings.publish_max_attempts:
                self._metrics.increment("result_publish_retry_total")
                if current.result is None:
                    raise RuntimeError("retryable publish receipt lost its payload")
                current = await self.enqueue(
                    current.index,
                    current.result,
                    started_at=current.started_at,
                    deadline=current.deadline,
                )
                continue
            publish_status = "failed"
            break
        self._log_failure(current, publish_status, error_code, attempts)
        return current.index, publish_status, error_code

    def _observe_receipt(self, pending: PendingPublish) -> None:
        self._observe_queue_residence(pending)
        self._observe_duration(pending)

    def _observe_queue_residence(self, pending: PendingPublish) -> None:
        self._metrics.observe(
            "publish_queue_residence_seconds",
            float(getattr(pending.receipt, "queue_residence_seconds", 0.0)),
        )

    def _observe_duration(self, pending: PendingPublish) -> None:
        self._metrics.observe(
            "publish_duration_seconds",
            asyncio.get_running_loop().time() - pending.started_at,
        )

    def _log_failure(
        self,
        pending: PendingPublish,
        publish_status: str,
        error_code: str,
        attempts: int,
    ) -> None:
        if self._failure_log_count >= self._failure_log_limit:
            return
        self._failure_log_count += 1
        phase = "enqueue" if error_code in {"publish_queue_timeout", "publish_total_timeout_before_delivery"} else "delivery"
        logger.warning(
            "event=result_publish_failed %s plugin_ref=%s "
            "model_id=%s target=%s phase=%s reason=%s attempts=%s "
            "timeout_seconds=%s failed_stage=result_publish error_type=PublishFailure",
            safe_log_value(self._log_identity, max_length=255),
            safe_log_value(self._request.plugin_ref),
            safe_log_value(self._request.params.get("model_id") or "-"),
            safe_log_value(pending.target or (pending.result.target if pending.result is not None else "-"), max_length=255),
            phase,
            safe_log_value(error_code or publish_status),
            attempts,
            (self._settings.publish_queue_timeout_seconds if phase == "enqueue" else self._settings.publish_total_timeout_seconds),
        )


def _requires_delivery(
    request: CollectionRequest,
    result: TargetCollectionResult,
) -> bool:
    """显式 callback / 扫描一枪保持协议；普通结果仅成功且非空时进入 metrics。"""
    if str(request.params.get("callback_subject") or "").strip():
        return True
    if str(request.params.get("credential_result_subject") or "").strip() == SCAN_CREDENTIAL_RESULT_SUBJECT:
        return True
    return result.status == "success" and has_publishable_metrics(result.value)
