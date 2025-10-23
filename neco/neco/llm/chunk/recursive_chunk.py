from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from neco.llm.chunk import BaseChunk


class RecursiveChunk(BaseChunk):
    """递归字符文本分割器，支持多种分隔符的智能分割"""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 128):
        """
        初始化递归分块器

        Args:
            chunk_size: 每个块的目标大小
            chunk_overlap: 块之间的重叠大小
        """
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )

    def _split_documents(self, docs: List[Document]) -> List[Document]:
        """使用递归字符分割器分割文档"""
        try:
            logger.info(f"开始递归分块处理，文档数量: {len(docs)}")
            result = self.text_splitter.split_documents(docs)
            logger.info(f"递归分块完成，分块数量: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"递归分块处理失败: {str(e)}")
            raise
