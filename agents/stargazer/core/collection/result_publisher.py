"""统一运行时的 NATS/业务回调结果发布器。"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from core.collection.contracts import PublishOutcome, PublishStatus, TargetCollectionResult, build_collection_result_id
from core.collection.runtime import CollectionRequest, RunLease
from core.logger import logger

CREDENTIAL_RESULT_EVENT_VERSION = 2
CREDENTIAL_FAILURE_ERROR_CODES = frozenset(
    {
        "auth_failed",
        "authentication_failed",
        "capability_denied",
        "snmp_error_status",
        "snmp_authorization_failed",
        "unauthorized",
    }
)


@dataclass(frozen=True)
class _BufferedPublishItem:
    request: CollectionRequest
    result: TargetCollectionResult
    lease: RunLease
    completion: asyncio.Future[PublishOutcome | None]
    state: _PublishAttemptState


class _PublishAttemptState:
    """跟踪结果是否仍可在触达 transport 前安全撤销。"""

    def __init__(self, completion: asyncio.Future[PublishOutcome | None]) -> None:
        self._completion = completion
        self._processing = False
        self._delivery_started = False
        self._cancelled = False
        self._enqueued_at = time.monotonic()
        self._queue_wait_seconds = 0.0
        self._queue_depth_at_enqueue = 0
        self._queue_residence_seconds = 0.0

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def delivery_started(self) -> bool:
        return self._delivery_started

    @property
    def queue_wait_seconds(self) -> float:
        return self._queue_wait_seconds

    @property
    def queue_depth_at_enqueue(self) -> int:
        return self._queue_depth_at_enqueue

    @property
    def queue_age_seconds(self) -> float:
        return max(0.0, time.monotonic() - self._enqueued_at)

    @property
    def queue_residence_seconds(self) -> float:
        if self._delivery_started:
            return self._queue_residence_seconds
        return self.queue_age_seconds

    def mark_enqueued(self, *, queue_wait_seconds: float, queue_depth: int) -> None:
        self._enqueued_at = time.monotonic()
        self._queue_wait_seconds = max(0.0, float(queue_wait_seconds))
        self._queue_depth_at_enqueue = max(0, int(queue_depth))

    def mark_processing(self) -> bool:
        if self._cancelled:
            return False
        self._processing = True
        return True

    def mark_delivery_started(self) -> bool:
        if self._cancelled:
            return False
        self._processing = True
        self._delivery_started = True
        self._queue_residence_seconds = self.queue_age_seconds
        return True

    def cancel_if_unattempted(self) -> bool:
        if self._processing or self._delivery_started or self._cancelled:
            return False
        self._cancelled = True
        if not self._completion.done():
            self._completion.set_result(
                PublishOutcome(
                    status=PublishStatus.RETRYABLE_FAILED,
                    error_code="publish_cancelled_before_delivery",
                )
            )
        return True


class FuturePublishReceipt:
    """发布队列回执；队列接纳与最终投递确认相互独立。"""

    def __init__(
        self,
        completion: asyncio.Future[PublishOutcome | None],
        state: _PublishAttemptState | None = None,
    ) -> None:
        self._completion = completion
        self._state = state or _PublishAttemptState(completion)

    def done(self) -> bool:
        return self._completion.done()

    async def wait(self):
        return await asyncio.shield(self._completion)

    def cancel_if_unattempted(self) -> bool:
        return self._state.cancel_if_unattempted()

    @property
    def delivery_started(self) -> bool:
        return self._state.delivery_started

    @property
    def queue_wait_seconds(self) -> float:
        return self._state.queue_wait_seconds

    @property
    def queue_depth_at_enqueue(self) -> int:
        return self._state.queue_depth_at_enqueue

    @property
    def queue_age_seconds(self) -> float:
        return self._state.queue_age_seconds

    @property
    def queue_residence_seconds(self) -> float:
        return self._state.queue_residence_seconds


class PublishShutdownError(RuntimeError):
    """发布器退出时仍无法确认投递结果。"""

    delivery_detected = True


class ImmediateResultPublishQueue:
    """把旧逐条 ResultSink 显式适配为 enqueue/receipt interface。"""

    def __init__(self, sink) -> None:
        self._sink = sink

    async def enqueue(self, request, result, lease) -> FuturePublishReceipt:
        completion = asyncio.create_task(
            self._sink.publish(request, result, lease),
            name=f"result-publish:{request.task_id}:{result.target}",
        )
        state = _PublishAttemptState(completion)
        state.mark_delivery_started()
        return FuturePublishReceipt(completion, state)


class BufferedResultPublisher:
    """有界聚合单目标结果，并把批处理细节隐藏在 publisher seam 后。"""

    def __init__(
        self,
        delegate,
        *,
        capacity: int,
        batch_size: int = 50,
        flush_interval_seconds: float = 0.02,
        worker_count: int = 1,
        metrics=None,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        if flush_interval_seconds <= 0:
            raise ValueError("flush_interval_seconds must be greater than zero")
        if worker_count <= 0:
            raise ValueError("worker_count must be greater than zero")
        self._delegate = delegate
        self._queue: asyncio.Queue[_BufferedPublishItem | None] = asyncio.Queue(maxsize=capacity)
        self._batch_size = int(batch_size)
        self.capacity = int(capacity)
        self._flush_interval_seconds = float(flush_interval_seconds)
        self._metrics = metrics
        self._worker_count = int(worker_count)
        self._writers: list[asyncio.Task] = []
        self._writer: asyncio.Task | None = None
        self._closed = False
        self._pending: set[asyncio.Future[PublishOutcome | None]] = set()
        self.peak_queue_depth = 0
        self._active_batch_started_at: dict[asyncio.Task, float] = {}

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def current_batch_age_seconds(self) -> float:
        if not self._active_batch_started_at:
            return 0.0
        oldest = min(self._active_batch_started_at.values())
        return max(0.0, time.monotonic() - oldest)

    async def enqueue(self, request, result, lease) -> FuturePublishReceipt:
        if self._closed:
            raise RuntimeError("result publisher is closed")
        loop = asyncio.get_running_loop()
        completion = loop.create_future()
        state = _PublishAttemptState(completion)
        self._pending.add(completion)
        completion.add_done_callback(self._pending.discard)
        item = _BufferedPublishItem(request, result, lease, completion, state)
        self._ensure_writer()
        enqueue_started = time.monotonic()
        await self._queue.put(item)
        queue_wait_seconds = time.monotonic() - enqueue_started
        state.mark_enqueued(
            queue_wait_seconds=queue_wait_seconds,
            # writer 可能在 put 返回前已取走当前项；至少记入刚被接纳的这一项。
            queue_depth=max(1, self._queue.qsize()),
        )
        if self._metrics is not None:
            self._metrics.observe("publish_queue_wait_seconds", queue_wait_seconds)
        self.peak_queue_depth = max(self.peak_queue_depth, self._queue.qsize())
        return FuturePublishReceipt(completion, state)

    async def publish(self, request, result, lease) -> None:
        receipt = await self.enqueue(request, result, lease)
        await receipt.wait()

    async def shutdown(self, *, grace_seconds: float = 30.0) -> None:
        if self._closed:
            return
        self._closed = True
        writers = tuple(self._writers)
        if not writers:
            return
        try:
            async with asyncio.timeout(max(0.0, grace_seconds)):
                for _writer in writers:
                    await self._queue.put(None)
                await asyncio.gather(*writers)
        except (TimeoutError, asyncio.CancelledError):
            if self._metrics is not None:
                self._metrics.increment("publish_shutdown_timeout_total")
            for writer in writers:
                if not writer.done():
                    writer.cancel()
            await asyncio.gather(*writers, return_exceptions=True)
            self._fail_pending(PublishShutdownError("result publisher shutdown grace expired"))
            self._discard_queued_items()
            if isinstance(asyncio.current_task(), asyncio.Task) and asyncio.current_task().cancelling():
                raise
        except Exception as error:  # writer 异常必须结束所有回执
            self._fail_pending(error)
            self._discard_queued_items()

    def _fail_pending(self, error: BaseException) -> None:
        for completion in tuple(self._pending):
            if not completion.done():
                completion.set_exception(error)

    def _discard_queued_items(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return

    def _ensure_writer(self) -> None:
        self._writers = [writer for writer in self._writers if not writer.done()]
        while len(self._writers) < self._worker_count:
            worker_index = len(self._writers)
            writer = asyncio.create_task(
                self._writer_loop(),
                name=f"collection-result-publisher:{worker_index}",
            )
            self._writers.append(writer)
        self._writer = self._writers[0]

    async def _writer_loop(self) -> None:
        while True:
            first = await self._queue.get()
            if first is None:
                return
            if first.state.cancelled:
                continue
            batch = [first]
            deadline = asyncio.get_running_loop().time() + self._flush_interval_seconds
            while len(batch) < self._batch_size:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    item = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                except TimeoutError:
                    break
                if item is None:
                    await self._deliver(batch)
                    return
                if not item.state.cancelled:
                    batch.append(item)
            await self._deliver(batch)

    async def _deliver(self, batch: list[_BufferedPublishItem]) -> None:
        tracks_transport_attempts = bool(getattr(self._delegate, "tracks_transport_attempts", False))
        if tracks_transport_attempts:
            batch = [item for item in batch if not item.state.cancelled]
        else:
            batch = [item for item in batch if item.state.mark_delivery_started()]
        if not batch:
            return
        flush_started = time.monotonic()
        current_task = asyncio.current_task()
        if current_task is not None:
            self._active_batch_started_at[current_task] = flush_started
        if self._metrics is not None:
            self._metrics.increment("publish_batch_total")
            self._metrics.increment("publish_batch_items_total", len(batch))
            self._metrics.observe("publish_batch_size", len(batch))
        publish_batch = getattr(self._delegate, "publish_batch", None)
        try:
            if callable(publish_batch):
                try:
                    outcomes = await publish_batch(tuple((item.request, item.result, item.lease, item.state) for item in batch))
                except Exception as exc:  # 同批各目标获得独立失败结论
                    for item in batch:
                        if not item.completion.done():
                            item.completion.set_exception(exc)
                else:
                    per_result = outcomes if isinstance(outcomes, Mapping) else {}
                    for item in batch:
                        if item.completion.done():
                            continue
                        result_id = build_collection_result_id(
                            task_id=item.request.task_id,
                            plugin_ref=item.request.plugin_ref,
                            target=item.result.target,
                            fence=item.lease.fence,
                            attempt_id=item.lease.attempt_id,
                        )
                        outcome = per_result.get(result_id)
                        if isinstance(outcome, BaseException):
                            item.completion.set_exception(outcome)
                        elif isinstance(outcome, PublishOutcome):
                            item.completion.set_result(outcome)
                        else:
                            item.completion.set_result(PublishOutcome(status=PublishStatus.CONFIRMED))
                return

            outcomes = await asyncio.gather(
                *(self._delegate.publish(item.request, item.result, item.lease) for item in batch),
                return_exceptions=True,
            )
            for item, outcome in zip(batch, outcomes):
                if item.completion.done():
                    continue
                if isinstance(outcome, BaseException):
                    item.completion.set_exception(outcome)
                else:
                    item.completion.set_result(PublishOutcome(status=PublishStatus.CONFIRMED))
        finally:
            if current_task is not None:
                self._active_batch_started_at.pop(current_task, None)
            if self._metrics is not None:
                self._metrics.observe("publish_flush_duration_seconds", time.monotonic() - flush_started)


class NatsResultPublisher:
    tracks_transport_attempts = True

    def __init__(
        self,
        *,
        metrics_publish: Callable | None = None,
        metrics_publish_batch: Callable | None = None,
        callback_publish: Callable | None = None,
        credential_result_publish: Callable | None = None,
        result_event_sink: Callable | None = None,
        metrics=None,
        event_max_attempts: int = 2,
    ) -> None:
        self._metrics_publish = metrics_publish
        self._metrics_publish_batch = metrics_publish_batch
        self._callback_publish = callback_publish
        self._credential_result_publish = credential_result_publish
        self._result_event_sink = result_event_sink
        self._metrics = metrics
        self._event_max_attempts = max(1, int(event_max_attempts))

    # fmt: off
    async def publish_batch(  # noqa: C901
        self, items
    ) -> dict[str, BaseException | PublishOutcome | None]:
        # fmt: on
        outcomes: dict[str, BaseException | PublishOutcome | None] = {}
        metrics_entries = []
        metric_events = []
        non_metrics = []
        for item in items:
            request, result, lease = item[:3]
            attempt_state = item[3] if len(item) > 3 else None
            if result.status == "deferred" or request.params.get("callback_subject"):
                non_metrics.append((request, result, lease, attempt_state))
                continue
            result_id = build_collection_result_id(
                task_id=request.task_id,
                plugin_ref=request.plugin_ref,
                target=result.target,
                fence=lease.fence,
                attempt_id=lease.attempt_id,
            )
            params = self._result_params(
                request, result, lease, result_id, attempt_state=attempt_state
            )
            metrics = result.value
            if not metrics or result.status not in {"success", "deferred"}:
                metrics = self._error_metrics(request, result, params)
            metrics_entries.append(({}, metrics, params, request.task_id))
            metric_events.append((request, result, lease, result_id))
            outcomes[result_id] = None

        if metrics_entries:
            metrics_publish_batch = self._metrics_publish_batch
            using_default_batch = (
                metrics_publish_batch is None and self._metrics_publish is None
            )
            if using_default_batch:
                from tasks.utils.nats_helper import publish_metrics_batch_to_nats

                metrics_publish_batch = publish_metrics_batch_to_nats
            if metrics_publish_batch is not None:
                try:
                    if using_default_batch:
                        batch_outcomes = await metrics_publish_batch(
                            tuple(metrics_entries), metrics=self._metrics
                        )
                    else:
                        batch_outcomes = await metrics_publish_batch(
                            tuple(metrics_entries)
                        )
                except Exception as error:  # noqa: BLE001 - 返回逐目标失败，不抛整批
                    for _request, _result, _lease, result_id in metric_events:
                        outcomes[result_id] = error
                else:
                    if isinstance(batch_outcomes, Mapping):
                        for result_id, outcome in batch_outcomes.items():
                            if result_id not in outcomes:
                                continue
                            if isinstance(outcome, ValueError):
                                outcomes[result_id] = PublishOutcome(
                                    status=PublishStatus.PERMANENT_FAILED,
                                    error_code=str(
                                        getattr(
                                            outcome,
                                            "error_code",
                                            "metrics_encode_failed",
                                        )
                                    ),
                                )
                            elif isinstance(outcome, BaseException):
                                outcomes[result_id] = outcome
            else:
                individual_outcomes = await asyncio.gather(
                    *(self._metrics_publish(*entry) for entry in metrics_entries),
                    return_exceptions=True,
                )
                for event, outcome in zip(metric_events, individual_outcomes):
                    if isinstance(outcome, BaseException):
                        outcomes[event[3]] = outcome
            for request, result, lease, result_id in metric_events:
                if outcomes[result_id] is not None:
                    continue
                try:
                    await self._record_event_with_retry(
                        request, result, lease, result_id
                    )
                except Exception as error:  # noqa: BLE001 - 事件记录按目标归因并保留原始上下文
                    logger.exception(
                        "event=result_event_record_failed task_id=%s target=%s error_type=%s",
                        request.task_id,
                        result.target,
                        type(error).__name__,
                    )
                    outcomes[result_id] = PublishOutcome(
                        status=PublishStatus.EVENT_FAILED,
                        error_code="result_event_record_failed",
                    )

        if non_metrics:

            async def publish_non_metric(request, result, lease, attempt_state):
                if (
                    attempt_state is not None
                    and not attempt_state.mark_delivery_started()
                ):
                    return PublishOutcome(
                        status=PublishStatus.RETRYABLE_FAILED,
                        error_code="publish_cancelled_before_delivery",
                    )
                await self.publish(request, result, lease)
                return None

            non_metric_outcomes = await asyncio.gather(
                *(
                    publish_non_metric(request, result, lease, attempt_state)
                    for request, result, lease, attempt_state in non_metrics
                ),
                return_exceptions=True,
            )
            for (request, result, lease, _attempt_state), outcome in zip(
                non_metrics, non_metric_outcomes
            ):
                result_id = build_collection_result_id(
                    task_id=request.task_id,
                    plugin_ref=request.plugin_ref,
                    target=result.target,
                    fence=lease.fence,
                    attempt_id=lease.attempt_id,
                )
                outcomes[result_id] = (
                    outcome
                    if isinstance(outcome, (BaseException, PublishOutcome))
                    else None
                )
        return outcomes

    async def publish(
        self,
        request: CollectionRequest,
        result: TargetCollectionResult,
        lease: RunLease,
    ) -> None:
        result_id = build_collection_result_id(
            task_id=request.task_id,
            plugin_ref=request.plugin_ref,
            target=result.target,
            fence=lease.fence,
            attempt_id=lease.attempt_id,
        )
        if result.status == "deferred":
            await self._record_event_with_retry(request, result, lease, result_id)
            return
        params = self._result_params(request, result, lease, result_id)
        if params.get("callback_subject"):
            callback_publish = self._callback_publish
            if callback_publish is None:
                from tasks.utils.nats_helper import publish_callback_to_nats

                callback_publish = publish_callback_to_nats
            payload = dict(result.value or {})
            payload.update(
                {
                    "collection_task_id": request.task_id,
                    "collection_fence": lease.fence,
                    "collection_target": result.target,
                    "collection_plugin_ref": request.plugin_ref,
                    "collection_result_id": result_id,
                }
            )
            await callback_publish(payload, params, request.task_id)
            await self._record_event_with_retry(request, result, lease, result_id)
            return

        metrics_publish = self._metrics_publish
        if metrics_publish is None:
            from tasks.utils.nats_helper import publish_metrics_to_nats

            metrics_publish = publish_metrics_to_nats
        metrics = result.value
        if not metrics or result.status not in {"success", "deferred"}:
            metrics = self._error_metrics(request, result, params)
        await metrics_publish({}, metrics, params, request.task_id)
        await self._record_event_with_retry(request, result, lease, result_id)

    async def _record_event_with_retry(self, request, result, lease, result_id) -> None:
        for attempt in range(self._event_max_attempts):
            try:
                await self._record_event(request, result, lease, result_id)
                return
            except Exception:  # noqa: BLE001 - 稳定 event_id 允许仅重试幂等事件
                if attempt + 1 >= self._event_max_attempts:
                    raise
                await asyncio.sleep(0)

    @staticmethod
    def _result_params(
        request, result, lease, result_id, *, attempt_state=None
    ) -> dict:
        params = dict(request.params)
        params.update(
            {
                "host": result.target,
                "collection_task_id": request.task_id,
                "collection_fence": lease.fence,
                "collection_target": result.target,
                "collection_plugin_ref": request.plugin_ref,
                "collection_result_id": result_id,
                "collect_status": result.status,
                "_publish_timestamp_ms": result.publish_timestamp_ms,
            }
        )
        if attempt_state is not None:
            params["_publish_attempt_state"] = attempt_state
        return params

    async def _record_event(
        self,
        request: CollectionRequest,
        result: TargetCollectionResult,
        lease: RunLease,
        result_id: str,
    ) -> None:
        should_sink = self._result_event_sink is not None
        should_publish = bool(str(request.params.get("credential_result_subject") or "").strip())
        if not should_sink and not should_publish:
            return

        credential_failures = tuple(getattr(result, "credential_failures", ()))
        for event_index, failure in enumerate(credential_failures):
            await self._emit_credential_event(
                request,
                self._build_credential_event(
                    request=request,
                    lease=lease,
                    result_id=result_id,
                    target=result.target,
                    credential_id=failure.credential_id,
                    status="failed",
                    error_code=failure.error_code,
                    attempts=result.attempts,
                    event_index=event_index,
                ),
            )

        if credential_failures and not result.credential_id:
            return

        await self._emit_credential_event(
            request,
            self._build_credential_event(
                request=request,
                lease=lease,
                result_id=result_id,
                target=result.target,
                credential_id=result.credential_id,
                status=result.status,
                error_code=result.error_code,
                attempts=result.attempts,
                event_index=len(credential_failures),
            ),
        )

    async def _emit_credential_event(self, request: CollectionRequest, event: dict) -> None:
        # Redis 批推路径会在 append 时补 finished_at；实时 NATS 必须自带，
        # 否则 Server v2 身份校验会拒收（unreachable 例外绕过）。
        if not str(event.get("finished_at") or "").strip():
            from datetime import datetime, timezone

            event["finished_at"] = datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            )
        if self._result_event_sink is not None:
            await self._result_event_sink(event)
        await self._publish_credential_result_if_needed(request, event)

    async def _publish_credential_result_if_needed(
        self, request: CollectionRequest, event: dict
    ) -> None:
        subject = str(request.params.get("credential_result_subject") or "").strip()
        if not subject:
            return

        publish = self._credential_result_publish
        if publish is None:
            from tasks.utils.nats_helper import publish_credential_result_to_nats

            publish = publish_credential_result_to_nats
        await publish(event, dict(request.params), request.task_id)

    @staticmethod
    def _build_credential_event(
        *,
        request: CollectionRequest,
        lease: RunLease,
        result_id: str,
        target: str,
        credential_id: str,
        status: str,
        error_code: str,
        attempts: int,
        event_index: int,
    ) -> dict:
        success = status == "success"
        failure_kind = (
            "credential"
            if status == "failed" and error_code in CREDENTIAL_FAILURE_ERROR_CODES
            else "task"
        )
        event_identity = "\0".join(
            (result_id, str(event_index), credential_id, status, error_code)
        )
        collect_task_id = request.params.get("collect_task_id") or request.task_id
        return {
            "event_id": hashlib.sha256(event_identity.encode("utf-8")).hexdigest(),
            "event_version": CREDENTIAL_RESULT_EVENT_VERSION,
            "producer": "stargazer",
            "scope_id": str(collect_task_id),
            "collect_task_id": collect_task_id,
            "run_id": request.task_id,
            "run_attempt_id": lease.attempt_id,
            "producer_instance": lease.owner_id,
            "plugin_ref": request.plugin_ref,
            "host": target,
            "credential_id": credential_id,
            "status": status,
            "error_code": error_code,
            "success": success,
            "failure_kind": "" if success else failure_kind,
            "error_message": "" if success else error_code,
            "attempts": attempts,
            "fence": lease.fence,
            "result_id": result_id,
            "event_index": event_index,
        }

    @staticmethod
    def _error_metrics(
        request: CollectionRequest,
        result: TargetCollectionResult,
        params: dict,
    ) -> str:
        error = RuntimeError(result.error_code or result.status)
        if str(request.params.get("plugin_family")) == "monitor":
            from tasks.utils.metrics_helper import generate_monitor_error_metrics

            return generate_monitor_error_metrics(params, error)
        from tasks.utils.metrics_helper import generate_plugin_error_metrics

        return generate_plugin_error_metrics(params, error)
