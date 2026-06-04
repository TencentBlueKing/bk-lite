import asyncio

from sanic.log import logger

from service.collect_credential_result_push_service import (
    COLLECT_CREDENTIAL_RESULT_PUSH_INTERVAL_SECONDS,
    CollectCredentialResultPushService,
)


async def push_collect_credential_results_once():
    result = await CollectCredentialResultPushService.push_once()
    if result.get("pushed"):
        logger.info(
            "Pushed collect credential results to CMDB via NATS, count=%s next_since=%s",
            result.get("pushed"),
            result.get("next_since"),
        )
    else:
        logger.info(
            "No collect credential results ready for CMDB push, next_since=%s",
            result.get("next_since"),
        )
    return result


def register_collect_credential_result_push_loop(app):
    @app.listener("before_server_start")
    async def start_collect_credential_result_push_loop(app, loop):
        logger.info(
            "Collect credential result push loop started, interval_seconds=%s",
            COLLECT_CREDENTIAL_RESULT_PUSH_INTERVAL_SECONDS,
        )

        async def _push_loop():
            while True:
                try:
                    logger.info(
                        "Waiting for next collect credential result push cycle, interval_seconds=%s",
                        COLLECT_CREDENTIAL_RESULT_PUSH_INTERVAL_SECONDS,
                    )
                    await asyncio.sleep(COLLECT_CREDENTIAL_RESULT_PUSH_INTERVAL_SECONDS)
                    await push_collect_credential_results_once()
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    logger.error(
                        "Failed to push collect credential results to CMDB via NATS: %s",
                        err,
                        exc_info=True,
                    )

        app.ctx.collect_credential_result_push_task = asyncio.create_task(_push_loop())

    @app.listener("after_server_stop")
    async def stop_collect_credential_result_push_loop(app, loop):
        task = getattr(app.ctx, "collect_credential_result_push_task", None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("Collect credential result push loop stopped")