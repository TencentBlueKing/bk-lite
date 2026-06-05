# -- coding: utf-8 --
import time
import traceback
from typing import Dict, Any

from sanic.log import logger

import core.host_remote_callback as host_remote_callback


async def _publish_host_remote_state_metric(
    callback_ctx: Dict[str, Any],
    callback_params: Dict[str, Any],
    task_id: str,
    event: str,
    status: str,
    extra_labels: Dict[str, Any] | None = None,
) -> None:
    from tasks.utils.metrics_helper import generate_host_remote_state_metric
    from tasks.utils.nats_helper import publish_metrics_to_nats

    state_metric = generate_host_remote_state_metric(
        event=event,
        task_id=task_id,
        status=status,
        monitor_type=callback_params.get("monitor_type", "host"),
        extra_labels=extra_labels,
    )
    await publish_metrics_to_nats(callback_ctx, state_metric, callback_params, task_id)


async def process_host_remote_callback_task(
    ctx: Dict, params: Dict[str, Any], task_id: str
) -> Dict[str, Any]:
    callback_context = await host_remote_callback.load_host_remote_callback_context(task_id)
    if not callback_context:
        raise RuntimeError(
            f"Missing Host Remote callback context for task_id={task_id}"
        )

    await host_remote_callback.mark_host_remote_processing_started(task_id)

    callback_params = callback_context.get("params") or {}
    callback_ctx = callback_context.get("ctx") or {}
    raw_callback = callback_context.get("raw_callback")
    if not isinstance(raw_callback, dict):
        err = RuntimeError(
            f"Missing Host Remote callback payload for task_id={task_id}"
        )
        await host_remote_callback.mark_host_remote_processing_failed(task_id, err)
        raise err

    try:
        from tasks.collectors.host_collector import HostCollector
        from tasks.utils.metrics_helper import generate_monitor_error_metrics
        from tasks.utils.nats_helper import publish_metrics_to_nats

        collector = HostCollector(callback_params)
        try:
            metrics_data = collector.process_adhoc_result(raw_callback)
        except Exception as processing_err:
            logger.error(
                f"[Host Remote Process] Callback processing failed for {task_id}: {processing_err}",
                exc_info=True,
            )
            error_metrics = generate_monitor_error_metrics(callback_params, processing_err)
            await publish_metrics_to_nats(callback_ctx, error_metrics, callback_params, task_id)
            await host_remote_callback.mark_host_remote_processing_failed(
                task_id,
                f"Host collection failed: {processing_err}",
            )
            await _publish_host_remote_state_metric(
                callback_ctx,
                callback_params,
                task_id,
                event="processing_failed",
                status="delivery_failed",
                extra_labels={"reason": "processing_error"},
            )
            return {
                "task_id": task_id,
                "status": "failed",
                "error": f"Host collection failed: {processing_err}",
                "monitor_type": callback_params.get("monitor_type", "host"),
            }

        await publish_metrics_to_nats(callback_ctx, metrics_data, callback_params, task_id)
        await _publish_host_remote_state_metric(
            callback_ctx,
            callback_params,
            task_id,
            event="published",
            status="published",
        )
        await host_remote_callback.mark_host_remote_processing_published(task_id)
        await host_remote_callback.clear_host_remote_callback_context(task_id)
        return {
            "task_id": task_id,
            "status": "success",
            "monitor_type": callback_params.get("monitor_type", "host"),
            "data_size": len(metrics_data),
            "completed_at": int(time.time() * 1000),
        }
    except Exception as err:
        logger.error(
            f"[Host Remote Process] {task_id} failed: {err}\n{traceback.format_exc()}"
        )
        if host_remote_callback.is_retryable_host_remote_publish_error(err):
            retry_info = await host_remote_callback.schedule_host_remote_publish_retry(
                task_id,
                err,
            )
            if retry_info.get("retry_scheduled"):
                return {
                    "task_id": task_id,
                    "status": "retry_scheduled",
                    "monitor_type": callback_params.get("monitor_type", "host"),
                    "retry_attempt": retry_info.get("attempt"),
                    "next_retry_at": retry_info.get("next_retry_at"),
                }

        await host_remote_callback.mark_host_remote_processing_failed(task_id, err)
        raise
