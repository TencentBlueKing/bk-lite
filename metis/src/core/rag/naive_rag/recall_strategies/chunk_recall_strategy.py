from typing import List

from langchain_core.documents import Document

from src.web.entity.rag.base.document_retriever_request import DocumentRetrieverRequest
from src.core.rag.naive_rag.recall_strategies.base_recall_strategy import BaseRecallStrategy


class ChunkRecallStrategy(BaseRecallStrategy):
    """Chunk 召回策略 - 直接返回搜索结果，不做额外处理"""

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return "chunk"

    def process_recall(self, req: DocumentRetrieverRequest, search_result: List[Document], rag_client) -> List[Document]:
        """
        处理 Chunk 召回模式 - 直接返回原始搜索结果

        Args:
            req: 检索请求对象
            search_result: 初始搜索结果
            rag_client: RAG客户端 (PgvectorRag)

        Returns:
            处理后的搜索结果（未做修改）
        """
        return search_result
