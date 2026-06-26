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
from apps.opspilot.utils.execution_interrupt import is_interrupt_requested_async
from apps.opspilot.utils.pending_hitl import register_pending

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
    bot_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    等待用户选择。

    Args:
        execution_id: 执行标识
        node_id: 节点标识
        choice_id: 选择请求唯一标识
        options: 选项列表，每个选项包含 key, label
        default_keys: 无人值守(unattended)时的默认选项 key 列表
        timeout_seconds: 已废弃（interactive 不再超时，无限等待）；保留以兼容签名
        poll_interval: 轮询间隔（秒）
        trigger_type: "interactive" (对话式) | "unattended" (定时任务)
        bot_id/session_id: 用于在等待期间续租会话级 pending 注册表（见 pending_hitl）。
            二者齐备时，等待循环每轮续租，使各对话入口能拦截"在回答 B"的消息。

    Returns:
        {"selected": [...], "source": "user"|"interrupted"|"auto"|"timeout"}

    说明（2026-06-18 变更）：
        interactive（真人对话）场景**不再超时、无限等待**用户应答；唯一的非应答退出是
        "中断"（用户点停止 → execution_interrupt 标志位）。废弃了 interactive 的
        "超时→默认值"回退。
        unattended（定时/无人值守）仍立即用默认值，绝不长等待，避免 headless 任务挂死。
        third_party（企微/钉钉等 webhook）保留有界等待 + 超时回退默认，避免悬挂请求。
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

    # interactive(真人对话)：无限等待（deadline=None）；
    # 其他渠道(third_party 等 webhook)：保留有界等待，超时回退默认，避免把请求悬挂。
    deadline = None if trigger_type == "interactive" else time.monotonic() + timeout_seconds

    while deadline is None or time.monotonic() < deadline:
        result = get_user_choice(execution_id, node_id, choice_id)
        if result:
            clear_user_choice(execution_id, node_id, choice_id)
            return {
                "selected": result["selected"],
                "source": "user",
            }

        # 中断：去掉超时后，interactive 唯一的非应答退出口
        if execution_id and await is_interrupt_requested_async(execution_id):
            logger.info(
                "Choice wait interrupted: execution_id=%s, choice_id=%s",
                execution_id,
                choice_id,
            )
            return {"selected": [], "source": "interrupted"}

        # 续租会话级 pending（heartbeat）：节点活着就一直新鲜，停止轮询后自动过期回收
        if bot_id and session_id:
            register_pending(
                bot_id,
                session_id,
                execution_id=execution_id,
                node_id=node_id,
                choice_id=choice_id,
            )

        await asyncio.sleep(poll_interval)

    # 仅有界等待(third_party 等)会走到这里：超时 → 使用默认值
    selected = default_keys if default_keys else [options[0]["key"]] if options else []
    logger.warning(
        "Choice timed out: execution_id=%s, choice_id=%s, using default=%s",
        execution_id,
        choice_id,
        selected,
    )
    return {"selected": selected, "source": "timeout"}
