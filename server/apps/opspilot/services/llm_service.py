"""
LLMService - 兼容层（向后兼容，委托给专职服务）

该服务类作为向后兼容层存在，所有方法委托给专门的服务类：
- ChatService: 处理聊天核心逻辑
- RAGService: 处理知识检索(RAG)
- HistoryService: 处理对话历史和消息格式化

建议：新代码应直接使用专门的服务类，而不是通过此兼容层。
"""

from typing import Any, Dict

from apps.opspilot.services.chat_service import chat_service


class LLMService:
    """
    LLM服务兼容层

    该类保留以确保向后兼容，所有方法委托给专门的服务类。
    建议新代码直接使用 chat_service、rag_service、history_service。
    """

    @staticmethod
    def chat(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """委托给 ChatService.chat"""
        return chat_service.chat(kwargs)

    @staticmethod
    def format_chat_server_kwargs(kwargs, llm_model):
        """委托给 ChatService.format_chat_server_kwargs"""
        return chat_service.format_chat_server_kwargs(kwargs, llm_model)


# 创建服务实例
llm_service = LLMService()
