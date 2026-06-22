"""Workflow 跨轮会话历史读取与注入工具（方案 A：单一会话历史线）。

把 WorkFlowConversationHistory 里已存的 (用户原话, 系统最终输出) 读回来，
注入到"面向用户原话"的 agent / 意图节点。不改表、不改记录逻辑。
"""
from typing import Any, Dict, List

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models.bot_mgmt import WorkFlowConversationHistory


def load_session_history(bot_id, user_id, session_id, exclude_execution_id, cap: int = 50) -> List[Dict[str, Any]]:
    """读取本会话历史轮次（不含当前轮），转成 chat_history 事件列表。

    - 按 (bot_id, user_id, session_id) 过滤，排除当前 execution_id（当前轮已落库的 user 记录）。
    - 取最近 cap 条做粗截断；精确加窗交给下游 process_chat_history。
    - session_id 为空或 bot_id 缺失时返回 []，避免串话。
    - 任何异常都降级为 []，绝不阻断对话。
    """
    if not session_id or bot_id is None:
        return []
    try:
        rows = list(
            WorkFlowConversationHistory.objects.filter(
                bot_id=bot_id, user_id=user_id, session_id=session_id
            )
            .exclude(execution_id=exclude_execution_id)
            .order_by("-conversation_time", "-id")[:cap]
        )
    except Exception as e:  # pragma: no cover - 防御性降级
        logger.warning(f"[history] 读取会话历史失败: bot_id={bot_id}, session_id={session_id}, error={e}")
        return []
    rows.reverse()  # 倒序取最近 cap 条后翻回时间正序
    history: List[Dict[str, Any]] = []
    for row in rows:
        event = "user" if row.conversation_role == "user" else "bot"
        history.append({"event": event, "message": row.conversation_content})
    return history
