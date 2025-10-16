from typing import List

from langchain_core.documents import Document

from neco.llm.chunk import BaseChunk


class FullChunk(BaseChunk):
    """全文分块器，不对文档进行分割，只添加元数据"""

    def _split_documents(self, docs: List[Document]) -> List[Document]:
        """
        不进行分割，直接返回原文档

        Args:
            docs: 待处理的文档列表

        Returns:
            原样返回的文档列表，不进行任何分割
        """
        return docs
