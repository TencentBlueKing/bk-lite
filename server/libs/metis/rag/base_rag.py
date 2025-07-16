from abc import ABC, abstractmethod
from typing import List

from langchain_core.documents import Document

from libs.metis.entity.rag.base.document_count_request import DocumentCountRequest
from libs.metis.entity.rag.base.document_delete_request import DocumentDeleteRequest
from libs.metis.entity.rag.base.document_ingest_request import DocumentIngestRequest
from libs.metis.entity.rag.base.document_list_request import DocumentListRequest
from libs.metis.entity.rag.base.document_metadata_update_request import DocumentMetadataUpdateRequest
from libs.metis.entity.rag.base.document_retriever_request import DocumentRetrieverRequest
from libs.metis.entity.rag.base.index_delete_request import IndexDeleteRequest


class BaseRag(ABC):
    """
    原生检索增强生成(RAG)系统的抽象基类。
    定义了所有RAG实现必须支持的基本接口。
    """

    @abstractmethod
    def update_metadata(self, req: DocumentMetadataUpdateRequest):
        """
        根据过滤条件更新文档的元数据

        Args:
            req: 包含索引名称、元数据过滤条件和新元数据的请求对象

        Returns:
            更新的文档数量
        """
        pass

    @abstractmethod
    def count_index_document(self, req: DocumentCountRequest):
        """
        计算索引中符合条件的文档数量

        Args:
            req: 包含索引名称和过滤条件的请求对象

        Returns:
            文档数量
        """
        pass

    @abstractmethod
    def delete_index(self, req: IndexDeleteRequest):
        """
        删除指定的索引

        Args:
            req: 包含索引名称的请求对象
        """
        pass

    @abstractmethod
    def list_index_document(self, req: DocumentListRequest):
        """
        列出索引中符合条件的文档

        Args:
            req: 包含索引名称、页码、大小和过滤条件的请求对象

        Returns:
            文档列表
        """
        pass

    @abstractmethod
    def delete_document(self, req: DocumentDeleteRequest):
        """
        删除符合条件的文档

        Args:
            req: 包含索引名称和过滤条件的请求对象
        """
        pass

    @abstractmethod
    def ingest(self, req: DocumentIngestRequest):
        """
        将文档导入到索引中

        Args:
            req: 包含索引名称、文档和嵌入模型信息的请求对象
        """
        pass

    @abstractmethod
    def search(self, req: DocumentRetrieverRequest) -> List[Document]:
        """
        搜索符合条件的文档

        Args:
            req: 包含搜索查询、索引名称和检索参数的请求对象

        Returns:
            检索到的文档列表
        """
        pass

    @abstractmethod
    def process_recall_stage(self, req: DocumentRetrieverRequest, search_result: List[Document]) -> List[Document]:
        """
        处理检索阶段，根据不同的召回模式处理搜索结果

        Args:
            req: 检索请求对象
            search_result: 初始搜索结果

        Returns:
            处理后的搜索结果
        """
        pass
