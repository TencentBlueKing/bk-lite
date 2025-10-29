from typing import List, Any

from langchain_core.documents import Document
from langchain_experimental.text_splitter import SemanticChunker
from loguru import logger

from neco.llm.chunk import BaseChunk


class SemanticChunk(BaseChunk):
    """语义分块器，基于语义相似度进行文档分割"""

    def __init__(self, semantic_embedding_model: Any, sentence_split_regex: str = r'(?<=[.?!。？！])\s*'):
        """
        初始化语义分块器

        Args:
            semantic_embedding_model: 用于计算语义相似度的嵌入模型
            sentence_split_regex: 句子分割正则表达式，默认按中英文标点符号分割
        """
        if semantic_embedding_model is None:
            raise ValueError("semantic_embedding_model 不能为空")

        self.semantic_embedding_model = semantic_embedding_model

        try:
            self.semantic_chunker = SemanticChunker(
                embeddings=semantic_embedding_model,
                sentence_split_regex=sentence_split_regex
            )
            logger.info(f"语义分块器初始化成功，使用正则表达式: {sentence_split_regex}")
        except Exception as e:
            logger.error(f"语义分块器初始化失败: {e}")
            raise

    def _split_documents(self, docs: List[Document]) -> List[Document]:
        """使用语义分块器分割文档"""
        if not docs:
            logger.warning("输入文档列表为空")
            return []

        try:
            logger.debug(f"开始语义分块，输入文档数量: {len(docs)}")
            result = self.semantic_chunker.split_documents(docs)
            logger.debug(f"语义分块完成，输出块数量: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"语义分块失败: {e}")
            raise
