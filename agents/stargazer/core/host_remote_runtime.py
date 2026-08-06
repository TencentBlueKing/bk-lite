import asyncio
import os

from sanic.log import logger

import core.host_remote_callback as host_remote_callback

_processing_tasks: dict[str, asyncio.Task] = {}


async def schedule_host_remote_processing(
    task_id: str, *, claim_token: str = ""
) -> dict:
    existing = _processing_tasks.get(task_id)
    if existing is not None and not existing.done():
        return {
            "task_id": task_id,
            "status": "duplicate_active",
            "processing_id": existing.get_name(),
        }
    claim_token = claim_token or (
        await host_remote_callback.claim_host_remote_processing(task_id)
    )
    if not claim_token:
        return {
            "task_id": task_id,
            "status": "duplicate_active",
            "processing_id": "",
        }

    async def process() -> None:
        from tasks.handlers.host_remote_handler import (
            process_host_remote_callback_task,
        )

        async def renew_claim() -> None:
            interval = max(
                1, host_remote_callback.HOST_REMOTE_PROCESSING_STALE_SECONDS // 3
            )
            while True:
                await asyncio.sleep(interval)
                if not await host_remote_callback.renew_host_remote_processing_claim(
                    task_id, claim_token
                ):
                    raise RuntimeError("lost Host Remote processing claim")

        renewal_task = asyncio.create_task(renew_claim())
        handler_task = asyncio.create_task(
            process_host_remote_callback_task({}, {}, task_id)
        )
        try:
            done, _pending = await asyncio.wait(
                (handler_task, renewal_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if renewal_task in done:
                await renewal_task
            await handler_task
        finally:
            if not handler_task.done():
                handler_task.cancel()
            renewal_task.cancel()
            await asyncio.gather(
                handler_task, renewal_task, return_exceptions=True
            )
            await host_remote_callback.release_host_remote_processing_claim(
                task_id, claim_token
            )

    task = asyncio.create_task(
        process(), name=f"host-remote-callback:{task_id}"
    )
    _processing_tasks[task_id] = task

    def consume(completed: asyncio.Task) -> None:
        _processing_tasks.pop(task_id, None)
        try:
            completed.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(
                "[Host Remote Runtime] callback processing failed task_id=%s",
                task_id,
            )

    task.add_done_callback(consume)
    return {
        "task_id": task_id,
        "status": "accepted",
        "processing_id": task.get_name(),
    }


def validate_host_remote_runtime_config() -> None:
    nats_urls = os.getenv("NATS_URLS", "").strip()
    nats_servers = os.getenv("NATS_SERVERS", "").strip()

    if not nats_urls and nats_servers:
        logger.warning(
            "[Host Remote Runtime] NATS_SERVERS is configured but NATS_URLS is empty; core.nats currently reads NATS_URLS"
        )

    if nats_urls and nats_servers and nats_urls != nats_servers:
        logger.warning(
            "[Host Remote Runtime] NATS_URLS and NATS_SERVERS differ; worker/server may use inconsistent NATS endpoints"
        )



async def sweep_host_remote_callback_contexts() -> None:
    callback_contexts = await host_remote_callback.list_host_remote_callback_contexts()
    if not callback_contexts:
        return

    now_ms = host_remote_callback._now_ms()
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
                task_info = await schedule_host_remote_processing(task_id)
                await host_remote_callback.mark_host_remote_processing_enqueued(
                    task_id,
                    processing_job_id=task_info.get("processing_id"),
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
                task_info = await schedule_host_remote_processing(task_id)
                await host_remote_callback.mark_host_remote_processing_enqueued(
                    task_id,
                    processing_job_id=task_info.get("processing_id"),
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
        tasks = tuple(task for task in _processing_tasks.values() if not task.done())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
