"""
LLMService - 兼容层（向后兼容，委托给专职服务）

该服务类作为向后兼容层存在，所有方法委托给专门的服务类：
- ChatService: 处理聊天核心逻辑
- RAGService: 处理知识检索(RAG)
- HistoryService: 处理对话历史和消息格式化

建议：新代码应直接使用专门的服务类，而不是通过此兼容层。
"""
from typing import Any, Dict, List, Tuple, Union

from apps.opspilot.services.chat_service import chat_service
from apps.opspilot.services.history_service import history_service
from apps.opspilot.services.rag_service import rag_service


class LLMService:
    """
    LLM服务兼容层

    该类保留以确保向后兼容，所有方法委托给专门的服务类。
    建议新代码直接使用 chat_service、rag_service、history_service。
    """

    def chat(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """委托给 ChatService.chat"""
        return chat_service.chat(kwargs)

    def invoke_chat(self, kwargs: Dict[str, Any]) -> Tuple[Dict, Dict, Dict]:
        """委托给 ChatService.invoke_chat"""
        return chat_service.invoke_chat(kwargs)

    def format_chat_server_kwargs(self, kwargs, llm_model):
        """委托给 ChatService.format_chat_server_kwargs"""
        return chat_service.format_chat_server_kwargs(kwargs, llm_model)

    @classmethod
    def format_naive_rag_kwargs(cls, kwargs: Dict[str, Any]) -> Tuple[List, Dict, Dict]:
        """委托给 RAGService.format_naive_rag_kwargs"""
        return rag_service.format_naive_rag_kwargs(kwargs)

    @staticmethod
    def set_km_request(knowledge_base_list, enable_km_route, km_llm_model):
        """委托给 RAGService.set_km_request"""
        return rag_service.set_km_request(knowledge_base_list, enable_km_route, km_llm_model)

    @staticmethod
    def set_default_naive_rag_kwargs(knowledge_base, score_threshold_map):
        """委托给 RAGService.set_default_naive_rag_kwargs"""
        return rag_service.set_default_naive_rag_kwargs(knowledge_base, score_threshold_map)

    @staticmethod
    def _process_user_message_and_images(user_message: Union[str, List[Dict[str, Any]]]) -> Tuple[str, List[str]]:
        """委托给 HistoryService.process_user_message_and_images"""
        return history_service.process_user_message_and_images(user_message)

    @staticmethod
    def process_chat_history(chat_history: List[Dict[str, Any]], window_size: int) -> List[Dict[str, Any]]:
        """委托给 HistoryService.process_chat_history"""
        return history_service.process_chat_history(chat_history, window_size)


# 创建服务实例
llm_service = LLMService()
