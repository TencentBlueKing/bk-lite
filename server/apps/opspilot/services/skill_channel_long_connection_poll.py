"""长连接常驻进程的一轮轮询。

只清理调用线程上的 Django 连接。回答线程有自己的连接，这里不会关掉。
同一轮里加载失败不对账、对账失败不取消息，避免把同一轮消息再跑一遍。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.db import close_old_connections

from apps.core.logger import opspilot_logger as logger
from apps.core.logger import safe_exception_info

STAGE_LOAD_CHANNELS = "load_channels"
STAGE_RECONCILE = "reconcile"
STAGE_PUMP = "pump"


def poll_long_connection_once(
    load: Callable[[], Any],
    reconcile: Callable[[Any], None],
    pump: Callable[[], None],
    *,
    loop_failed_template: str,
    cleanup_failed_template: str,
) -> None:
    stage = STAGE_LOAD_CHANNELS
    try:
        close_old_connections()
        channels = load()
        stage = STAGE_RECONCILE
        reconcile(channels)
        stage = STAGE_PUMP
        pump()
    except Exception as exc:
        logger.error(loop_failed_template, stage, type(exc).__name__, exc_info=safe_exception_info(exc))
    finally:
        _close_db_quietly(cleanup_failed_template)


def _close_db_quietly(template: str) -> None:
    try:
        close_old_connections()
    except Exception as exc:
        logger.warning(template, type(exc).__name__)
