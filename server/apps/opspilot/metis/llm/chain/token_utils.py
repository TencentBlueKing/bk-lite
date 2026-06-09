"""
共享的 tiktoken token 计数工具

集中管理 tokenizer 的获取与 token 计数逻辑，避免在多个模块中重复
copy-paste 的 encoding_for_model / cl100k_base 回退代码。
"""

from typing import List

import tiktoken
from langchain_core.messages import BaseMessage


def get_encoding(model: str = "gpt-4o"):
    """获取 tokenizer，未知模型回退到通用编码器 cl100k_base。"""
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_text_tokens(text: str, model: str = "gpt-4o") -> int:
    """计算单段文本的 token 数量。"""
    encoding = get_encoding(model)
    return len(encoding.encode(text))


def count_message_tokens(messages: List[BaseMessage], model: str = "gpt-4o") -> int:
    """
    计算消息列表的总 token 数量。

    Args:
        messages: 消息列表
        model: 用于选择 tokenizer 的模型名称

    Returns:
        总 token 数
    """
    encoding = get_encoding(model)

    total_tokens = 0
    for msg in messages:
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            total_tokens += len(encoding.encode(content))
        elif isinstance(content, list):
            # 多模态消息（如图片+文字）
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total_tokens += len(encoding.encode(part.get("text", "")))
                elif isinstance(part, str):
                    total_tokens += len(encoding.encode(part))
        # tool_calls 的 token 估算
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                total_tokens += len(encoding.encode(str(tc.get("args", {}))))
                total_tokens += len(encoding.encode(tc.get("name", "")))

    return total_tokens
