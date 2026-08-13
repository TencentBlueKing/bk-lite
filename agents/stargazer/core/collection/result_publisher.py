"""统一运行时的 NATS/业务回调结果发布器。"""

from __future__ import annotations

import hashlib
from typing import Callable

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
