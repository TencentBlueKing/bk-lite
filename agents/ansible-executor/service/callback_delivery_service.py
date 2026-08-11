"""Executor 完成回调、压缩与可恢复重试。"""

import asyncio
import json
from copy import deepcopy
from typing import Any

import nats.errors
from core.config import logger
from service.task_store_sanitization import _sanitize_callback_for_storage


class CallbackDeliveryMixin:
    CALLBACK_PAYLOAD_MARGIN_BYTES = 4 * 1024
    CALLBACK_RESULT_TEXT_MAX_CHARS = 8 * 1024

    @classmethod
    def _callback_request_size_bytes(cls, payload: dict[str, Any]) -> int:
        request_payload = json.dumps(
            {"args": [payload], "kwargs": {}},
            ensure_ascii=False,
        ).encode("utf-8")
        return len(request_payload)

    @classmethod
    def _truncate_callback_text(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        if len(value) <= cls.CALLBACK_RESULT_TEXT_MAX_CHARS:
            return value
        return value[: cls.CALLBACK_RESULT_TEXT_MAX_CHARS] + "\n...[truncated for callback]"

    @classmethod
    def _compact_callback_payload(cls, payload: dict[str, Any], max_bytes: int) -> dict[str, Any]:
        callback_payload = deepcopy(payload)
        if cls._callback_request_size_bytes(callback_payload) <= max_bytes:
            return callback_payload

        result_summary = callback_payload.get("result_summary")
        if isinstance(result_summary, dict):
            result_summary.pop("stdout_combined", None)
            result_summary["callback_payload_truncated"] = True
        if cls._callback_request_size_bytes(callback_payload) <= max_bytes:
            return callback_payload

        result = callback_payload.get("result")
        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    for field in ("stdout", "stderr", "error_message"):
                        item[field] = cls._truncate_callback_text(item.get(field, ""))
        elif isinstance(result, str):
            callback_payload["result"] = cls._truncate_callback_text(result)
        callback_payload["error"] = cls._truncate_callback_text(callback_payload.get("error", ""))
        if cls._callback_request_size_bytes(callback_payload) <= max_bytes:
            return callback_payload

        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    item.update(stdout="", stderr="", error_message="")
        elif isinstance(callback_payload.get("result"), str):
            callback_payload["result"] = ""
        if isinstance(result_summary, dict):
            callback_payload["result_summary"] = {
                key: result_summary[key]
                for key in (
                    "host_count",
                    "output_truncated",
                    "output_bytes_total",
                    "output_bytes_retained",
                    "output_max_bytes",
                    "callback_payload_truncated",
                )
                if key in result_summary
            }
        callback_payload["callback_payload_truncated"] = True
        return callback_payload

    def _prepare_callback_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        max_payload = int(getattr(self.nc, "max_payload", 1024 * 1024) or 1024 * 1024)
        return self._compact_callback_payload(
            payload,
            max(1024, max_payload - self.CALLBACK_PAYLOAD_MARGIN_BYTES),
        )

    async def _invoke_callback(self, callback: dict[str, Any] | None, payload: dict[str, Any]):
        if not callback or not isinstance(callback, dict):
            return
        subject = str(callback.get("subject", "")).strip()
        namespace = str(callback.get("namespace", "")).strip()
        method_name = str(callback.get("method_name", "")).strip()
        instance_id = str(callback.get("instance_id", "")).strip()
        if not subject and (not namespace or not method_name):
            logger.warning(
                "skip invalid callback config: subject=%s namespace=%s method_name=%s instance_id=%s",
                subject,
                namespace,
                method_name,
                instance_id,
            )
            return
        if not subject:
            subject = f"{namespace}.{method_name}.{instance_id}" if instance_id else f"{namespace}.{method_name}"
        self._validate_callback_subject(subject)

        callback_payload = dict(payload)
        context = callback.get("context")
        if isinstance(context, dict):
            callback_payload["callback_context"] = deepcopy(context)
        request_payload = json.dumps(
            {"args": [callback_payload], "kwargs": {}},
            ensure_ascii=False,
        ).encode("utf-8")
        response = await self.nc.request(
            subject,
            request_payload,
            timeout=int(callback.get("timeout", self.config.callback_timeout)),
        )
        try:
            response_payload = json.loads(response.data.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("invalid JSON callback response") from error
        if not isinstance(response_payload, dict):
            raise ValueError("non-object callback response")
        if response_payload.get("success") is False:
            raise RuntimeError(
                response_payload.get("message")
                or response_payload.get("error")
                or "callback request failed"
            )
        result_payload = response_payload.get("result")
        if isinstance(result_payload, dict) and result_payload.get("success") is False:
            raise RuntimeError(
                result_payload.get("message")
                or result_payload.get("error")
                or "callback handler failed"
            )
        logger.info("callback sent: subject=%s task_id=%s", subject, payload.get("task_id"))

    async def _enqueue_callback_retry(self, callback: dict[str, Any], payload: dict[str, Any], reason: str):
        retry_payload = {
            "callback": _sanitize_callback_for_storage(callback),
            "payload": payload,
            "reason": reason,
            "task_id": payload.get("task_id"),
            "enqueued_at": self._now_iso(),
        }
        await self.js.publish(
            self.retry_subject,
            json.dumps(retry_payload, ensure_ascii=False).encode("utf-8"),
        )

    async def _deliver_callback_result(
        self,
        task_id: str,
        callback: dict[str, Any],
        result: dict[str, Any],
        final_status: str,
    ) -> None:
        callback_payload = self._prepare_callback_payload(result)
        try:
            await self._invoke_callback(callback, callback_payload)
        except Exception as callback_error:
            result["callback_error"] = str(callback_error)
            # JetStream publish 成功后才将本地状态标记为 failed（即 retry 已持久化）。
            # publish 失败时保留 pending，让主任务重投重新进入本方法。
            await self._enqueue_callback_retry(
                callback,
                callback_payload,
                str(callback_error),
            )
            self.task_store.update_callback_status(
                task_id,
                "failed",
                result,
                self._now_iso(),
                preserve_status=final_status,
            )
            return
        self.task_store.update_callback_status(
            task_id,
            "sent",
            result,
            self._now_iso(),
            preserve_status=final_status,
        )

    async def _resume_pending_callback(self, task_id: str) -> None:
        stored_task = self.task_store.get_task(task_id)
        if not stored_task or stored_task.get("callback_status") != "pending":
            return
        callback = self._load_callback(task_id, stored_task.get("callback"))
        if not callback:
            raise RuntimeError(f"callback config unavailable: task_id={task_id}")
        result = stored_task.get("result") or {}
        final_status = stored_task.get("execution_status") or (
            "success" if result.get("success") else "failed"
        )
        await self._deliver_callback_result(
            task_id,
            callback,
            result,
            final_status,
        )

    def _load_callback(self, task_id: str, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
        callback = self.task_store.get_callback_config(task_id)
        if callback:
            return callback
        fallback = fallback if isinstance(fallback, dict) else {}
        context = fallback.get("context")
        if isinstance(context, dict) and context.get("token") == "***":
            return {}
        return fallback

    @staticmethod
    def _build_callback_retry_dlq_payload(
        data: dict[str, Any],
        error: str,
        delivered: int,
        timestamp: str,
    ) -> dict[str, Any]:
        return {
            "type": "callback_retry",
            "task_id": data.get("task_id"),
            "reason": data.get("reason", ""),
            "callback": _sanitize_callback_for_storage(data.get("callback")),
            "payload": data.get("payload") or {},
            "error": error,
            "delivered": delivered,
            "timestamp": timestamp,
        }

    async def _callback_retry_loop(self):
        while True:
            try:
                messages = await self.retry_psub.fetch(batch=1, timeout=1)
            except nats.errors.TimeoutError:
                continue
            if not messages:
                await asyncio.sleep(0.05)
                continue

            message = messages[0]
            data: dict[str, Any] = {}
            task_id = ""
            try:
                data = json.loads(message.data.decode("utf-8"))
                payload = data.get("payload") or {}
                task_id = str(data.get("task_id", ""))
                callback = self._load_callback(task_id, data.get("callback"))
                if not callback:
                    stored_task = self.task_store.get_task(task_id)
                    if stored_task and stored_task.get("callback_status") == "sent":
                        await message.ack()
                        continue
                    raise RuntimeError(f"callback config unavailable: task_id={task_id}")
                await self._invoke_callback(callback, payload)
                final_status = "success" if payload.get("success") else "failed"
                self.task_store.update_callback_status(
                    task_id,
                    "sent",
                    payload,
                    self._now_iso(),
                    preserve_status=final_status,
                )
                await message.ack()
            except Exception as error:
                metadata = message.metadata
                if metadata and metadata.num_delivered >= self.config.js_max_deliver:
                    dlq_payload = self._build_callback_retry_dlq_payload(
                        data,
                        str(error),
                        metadata.num_delivered,
                        self._now_iso(),
                    )
                    await self.nc.publish(
                        self.config.dlq_subject,
                        json.dumps(dlq_payload, ensure_ascii=False).encode("utf-8"),
                    )
                    if task_id:
                        self.task_store.clear_callback_config(task_id)
                    await message.ack()
                else:
                    await message.nak()
