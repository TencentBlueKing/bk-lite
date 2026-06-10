"""
消息裁剪模块 (Message Trimming)

在 compaction（摘要压缩）之前执行的轻量级裁剪，处理：
1. 单条消息 token 过长 → 截断尾部，保留前 N tokens
2. 图片消息老化 → 早期轮次的 base64 图片移除，仅保留文字部分

设计原则：
- 不修改原始消息列表（返回新列表）
- 保留 SystemMessage 不裁剪
- 图片保留最近 N 条含图片的消息
- 截断只影响 content 字符串，不影响 tool_calls 等结构
"""

from typing import List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from loguru import logger

from apps.opspilot.metis.llm.chain.entity import MessageTrimConfig
from apps.opspilot.metis.llm.chain.token_utils import get_encoding as _get_encoding


def _truncate_text(text: str, max_tokens: int, encoding, suffix_template: str) -> str:
    """截断文本到指定 token 数"""
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text
    # 保留前 max_tokens 个 token
    truncated_tokens = tokens[:max_tokens]
    truncated_text = encoding.decode(truncated_tokens)
    suffix = suffix_template.format(kept=max_tokens)
    return truncated_text + f"\n{suffix}"


def _message_has_images(msg: BaseMessage) -> bool:
    """检查消息是否包含图片"""
    content = getattr(msg, "content", None)
    if isinstance(content, list):
        return any(isinstance(part, dict) and part.get("type") == "image_url" for part in content)
    return False


def _strip_images_from_message(msg: BaseMessage) -> BaseMessage:
    """移除消息中的图片部分，仅保留文字"""
    content = getattr(msg, "content", None)
    if not isinstance(content, list):
        return msg

    text_parts = []
    image_count = 0
    for part in content:
        if isinstance(part, dict):
            if part.get("type") == "text":
                text_parts.append(part)
            elif part.get("type") == "image_url":
                image_count += 1
        elif isinstance(part, str):
            text_parts.append({"type": "text", "text": part})

    # 添加图片移除提示
    if image_count > 0:
        text_parts.append({"type": "text", "text": f"[{image_count} 张图片已从历史中移除以节省上下文]"})

    # 如果只剩一个文本部分，简化为字符串
    if len(text_parts) == 1 and text_parts[0].get("type") == "text":
        new_content = text_parts[0]["text"]
    else:
        new_content = text_parts if text_parts else "[图片消息，内容已清理]"

    # 创建同类型新消息
    if isinstance(msg, HumanMessage):
        return HumanMessage(content=new_content)
    elif isinstance(msg, AIMessage):
        return AIMessage(
            content=new_content,
            tool_calls=getattr(msg, "tool_calls", None) or [],
            additional_kwargs=getattr(msg, "additional_kwargs", {}),
        )
    return msg


def trim_messages(
    messages: List[BaseMessage],
    config: MessageTrimConfig,
    model_name: str = "gpt-4o",
) -> List[BaseMessage]:
    """
    对消息列表执行轻量级裁剪。

    处理顺序：
    1. 图片老化清理：只保留最近 N 条含图片的消息，更早的移除图片
    2. 单条消息截断：超过 max_single_message_tokens 的消息截断尾部

    Args:
        messages: 消息列表
        config: 裁剪配置
        model_name: 用于 tokenizer 的模型名

    Returns:
        裁剪后的新消息列表
    """
    if not config.enabled:
        return messages

    encoding = _get_encoding(model_name)
    result = list(messages)  # shallow copy

    # ========== Step 1: 图片老化清理 ==========
    if config.image_retain_recent > 0:
        # 找到所有含图片的消息索引（从后往前）
        image_indices = [i for i, m in enumerate(result) if _message_has_images(m)]

        if len(image_indices) > config.image_retain_recent:
            # 需要清理的图片消息（最早的）
            indices_to_strip = image_indices[: -config.image_retain_recent]
            stripped_count = 0
            for idx in indices_to_strip:
                result[idx] = _strip_images_from_message(result[idx])
                stripped_count += 1
            if stripped_count > 0:
                logger.debug(f"MessageTrim: 移除 {stripped_count} 条早期消息中的图片")

    # ========== Step 2: 单条消息截断 ==========
    max_tokens = config.max_single_message_tokens
    if max_tokens > 0:
        trimmed_count = 0
        for i, msg in enumerate(result):
            # 跳过 SystemMessage
            if isinstance(msg, SystemMessage):
                continue

            content = getattr(msg, "content", "")
            if not isinstance(content, str):
                # 多模态消息跳过截断（已在图片清理中处理）
                continue

            tokens = encoding.encode(content)
            if len(tokens) > max_tokens:
                new_content = _truncate_text(content, max_tokens, encoding, config.trim_tool_message_prefix)
                # 创建同类型新消息保留其他属性
                if isinstance(msg, ToolMessage):
                    result[i] = ToolMessage(
                        content=new_content,
                        tool_call_id=getattr(msg, "tool_call_id", ""),
                    )
                elif isinstance(msg, AIMessage):
                    result[i] = AIMessage(
                        content=new_content,
                        tool_calls=getattr(msg, "tool_calls", None) or [],
                        additional_kwargs=getattr(msg, "additional_kwargs", {}),
                    )
                elif isinstance(msg, HumanMessage):
                    result[i] = HumanMessage(content=new_content)
                trimmed_count += 1

        if trimmed_count > 0:
            logger.debug(f"MessageTrim: 截断 {trimmed_count} 条过长消息 (阈值={max_tokens} tokens)")

    return result
