"""统一运行时的 NATS/业务回调结果发布器。"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Callable, Mapping

from core.collection.contracts import TargetCollectionResult, build_collection_result_id
from core.collection.runtime import CollectionRequest, RunLease

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
    completion: asyncio.Future[None]


class FuturePublishReceipt:
    """发布队列回执；队列接纳与最终投递确认相互独立。"""

    def __init__(self, completion: asyncio.Future[None]) -> None:
        self._completion = completion

    def done(self) -> bool:
        return self._completion.done()

    async def wait(self) -> None:
        await self._completion


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
        return FuturePublishReceipt(completion)


class BufferedResultPublisher:
    """有界聚合单目标结果，并把批处理细节隐藏在 publisher seam 后。"""

    def __init__(
        self,
        delegate,
        *,
        capacity: int,
        batch_size: int = 50,
        flush_interval_seconds: float = 0.01,
        metrics=None,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        if flush_interval_seconds <= 0:
            raise ValueError("flush_interval_seconds must be greater than zero")
        self._delegate = delegate
        self._queue: asyncio.Queue[_BufferedPublishItem | None] = asyncio.Queue(maxsize=capacity)
        self._batch_size = int(batch_size)
        self.capacity = int(capacity)
        self._flush_interval_seconds = float(flush_interval_seconds)
        self._metrics = metrics
        self._writer: asyncio.Task | None = None
        self._closed = False
        self._pending: set[asyncio.Future[None]] = set()
        self.peak_queue_depth = 0

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    async def enqueue(self, request, result, lease) -> FuturePublishReceipt:
        if self._closed:
            raise RuntimeError("result publisher is closed")
        loop = asyncio.get_running_loop()
        completion = loop.create_future()
        self._pending.add(completion)
        completion.add_done_callback(self._pending.discard)
        item = _BufferedPublishItem(request, result, lease, completion)
        self._ensure_writer()
        enqueue_started = time.monotonic()
        await self._queue.put(item)
        if self._metrics is not None:
            self._metrics.observe("publish_queue_wait_seconds", time.monotonic() - enqueue_started)
        self.peak_queue_depth = max(self.peak_queue_depth, self._queue.qsize())
        return FuturePublishReceipt(completion)

    async def publish(self, request, result, lease) -> None:
        receipt = await self.enqueue(request, result, lease)
        await receipt.wait()

    async def shutdown(self, *, grace_seconds: float = 30.0) -> None:
        if self._closed:
            return
        self._closed = True
        writer = self._writer
        if writer is None:
            return
        try:
            async with asyncio.timeout(max(0.0, grace_seconds)):
                await self._queue.put(None)
                await writer
        except (TimeoutError, asyncio.CancelledError):
            if self._metrics is not None:
                self._metrics.increment("publish_shutdown_timeout_total")
            if not writer.done():
                writer.cancel()
            await asyncio.gather(writer, return_exceptions=True)
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
        if self._writer is None or self._writer.done():
            self._writer = asyncio.create_task(self._writer_loop(), name="collection-result-publisher")

    async def _writer_loop(self) -> None:
        while True:
            first = await self._queue.get()
            if first is None:
                return
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
                batch.append(item)
            await self._deliver(batch)

    async def _deliver(self, batch: list[_BufferedPublishItem]) -> None:
        flush_started = time.monotonic()
        if self._metrics is not None:
            self._metrics.increment("publish_batch_total")
            self._metrics.increment("publish_batch_items_total", len(batch))
            self._metrics.observe("publish_batch_size", len(batch))
        publish_batch = getattr(self._delegate, "publish_batch", None)
        try:
            if callable(publish_batch):
                try:
                    outcomes = await publish_batch(tuple((item.request, item.result, item.lease) for item in batch))
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
                        )
                        outcome = per_result.get(result_id)
                        if isinstance(outcome, BaseException):
                            item.completion.set_exception(outcome)
                        else:
                            item.completion.set_result(None)
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
                    item.completion.set_result(None)
        finally:
            if self._metrics is not None:
                self._metrics.observe("publish_flush_duration_seconds", time.monotonic() - flush_started)


class NatsResultPublisher:
    def __init__(
        self,
        *,
        metrics_publish: Callable | None = None,
        metrics_publish_batch: Callable | None = None,
        callback_publish: Callable | None = None,
        result_event_sink: Callable | None = None,
        metrics=None,
    ) -> None:
        self._metrics_publish = metrics_publish
        self._metrics_publish_batch = metrics_publish_batch
        self._callback_publish = callback_publish
        self._result_event_sink = result_event_sink
        self._metrics = metrics

    async def publish_batch(self, items) -> dict[str, BaseException | None]:
        outcomes: dict[str, BaseException | None] = {}
        metrics_entries = []
        metric_events = []
        non_metrics = []
        for request, result, lease in items:
            if result.status == "deferred" or request.params.get("callback_subject"):
                non_metrics.append((request, result, lease))
                continue
            result_id = build_collection_result_id(
                task_id=request.task_id,
                plugin_ref=request.plugin_ref,
                target=result.target,
                fence=lease.fence,
            )
            params = self._result_params(request, result, lease, result_id)
            metrics = result.value
            if not metrics or result.status not in {"success", "deferred"}:
                metrics = self._error_metrics(request, result, params)
            metrics_entries.append(({}, metrics, params, request.task_id))
            metric_events.append((request, result, lease, result_id))
            outcomes[result_id] = None

        if metrics_entries:
            metrics_publish_batch = self._metrics_publish_batch
            using_default_batch = metrics_publish_batch is None and self._metrics_publish is None
            if using_default_batch:
                from tasks.utils.nats_helper import publish_metrics_batch_to_nats

                metrics_publish_batch = publish_metrics_batch_to_nats
            if metrics_publish_batch is not None:
                try:
                    if using_default_batch:
                        batch_outcomes = await metrics_publish_batch(tuple(metrics_entries), metrics=self._metrics)
                    else:
                        batch_outcomes = await metrics_publish_batch(tuple(metrics_entries))
                except Exception as error:  # noqa: BLE001 - 返回逐目标失败，不抛整批
                    for _request, _result, _lease, result_id in metric_events:
                        outcomes[result_id] = error
                else:
                    if isinstance(batch_outcomes, Mapping):
                        for result_id, outcome in batch_outcomes.items():
                            if result_id in outcomes and isinstance(outcome, BaseException):
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
                    await self._record_event(request, result, lease, result_id)
                except Exception as error:  # noqa: BLE001 - 事件记录按目标归因
                    outcomes[result_id] = error

        if non_metrics:
            non_metric_outcomes = await asyncio.gather(
                *(self.publish(request, result, lease) for request, result, lease in non_metrics),
                return_exceptions=True,
            )
            for (request, result, lease), outcome in zip(non_metrics, non_metric_outcomes):
                result_id = build_collection_result_id(
                    task_id=request.task_id,
                    plugin_ref=request.plugin_ref,
                    target=result.target,
                    fence=lease.fence,
                )
                outcomes[result_id] = outcome if isinstance(outcome, BaseException) else None
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
            await self._record_event(request, result, lease, result_id)
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
            await self._record_event(request, result, lease, result_id)
            return

        metrics_publish = self._metrics_publish
        if metrics_publish is None:
            from tasks.utils.nats_helper import publish_metrics_to_nats

            metrics_publish = publish_metrics_to_nats
        metrics = result.value
        if not metrics or result.status not in {"success", "deferred"}:
            metrics = self._error_metrics(request, result, params)
        await metrics_publish({}, metrics, params, request.task_id)
        await self._record_event(request, result, lease, result_id)

    @staticmethod
    def _result_params(request, result, lease, result_id) -> dict:
        params = dict(request.params)
        params.update(
            {
                "host": result.target,
                "collection_task_id": request.task_id,
                "collection_fence": lease.fence,
                "collection_target": result.target,
                "collection_plugin_ref": request.plugin_ref,
                "collection_result_id": result_id,
            }
        )
        return params

    async def _record_event(
        self,
        request: CollectionRequest,
        result: TargetCollectionResult,
        lease: RunLease,
        result_id: str,
    ) -> None:
        if self._result_event_sink is None:
            return
        credential_failures = tuple(getattr(result, "credential_failures", ()))
        for event_index, failure in enumerate(credential_failures):
            await self._result_event_sink(
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
                )
            )

        if credential_failures and not result.credential_id:
            return

        await self._result_event_sink(
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
            )
        )

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
        failure_kind = "credential" if status == "failed" and error_code in CREDENTIAL_FAILURE_ERROR_CODES else "task"
        event_identity = "\0".join((result_id, str(event_index), credential_id, status, error_code))
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
