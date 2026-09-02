"""
上下文 Compaction 模块

在 Agent 循环中，当消息列表的 token 总量超过阈值时，自动压缩历史消息为摘要，
避免长任务因 token 超限而失败。

设计原则：
1. 保留 SystemMessage 不压缩
2. 保留最近 N 条消息（确保 tool_call/tool_result 配对完整）
3. 中间消息用 LLM 生成摘要替换
4. 使用 isolated LLM 调用，不被 LangGraph 流捕获
"""

from typing import List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.token_utils import count_message_tokens
from apps.opspilot.metis.utils.template_loader import TemplateLoader

COMPACTION_SKIP_LOG = "event=llm_compaction_skip packet_tokens=%s threshold=%s extra_tokens=%s reason=%s"
COMPACTION_START_LOG = "event=llm_compaction_start packet_tokens=%s threshold=%s extra_tokens=%s keep_recent=%s"
COMPACTION_DONE_LOG = "event=llm_compaction_done packet_tokens=%s result_tokens=%s extra_tokens=%s"
SUMMARY_HUMAN_PREFIX = "[以下是之前对话的摘要，用于保持上下文连贯性]\n\n"


class CompactionConfig(BaseModel):
    """Compaction 配置"""

    enabled: bool = Field(default=True, description="是否启用上下文压缩")
    max_token_threshold: int = Field(default=0, description="触发压缩的 token 阈值；0 表示未注入模型派生值时不压缩")
    keep_recent_messages: int = Field(default=12, description="保留最近的消息数量（确保 tool_call 配对完整）")
    summary_max_tokens: int = Field(default=2000, description="摘要的最大 token 数")


def _find_safe_split_point(messages: List[BaseMessage], keep_recent: int) -> int:
    """
    找到安全的分割点，确保不会切断 tool_call/tool_result 配对。

    从 messages[-keep_recent] 位置向前搜索，找到一个不会破坏配对的位置。

    Args:
        messages: 非 system 消息列表
        keep_recent: 期望保留的最近消息数

    Returns:
        分割点索引（此索引之前的消息将被压缩）
    """
    if len(messages) <= keep_recent:
        return 0

    split_idx = len(messages) - keep_recent

    # 向前调整，确保不切断 tool_call -> tool_result 配对
    # 如果 split_idx 处是 ToolMessage，向前找到对应的 AIMessage（含 tool_calls）
    while split_idx > 0 and isinstance(messages[split_idx], ToolMessage):
        split_idx -= 1

    # 如果 split_idx 处是含 tool_calls 的 AIMessage，则需要包含后续的 ToolMessage
    # 这种情况下向后移动 split_idx 到 ToolMessage 之后
    if split_idx < len(messages) and isinstance(messages[split_idx], AIMessage):
        tool_calls = getattr(messages[split_idx], "tool_calls", None)
        if tool_calls:
            # 这条 AIMessage 有 tool_calls，需要和后面的 ToolMessage 一起保留
            # 所以 split_idx 应该在这条 AIMessage 之前
            split_idx = max(0, split_idx - 1)
            # 再次检查避免切断
            while split_idx > 0 and isinstance(messages[split_idx], ToolMessage):
                split_idx -= 1

    return split_idx


def _summary_human_message(summary: str) -> HumanMessage:
    return HumanMessage(content=f"{SUMMARY_HUMAN_PREFIX}{summary}")


def _last_human_index(messages: List[BaseMessage]) -> int:
    last_idx = -1
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            last_idx = index
    return last_idx


def _format_messages_for_summary(messages: List[BaseMessage]) -> str:
    """
    将消息列表格式化为用于摘要的文本

    Args:
        messages: 要摘要的消息列表

    Returns:
        格式化后的文本
    """
    parts = []
    for msg in messages:
        role = msg.__class__.__name__.replace("Message", "")
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            content = " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
        # 截断过长的单条消息
        if len(content) > 3000:
            content = content[:3000] + "...(truncated)"

        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            tc_summary = ", ".join(f"{tc.get('name', '?')}(...)" for tc in tool_calls)
            parts.append(f"[{role}] called tools: {tc_summary}")
            if content:
                parts.append(f"[{role}] {content}")
        else:
            if content:
                parts.append(f"[{role}] {content}")

    return "\n".join(parts)


async def generate_summary(
    messages_to_compress: List[BaseMessage],
    llm: ChatOpenAI,
    max_tokens: int = 2000,
) -> str:
    """
    使用 LLM 生成消息摘要

    Args:
        messages_to_compress: 需要压缩的消息列表
        llm: LLM 客户端（isolated 模式，不被 LangGraph 捕获）
        max_tokens: 摘要最大 token 数

    Returns:
        摘要文本
    """
    conversation_text = _format_messages_for_summary(messages_to_compress)

    summary_prompt = TemplateLoader.render_template(
        "prompts/graph/compaction_summary_prompt",
        {"conversation_text": conversation_text, "max_tokens": max_tokens},
    )

    try:
        response = await llm.ainvoke([HumanMessage(content=summary_prompt)])
        return response.content
    except Exception as e:
        logger.exception(f"Compaction 摘要生成失败: {e}，回退到简单截断")
        # 回退策略：简单截断
        truncated = conversation_text[:4000]
        return f"[对话历史摘要 - 自动截断]\n{truncated}"


async def compact_messages(
    messages: List[BaseMessage],
    llm: ChatOpenAI,
    config: Optional[CompactionConfig] = None,
    model_name: str = "gpt-4o",
    extra_tokens: int = 0,
    force: bool = False,
) -> List[BaseMessage]:
    """
    检测消息 token 总量，超过阈值时压缩中间消息为摘要。

    此函数在 agent_node 调用 LLM 前执行，对调用方透明。

    Args:
        messages: 当前完整的消息列表
        llm: LLM 客户端（用于生成摘要，应为 isolated 模式）
        config: Compaction 配置，None 时使用默认配置
        model_name: 用于 token 计算的模型名称
        extra_tokens: 额外计入阈值的 token（如本轮工具 Schema）
        force: 忽略阈值，只要有可压历史就压缩（供应商超窗重试）

    Returns:
        压缩后的消息列表（可能与原列表相同，如果不需要压缩）
    """
    if config is None:
        config = CompactionConfig()

    if not config.enabled:
        return messages

    extra = max(int(extra_tokens or 0), 0)
    packet_tokens = count_message_tokens(messages, model_name) + extra
    threshold = config.max_token_threshold

    if not force and packet_tokens <= threshold:
        logger.debug(COMPACTION_SKIP_LOG, packet_tokens, threshold, extra, "below_threshold")
        return messages

    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    non_system_msgs = [m for m in messages if not isinstance(m, SystemMessage)]

    if not non_system_msgs:
        logger.debug(COMPACTION_SKIP_LOG, packet_tokens, threshold, extra, "no_history")
        return messages

    split_idx = _find_safe_split_point(non_system_msgs, config.keep_recent_messages)
    to_compress = non_system_msgs[:split_idx]
    to_keep = non_system_msgs[split_idx:]

    if split_idx == 0 or not to_compress:
        logger.debug(COMPACTION_SKIP_LOG, packet_tokens, threshold, extra, "split_zero")
        return messages

    logger.info(COMPACTION_START_LOG, packet_tokens, threshold, extra, config.keep_recent_messages)

    summary = await generate_summary(to_compress, llm, config.summary_max_tokens)
    compacted = system_msgs + [_summary_human_message(summary)] + to_keep
    result_tokens = count_message_tokens(compacted, model_name) + extra
    logger.info(COMPACTION_DONE_LOG, packet_tokens, result_tokens, extra)

    return compacted


async def compact_leaving_current_user(
    messages: List[BaseMessage],
    llm: ChatOpenAI,
    config: Optional[CompactionConfig] = None,
    model_name: str = "gpt-4o",
    extra_tokens: int = 0,
) -> List[BaseMessage]:
    """Replace non-system history except the current user (and any suffix) with one summary."""
    if config is None:
        config = CompactionConfig()
    if not config.enabled:
        return messages

    extra = max(int(extra_tokens or 0), 0)
    packet_tokens = count_message_tokens(messages, model_name) + extra
    threshold = config.max_token_threshold
    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    last_idx = _last_human_index(messages)
    if last_idx < 0:
        logger.debug(COMPACTION_SKIP_LOG, packet_tokens, threshold, extra, "no_history")
        return messages

    current = messages[last_idx]
    to_compress = [message for index, message in enumerate(messages) if index != last_idx and not isinstance(message, SystemMessage)]
    if not to_compress:
        logger.debug(COMPACTION_SKIP_LOG, packet_tokens, threshold, extra, "no_history")
        return messages

    logger.info(COMPACTION_START_LOG, packet_tokens, threshold, extra, 1)
    summary = await generate_summary(to_compress, llm, config.summary_max_tokens)
    compacted = system_msgs + [_summary_human_message(summary)] + [current] + list(messages[last_idx + 1 :])
    result_tokens = count_message_tokens(compacted, model_name) + extra
    logger.info(COMPACTION_DONE_LOG, packet_tokens, result_tokens, extra)
    return compacted
