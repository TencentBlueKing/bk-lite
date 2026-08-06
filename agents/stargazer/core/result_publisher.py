"""统一运行时的 NATS/业务回调结果发布器。"""

from __future__ import annotations

import hashlib
from typing import Callable

from core.collection_runtime import CollectionRequest, RunLease
from core.target_collection_executor import TargetCollectionResult


class NatsResultPublisher:
    def __init__(
        self,
        *,
        metrics_publish: Callable | None = None,
        callback_publish: Callable | None = None,
        result_event_sink: Callable | None = None,
    ) -> None:
        self._metrics_publish = metrics_publish
        self._callback_publish = callback_publish
        self._result_event_sink = result_event_sink

    async def publish(
        self,
        request: CollectionRequest,
        result: TargetCollectionResult,
        lease: RunLease,
    ) -> None:
        result_id = _result_id(request, result, lease)
        if result.status == "deferred":
            await self._record_event(request, result, lease, result_id)
            return
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


def _result_id(
    request: CollectionRequest,
    result: TargetCollectionResult,
    lease: RunLease,
) -> str:
    identity = "\0".join(
        (request.task_id, request.plugin_ref, result.target, str(lease.fence))
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()
