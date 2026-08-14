"""统一运行时的 NATS/业务回调结果发布器。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from core.collection.contracts import TargetCollectionResult, build_collection_result_id
from core.collection.runtime import CollectionRequest, RunLease


@dataclass(frozen=True)
class _BufferedPublishItem:
    request: CollectionRequest
    result: TargetCollectionResult
    lease: RunLease
    completion: asyncio.Future[None]


class BufferedResultPublisher:
    """有界聚合单目标结果，并把批处理细节隐藏在 publisher seam 后。"""

    def __init__(
        self,
        delegate,
        *,
        capacity: int,
        batch_size: int = 50,
        flush_interval_seconds: float = 0.01,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        if flush_interval_seconds <= 0:
            raise ValueError("flush_interval_seconds must be greater than zero")
        self._delegate = delegate
        self._queue: asyncio.Queue[_BufferedPublishItem | None] = asyncio.Queue(
            maxsize=capacity
        )
        self._batch_size = int(batch_size)
        self.capacity = int(capacity)
        self._flush_interval_seconds = float(flush_interval_seconds)
        self._writer: asyncio.Task | None = None
        self._closed = False
        self.peak_queue_depth = 0

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    async def publish(self, request, result, lease) -> None:
        if self._closed:
            raise RuntimeError("result publisher is closed")
        loop = asyncio.get_running_loop()
        completion = loop.create_future()
        item = _BufferedPublishItem(request, result, lease, completion)
        self._ensure_writer()
        await self._queue.put(item)
        self.peak_queue_depth = max(self.peak_queue_depth, self._queue.qsize())
        await completion

    async def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        writer = self._writer
        if writer is None:
            return
        await self._queue.put(None)
        await writer

    def _ensure_writer(self) -> None:
        if self._writer is None or self._writer.done():
            self._writer = asyncio.create_task(
                self._writer_loop(), name="collection-result-publisher"
            )

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
        publish_batch = getattr(self._delegate, "publish_batch", None)
        if callable(publish_batch):
            try:
                await publish_batch(
                    tuple((item.request, item.result, item.lease) for item in batch)
                )
            except Exception as exc:  # 同批各目标获得独立失败结论
                for item in batch:
                    if not item.completion.done():
                        item.completion.set_exception(exc)
            else:
                for item in batch:
                    if not item.completion.done():
                        item.completion.set_result(None)
            return

        outcomes = await asyncio.gather(
            *(
                self._delegate.publish(item.request, item.result, item.lease)
                for item in batch
            ),
            return_exceptions=True,
        )
        for item, outcome in zip(batch, outcomes):
            if item.completion.done():
                continue
            if isinstance(outcome, BaseException):
                item.completion.set_exception(outcome)
            else:
                item.completion.set_result(None)


class NatsResultPublisher:
    def __init__(
        self,
        *,
        metrics_publish: Callable | None = None,
        metrics_publish_batch: Callable | None = None,
        callback_publish: Callable | None = None,
        result_event_sink: Callable | None = None,
    ) -> None:
        self._metrics_publish = metrics_publish
        self._metrics_publish_batch = metrics_publish_batch
        self._callback_publish = callback_publish
        self._result_event_sink = result_event_sink

    async def publish_batch(self, items) -> None:
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
            metrics_entries.append(({}, str(metrics), params, request.task_id))
            metric_events.append((request, result, lease, result_id))

        if metrics_entries:
            metrics_publish_batch = self._metrics_publish_batch
            if metrics_publish_batch is None and self._metrics_publish is None:
                from tasks.utils.nats_helper import publish_metrics_batch_to_nats

                metrics_publish_batch = publish_metrics_batch_to_nats
            if metrics_publish_batch is not None:
                await metrics_publish_batch(tuple(metrics_entries))
            else:
                await asyncio.gather(
                    *(self._metrics_publish(*entry) for entry in metrics_entries)
                )
            for request, result, lease, result_id in metric_events:
                await self._record_event(request, result, lease, result_id)

        if non_metrics:
            await asyncio.gather(
                *(
                    self.publish(request, result, lease)
                    for request, result, lease in non_metrics
                )
            )

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
        await metrics_publish({}, str(metrics), params, request.task_id)
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
        await self._result_event_sink(
            {
                "collect_task_id": request.task_id,
                "plugin_ref": request.plugin_ref,
                "host": result.target,
                "credential_id": result.credential_id,
                "status": result.status,
                "error_code": result.error_code,
                "attempts": result.attempts,
                "fence": lease.fence,
                "result_id": result_id,
            }
        )

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
