from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from neco.llm.chunk import BaseChunk


class FixedSizeChunk(BaseChunk):
    """固定大小分块器，不设置重叠"""

    def __init__(self, chunk_size: int = 500) -> None:
        """
        初始化固定大小分块器

        Args:
            chunk_size: 每个块的固定大小
        """
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=0,
            length_function=len,
            is_separator_regex=False,
        )

    def _split_documents(self, docs: List[Document]) -> List[Document]:
        """使用固定大小分割器分割文档"""
        try:
            logger.info(f"开始固定大小分块处理，文档数量: {len(docs)}")
            result = self.text_splitter.split_documents(docs)
            logger.info(f"固定大小分块完成，分块数量: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"固定大小分块处理失败: {str(e)}")
            raise
