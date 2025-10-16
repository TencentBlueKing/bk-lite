from typing import List, TYPE_CHECKING

from langchain_core.documents import Document
from loguru import logger

from neco.llm.rag.naive_rag.recall_strategies.base_recall_strategy import BaseRecallStrategy
from neco.llm.rag.naive_rag_entity import DocumentListRequest, DocumentRetrieverRequest

if TYPE_CHECKING:
    from neco.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag


class OriginRecallStrategy(BaseRecallStrategy):
    """Origin 召回策略 - 根据 knowledge_id 恢复原始文档片段"""

    # 常量配置：避免硬编码
    _MAX_QUERY_SIZE = 10000  # 单次查询最大文档数量
    _MAX_KNOWLEDGE_IDS = 100  # 最大处理的 knowledge_id 数量

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return "origin"

    def process_recall(self, req: DocumentRetrieverRequest, search_result: List[Document], rag_client: "PgvectorRag") -> List[Document]:
        """
        处理 Origin 召回模式

        Args:
            req: 检索请求对象
            search_result: 初始搜索结果
            rag_client: RAG客户端 (PgvectorRag)

        Returns:
            处理后的搜索结果

        Raises:
            ValueError: 当 knowledge_id 数量超过限制时
        """
        # 1. 从搜索结果中提取所有相关的 knowledge_id
        knowledge_id_set = set()
        for doc in search_result:
            knowledge_id = doc.metadata.get('knowledge_id')
            if knowledge_id:
                knowledge_id_set.add(knowledge_id)

        if not knowledge_id_set:
            logger.warning("Origin召回策略: 搜索结果中未找到有效的knowledge_id")
            return search_result

        # 2. 安全检查：防止查询过多数据
        if len(knowledge_id_set) > self._MAX_KNOWLEDGE_IDS:
            logger.warning(
                f"Origin召回策略: knowledge_id数量({len(knowledge_id_set)})超过限制({self._MAX_KNOWLEDGE_IDS})，截取处理")
            knowledge_id_set = set(list(knowledge_id_set)[
                                   :self._MAX_KNOWLEDGE_IDS])

        # 3. 通过RAG客户端查找所有的 knowledge_id 内容
        try:
            # 使用PgvectorRag的list_index_document方法查询
            list_req = DocumentListRequest(
                index_name=req.index_name,
                metadata_filter={"knowledge_id__in": list(knowledge_id_set)},
                page=0,
                size=self._MAX_QUERY_SIZE,
                query=""  # Origin召回策略不需要文本查询
            )
            all_knowledge_docs = rag_client.list_index_document(list_req)

            logger.info(
                f"Origin召回策略: 查询完成，knowledge_id数量={len(knowledge_id_set)}, 文档片段数={len(all_knowledge_docs)}")

        except (ConnectionError, TimeoutError) as e:
            logger.error(
                f"Origin召回策略: 数据库连接失败，回退到原始结果 - {type(e).__name__}: {e}")
            return search_result
        except ValueError as e:
            logger.error(f"Origin召回策略: 请求参数错误，回退到原始结果 - {e}")
            return search_result
        except Exception as e:
            logger.error(f"Origin召回策略: 查询异常，回退到原始结果 - {type(e).__name__}: {e}")
            return search_result

        # 4. 按 knowledge_id 组织文档
        knowledge_docs = {}
        for doc in all_knowledge_docs:
            knowledge_id = doc.metadata.get('knowledge_id')
            if knowledge_id:
                if knowledge_id not in knowledge_docs:
                    knowledge_docs[knowledge_id] = []
                knowledge_docs[knowledge_id].append(doc)

        # 5. 按 knowledge_id 分组处理并重组文档
        result_hits = []
        for knowledge_id, docs in knowledge_docs.items():
            # 按 segment_number 排序，确保文档片段的逻辑顺序
            sorted_docs = sorted(docs, key=lambda x: int(
                x.metadata.get('segment_number', 0)))

            if not sorted_docs:
                continue

            # 合并所有片段的内容
            combined_content = ""
            base_metadata = sorted_docs[0].metadata.copy()

            for doc in sorted_docs:
                if combined_content:
                    combined_content += "\n"  # 片段之间用换行分隔
                combined_content += doc.page_content

            # 创建新的合并文档
            # 更新元数据，移除 segment_number（因为已经合并）
            if 'segment_number' in base_metadata:
                del base_metadata['segment_number']

            # 添加合并信息到元数据
            base_metadata['is_merged_origin'] = True
            base_metadata['merged_segment_count'] = len(sorted_docs)

            merged_doc = Document(
                page_content=combined_content,
                metadata=base_metadata
            )
            result_hits.append(merged_doc)

        logger.info(
            f"Origin召回策略: 重组完成，knowledge数量={len(result_hits)}, 原始片段数={len(all_knowledge_docs)}")
        return result_hits
