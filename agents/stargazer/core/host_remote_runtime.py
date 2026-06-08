import asyncio
import os

from sanic.log import logger

import core.host_remote_callback as host_remote_callback
from core.task_queue import get_task_queue


def validate_host_remote_runtime_config() -> None:
    nats_urls = os.getenv("NATS_URLS", "").strip()
    nats_servers = os.getenv("NATS_SERVERS", "").strip()
    task_job_timeout = int(os.getenv("TASK_JOB_TIMEOUT", "600"))
    callback_deadline = host_remote_callback.HOST_REMOTE_CALLBACK_DEADLINE_SECONDS
    submit_accept_timeout = host_remote_callback.HOST_REMOTE_SUBMIT_ACCEPT_TIMEOUT_SECONDS

    if not nats_urls and nats_servers:
        logger.warning(
            "[Host Remote Runtime] NATS_SERVERS is configured but NATS_URLS is empty; core.nats currently reads NATS_URLS"
        )

    if nats_urls and nats_servers and nats_urls != nats_servers:
        logger.warning(
            "[Host Remote Runtime] NATS_URLS and NATS_SERVERS differ; worker/server may use inconsistent NATS endpoints"
        )

    if callback_deadline >= task_job_timeout:
        logger.warning(
            "[Host Remote Runtime] HOST_REMOTE_CALLBACK_DEADLINE_SECONDS >= TASK_JOB_TIMEOUT; waiting callbacks may overlap worker job timeout assumptions"
        )

    if submit_accept_timeout >= task_job_timeout:
        logger.warning(
            "[Host Remote Runtime] HOST_REMOTE_SUBMIT_ACCEPT_TIMEOUT_SECONDS >= TASK_JOB_TIMEOUT; pre-accept waiting may overlap worker job timeout assumptions"
        )


async def sweep_host_remote_callback_contexts() -> None:
    callback_contexts = await host_remote_callback.list_host_remote_callback_contexts()
    if not callback_contexts:
        return

    now_ms = host_remote_callback._now_ms()
    task_queue = get_task_queue()

    for callback_context in callback_contexts:
        task_id = callback_context.get("task_id")
        status = callback_context.get("status") or {}
        execution = status.get("execution")
        delivery = status.get("delivery")

        if execution == "waiting_callback":
            deadline_at = int(callback_context.get("callback_deadline_at") or 0)
            if not deadline_at:
                created_at = int(callback_context.get("created_at") or 0)
                if created_at and (
                    created_at
                    + host_remote_callback.HOST_REMOTE_SUBMIT_ACCEPT_TIMEOUT_SECONDS * 1000
                    <= now_ms
                ):
                    await host_remote_callback.mark_host_remote_callback_timeout(
                        task_id,
                        reason="submit accept timeout",
                    )
                    await host_remote_callback.clear_host_remote_running_flag(task_id)
                    continue
            elif deadline_at <= now_ms:
                await host_remote_callback.mark_host_remote_callback_timeout(task_id)
                await host_remote_callback.clear_host_remote_running_flag(task_id)
                continue

        if delivery == "publish_pending":
            next_retry_at = int(callback_context.get("next_retry_at") or 0)
            if next_retry_at and next_retry_at <= now_ms:
                task_info = await task_queue.enqueue_host_remote_processing_task(task_id)
                await host_remote_callback.mark_host_remote_processing_enqueued(
                    task_id,
                    processing_job_id=task_info.get("job_id"),
                )
                continue

        if delivery == "processing":
            process_started_at = int(callback_context.get("process_started_at") or 0)
            if not process_started_at:
                continue
            stale_deadline = process_started_at + (
                host_remote_callback.HOST_REMOTE_PROCESSING_STALE_SECONDS * 1000
            )
            if stale_deadline <= now_ms:
                task_info = await task_queue.enqueue_host_remote_processing_task(task_id)
                await host_remote_callback.mark_host_remote_processing_enqueued(
                    task_id,
                    processing_job_id=task_info.get("job_id"),
                )


async def host_remote_sweeper_loop(app) -> None:
    interval = host_remote_callback.HOST_REMOTE_SWEEP_INTERVAL_SECONDS
    while True:
        try:
            await asyncio.sleep(interval)
            await sweep_host_remote_callback_contexts()
        except asyncio.CancelledError:
            logger.info("[Host Remote Runtime] sweeper stopped")
            raise
        except Exception as err:
            logger.error(
                f"[Host Remote Runtime] sweeper failed: {err}",
                exc_info=True,
            )


def register_host_remote_runtime(app) -> None:
    validate_host_remote_runtime_config()

    @app.listener("after_server_start")
    async def start_host_remote_sweeper(app, loop):
        app.ctx.host_remote_sweeper_task = asyncio.create_task(
            host_remote_sweeper_loop(app)
        )
        logger.info("[Host Remote Runtime] sweeper started")

    @app.listener("after_server_stop")
    async def stop_host_remote_sweeper(app, loop):
        sweeper_task = getattr(app.ctx, "host_remote_sweeper_task", None)
        if sweeper_task:
            sweeper_task.cancel()
            try:
                await sweeper_task
            except asyncio.CancelledError:
                pass
