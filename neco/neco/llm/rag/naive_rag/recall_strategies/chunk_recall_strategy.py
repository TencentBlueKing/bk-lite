from typing import List, TYPE_CHECKING

from langchain_core.documents import Document

from neco.llm.rag.naive_rag.recall_strategies.base_recall_strategy import BaseRecallStrategy
from neco.llm.rag.naive_rag_entity import DocumentRetrieverRequest

if TYPE_CHECKING:
    from neco.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag


class ChunkRecallStrategy(BaseRecallStrategy):
    """Chunk 召回策略 - 直接返回搜索结果，不做额外处理"""

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return "chunk"

    def process_recall(self, req: DocumentRetrieverRequest, search_result: List[Document], rag_client: "PgvectorRag") -> List[Document]:
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
