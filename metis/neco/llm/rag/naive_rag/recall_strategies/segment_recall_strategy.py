from typing import List, TYPE_CHECKING

from langchain_core.documents import Document
from loguru import logger
from neco.llm.rag.naive_rag.recall_strategies.base_recall_strategy import BaseRecallStrategy
from neco.llm.rag.naive_rag_entity import DocumentListRequest, DocumentRetrieverRequest


if TYPE_CHECKING:
    from neco.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag


class SegmentRecallStrategy(BaseRecallStrategy):
    """Segment 召回策略 - 根据 segment_id 恢复段落片段"""

    # 常量配置：避免硬编码
    _MAX_QUERY_SIZE = 10000  # 单次查询最大文档数量
    _MAX_SEGMENT_IDS = 100  # 最大处理的 segment_id 数量

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return "segment"

    def process_recall(self, req: DocumentRetrieverRequest, search_result: List[Document], rag_client: "PgvectorRag") -> List[Document]:
        """
        处理 Segment 召回模式

        Args:
            req: 检索请求对象
            search_result: 初始搜索结果
            rag_client: RAG客户端 (PgvectorRag)

        Returns:
            处理后的搜索结果

        Raises:
            ValueError: 当 segment_id 数量超过限制时
        """
        # 1. 从搜索结果中提取所有相关的 segment_id
        segments_id_set = set()
        for doc in search_result:
            segment_id = doc.metadata.get('segment_id')
            if segment_id:
                segments_id_set.add(segment_id)

        if not segments_id_set:
            logger.warning("Segment召回策略: 搜索结果中未找到有效的segment_id")
            return search_result

        # 2. 安全检查：防止查询过多数据
        if len(segments_id_set) > self._MAX_SEGMENT_IDS:
            logger.warning(
                f"Segment召回策略: segment_id数量({len(segments_id_set)})超过限制({self._MAX_SEGMENT_IDS})，截取处理")
            segments_id_set = set(list(segments_id_set)[
                                  :self._MAX_SEGMENT_IDS])

        # 3. 通过RAG客户端查找所有的 segment_id 内容
        try:
            # 使用PgvectorRag的list_index_document方法查询
            list_req = DocumentListRequest(
                index_name=req.index_name,
                metadata_filter={"segment_id__in": list(segments_id_set)},
                page=0,
                size=self._MAX_QUERY_SIZE,
                query=""  # Segment召回策略不需要文本查询
            )
            all_segment_docs = rag_client.list_index_document(list_req)

            logger.info(
                f"Segment召回策略: 查询完成，segment_id数量={len(segments_id_set)}, 文档片段数={len(all_segment_docs)}")

        except (ConnectionError, TimeoutError) as e:
            logger.error(
                f"Segment召回策略: 数据库连接失败，回退到原始结果 - {type(e).__name__}: {e}")
            return search_result
        except ValueError as e:
            logger.error(f"Segment召回策略: 请求参数错误，回退到原始结果 - {e}")
            return search_result
        except Exception as e:
            logger.error(
                f"Segment召回策略: 查询异常，回退到原始结果 - {type(e).__name__}: {e}")
            return search_result

        # 4. 按 segment_id 分组处理
        segment_id_dict = {}
        for doc in all_segment_docs:
            segment_id = doc.metadata.get('segment_id')
            if segment_id:
                if segment_id not in segment_id_dict:
                    segment_id_dict[segment_id] = []
                segment_id_dict[segment_id].append(doc)

        # 5. 按 segment_id 分组处理并重组文档
        result_hits = []
        for segment_id, docs in segment_id_dict.items():
            # 按 chunk_number 排序，确保文档片段的逻辑顺序
            sorted_docs = sorted(docs, key=lambda x: int(
                x.metadata.get('chunk_number', 0)))

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
            # 更新元数据，移除 chunk_number（因为已经合并）
            if 'chunk_number' in base_metadata:
                del base_metadata['chunk_number']

            # 添加合并信息到元数据
            base_metadata['is_merged_segment'] = True
            base_metadata['merged_chunk_count'] = len(sorted_docs)

            merged_doc = Document(
                page_content=combined_content,
                metadata=base_metadata
            )
            result_hits.append(merged_doc)

        logger.info(
            f"Segment召回策略: 重组完成，segment数量={len(result_hits)}, 原始片段数={len(all_segment_docs)}")
        return result_hits
