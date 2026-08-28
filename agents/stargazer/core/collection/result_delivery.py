"""单次采集运行的结果入队、确认与有限重试。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace

from core.collection.contracts import PublishOutcome, PublishStatus, ResultPublisher, TargetCollectionResult, TargetExecutorSettings
from core.collection.metrics import CollectionMetrics
from core.collection.result_publisher import FuturePublishReceipt
from core.collection.runtime import CollectionRequest, RunLease
from core.logger import logger, safe_log_value


@dataclass(frozen=True)
class PendingPublish:
    """已进入发布队列、等待最终确认的目标结果。"""

    index: int
    result: TargetCollectionResult
    receipt: object
    started_at: float
    deadline: float


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
    ) -> PendingPublish:
        loop = asyncio.get_running_loop()
        if result.publish_timestamp_ms <= 0:
            result = replace(result, publish_timestamp_ms=int(time.time() * 1000))
        attempt_started_at = loop.time()
        started_at = attempt_started_at if started_at is None else started_at
        deadline = started_at + self._settings.publish_total_timeout_seconds if deadline is None else deadline
        queue_deadline = min(
            deadline,
            attempt_started_at + self._settings.publish_queue_timeout_seconds,
        )
        try:
            async with asyncio.timeout_at(queue_deadline):
                receipt = await self._publisher.enqueue(
                    self._request,
                    result,
                    self._lease,
                )
        except Exception as error:  # noqa: BLE001 - 统一交给 finish 的有限重试
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
            receipt = FuturePublishReceipt(completion)
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
        )

    async def finish(self, pending: PendingPublish) -> tuple[int, str, str]:
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
            safe_log_value(pending.result.target, max_length=255),
            phase,
            safe_log_value(error_code or publish_status),
            attempts,
            (self._settings.publish_queue_timeout_seconds if phase == "enqueue" else self._settings.publish_total_timeout_seconds),
        )
