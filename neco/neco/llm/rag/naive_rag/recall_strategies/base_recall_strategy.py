from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING

from langchain_core.documents import Document

from neco.llm.rag.naive_rag_entity import DocumentRetrieverRequest

if TYPE_CHECKING:
    from neco.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag


class BaseRecallStrategy(ABC):
    """召回策略基类"""

    @abstractmethod
    def process_recall(self, req: DocumentRetrieverRequest, search_result: List[Document], rag_client: "PgvectorRag") -> List[Document]:
        """
        处理召回逻辑

        Args:
            req: 检索请求对象
            search_result: 初始搜索结果
            rag_client: RAG客户端 (PgvectorRag)

        Returns:
            处理后的搜索结果
        """
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """
        获取策略名称

        Returns:
            策略名称
        """
        pass
