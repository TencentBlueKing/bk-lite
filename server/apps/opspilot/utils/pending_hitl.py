"""
待处理 HITL（人工介入）会话级注册表

记录"某 bot 的某 session 当前有一个正在等待用户输入的智能体节点"，供各对话入口
在新建执行前拦截：命中则把用户消息当作答案投递给等待中的节点，而不是从入口节点
重跑整张工作流（否则回复会跑回第一个智能体 A，而非正在等待的 B）。

Key 结构: pending_hitl:{bot_id}:{session_id}
Value: {"kind", "execution_id", "node_id", "choice_id", "created_at"}

采用自续租约（lease）：interactive 等待循环每轮调用 register_pending 续写，TTL 较短
（LEASE_TTL）。节点一旦应答/中断/断连而停止续写，租约会在 ~LEASE_TTL 内自动过期回收，
因此即使显式清理被跳过（例如硬取消），也不会把后续消息误吞给一个已死的等待。

注意：本注册表仅在 (bot_id, session_id) 均存在时生效；任一缺失则不登记，入口退回
现有"新建执行"行为。
"""

import os
import time
from typing import Any, Dict, Optional

from django.core.cache import cache

from apps.core.logger import opspilot_logger as logger

# 租约 TTL（秒）。等待中每轮续租；停止续租后 ~LEASE_TTL 内自动过期。
# 非产品层配置项：保留 env 仅为测试/部署兜底，不在产品层开放给用户。
LEASE_TTL = int(os.getenv("PENDING_HITL_LEASE_TTL", "30"))
PENDING_HITL_PREFIX = "pending_hitl"


def _get_pending_cache_key(bot_id: Any, session_id: Any) -> str:
    return f"{PENDING_HITL_PREFIX}:{bot_id}:{session_id}"


def register_pending(
    bot_id: Any,
    session_id: Any,
    *,
    execution_id: str,
    node_id: str,
    choice_id: str,
    kind: str = "choice",
) -> Optional[Dict[str, Any]]:
    """登记/续租一个待处理 HITL。

    缺 bot_id 或 session_id 时不登记（无法按会话定位），返回 None。
    重复调用即续租（刷新 TTL），用作等待期间的 heartbeat。
    """
    if not bot_id or not session_id:
        return None
    payload = {
        "kind": kind,
        "execution_id": execution_id,
        "node_id": node_id,
        "choice_id": choice_id,
        "created_at": int(time.time() * 1000),
    }
    cache.set(_get_pending_cache_key(bot_id, session_id), payload, LEASE_TTL)
    return payload


def get_pending(bot_id: Any, session_id: Any) -> Optional[Dict[str, Any]]:
    """获取该 (bot, session) 当前待处理 HITL；无/已过期返回 None。"""
    if not bot_id or not session_id:
        return None
    return cache.get(_get_pending_cache_key(bot_id, session_id))


def clear_pending(bot_id: Any, session_id: Any) -> None:
    """清理该 (bot, session) 的待处理 HITL（幂等）。"""
    if not bot_id or not session_id:
        return
    cache.delete(_get_pending_cache_key(bot_id, session_id))


def try_deliver_to_pending(bot_id: Any, session_id: Any, message: str) -> Optional[Dict[str, Any]]:
    """入口拦截：若该 (bot, session) 有待处理 HITL，则把 message 当作答案投递给等待中的节点。

    命中并投递成功 → 返回投递信息 dict（含 delivered_to_pending=True 与定位字段）；
    未命中 → 返回 None（调用方按现有逻辑新建执行）。

    投递复用 user_choice 的选择通道（selected=[message]），等待中的 wait_for_choice 轮询
    会立即命中并让节点续跑；随后清理本注册项（节点侧 finally 也会清理，幂等）。
    """
    pending = get_pending(bot_id, session_id)
    if not pending:
        return None

    # 延迟导入避免与 user_choice 形成模块级循环依赖
    from apps.opspilot.utils.user_choice import submit_user_choice

    submit_user_choice(
        execution_id=pending["execution_id"],
        node_id=pending["node_id"],
        choice_id=pending["choice_id"],
        selected=[message],
    )
    clear_pending(bot_id, session_id)
    logger.info(
        "Delivered chat message to pending HITL: bot_id=%s, session_id=%s, execution_id=%s, node_id=%s, choice_id=%s",
        bot_id,
        session_id,
        pending["execution_id"],
        pending["node_id"],
        pending["choice_id"],
    )
    return {"delivered_to_pending": True, **pending}
