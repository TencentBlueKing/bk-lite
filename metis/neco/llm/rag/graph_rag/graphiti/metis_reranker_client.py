import asyncio
from typing import List, Tuple

from graphiti_core.cross_encoder.client import CrossEncoderClient
from langchain_core.documents import Document
from loguru import logger

from neco.llm.rag.graph_rag.graphiti.metis_reranker_config import MetisRerankerConfig
from neco.llm.rerank.rerank_config import ReRankConfig
from neco.llm.rerank.rerank_manager import ReRankManager


class MetisRerankerClient(CrossEncoderClient):
    """Metis 重排序客户端

    实现 GraphitiCore CrossEncoderClient 接口，
    使用 Metis 重排序服务对文档进行重排序。
    """

    def __init__(self, config: MetisRerankerConfig) -> None:
        self.config = config

    async def rank(self, query: str, passages: List[str]) -> List[Tuple[str, float]]:
        """重排序方法，返回(文档内容, 分数)的元组列表

        Args:
            query: 查询字符串
            passages: 待重排序的文档列表

        Returns:
            重排序后的(文档内容, 分数)元组列表，按分数降序排列

        Raises:
            ValueError: 输入参数无效时抛出
        """
        # 输入验证
        if not query or not query.strip():
            logger.warning("查询为空，返回原始文档列表")
            return [(passage, 0.0) for passage in passages]

        if not passages:
            logger.warning("文档列表为空")
            return []

        try:
            logger.debug(f"开始重排序 - 查询长度: {len(query)}, 文档数量: {len(passages)}")

            # 将passages转换为Document对象
            documents = [Document(page_content=passage)
                         for passage in passages]

            # 创建重排序配置
            rerank_config = ReRankConfig(
                model_base_url=self.config.url,
                model_name=self.config.model_name,
                api_key=self.config.api_key,
                query=query,
                top_k=len(passages)  # 返回所有文档
            )

            # 在线程池中执行同步的重排序操作，避免阻塞事件循环
            loop = asyncio.get_event_loop()
            reranked_docs = await loop.run_in_executor(
                None,
                ReRankManager.rerank_documents_with_config,
                rerank_config,
                documents
            )

            # 转换为graphiti需要的格式：(内容, 分数)
            result = []
            for doc in reranked_docs:
                score = 0.0
                if hasattr(doc, 'metadata') and doc.metadata:
                    score = doc.metadata.get('relevance_score', 0.0)
                result.append((doc.page_content, score))

            logger.debug(f"重排序完成 - 输出文档数量: {len(result)}")
            return result

        except ValueError as e:
            logger.error(f"重排序参数错误: {e}")
            raise
        except Exception as e:
            logger.warning(f"重排序失败，返回原始顺序: {e}")
            # 如果重排序失败，返回原始顺序且分数为0
            return [(passage, 0.0) for passage in passages]
