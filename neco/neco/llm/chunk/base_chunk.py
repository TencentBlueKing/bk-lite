import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import List

from langchain_core.documents import Document
from loguru import logger


class BaseChunk(ABC):
    """文档分块的基类，提供通用的元数据添加功能"""

    @abstractmethod
    def _split_documents(self, docs: List[Document]) -> List[Document]:
        """子类需要实现的文档分割方法"""
        pass

    def chunk(self, docs: List[Document]) -> List[Document]:
        """
        对文档进行分块，并添加必要的元数据

        Args:
            docs: 待分块的文档列表

        Returns:
            分块后的文档列表，包含chunk_id、chunk_number等元数据
        """
        if not docs:
            logger.warning("输入文档列表为空，直接返回空列表")
            return []

        logger.info(f"开始文档分块处理，文档数量: {len(docs)}")

        try:
            # 1. 调用子类的分割方法
            split_docs = self._split_documents(docs)
            logger.debug(f"文档分割完成，分块数量: {len(split_docs)}")

            # 2. 按照 segment_number 分组
            grouped_docs = defaultdict(list)
            for doc in split_docs:
                segment_number = doc.metadata.get('segment_number', 0)
                grouped_docs[segment_number].append(doc)

            logger.debug(f"文档分组完成，分组数量: {len(grouped_docs)}")

            # 3. 为每个组内的文档添加 chunk_number 和 chunk_id
            result_docs = []
            for segment_number, segment_docs in grouped_docs.items():
                for chunk_number, doc in enumerate(segment_docs):
                    doc.metadata['chunk_number'] = str(chunk_number)
                    doc.metadata['chunk_id'] = str(uuid.uuid4())
                    # 确保segment_number存在
                    doc.metadata['segment_number'] = segment_number
                    result_docs.append(doc)

            logger.info(f"文档分块处理完成，最终分块数量: {len(result_docs)}")
            return result_docs

        except Exception as e:
            logger.error(f"文档分块处理失败: {str(e)}", exc_info=True)
            raise
