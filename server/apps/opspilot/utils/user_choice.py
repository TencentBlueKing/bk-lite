"""
用户选择控制模块

提供基于 django cache 的选择信号存储，用于 Agent 需要用户从多个选项中选择时。

Key 结构: choice:{execution_id}:{node_id}:{choice_id}
Value: {"selected": [...], "selected_at": timestamp}
"""

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

from django.core.cache import cache

from apps.core.logger import opspilot_logger as logger

CHOICE_CACHE_TTL = int(os.getenv("CHOICE_CACHE_TTL", "600"))
CHOICE_CACHE_PREFIX = "choice"


def _get_choice_cache_key(execution_id: str, node_id: str, choice_id: str) -> str:
    return f"{CHOICE_CACHE_PREFIX}:{execution_id}:{node_id}:{choice_id}"


def submit_user_choice(
    execution_id: str,
    node_id: str,
    choice_id: str,
    selected: List[str],
) -> Dict[str, Any]:
    """提交用户选择（由 API 端点调用）。"""
    payload = {
        "selected": selected,
        "selected_at": int(time.time() * 1000),
    }
    key = _get_choice_cache_key(execution_id, node_id, choice_id)
    cache.set(key, payload, CHOICE_CACHE_TTL)
    logger.info(
        "User choice submitted: execution_id=%s, node_id=%s, choice_id=%s, selected=%s",
        execution_id,
        node_id,
        choice_id,
        selected,
    )
    return payload


def get_user_choice(execution_id: str, node_id: str, choice_id: str) -> Optional[Dict[str, Any]]:
    """获取用户选择（轮询用）。"""
    key = _get_choice_cache_key(execution_id, node_id, choice_id)
    return cache.get(key)


def clear_user_choice(execution_id: str, node_id: str, choice_id: str) -> None:
    """清理用户选择。"""
    key = _get_choice_cache_key(execution_id, node_id, choice_id)
    cache.delete(key)


async def wait_for_choice(
    execution_id: str,
    node_id: str,
    choice_id: str,
    options: List[Dict[str, Any]],
    default_keys: List[str],
    timeout_seconds: int = 300,
    poll_interval: float = 1.0,
    trigger_type: str = "interactive",
) -> Dict[str, Any]:
    """
    等待用户选择。

    Args:
        execution_id: 执行标识
        node_id: 节点标识
        choice_id: 选择请求唯一标识
        options: 选项列表，每个选项包含 key, label
        default_keys: 超时时的默认选项 key 列表
        timeout_seconds: 超时时间（秒）
        poll_interval: 轮询间隔（秒）
        trigger_type: "interactive" (对话式) | "unattended" (定时任务)

    Returns:
        {"selected": [...], "source": "user"|"timeout"|"auto"}
    """
    # 无人值守场景：不等待，立即使用默认值
    if trigger_type == "unattended":
        selected = default_keys if default_keys else [options[0]["key"]] if options else []
        logger.info(
            "Choice auto-resolved (unattended): execution_id=%s, choice_id=%s, selected=%s",
            execution_id,
            choice_id,
            selected,
        )
        return {"selected": selected, "source": "auto"}

    # 对话式：轮询等待
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = get_user_choice(execution_id, node_id, choice_id)
        if result:
            clear_user_choice(execution_id, node_id, choice_id)
            return {
                "selected": result["selected"],
                "source": "user",
            }
        await asyncio.sleep(poll_interval)

    # 超时 → 使用默认值
    selected = default_keys if default_keys else [options[0]["key"]] if options else []
    logger.warning(
        "Choice timed out: execution_id=%s, choice_id=%s, using default=%s",
        execution_id,
        choice_id,
        selected,
    )
    return {"selected": selected, "source": "timeout"}
