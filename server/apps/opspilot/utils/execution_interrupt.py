"""
执行中断控制模块

提供基于 django cache 的轻量级中断信号存储，用于 workflow / AGUI / tools 协作式中断。
缓存过期后自动回退到数据库查询 WorkFlowTaskResult.status == INTERRUPTED。

配置项：
    WORKFLOW_INTERRUPT_CACHE_TTL (环境变量):
        中断信号缓存过期时间（秒），默认 3600（1 小时）。
        对于长时间运行的工作流，可适当增大此值。
        缓存过期后会自动回退到数据库查询，确保中断信号不丢失。

        示例：
            export WORKFLOW_INTERRUPT_CACHE_TTL=7200  # 2 小时
"""

import os
import time
from typing import Any, Dict, Optional

from django.core.cache import cache

from apps.core.logger import opspilot_logger as logger

INTERRUPT_CACHE_TTL = int(os.getenv("WORKFLOW_INTERRUPT_CACHE_TTL", "3600"))
INTERRUPT_CACHE_PREFIX = "workflow_interrupt"


def _check_interrupt_in_database(execution_id: str) -> bool:
    """
    数据库兜底查询：检查 WorkFlowTaskResult.status == INTERRUPTED。

    仅在缓存未命中时调用，避免频繁数据库访问。
    使用 exists() 优化查询性能。
    """
    # 延迟导入避免循环依赖
    from apps.opspilot.enum import WorkFlowTaskStatus
    from apps.opspilot.models import WorkFlowTaskResult

    try:
        return WorkFlowTaskResult.objects.filter(
            execution_id=execution_id,
            status=WorkFlowTaskStatus.INTERRUPTED,
        ).exists()
    except Exception as e:
        logger.warning(
            "Failed to check interrupt status in database: execution_id=%s, error=%s",
            execution_id,
            str(e),
        )
        return False


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
    """
    检查是否已请求中断。

    双重检查机制：
    1. 优先查询缓存（快速路径）
    2. 缓存未命中时回退到数据库查询 WorkFlowTaskResult.status == INTERRUPTED

    这确保即使缓存过期（默认 1 小时），长时间运行的任务仍能检测到中断请求。
    """
    if not execution_id:
        return False

    # 快速路径：缓存命中
    cache_result = get_interrupt_request(execution_id)
    if cache_result is not None:
        logger.debug("Interrupt check hit cache: execution_id=%s", execution_id)
        return True

    # 慢速路径：数据库兜底
    db_result = _check_interrupt_in_database(execution_id)
    if db_result:
        logger.info(
            "Interrupt check hit database (cache expired): execution_id=%s",
            execution_id,
        )
    return db_result


def clear_interrupt_request(execution_id: str) -> None:
    """清理中断请求。"""
    if not execution_id:
        return
    cache.delete(_get_interrupt_cache_key(execution_id))
    logger.info("Execution interrupt request cleared: execution_id=%s", execution_id)
