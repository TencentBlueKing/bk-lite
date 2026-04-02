"""
执行中断控制模块

提供基于 django cache 的轻量级中断信号存储，用于 workflow / AGUI / tools 协作式中断。
"""

import os
import time
from typing import Any, Dict, Optional

from django.core.cache import cache

from apps.core.logger import opspilot_logger as logger

INTERRUPT_CACHE_TTL = int(os.getenv("WORKFLOW_INTERRUPT_CACHE_TTL", "3600"))
INTERRUPT_CACHE_PREFIX = "workflow_interrupt"


def _get_interrupt_cache_key(execution_id: str) -> str:
    return f"{INTERRUPT_CACHE_PREFIX}:{execution_id}"


def request_interrupt(execution_id: str, reason: str = "user_manual", meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """记录中断请求。"""
    payload = {
        "execution_id": execution_id,
        "reason": reason,
        "requested_at": int(time.time() * 1000),
        "meta": meta or {},
    }
    cache.set(_get_interrupt_cache_key(execution_id), payload, INTERRUPT_CACHE_TTL)
    logger.info("Execution interrupt requested: execution_id=%s, reason=%s", execution_id, reason)
    return payload


def get_interrupt_request(execution_id: str) -> Optional[Dict[str, Any]]:
    """获取中断请求信息。"""
    if not execution_id:
        return None
    return cache.get(_get_interrupt_cache_key(execution_id))


def is_interrupt_requested(execution_id: str) -> bool:
    """检查是否已请求中断。"""
    if not execution_id:
        return False
    return get_interrupt_request(execution_id) is not None


def clear_interrupt_request(execution_id: str) -> None:
    """清理中断请求。"""
    if not execution_id:
        return
    cache.delete(_get_interrupt_cache_key(execution_id))
    logger.info("Execution interrupt request cleared: execution_id=%s", execution_id)
