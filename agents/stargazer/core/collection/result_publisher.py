"""统一运行时的 NATS/业务回调结果发布器。"""

from __future__ import annotations

import asyncio
import hashlib
import time
import traceback
from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone

from core.collection.contracts import (
    PublishOutcome,
    PublishStatus,
    StructuredMetricsPayload,
    TargetCollectionResult,
    build_collection_result_id,
    has_publishable_metrics,
)
from core.collection.round_metadata import (
    SUPPORTED_MODELS,
    RoundMetadataConflictError,
    RoundMetadataError,
    RoundMetadataValidationError,
    build_round_metadata_envelope,
)
from core.collection.runtime import CollectionRequest, RunLease
from core.infra.publish_budget import PublishBudget

SCAN_CREDENTIAL_RESULT_SUBJECT = "receive_scan_credential_result"
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


@dataclass
class _BufferedPublishItem:
    request: CollectionRequest
    result: TargetCollectionResult | None
    lease: RunLease
    completion: asyncio.Future[PublishOutcome | None]
    state: _PublishAttemptState
    payload_permit: PayloadPermit
    steps: AsyncGenerator[tuple[str | None, BaseException | PublishOutcome | None], None] | None = None


def _clear_exception_locals(error: BaseException) -> None:
    """保留异常身份、链和堆栈位置，但终态不通过 traceback 持有大 payload。"""
    pending = [error]
    visited = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        if current.__traceback__ is not None:
            traceback.clear_frames(current.__traceback__)
        pending.extend(cause for cause in (current.__cause__, current.__context__) if cause is not None)


class PayloadPermit:
    """覆盖目标执行、排队、活动 Writer 与 transport 的单一 payload 生命周期额度。"""

    def __init__(self, publisher: BufferedResultPublisher) -> None:
        self._publisher = publisher
        self._attached = False
        self._released = False

    def attach(self, publisher: BufferedResultPublisher) -> None:
        if publisher is not self._publisher:
            raise ValueError("payload permit belongs to another publisher")
        if self._released:
            raise RuntimeError("payload permit is already released")
        if self._attached:
            raise RuntimeError("payload permit is already attached")
        self._attached = True

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._publisher._release_payload_permit()


class _PublishAttemptState:
    """跟踪结果是否仍可在触达 transport 前安全撤销。"""

    def __init__(
        self,
        completion: asyncio.Future[PublishOutcome | None],
        *,
        deadline: float | None = None,
        send_timeout_seconds: float | None = None,
        max_attempts: int = 2,
    ) -> None:
        self._completion = completion
        self._deadline = deadline
        self.send_budget = PublishBudget(send_timeout_seconds) if send_timeout_seconds is not None else None
        self.max_attempts = max_attempts
        self._processing = False
        self._delivery_started = False
        self._cancelled = False
        self._payload_released = False
        self._enqueued_at = time.monotonic()
        self._queue_wait_seconds = 0.0
        self._queue_depth_at_enqueue = 0
        self._queue_residence_seconds = 0.0
        self._terminal_at: float | None = None
        self._first_delivery_at: float | None = None
        completion.add_done_callback(self._mark_terminal)

    def _mark_terminal(self, _completion) -> None:
        if self._terminal_at is None:
            self._terminal_at = time.monotonic()
        # Run 可能已按总截止结束等待；仍消费后台终态异常，wait() 保留原异常。
        if not _completion.cancelled():
            _completion.exception()

    @property
    def terminal_at(self) -> float | None:
        return self._terminal_at

    @property
    def delivery_duration_seconds(self) -> float:
        if self.send_budget is not None:
            return self.send_budget.elapsed
        if self._first_delivery_at is None:
            return 0.0
        return max(0.0, (self._terminal_at or time.monotonic()) - self._first_delivery_at)

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def deadline(self) -> float | None:
        return self._deadline

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
        return max(0.0, (self._terminal_at or time.monotonic()) - self._enqueued_at)

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
        if not self._delivery_started:
            self._first_delivery_at = time.monotonic()
            self._queue_residence_seconds = self.queue_age_seconds
            self._delivery_started = True
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

    def release_payload_once(self) -> bool:
        if self._payload_released:
            return False
        self._payload_released = True
        return True


class FuturePublishReceipt:
    """发布队列回执；队列接纳与最终投递确认相互独立。"""

    def __init__(
        self,
        completion: asyncio.Future[PublishOutcome | None],
        state: _PublishAttemptState | None = None,
        *,
        retries_managed: bool = False,
    ) -> None:
        self._completion = completion
        self._state = state or _PublishAttemptState(completion)
        self.retries_managed = bool(retries_managed)

    def done(self) -> bool:
        return self._completion.done()

    @property
    def failed_stage(self) -> str:
        if not self._completion.done() or self._completion.cancelled():
            return ""
        error = self._completion.exception()
        return str(getattr(error, "failed_stage", "") or getattr(error, "timeout_phase", ""))

    @property
    def credit_wait_seconds(self) -> float:
        budget = self._state.send_budget
        return budget.credit_wait_seconds if budget is not None else 0.0

    def add_done_callback(self, callback) -> None:
        self._completion.add_done_callback(callback)

    def remove_done_callback(self, callback) -> None:
        self._completion.remove_done_callback(callback)

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

    @property
    def terminal_at(self) -> float | None:
        return self._state.terminal_at

    @property
    def delivery_duration_seconds(self) -> float:
        return self._state.delivery_duration_seconds


class PublishShutdownError(RuntimeError):
    """发布器退出时仍无法确认投递结果。"""

    delivery_detected = True


class ImmediateResultPublishQueue:
    """把旧逐条 ResultSink 显式适配为 enqueue/receipt interface。"""

    def __init__(self, sink) -> None:
        self._sink = sink

    async def enqueue(self, request, result, lease, *, deadline: float | None = None) -> FuturePublishReceipt:
        completion = asyncio.create_task(
            self._sink.publish(request, result, lease),
            name=f"result-publish:{request.task_id}:{result.target}",
        )
        state = _PublishAttemptState(completion, deadline=deadline)
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
        self._cooperative = bool(getattr(delegate, "cooperative_publish", False))
        self._queue: asyncio.Queue[_BufferedPublishItem | None] = asyncio.Queue(maxsize=capacity)
        self._payload_slots = asyncio.BoundedSemaphore(capacity)
        self._batch_size = int(batch_size)
        self.capacity = int(capacity)
        self._flush_interval_seconds = float(flush_interval_seconds)
        self._metrics = metrics
        self._worker_count = int(worker_count)
        self._writers: list[asyncio.Task] = []
        self._turns: set[asyncio.Task] = set()
        self._writer: asyncio.Task | None = None
        self._closed = False
        self._pending: set[asyncio.Future[PublishOutcome | None]] = set()
        self._pending_payloads = 0
        self.peak_pending_payloads = 0
        self.peak_queue_depth = 0
        self._active_batch_started_at: dict[asyncio.Task, float] = {}

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def pending_payloads(self) -> int:
        return self._pending_payloads

    @property
    def current_batch_age_seconds(self) -> float:
        if not self._active_batch_started_at:
            return 0.0
        oldest = min(self._active_batch_started_at.values())
        return max(0.0, time.monotonic() - oldest)

    def manages_retries_for(self, request: CollectionRequest) -> bool:
        manages_retries_for = getattr(self._delegate, "manages_retries_for", None)
        return bool(manages_retries_for(request) if callable(manages_retries_for) else False)

    @property
    def manages_delivery_budget(self) -> bool:
        return self._cooperative

    async def reserve_payload(self) -> PayloadPermit:
        """在执行可能产生大结果的目标前预留额度，随后把所有权转交给 Publisher。"""

        if self._closed:
            raise RuntimeError("result publisher is closed")
        await self._payload_slots.acquire()
        if self._closed:
            self._payload_slots.release()
            raise RuntimeError("result publisher is closed")
        self._pending_payloads += 1
        self.peak_pending_payloads = max(self.peak_pending_payloads, self._pending_payloads)
        if self._metrics is not None:
            self._metrics.add_gauge("publish_payloads_pending", 1)
        return PayloadPermit(self)

    async def enqueue(
        self,
        request,
        result,
        lease,
        *,
        deadline: float | None = None,
        payload_permit: PayloadPermit | None = None,
        send_timeout_seconds: float | None = None,
        max_attempts: int = 2,
    ) -> FuturePublishReceipt:
        if self._closed:
            if payload_permit is not None:
                payload_permit.release()
            raise RuntimeError("result publisher is closed")
        permit = payload_permit or await self.reserve_payload()
        try:
            permit.attach(self)
        except BaseException:
            permit.release()
            raise
        loop = asyncio.get_running_loop()
        completion = loop.create_future()
        state = _PublishAttemptState(completion, deadline=deadline, send_timeout_seconds=send_timeout_seconds, max_attempts=max_attempts)
        self._pending.add(completion)
        completion.add_done_callback(self._pending.discard)
        item = _BufferedPublishItem(request, result, lease, completion, state, permit)
        self._ensure_writer()
        enqueue_started = time.monotonic()
        try:
            await self._queue.put(item)
        except BaseException:
            if not completion.done():
                completion.cancel()
            self._release_payload(item)
            raise
        queue_wait_seconds = time.monotonic() - enqueue_started
        state.mark_enqueued(
            queue_wait_seconds=queue_wait_seconds,
            # writer 可能在 put 返回前已取走当前项；至少记入刚被接纳的这一项。
            queue_depth=max(1, self._queue.qsize()),
        )
        if self._metrics is not None:
            self._metrics.observe("publish_queue_wait_seconds", queue_wait_seconds)
        self.peak_queue_depth = max(self.peak_queue_depth, self._queue.qsize())
        return FuturePublishReceipt(
            completion,
            state,
            retries_managed=self.manages_retries_for(request),
        )

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
                if self._cooperative:
                    # 轮转项仍属同一个未完成结果；排空后才放退出哨兵。
                    await self._queue.join()
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
            turns = tuple(self._turns)
            for turn in turns:
                turn.cancel()
            await asyncio.gather(*turns, return_exceptions=True)
            self._fail_pending(PublishShutdownError("result publisher shutdown grace expired"))
            await self._discard_queued_items()
            if isinstance(asyncio.current_task(), asyncio.Task) and asyncio.current_task().cancelling():
                raise
        except Exception as error:  # writer 异常必须结束所有回执
            self._fail_pending(error)
            await self._discard_queued_items()

    def _fail_pending(self, error: BaseException) -> None:
        for completion in tuple(self._pending):
            if not completion.done():
                completion.set_exception(error)

    async def _discard_queued_items(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if item is not None:
                await self._close_item(item)
            if self._cooperative:
                self._queue.task_done()

    async def _close_item(self, item: _BufferedPublishItem) -> None:
        try:
            if item.steps is not None:
                await item.steps.aclose()
        finally:
            item.steps = None
            item.result = None
            self._release_payload(item)

    def _release_payload(self, item: _BufferedPublishItem) -> None:
        if not item.state.release_payload_once():
            return
        item.payload_permit.release()

    def _release_payload_permit(self) -> None:
        self._pending_payloads = max(0, self._pending_payloads - 1)
        self._payload_slots.release()
        if self._metrics is not None:
            self._metrics.add_gauge("publish_payloads_pending", -1)

    def _ensure_writer(self) -> None:
        self._writers = [writer for writer in self._writers if not writer.done()]
        while len(self._writers) < self._worker_count:
            worker_index = len(self._writers)
            writer = asyncio.create_task(
                self._cooperative_writer_loop() if self._cooperative else self._writer_loop(),
                name=f"collection-result-publisher:{worker_index}",
            )
            self._writers.append(writer)
        self._writer = self._writers[0]

    async def _cooperative_writer_loop(self) -> None:
        """Writer 调度有界 quantum；等待 ACK 不占用调度 Worker。"""
        while True:
            item = await self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            # 每个 Payload 仅一个活动 quantum；任务数受 capacity 硬限制，
            # 实际 NATS 消息/字节仍由共享 JetStream 双信贷限制。
            turn = asyncio.create_task(self._publish_turn(item), name="collection-publish-quantum")
            self._turns.add(turn)
            turn.add_done_callback(self._turns.discard)
            item = None

    async def _publish_turn(self, item: _BufferedPublishItem) -> None:
        requeued = False
        current_task = asyncio.current_task()
        started = time.monotonic()
        try:
            if item.state.cancelled:
                return
            if current_task is not None:
                self._active_batch_started_at[current_task] = started
            if item.steps is None:
                assert item.result is not None
                item.steps = self._delegate.publish_steps((item.request, item.result, item.lease, item.state))
            result_id, outcome = await anext(item.steps)
            if result_id is None:
                # 当前 quantum 持有一个额度，回队必有空位。
                self._queue.put_nowait(item)
                requeued = True
            else:
                await self._close_item(item)
                if isinstance(outcome, BaseException):
                    _clear_exception_locals(outcome)
                _complete_publish_item(item, outcome)
        except asyncio.CancelledError as error:
            await self._close_item(item)
            _clear_exception_locals(error)
            raise
        except Exception as error:
            if isinstance(error, TimeoutError) and not hasattr(error, "delivery_detected"):
                error.delivery_detected = item.state.delivery_started
            await self._close_item(item)
            _clear_exception_locals(error)
            if not item.completion.done():
                item.completion.set_exception(error)
        finally:
            if not requeued:
                await self._close_item(item)
            self._queue.task_done()
            if current_task is not None:
                self._active_batch_started_at.pop(current_task, None)
            if self._metrics is not None:
                self._metrics.observe("publish_flush_duration_seconds", time.monotonic() - started)

    async def _writer_loop(self) -> None:
        while True:
            first = await self._queue.get()
            if first is None:
                return
            owned_items = [first]
            batch = [] if first.state.cancelled else [first]
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
                    try:
                        await self._deliver(batch)
                    finally:
                        for owned in owned_items:
                            self._release_payload(owned)
                    return
                owned_items.append(item)
                if not item.state.cancelled:
                    batch.append(item)
            try:
                await self._deliver(batch)
            finally:
                for owned in owned_items:
                    self._release_payload(owned)

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
        publish_batch_events = getattr(self._delegate, "publish_batch_events", None)
        publish_batch = getattr(self._delegate, "publish_batch", None)
        try:
            if callable(publish_batch_events):
                await self._deliver_event_batch(batch, publish_batch_events)
                return
            if callable(publish_batch):
                await self._deliver_mapping_batch(batch, publish_batch)
                return
            await self._deliver_individually(batch)
        finally:
            if current_task is not None:
                self._active_batch_started_at.pop(current_task, None)
            if self._metrics is not None:
                self._metrics.observe("publish_flush_duration_seconds", time.monotonic() - flush_started)

    async def _deliver_event_batch(self, batch, publish_batch_events) -> None:
        items_by_result_id = {_publish_item_result_id(item): item for item in batch}
        try:
            async for result_id, outcome in publish_batch_events(tuple((item.request, item.result, item.lease, item.state) for item in batch)):
                item = items_by_result_id.pop(str(result_id), None)
                if item is None or item.completion.done():
                    continue
                _complete_publish_item(item, outcome)
        except Exception as exc:
            for item in items_by_result_id.values():
                if not item.completion.done():
                    item.completion.set_exception(exc)
        else:
            for item in items_by_result_id.values():
                if not item.completion.done():
                    item.completion.set_result(
                        PublishOutcome(
                            status=PublishStatus.RETRYABLE_FAILED,
                            error_code="publish_batch_terminal_missing",
                        )
                    )

    async def _deliver_mapping_batch(self, batch, publish_batch) -> None:
        try:
            outcomes = await publish_batch(tuple((item.request, item.result, item.lease, item.state) for item in batch))
        except Exception as exc:  # 同批各目标获得独立失败结论
            for item in batch:
                if not item.completion.done():
                    item.completion.set_exception(exc)
            return

        per_result = outcomes if isinstance(outcomes, Mapping) else {}
        for item in batch:
            if item.completion.done():
                continue
            outcome = per_result.get(_publish_item_result_id(item))
            _complete_publish_item(item, outcome)

    async def _deliver_individually(self, batch) -> None:
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


def _publish_item_result_id(item: _BufferedPublishItem) -> str:
    assert item.result is not None
    return build_collection_result_id(
        task_id=item.request.task_id,
        plugin_ref=item.request.plugin_ref,
        target=item.result.target,
        fence=item.lease.fence,
        attempt_id=item.lease.attempt_id,
    )


def _complete_publish_item(item: _BufferedPublishItem, outcome) -> None:
    if item.completion.done():
        return
    if isinstance(outcome, BaseException):
        item.completion.set_exception(outcome)
    elif isinstance(outcome, PublishOutcome):
        item.completion.set_result(outcome)
    else:
        item.completion.set_result(PublishOutcome(status=PublishStatus.CONFIRMED))


class NatsResultPublisher:
    tracks_transport_attempts = True

    def __init__(
        self,
        *,
        metrics_publish: Callable | None = None,
        metrics_publish_batch: Callable | None = None,
        callback_publish: Callable | None = None,
        credential_result_publish: Callable | None = None,
        round_metadata_store=None,
        metrics=None,
        prepare_timeout_seconds: float = 30.0,
    ) -> None:
        self._metrics_publish = metrics_publish
        self._metrics_publish_batch = metrics_publish_batch
        self._callback_publish = callback_publish
        self._credential_result_publish = credential_result_publish
        self._round_metadata_store = round_metadata_store
        self._metrics = metrics
        if prepare_timeout_seconds <= 0:
            raise ValueError("prepare_timeout_seconds must be greater than zero")
        self._prepare_timeout_seconds = prepare_timeout_seconds

    def manages_retries_for(self, request: CollectionRequest) -> bool:
        """默认 metrics JetStream 在 transport 内完成有限重试。"""

        return not request.params.get("callback_subject") and self._metrics_publish is None and self._metrics_publish_batch is None

    @property
    def cooperative_publish(self) -> bool:
        return self._metrics_publish is None and self._metrics_publish_batch is None

    async def publish_steps(self, item):
        """发布器内部游标：None ID 表示让出 Writer，非空 ID 表示目标终态。"""
        events = self.publish_batch_events((item,), cooperative=True)
        try:
            async for result_id, outcome in events:
                yield result_id, outcome
        finally:
            await events.aclose()

    async def publish_batch(self, items) -> dict[str, BaseException | PublishOutcome | None]:
        """兼容批量调用方；内部按逐目标终态事件收集结果。"""
        outcomes: dict[str, BaseException | PublishOutcome | None] = {}
        async for result_id, outcome in self.publish_batch_events(items):
            outcomes[result_id] = outcome
        return outcomes

    async def publish_batch_events(self, items, *, cooperative=False):  # noqa: C901
        """逐目标产出发布终态，避免同批慢结果阻塞已经完成的回执。"""
        metrics_entries = []
        metric_events = []
        non_metrics = []
        for item in items:
            request, result, lease = item[:3]
            attempt_state = item[3] if len(item) > 3 else None
            result_id = build_collection_result_id(
                task_id=request.task_id,
                plugin_ref=request.plugin_ref,
                target=result.target,
                fence=lease.fence,
                attempt_id=lease.attempt_id,
            )
            deadline = getattr(attempt_state, "deadline", None)
            if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                yield (
                    result_id,
                    PublishOutcome(
                        status=PublishStatus.RETRYABLE_FAILED,
                        error_code="publish_total_timeout_before_delivery",
                    ),
                )
                if self._metrics is not None:
                    self._metrics.increment("publish_deadline_expired_total")
                continue
            if request.params.get("callback_subject"):
                non_metrics.append((request, result, lease, attempt_state))
                continue
            try:
                if str(request.params.get("credential_result_subject") or "").strip() == SCAN_CREDENTIAL_RESULT_SUBJECT:
                    budget = getattr(attempt_state, "send_budget", None)
                    if attempt_state is not None:
                        attempt_state.mark_delivery_started()
                    with budget.sending() if budget is not None else nullcontext(deadline) as send_deadline:
                        async with asyncio.timeout_at(send_deadline):
                            await self._publish_scan_credential_result_if_needed(request, result, lease, result_id)
            except Exception as error:  # noqa: BLE001 - 返回逐目标失败，不抛整批
                yield result_id, error
                continue
            if result.status != "success" or not has_publishable_metrics(result.value):
                yield result_id, None
                continue
            params = self._result_params(request, result, lease, result_id, attempt_state=attempt_state)
            metrics = result.value
            try:
                await self._prepare_round_metadata(request, result, attempt_state)
            except (RoundMetadataConflictError, RoundMetadataValidationError) as error:
                yield (
                    result_id,
                    PublishOutcome(
                        status=PublishStatus.PERMANENT_FAILED,
                        error_code=error.error_code,
                    ),
                )
                continue
            except Exception as error:  # noqa: BLE001 - 发布器在持有 payload 期间已完成有限重试
                error.delivery_detected = False
                error.failed_stage = "round_metadata"
                yield result_id, error
                continue
            metrics_entries.append(({}, metrics, params, request.task_id))
            metric_events.append((request, result, lease, result_id))

        if metrics_entries:
            metrics_publish_batch = self._metrics_publish_batch
            using_default_batch = metrics_publish_batch is None and self._metrics_publish is None
            if using_default_batch:
                from tasks.utils.nats_helper import iter_metrics_batch_outcomes

                if cooperative:
                    from tasks.utils.nats_helper import iter_metrics_publish_steps

                    events = iter_metrics_publish_steps(metrics_entries[0], metrics=self._metrics)
                else:
                    events = iter_metrics_batch_outcomes(tuple(metrics_entries), metrics=self._metrics)
                try:
                    async for result_id, outcome in events:
                        yield result_id, outcome
                finally:
                    await events.aclose()
            elif metrics_publish_batch is not None:
                try:
                    batch_outcomes = await metrics_publish_batch(tuple(metrics_entries))
                except Exception as error:  # noqa: BLE001 - 返回逐目标失败，不抛整批
                    for _request, _result, _lease, result_id in metric_events:
                        yield result_id, error
                else:
                    per_result = batch_outcomes if isinstance(batch_outcomes, Mapping) else {}
                    for _request, _result, _lease, result_id in metric_events:
                        outcome = per_result.get(result_id)
                        if isinstance(outcome, ValueError):
                            yield (
                                result_id,
                                PublishOutcome(
                                    status=PublishStatus.PERMANENT_FAILED,
                                    error_code=str(
                                        getattr(
                                            outcome,
                                            "error_code",
                                            "metrics_encode_failed",
                                        )
                                    ),
                                ),
                            )
                        else:
                            yield result_id, outcome if isinstance(outcome, BaseException) else None
            else:
                individual_outcomes = await asyncio.gather(
                    *(self._metrics_publish(*entry) for entry in metrics_entries),
                    return_exceptions=True,
                )
                for event, outcome in zip(metric_events, individual_outcomes):
                    yield event[3], outcome if isinstance(outcome, BaseException) else None
        if non_metrics:

            async def publish_non_metric(request, result, lease, attempt_state):
                if attempt_state is not None and not attempt_state.mark_delivery_started():
                    return PublishOutcome(
                        status=PublishStatus.RETRYABLE_FAILED,
                        error_code="publish_cancelled_before_delivery",
                    )
                budget = getattr(attempt_state, "send_budget", None)
                with budget.sending() if budget is not None else nullcontext(getattr(attempt_state, "deadline", None)) as send_deadline:
                    async with asyncio.timeout_at(send_deadline):
                        await self.publish(request, result, lease)
                return None

            non_metric_outcomes = await asyncio.gather(
                *(publish_non_metric(request, result, lease, attempt_state) for request, result, lease, attempt_state in non_metrics),
                return_exceptions=True,
            )
            for (request, result, lease, _attempt_state), outcome in zip(non_metrics, non_metric_outcomes):
                result_id = build_collection_result_id(
                    task_id=request.task_id,
                    plugin_ref=request.plugin_ref,
                    target=result.target,
                    fence=lease.fence,
                    attempt_id=lease.attempt_id,
                )
                yield result_id, outcome if isinstance(outcome, (BaseException, PublishOutcome)) else None

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
        params = self._result_params(request, result, lease, result_id)
        await self._publish_scan_credential_result_if_needed(request, result, lease, result_id)
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
            return
        if result.status != "success" or not has_publishable_metrics(result.value):
            return

        await self._persist_round_metadata(request, result)

        metrics_publish = self._metrics_publish
        if metrics_publish is None:
            from tasks.utils.nats_helper import publish_metrics_to_nats

            metrics_publish = publish_metrics_to_nats
        metrics = result.value
        await metrics_publish({}, metrics, params, request.task_id)

    async def _prepare_round_metadata(self, request, result, attempt_state) -> None:
        """幂等元数据写入先于指标发送；准备阶段单独有界，不占 NATS 发送预算。"""
        deadline = asyncio.get_running_loop().time() + self._prepare_timeout_seconds
        legacy_deadline = getattr(attempt_state, "deadline", None)
        if legacy_deadline is not None:
            deadline = min(deadline, legacy_deadline)
        started = time.monotonic()
        try:
            async with asyncio.timeout_at(deadline):
                for attempt in range(getattr(attempt_state, "max_attempts", 2)):
                    try:
                        await self._persist_round_metadata(request, result)
                        return
                    except (RoundMetadataConflictError, RoundMetadataValidationError):
                        raise
                    except Exception:
                        if attempt + 1 >= getattr(attempt_state, "max_attempts", 2):
                            raise
                        if self._metrics is not None:
                            self._metrics.increment("publish_prepare_retry_total")
                        await asyncio.sleep(0.1 * (attempt + 1))
        finally:
            if self._metrics is not None:
                self._metrics.observe("publish_prepare_duration_seconds", time.monotonic() - started)

    async def _persist_round_metadata(self, request, result) -> None:
        payload = result.value
        requires_metadata = request.params.get("model_id") in SUPPORTED_MODELS and result.status == "success"
        if not isinstance(payload, StructuredMetricsPayload):
            if requires_metadata:
                raise RoundMetadataValidationError("metadata_missing")
            return
        if not payload.round_metadata:
            if requires_metadata:
                raise RoundMetadataValidationError("metadata_missing")
            return
        if self._round_metadata_store is None:
            raise RoundMetadataError("metadata_unavailable")
        envelope = build_round_metadata_envelope(
            task_id=request.task_id,
            target=result.target,
            plugin_ref=request.plugin_ref,
            model_id=request.params.get("model_id"),
            publish_timestamp_ms=result.publish_timestamp_ms,
            metadata=payload.round_metadata,
        )
        await self._round_metadata_store.save(envelope)

    @staticmethod
    def _result_params(request, result, lease, result_id, *, attempt_state=None) -> dict:
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

    async def _publish_scan_credential_result_if_needed(
        self,
        request: CollectionRequest,
        result: TargetCollectionResult,
        lease: RunLease,
        result_id: str,
    ) -> None:
        if str(request.params.get("credential_result_subject") or "").strip() != SCAN_CREDENTIAL_RESULT_SUBJECT:
            return
        credential_failures = tuple(getattr(result, "credential_failures", ()))
        for event_index, failure in enumerate(credential_failures):
            await self._emit_scan_credential_event(
                request,
                self._build_credential_event(
                    request=request,
                    result=result,
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
        await self._emit_scan_credential_event(
            request,
            self._build_credential_event(
                request=request,
                result=result,
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

    async def _emit_scan_credential_event(self, request: CollectionRequest, event: dict) -> None:
        if not str(event.get("finished_at") or "").strip():
            event["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        publish = self._credential_result_publish
        if publish is None:
            from core.infra.control_transport import get_control_transport

            async def publish(result, _params, _task_id):
                await get_control_transport().publish_collection_callback(
                    SCAN_CREDENTIAL_RESULT_SUBJECT,
                    result,
                )

        await publish(event, dict(request.params), request.task_id)

    @classmethod
    def _build_credential_event(
        cls,
        *,
        request: CollectionRequest,
        result: TargetCollectionResult,
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
        failure_kind = "credential" if status == "failed" and error_code in CREDENTIAL_FAILURE_ERROR_CODES else "task"
        event_identity = "\0".join((result_id, str(event_index), credential_id, status, error_code))
        collect_task_id = request.params.get("collect_task_id") or request.task_id
        snapshot, port = cls._extract_scan_snapshot(request, result)
        event = {
            "event_id": hashlib.sha256(event_identity.encode("utf-8")).hexdigest(),
            "event_version": str(CREDENTIAL_RESULT_EVENT_VERSION),
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
            "snapshot": snapshot,
        }
        if port > 0:
            event["port"] = port
        return event

    _SCAN_SNAPSHOT_KEYS = (
        "hostname",
        "os_type",
        "os_name",
        "os_version",
        "os_bit",
        "cpu_arch",
        "cpu_model",
        "cpu_core",
        "memory",
        "disk",
        "inner_mac",
        "serial_number",
        "uuid",
        "board_serial",
        "inst_name",
        "ip_addr",
        "soid",
        "sysobjectid",
        "sysname",
        "sysdescr",
        "device_type",
        "brand",
        "model",
        "version",
        "db_version",
    )

    @classmethod
    def _iter_scan_snapshot_sources(cls, data: Mapping):
        """展开 host / network_system 等列表桶，兼容扁平 system 字典。"""
        preferred = (
            "system",
            "network_system",
            "host",
            "physcial_server",
            "physical_server",
        )
        for key in preferred:
            value = data.get(key)
            if isinstance(value, Mapping):
                yield value
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, Mapping):
                        yield item
        for value in data.values():
            if isinstance(value, Mapping):
                yield value
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, Mapping):
                        yield item

    @classmethod
    def _extract_scan_snapshot(
        cls,
        request: CollectionRequest,
        result: TargetCollectionResult,
    ) -> tuple[dict, int]:
        """从 params / 采集结果尽力提取扫描命中身份；缺字段时仍可推进进度。"""
        snapshot: dict = {"host": result.target}
        port = 0

        def _coerce_port(raw) -> int:
            try:
                value = int(raw)
            except (TypeError, ValueError):
                return 0
            return value if value > 0 else 0

        for key in ("port", "snmp_port", "http_port"):
            candidate = _coerce_port(request.params.get(key))
            if candidate:
                port = candidate
                break

        payload = result.value
        data: Mapping | None = None
        if isinstance(payload, StructuredMetricsPayload):
            if isinstance(payload.data, Mapping):
                data = payload.data
        elif isinstance(payload, Mapping):
            data = payload

        if data is not None:
            for source in cls._iter_scan_snapshot_sources(data):
                soid = source.get("sysobjectid") or source.get("sysObjectID") or source.get("soid")
                if soid not in (None, "") and "sysobjectid" not in snapshot:
                    snapshot["sysobjectid"] = str(soid)
                    snapshot.setdefault("soid", str(soid))
                candidate = _coerce_port(source.get("port") or source.get("snmp_port"))
                if candidate:
                    port = candidate
                for key in cls._SCAN_SNAPSHOT_KEYS:
                    if key in snapshot and snapshot.get(key) not in (None, ""):
                        continue
                    value = source.get(key)
                    if value not in (None, ""):
                        snapshot[key] = value if isinstance(value, (int, float, bool)) else str(value)

        if port > 0:
            snapshot["port"] = port
        return snapshot, port
