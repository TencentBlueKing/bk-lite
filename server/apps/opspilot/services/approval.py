"""
人工审批控制模块

提供基于 django cache 的审批信号存储，用于 Agent 在执行危险工具前等待人类确认。

Key 结构: approval:{execution_id}:{node_id}:{tool_call_id}
Value: {"decision": "approve"|"reject", "reason": "", "decided_by": "", "decided_at": timestamp}
"""

import asyncio
import os
import time
from typing import Any, Dict, Optional

from django.core.cache import cache

from apps.core.logger import opspilot_logger as logger

APPROVAL_CACHE_TTL = int(os.getenv("APPROVAL_CACHE_TTL", "600"))
APPROVAL_CACHE_PREFIX = "approval"


def _get_approval_cache_key(execution_id: str, node_id: str, tool_call_id: str) -> str:
    return f"{APPROVAL_CACHE_PREFIX}:{execution_id}:{node_id}:{tool_call_id}"


def submit_approval_decision(
    execution_id: str,
    node_id: str,
    tool_call_id: str,
    decision: str,
    reason: str = "",
    decided_by: str = "",
) -> Dict[str, Any]:
    """提交审批决策（由 API 端点调用）。"""
    payload = {
        "decision": decision,
        "reason": reason,
        "decided_by": decided_by,
        "decided_at": int(time.time() * 1000),
    }
    key = _get_approval_cache_key(execution_id, node_id, tool_call_id)
    cache.set(key, payload, APPROVAL_CACHE_TTL)
    logger.info(
        "Approval decision submitted: execution_id=%s, node_id=%s, tool_call_id=%s, decision=%s",
        execution_id,
        node_id,
        tool_call_id,
        decision,
    )
    return payload


def get_approval_decision(execution_id: str, node_id: str, tool_call_id: str) -> Optional[Dict[str, Any]]:
    """获取审批决策（轮询用）。"""
    key = _get_approval_cache_key(execution_id, node_id, tool_call_id)
    return cache.get(key)


def clear_approval_decision(execution_id: str, node_id: str, tool_call_id: str) -> None:
    """清理审批决策。"""
    key = _get_approval_cache_key(execution_id, node_id, tool_call_id)
    cache.delete(key)


async def wait_for_approval(
    execution_id: str,
    node_id: str,
    tool_call_id: str,
    timeout_seconds: int = 300,
    poll_interval: float = 1.0,
    trigger_type: str = "interactive",
    unattended_strategy: str = "skip",
    timeout_fallback: str = "skip",
) -> Dict[str, Any]:
    """
    等待审批决策。

    Args:
        trigger_type: "interactive" (对话式) | "unattended" (定时任务) | "third_party" (第三方渠道)
        unattended_strategy: 无人值守时的自动策略 "skip"|"deny"|"allow"
        timeout_fallback: 超时时的降级策略 "skip"|"deny"

    Returns:
        {"decision": "approve"|"reject"|"skip", "reason": "...", "source": "user"|"auto"|"timeout"}
    """
    # 无人值守场景：不等待，立即按策略返回
    if trigger_type == "unattended":
        decision = "approve" if unattended_strategy == "allow" else ("reject" if unattended_strategy == "deny" else "skip")
        logger.info(
            "Approval auto-resolved (unattended): execution_id=%s, node_id=%s, tool_call_id=%s, decision=%s",
            execution_id,
            node_id,
            tool_call_id,
            decision,
        )
        return {"decision": decision, "reason": f"无人值守自动策略: {unattended_strategy}", "source": "auto"}

    # 对话式/第三方渠道：轮询等待
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = get_approval_decision(execution_id, node_id, tool_call_id)
        if result:
            # 清理已消费的决策
            clear_approval_decision(execution_id, node_id, tool_call_id)
            return {
                "decision": result["decision"],
                "reason": result.get("reason", ""),
                "source": "user",
                "decided_by": result.get("decided_by", ""),
            }
        await asyncio.sleep(poll_interval)

    # 超时 → 降级
    decision = "approve" if timeout_fallback == "allow" else ("reject" if timeout_fallback == "deny" else "skip")
    logger.warning(
        "Approval timed out: execution_id=%s, node_id=%s, tool_call_id=%s, fallback=%s",
        execution_id,
        node_id,
        tool_call_id,
        decision,
    )
    return {"decision": decision, "reason": f"审批超时({timeout_seconds}s), 降级策略: {timeout_fallback}", "source": "timeout"}
