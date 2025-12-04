import copy
import json
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from langchain_core.documents import Document
from langchain_postgres import PGVector
from loguru import logger

from apps.opspilot.metis.llm.chunk.fixed_size_chunk import FixedSizeChunk
from apps.opspilot.metis.llm.chunk.full_chunk import FullChunk
from apps.opspilot.metis.llm.chunk.recursive_chunk import RecursiveChunk
from apps.opspilot.metis.llm.chunk.semantic_chunk import SemanticChunk
from apps.opspilot.metis.llm.embed.embed_manager import EmbedManager
from apps.opspilot.metis.llm.loader.doc_loader import DocLoader
from apps.opspilot.metis.llm.loader.excel_loader import ExcelLoader
from apps.opspilot.metis.llm.loader.image_loader import ImageLoader
from apps.opspilot.metis.llm.loader.markdown_loader import MarkdownLoader
from apps.opspilot.metis.llm.loader.pdf_loader import PDFLoader
from apps.opspilot.metis.llm.loader.ppt_loader import PPTLoader
from apps.opspilot.metis.llm.loader.raw_loader import RawLoader
from apps.opspilot.metis.llm.loader.text_loader import TextLoader
from apps.opspilot.metis.llm.loader.website_loader import WebSiteLoader
from apps.opspilot.metis.llm.rag.naive_rag.pgvector.database_manager import DatabaseManager
from apps.opspilot.metis.llm.rag.naive_rag.pgvector.query_builder import QueryBuilder
from apps.opspilot.metis.llm.rag.naive_rag.recall_strategies.recall_strategy_factory import RecallStrategyFactory
from apps.opspilot.metis.llm.rag.naive_rag_entity import (
    DocumentCountRequest,
    DocumentDeleteRequest,
    DocumentIngestRequest,
    DocumentListRequest,
    DocumentMetadataUpdateRequest,
    DocumentRetrieverRequest,
    IndexDeleteRequest,
)
from apps.opspilot.metis.llm.rerank.rerank_manager import ReRankManager
from apps.opspilot.metis.ocr.ocr_manager import OcrManager


class PgvectorRag:
    """基于PostgreSQL + pgvector的RAG实现

    提供基于向量搜索的文档检索功能，支持：
    - 相似度搜索和MMR搜索
    - 元数据过滤
    - 重排序和召回处理
    - 完整的CRUD操作
    """

    # 常量定义
    _DOC_KEY_LENGTH = 100  # 用于MMR分数映射的文档内容长度
    _DB_CONNECT_TIMEOUT = 30  # 数据库连接超时秒数
    _MMR_SCORE_MIN = 0.3  # MMR最小分数
    _MMR_SCORE_MAX = 1.0  # MMR最大分数
    _MMR_SCORE_STEP = 0.1  # MMR分数衰减步长

    def __init__(self):
        self.db_url = os.getenv("METIS_DB_URI")
        self._db_manager = DatabaseManager(self.db_url)

    # ==================== 核心搜索功能 ====================

    def search(self, req: DocumentRetrieverRequest) -> List[Document]:
        """搜索符合条件的文档

        Args:
            req: 文档检索请求，包含搜索参数和过滤条件

        Returns:
            匹配的文档列表
        """
        logger.info(f"文档搜索开始 - 索引: {req.index_name}, naive_rag: {req.enable_naive_rag}, qa_rag: {req.enable_qa_rag}")

        results = []

        if req.enable_naive_rag:
            naive_results = self._search_by_type(req, "naive")
            results.extend(naive_results)

        if req.enable_qa_rag:
            qa_results = self._search_by_type(req, "qa")
            results.extend(qa_results)

        logger.info(f"文档搜索完成 - 索引: {req.index_name}, 结果数: {len(results)}")
        return results

    def _search_by_type(self, req: DocumentRetrieverRequest, rag_type: str) -> List[Document]:
        """按类型执行搜索"""
        logger.debug(f"搜索执行开始 - 类型: {rag_type}, 索引: {req.index_name}")

        search_req = copy.deepcopy(req)
        search_req.metadata_filter = search_req.metadata_filter or {}

        if rag_type == "naive":
            search_req.metadata_filter["is_doc"] = "1"
        elif rag_type == "qa":
            search_req.metadata_filter["is_doc"] = "0"
            search_req.k = req.qa_size

        try:
            results = self._perform_search(search_req)
            results = self._process_search_results(results, req, rag_type)

            logger.debug(f"搜索执行完成 - 类型: {rag_type}, 结果数: {len(results)}")
            return results
        except Exception as e:
            logger.error(f"搜索执行失败 - 类型: {rag_type}, 索引: {req.index_name}, 错误: {e}")
            # 搜索失败返回空列表，不影响其他类型搜索
            return []

    def _perform_search(self, req: DocumentRetrieverRequest) -> List[Document]:
        """执行向量搜索

        Args:
            req: 文档检索请求

        Returns:
            搜索结果文档列表
        """
        try:
            req.validate_search_params()

            vector_store = self._create_vector_store(req)
            search_kwargs = self._build_search_kwargs(req)

            # 执行搜索
            if req.search_type == "mmr":
                return self._execute_mmr_search(vector_store, req, search_kwargs)
            else:
                return self._execute_similarity_search(vector_store, req, search_kwargs)

        except Exception as e:
            logger.error(f"向量搜索异常 - 索引: {req.index_name}, 查询: {req.search_query[:50]}..., 错误: {e}")
            # 向量搜索失败返回空结果，允许系统继续运行
            return []

    def _create_vector_store(self, req: DocumentRetrieverRequest) -> PGVector:
        """创建向量存储实例"""
        embedding = EmbedManager().get_embed(req.embed_model_base_url, req.embed_model_name, req.embed_model_api_key, req.embed_model_base_url)

        return PGVector(
            embeddings=embedding,
            collection_name=req.index_name,
            connection=self.db_url,
            use_jsonb=True,
        )

    def _build_search_kwargs(self, req: DocumentRetrieverRequest) -> dict:
        """构建搜索参数"""
        search_kwargs = {"k": req.k}
        if req.metadata_filter:
            # 直接使用内部过滤器格式，简化逻辑
            pgvector_filter = self._build_pgvector_filter(req.metadata_filter)
            if pgvector_filter:
                search_kwargs["filter"] = pgvector_filter
        return search_kwargs

    def _execute_mmr_search(self, vector_store: PGVector, req: DocumentRetrieverRequest, search_kwargs: dict) -> List[Document]:
        """执行MMR搜索"""
        search_kwargs.update({"fetch_k": req.get_effective_fetch_k(), "lambda_mult": req.lambda_mult})

        # 先获取带分数的相似度搜索结果用于MMR
        candidate_docs_with_scores = vector_store.similarity_search_with_relevance_scores(
            req.search_query, k=req.get_effective_fetch_k(), score_threshold=req.score_threshold or 0.0, filter=search_kwargs.get("filter")
        )

        # 执行MMR搜索
        results = vector_store.max_marginal_relevance_search(req.search_query, **search_kwargs)

        # 为MMR结果设置相似度分数
        self._set_mmr_scores(results, candidate_docs_with_scores)

        # 添加搜索元数据
        self._add_search_metadata(results, req)

        logger.debug(f"MMR搜索完成 - 结果数: {len(results)}")
        return results

    def _execute_similarity_search(self, vector_store: PGVector, req: DocumentRetrieverRequest, search_kwargs: dict) -> List[Document]:
        """执行相似度搜索"""
        results_with_scores = vector_store.similarity_search_with_relevance_scores(
            req.search_query, k=req.k, score_threshold=req.score_threshold or 0.0, filter=search_kwargs.get("filter")
        )

        results = []
        for doc, score in results_with_scores:
            if not hasattr(doc, "metadata"):
                doc.metadata = {}
            doc.metadata["similarity_score"] = float(score)
            doc.metadata["search_method"] = "similarity"
            results.append(doc)

        # 添加搜索元数据
        self._add_search_metadata(results, req)

        logger.debug(f"相似度搜索完成 - 结果数: {len(results)}")
        return results

    def _set_mmr_scores(self, results: List[Document], candidate_docs_with_scores: List[tuple]) -> None:
        """为MMR结果设置相似度分数"""
        score_map = {}
        for doc, score in candidate_docs_with_scores:
            doc_key = doc.page_content[: self._DOC_KEY_LENGTH]  # 使用内容前N字符作为键
            score_map[doc_key] = float(score)

        for i, doc in enumerate(results):
            if not hasattr(doc, "metadata"):
                doc.metadata = {}

            doc_key = doc.page_content[: self._DOC_KEY_LENGTH]
            if doc_key in score_map:
                doc.metadata["similarity_score"] = score_map[doc_key]
            else:
                # 如果找不到对应分数，使用排序位置计算近似分数
                # 分数范围0.3-1.0，排名越靠前分数越高
                normalized_score = max(self._MMR_SCORE_MIN, self._MMR_SCORE_MAX - (i * self._MMR_SCORE_STEP))
                doc.metadata["similarity_score"] = normalized_score

            doc.metadata["search_method"] = "mmr"
            doc.metadata["mmr_rank"] = i + 1

    def _add_search_metadata(self, results: List[Document], req: DocumentRetrieverRequest) -> None:
        """为搜索结果添加元数据"""
        for i, doc in enumerate(results):
            if not hasattr(doc, "metadata"):
                doc.metadata = {}
            doc.metadata.update({"search_type": req.search_type, "rank": i + 1, "index_name": req.index_name})

    # ==================== 数据库连接和查询 ====================
    # 注意：直接使用 self._db_manager.execute_query() 和 self._db_manager.execute_update()
    # 移除了不必要的包装函数

    # ==================== 工具方法 ====================

    def _get_chunk_ids_by_knowledge_ids(self, knowledge_ids: List[str]) -> List[str]:
        """根据knowledge_ids查询chunk_ids"""
        if not knowledge_ids:
            return []

        query = """
            SELECT id FROM langchain_pg_embedding
            WHERE cmetadata->>'knowledge_id' = ANY(%(knowledge_ids)s)
        """
        results = self._db_manager.execute_query(query, {"knowledge_ids": knowledge_ids})
        return [result["id"] for result in results]

    def _collect_target_chunk_ids(self, chunk_ids: Optional[List[str]], knowledge_ids: Optional[List[str]]) -> List[str]:
        """收集要处理的chunk_ids"""
        all_chunk_ids = []

        if chunk_ids:
            all_chunk_ids.extend(chunk_ids)

        if knowledge_ids:
            found_chunk_ids = self._get_chunk_ids_by_knowledge_ids(knowledge_ids)
            all_chunk_ids.extend(found_chunk_ids)

        return list(set(all_chunk_ids))  # 去重

    def _build_metadata_filter(self, metadata_filter: dict, params: Dict[str, Any]) -> str:
        """构建元数据过滤条件 - 委托给QueryBuilder"""
        return QueryBuilder.build_metadata_filter(metadata_filter, params)

    # 移除了 _build_single_filter_condition 包装函数，直接使用 QueryBuilder._build_single_filter_condition

    def _build_where_clauses(self, req: Union[DocumentCountRequest, DocumentListRequest], where_clauses: List[str], params: Dict[str, Any]) -> None:
        """构建WHERE子句"""
        where_clauses.append("c.name = %(index_name)s")
        params["index_name"] = req.index_name

        if hasattr(req, "metadata_filter") and req.metadata_filter:
            metadata_condition = self._build_metadata_filter(req.metadata_filter, params)
            if metadata_condition:
                where_clauses.append(metadata_condition)

        if hasattr(req, "query") and req.query:
            where_clauses.append("e.document ILIKE %(query_pattern)s")
            params["query_pattern"] = f"%{req.query}%"

    # ==================== CRUD操作 ====================

    def update_metadata(self, req: DocumentMetadataUpdateRequest) -> None:
        """更新文档元数据"""
        chunk_ids = self._collect_target_chunk_ids(req.chunk_ids, req.knowledge_ids)

        if not chunk_ids:
            logger.info("元数据更新跳过 - 原因: 未找到匹配的文档")
            return

        logger.info(f"元数据更新开始 - 目标chunks: {len(chunk_ids)}")

        # 验证要更新的记录是否存在
        check_query = """
            SELECT id FROM langchain_pg_embedding
            WHERE id = ANY(%(chunk_ids)s)
        """
        existing_records = self._db_manager.execute_query(check_query, {"chunk_ids": chunk_ids})
        existing_ids = [record["id"] for record in existing_records]

        if not existing_ids:
            logger.warning(f"元数据更新失败 - 原因: 指定chunks不存在, 数量: {len(chunk_ids)}")
            return

        if len(existing_ids) != len(chunk_ids):
            missing_count = len(chunk_ids) - len(existing_ids)
            logger.warning(f"元数据更新部分失败 - 缺失chunks: {missing_count}个")

        query = """
            UPDATE langchain_pg_embedding
            SET cmetadata = cmetadata || %(new_metadata)s::jsonb
            WHERE id = ANY(%(chunk_ids)s)
        """
        params = {"new_metadata": json.dumps(req.metadata), "chunk_ids": existing_ids}

        try:
            affected_rows = self._db_manager.execute_update(query, params)

            if affected_rows > 0:
                logger.info(f"元数据更新详情 - 更新数量: {affected_rows}")
            else:
                logger.warning("元数据更新无效果 - 可能原因: 数据无变化")
        except Exception as e:
            logger.error(f"元数据更新异常详情 - 错误: {e}")
            raise

    def count_index_document(self, req: DocumentCountRequest) -> int:
        """统计索引中符合条件的文档数量"""
        where_clauses = []
        params = {}
        self._build_where_clauses(req, where_clauses, params)

        where_clause = " AND ".join(where_clauses) if where_clauses else "TRUE"

        count_query = (
            """
        SELECT COUNT(*) as count
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
        WHERE """
            + where_clause
        )

        try:
            results = self._db_manager.execute_query(count_query, params)
            count = results[0]["count"] if results else 0
            logger.info(f"文档计数详情 - 索引: {req.index_name}, 文档数: {count}")
            return count
        except Exception as e:
            if "does not exist" in str(e):
                logger.info(f"文档计数详情 - 索引: {req.index_name}, 文档数: 0 (索引不存在)")
                return 0
            logger.error(f"文档计数异常 - 索引: {req.index_name}")
            raise

    def delete_index(self, req: IndexDeleteRequest) -> None:
        """删除指定的索引"""
        logger.info(f"索引删除开始 - 索引: {req.index_name}")

        try:
            query = "DELETE FROM langchain_pg_collection WHERE name = %(collection_name)s"
            affected_rows = self._db_manager.execute_update(query, {"collection_name": req.index_name})

            if affected_rows > 0:
                logger.info(f"索引删除详情 - 索引: {req.index_name}, 清理记录: {affected_rows}")
            else:
                logger.info(f"索引删除详情 - 索引: {req.index_name} (索引不存在)")
        except Exception as e:
            if "does not exist" in str(e):
                logger.info(f"索引删除详情 - 索引: {req.index_name} (索引不存在)")
            else:
                logger.error(f"索引删除异常 - 索引: {req.index_name}")
                raise

    # ==================== 文档操作 ====================
    # 移除了 _build_document_list_query 包装函数，直接使用 QueryBuilder.build_document_list_query

    def list_index_document(self, req: DocumentListRequest) -> List[Document]:
        """列出索引中符合条件的文档"""
        try:
            where_clause, params = self._build_list_where_clause(req)
            query = QueryBuilder.build_document_list_query(req, where_clause, params)
            results = self._db_manager.execute_query(query, params)

            documents = self._convert_results_to_documents(results)

            page_info = f" (分页: {req.page}/{req.size})" if req.page > 0 and req.size > 0 else ""
            logger.info(f"文档列表查询完成 - 索引: {req.index_name}, 返回: {len(documents)}个{page_info}")
            return documents

        except Exception as e:
            if "does not exist" in str(e):
                logger.info(f"文档列表查询完成 - 索引: {req.index_name}, 返回: 0个 (索引不存在)")
                return []
            logger.error(f"文档列表查询失败 - 索引: {req.index_name}, 错误: {e}")
            raise

    def _build_list_where_clause(self, req: DocumentListRequest) -> tuple[str, Dict[str, Any]]:
        """构建列表查询的WHERE子句"""
        where_clauses = []
        params = {}

        where_clauses.append("c.name = %(index_name)s")
        params["index_name"] = req.index_name

        if req.metadata_filter:
            metadata_condition = self._build_metadata_filter(req.metadata_filter, params)
            if metadata_condition:
                where_clauses.append(metadata_condition)

        if req.query:
            where_clauses.append("e.document ILIKE %(query_pattern)s")
            params["query_pattern"] = f"%{req.query}%"

        where_clause = " AND ".join(where_clauses) if where_clauses else "TRUE"
        return where_clause, params

    def _convert_results_to_documents(self, results: List[Dict]) -> List[Document]:
        """将查询结果转换为Document对象"""
        documents = []
        for result in results:
            metadata = result["cmetadata"] if isinstance(result["cmetadata"], dict) else {}
            metadata.update({"chunk_id": result["id"], "qa_count": result["qa_count"]})

            documents.append(Document(id=result["id"], page_content=result["document"], metadata=metadata))
        return documents

    def _handle_qa_records(self, chunk_ids: List[str], keep_qa: bool) -> None:
        """处理QA记录"""
        if keep_qa:
            # 更新关联QA记录的base_chunk_id为空
            query = """
                UPDATE langchain_pg_embedding
                SET cmetadata = jsonb_set(cmetadata, '{base_chunk_id}', '""'::jsonb)
                WHERE cmetadata->>'base_chunk_id' = ANY(%(chunk_ids)s)
            """
            affected_rows = self._db_manager.execute_update(query, {"chunk_ids": chunk_ids})
            if affected_rows > 0:
                logger.info(f"QA记录保留处理完成 - 更新关联: {affected_rows}个")
        else:
            # 删除关联的QA记录
            query = """
                DELETE FROM langchain_pg_embedding
                WHERE cmetadata->>'base_chunk_id' = ANY(%(chunk_ids)s)
            """
            affected_rows = self._db_manager.execute_update(query, {"chunk_ids": chunk_ids})
            if affected_rows > 0:
                logger.info(f"QA记录清理完成 - 删除: {affected_rows}个")

    def delete_document(self, req: DocumentDeleteRequest) -> None:
        """删除文档记录"""
        chunk_ids = self._collect_target_chunk_ids(req.chunk_ids, req.knowledge_ids)

        if not chunk_ids:
            logger.info("文档删除跳过 - 原因: 未找到匹配的文档")
            return

        logger.info(f"文档删除开始 - 目标chunks: {len(chunk_ids)}, 保留QA: {req.keep_qa}")

        try:
            # 处理关联的QA记录
            self._handle_qa_records(chunk_ids, req.keep_qa)

            # 删除主文档
            query = "DELETE FROM langchain_pg_embedding WHERE id = ANY(%(chunk_ids)s)"
            affected_rows = self._db_manager.execute_update(query, {"chunk_ids": chunk_ids})

            logger.info(f"文档删除成功 - 删除数量: {affected_rows}")
        except Exception as e:
            logger.error(f"文档删除失败 - 错误: {e}")
            raise

    def ingest(self, req: DocumentIngestRequest) -> List[str]:
        """将文档导入到索引中"""
        logger.info(f"文档导入开始 - 索引: {req.index_name}, 模式: {req.index_mode}, 文档数: {len(req.docs)}")

        if req.index_mode == "overwrite":
            query = "DELETE FROM langchain_pg_collection WHERE name = %(index_name)s"
            affected_rows = self._db_manager.execute_update(query, {"index_name": req.index_name})
            logger.info(f"覆盖模式清理完成 - 索引: {req.index_name}, 清理记录: {affected_rows}")

        embedding = EmbedManager().get_embed(req.embed_model_base_url, req.embed_model_name, req.embed_model_api_key, req.embed_model_base_url)

        vector_store = PGVector(
            embeddings=embedding,
            collection_name=req.index_name,
            connection=self.db_url,
            use_jsonb=True,
        )

        try:
            chunk_ids = [doc.metadata["chunk_id"] for doc in req.docs]
            vector_store.add_documents(req.docs, ids=chunk_ids)

            logger.info(f"文档导入成功 - 索引: {req.index_name}, 导入数量: {len(req.docs)}")
            return chunk_ids
        except Exception as e:
            logger.error(f"文档导入失败 - 索引: {req.index_name}, 错误: {e}")
            raise

    # ==================== 搜索结果处理 ====================

    def _process_search_results(self, results: List[Document], req: DocumentRetrieverRequest, rag_type: str) -> List[Document]:
        """处理搜索结果"""
        # 清理和添加QA答案
        for doc in results:
            for field in ["embedding", "vector"]:
                if field in doc.metadata:
                    del doc.metadata[field]
            if "qa_answer" in doc.metadata:
                doc.page_content += f"\n{doc.metadata['qa_answer']}"

        # 重排序处理
        if req.enable_rerank and results:
            results = self._rerank_results(req, results)
        if rag_type == "naive":
            results = self.process_recall_stage(req, results)

        return results

    def _build_pgvector_filter(self, metadata_filter: dict) -> dict:
        """构建pgvector兼容的过滤条件"""
        if not metadata_filter:
            return {}

        pgvector_filter = {}
        for key, value in metadata_filter.items():
            if key.endswith("__exists"):
                field = key.replace("__exists", "")
                pgvector_filter[field] = {"$ne": None}
            elif key.endswith("__missing"):
                field = key.replace("__missing", "")
                pgvector_filter[field] = {"$eq": None}
            elif key.endswith("__like"):
                field = key.replace("__like", "")
                pgvector_filter[field] = {"$like": value}
            elif key.endswith("__ilike"):
                field = key.replace("__ilike", "")
                pgvector_filter[field] = {"$ilike": value}
            elif key.endswith("__not_blank"):
                field = key.replace("__not_blank", "")
                pgvector_filter[field] = {"$ne": ""}
            elif key.endswith("__in"):
                field = key.replace("__in", "")
                if isinstance(value, list) and value:
                    pgvector_filter[field] = {"$in": value}
            else:
                pgvector_filter[key] = {"$eq": value}

        return pgvector_filter

    # ==================== 重排序和召回处理 ====================

    def _rerank_results(self, req: DocumentRetrieverRequest, results: List[Document]) -> List[Document]:
        """重排序处理"""
        if not results:
            return results

        reranked_results = ReRankManager.rerank_documents(
            rerank_model_base_url=req.rerank_model_base_url,
            rerank_model_name=req.rerank_model_name,
            rerank_model_api_key=req.rerank_model_api_key,
            search_query=req.search_query,
            search_result=results,
            rerank_top_k=req.rerank_top_k,
        )

        logger.debug(f"重排序完成 - 输入: {len(results)}, 输出: {len(reranked_results)}")
        return reranked_results

    def process_recall_stage(self, req: DocumentRetrieverRequest, results: List[Document]) -> List[Document]:
        """处理检索阶段，根据不同的召回模式处理搜索结果"""
        recall_mode = req.rag_recall_mode

        try:
            strategy = RecallStrategyFactory.get_strategy(recall_mode)
            processed_results = strategy.process_recall(req, results, self)

            logger.debug(f"召回处理完成 - 模式: {recall_mode}, 输入: {len(results)}, 输出: {len(processed_results)}")
            return processed_results
        except ValueError:
            logger.warning(f"召回策略异常 - 模式: '{recall_mode}' 不存在, 使用默认策略 'chunk'")
            default_strategy = RecallStrategyFactory.get_strategy("chunk")
            processed_results = default_strategy.process_recall(req, results, self)

            logger.debug(f"默认召回处理完成 - 输入: {len(results)}, 输出: {len(processed_results)}")
            return processed_results

    # ==================== 文档处理辅助方法 ====================

    @classmethod
    def store_documents_to_pg(cls, chunked_docs, knowledge_base_id, embed_model_base_url, embed_model_api_key, embed_model_name, metadata=None):
        """将文档存储到PgVector

        Args:
            chunked_docs: 分块后的文档
            knowledge_base_id: 知识库ID
            embed_model_base_url: 嵌入模型基础URL
            embed_model_api_key: 嵌入模型API密钥
            embed_model_name: 嵌入模型名称
            metadata: 额外的元数据
        """
        if metadata is None:
            metadata = {}

        logger.debug(f"存储文档到PgVector, 知识库ID: {knowledge_base_id}, 模型名称: {embed_model_name}, 分块数: {len(chunked_docs)}")

        # 自动添加创建时间
        created_time = datetime.now().isoformat()
        logger.debug(f"为文档添加创建时间: {created_time}")

        for doc in chunked_docs:
            # 添加创建时间到每个文档的元数据中
            doc.metadata["created_time"] = created_time

        # 应用额外的元数据
        if metadata:
            logger.debug(f"应用额外元数据: {metadata}")
            for doc in chunked_docs:
                doc.metadata.update(metadata)

        pg_store_request = DocumentIngestRequest(
            index_name=knowledge_base_id,
            docs=chunked_docs,
            embed_model_base_url=embed_model_base_url,
            embed_model_api_key=embed_model_api_key,
            embed_model_name=embed_model_name,
        )

        try:
            start_time = time.time()
            rag = PgvectorRag()
            rag.ingest(pg_store_request)
            elapsed_time = time.time() - start_time
            logger.debug(f"PgVector存储完成, 耗时: {elapsed_time:.2f}秒")
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"PgVector存储失败, 耗时: {elapsed_time:.2f}秒, 错误: {e}")
            raise

    @classmethod
    def perform_chunking(cls, docs, chunk_mode, request_params, is_preview, content_type):
        """执行文档分块并记录相关日志

        Args:
            docs: 文档列表
            chunk_mode: 分块模式
            request_params: 请求参数字典
            is_preview: 是否为预览模式
            content_type: 内容类型

        Returns:
            分块后的文档列表
        """
        mode = "预览" if is_preview else "正式处理"
        logger.debug(f"{content_type}分块 [{mode}], 模式: {chunk_mode}, 文档数: {len(docs)}")

        chunker = cls.get_chunker(chunk_mode, request_params)
        chunked_docs = chunker.chunk(docs)
        logger.debug(f"{content_type}分块完成, 输入文档: {len(docs)}, 输出分块: {len(chunked_docs)}")
        return chunked_docs

    @classmethod
    def prepare_documents_metadata(cls, docs, is_preview, title, knowledge_id=None):
        """准备文档的元数据

        Args:
            docs: 文档列表
            is_preview: 是否为预览模式
            title: 文档标题
            knowledge_id: 知识库ID，预览模式下不需要

        Returns:
            处理后的文档列表
        """
        mode = "预览" if is_preview else "正式处理"
        logger.debug(f"准备文档元数据 [{mode}], 标题: {title}, 知识ID: {knowledge_id}, 文档数: {len(docs)}")
        if is_preview:
            return cls.process_documents(docs, title)
        else:
            return cls.process_documents(docs, title, knowledge_id)

    @classmethod
    def serialize_documents(cls, docs):
        """将文档序列化为JSON格式"""
        logger.debug(f"序列化 {len(docs)} 个文档")
        serialized_docs = []
        for doc in docs:
            serialized_docs.append({"page_content": doc.page_content, "metadata": doc.metadata})
        return serialized_docs

    @classmethod
    def process_documents(cls, docs, knowledge_title, knowledge_id=None):
        """处理文档，添加元数据"""
        logger.debug(f"处理文档元数据，标题: {knowledge_title}, ID: {knowledge_id}, 文档数量: {len(docs)}")
        for index, doc in enumerate(docs):
            doc.metadata["knowledge_title"] = knowledge_title
            if knowledge_id:
                doc.metadata["knowledge_id"] = knowledge_id
            doc.metadata["segment_id"] = str(uuid.uuid4())
            doc.metadata["segment_number"] = str(index)
        return docs

    @classmethod
    def get_chunker(cls, chunk_mode, request_params):
        """根据分块模式返回相应的分块器

        Args:
            chunk_mode: 分块模式
            request_params: 请求参数字典
        """
        logger.debug(f"初始化分块器，模式: {chunk_mode}")
        if chunk_mode == "fixed_size":
            chunk_size = int(request_params.get("chunk_size", 256))
            logger.debug(f"使用固定大小分块，大小: {chunk_size}")
            return FixedSizeChunk(chunk_size=chunk_size)

        elif chunk_mode == "full":
            logger.debug("使用全文分块")
            return FullChunk()

        elif chunk_mode == "recursive":
            chunk_size = int(request_params.get("chunk_size", 256))
            chunk_overlap = int(request_params.get("chunk_overlap", 128))
            logger.debug(f"使用递归分块，大小: {chunk_size}, 重叠: {chunk_overlap}")
            return RecursiveChunk(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        elif chunk_mode == "semantic":
            semantic_chunk_model = request_params.get("semantic_chunk_model")
            semantic_chunk_model_base_url = request_params.get("semantic_chunk_model_base_url")
            logger.debug(f"使用语义分块，模型: {semantic_chunk_model}, URL: {semantic_chunk_model_base_url}")
            semantic_chunk_model_api_key = request_params.get("semantic_chunk_model_api_key")
            embeddings = EmbedManager().get_embed(
                protocol=semantic_chunk_model_base_url,
                model_name=semantic_chunk_model,
                model_api_key=semantic_chunk_model_api_key,
                model_base_url=semantic_chunk_model_base_url,
            )
            return SemanticChunk(embeddings)
        else:
            error_msg = f"不支持的分块模式: {chunk_mode}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    @classmethod
    def get_file_loader(cls, file_path, file_extension, load_mode, request_params):
        """根据文件类型选择适当的加载器

        Args:
            file_path: 文件路径
            file_extension: 文件扩展名
            load_mode: 加载模式
            request_params: 请求参数字典
        """
        logger.debug(f"为文件 {file_path} (类型: {file_extension}) 初始化加载器")

        ocr_type = request_params.get("ocr_type")
        base_url = request_params.get("olm_base_url") or request_params.get("azure_endpoint")
        model = request_params.get("olm_model")
        api_key = request_params.get("olm_api_key") or request_params.get("azure_api_key")

        ocr = OcrManager.load_ocr(ocr_type=ocr_type, model=model, base_url=base_url, api_key=api_key)

        if file_extension in ["docx", "doc"]:
            return DocLoader(file_path, ocr, load_mode)
        elif file_extension in ["pptx", "ppt"]:
            return PPTLoader(file_path, load_mode)
        elif file_extension == "txt":
            return TextLoader(file_path, load_mode)
        elif file_extension in ["jpg", "png", "jpeg"]:
            return ImageLoader(file_path, ocr, load_mode)
        elif file_extension == "pdf":
            return PDFLoader(file_path, ocr, load_mode)
        elif file_extension in ["xlsx", "xls", "csv"]:
            return ExcelLoader(file_path, load_mode)
        elif file_extension in ["md"]:
            return MarkdownLoader(file_path, load_mode)
        else:
            raise ValueError(f"不支持的文件类型: {file_extension}")

    # ==================== 文档摄取接口 ====================

    def custom_content_ingest(self, content: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """自定义内容摄取接口

        Args:
            content: 自定义内容文本
            params: 包含以下参数的字典:
                - is_preview: 是否为预览模式
                - chunk_mode: 分块模式
                - metadata: 元数据字典
                - knowledge_base_id: 知识库ID
                - embed_model_base_url: 嵌入模型URL
                - embed_model_api_key: 嵌入模型API密钥
                - embed_model_name: 嵌入模型名称
                - knowledge_id: 知识ID

        Returns:
            包含状态和结果信息的字典
        """
        logger.info(f"自定义内容摄取开始 - 预览模式: {params['is_preview']}")

        # 加载自定义内容
        loader = RawLoader(content)
        docs = loader.load()

        # 对于自定义内容，如果不是预览模式，需要手动处理分块
        if not params["is_preview"]:
            # 处理文档元数据
            docs = self.prepare_documents_metadata(docs, is_preview=params["is_preview"], title="自定义内容", knowledge_id=params["knowledge_id"])

            # 执行文档分块
            chunker = self.get_chunker(params["chunk_mode"], params)
            chunked_docs = chunker.chunk(docs)

            # 执行文档存储
            logger.debug(f"开始存储{len(chunked_docs)}个文档分块")
            self.store_documents_to_pg(
                chunked_docs=chunked_docs,
                knowledge_base_id=params["knowledge_base_id"],
                embed_model_base_url=params["embed_model_base_url"],
                embed_model_api_key=params["embed_model_api_key"],
                embed_model_name=params["embed_model_name"],
                metadata=params["metadata"],
            )
            logger.info(f"自定义内容摄取成功 - 分块数: {len(chunked_docs)}")
            return {"status": "success", "message": "", "chunks_size": len(chunked_docs)}
        else:
            # 预览模式使用统一流水线
            return self._process_documents_pipeline(docs, "自定义内容", params, "自定义内容")

    def website_ingest(self, url: str, max_depth: int, params: Dict[str, Any]) -> Dict[str, Any]:
        """网站内容摄取接口

        Args:
            url: 网站URL
            max_depth: 爬取最大深度
            params: 参数字典（同custom_content_ingest）

        Returns:
            包含状态和结果信息的字典
        """
        logger.info(f"网站内容摄取开始 - URL: {url}, 最大深度: {max_depth}, 预览模式: {params['is_preview']}")

        # 加载网站内容
        loader = WebSiteLoader(url, max_depth)
        docs = loader.load()

        # 使用统一的文档处理流水线
        result = self._process_documents_pipeline(docs, url, params, "网站内容")
        logger.info(f"网站内容摄取完成 - URL: {url}, 分块数: {result.get('chunks_size', 0)}")
        return result

    def file_ingest(self, file_path: str, file_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """文件内容摄取接口

        Args:
            file_path: 文件路径（临时文件）
            file_name: 原始文件名
            params: 参数字典（同custom_content_ingest，额外包含 load_mode）

        Returns:
            包含状态和结果信息的字典
        """
        # 文件类型验证
        allowed_types = ["docx", "pptx", "ppt", "doc", "txt", "jpg", "png", "jpeg", "pdf", "csv", "xlsx", "xls", "md"]

        file_extension = file_name.split(".")[-1].lower() if "." in file_name else ""
        if file_extension not in allowed_types:
            error_msg = f"不支持的文件类型。支持的类型: {', '.join(allowed_types)}"
            logger.error(f"文件摄取失败 - {error_msg}")
            return {"status": "error", "message": error_msg}

        load_mode = params.get("load_mode", "full")
        logger.info(f"文件内容摄取开始 - 文件: {file_name}, 类型: {file_extension}, 预览模式: {params['is_preview']}")

        try:
            # 加载文件内容
            loader = self.get_file_loader(file_path, file_extension, load_mode, params)
            docs = loader.load()

            # 使用统一的文档处理流水线
            result = self._process_documents_pipeline(docs, file_name, params, "文件内容")
            logger.info(f"文件内容摄取完成 - 文件: {file_name}, 分块数: {result.get('chunks_size', 0)}")
            return result
        except Exception as e:
            logger.error(f"文件内容摄取失败 - 文件: {file_name}, 错误: {e}")
            raise

    def _process_documents_pipeline(self, docs, title: str, params: Dict[str, Any], content_type: str) -> Dict[str, Any]:
        """
        统一的文档处理流水线

        Args:
            docs: 原始文档列表
            title: 文档标题
            params: 参数字典
            content_type: 内容类型描述（用于日志）

        Returns:
            包含状态和结果信息的字典
        """
        # 处理文档元数据
        docs = self.prepare_documents_metadata(docs, is_preview=params["is_preview"], title=title, knowledge_id=params["knowledge_id"])

        # 执行文档分块并记录日志
        chunked_docs = self.perform_chunking(docs, params["chunk_mode"], params, params["is_preview"], content_type)

        # 处理预览模式
        if params["is_preview"]:
            return {"status": "success", "message": "", "documents": self.serialize_documents(chunked_docs), "chunks_size": len(chunked_docs)}

        # 执行文档存储
        logger.debug(f"开始存储{content_type}{len(chunked_docs)}个文档分块")
        self.store_documents_to_pg(
            chunked_docs=chunked_docs,
            knowledge_base_id=params["knowledge_base_id"],
            embed_model_base_url=params["embed_model_base_url"],
            embed_model_api_key=params["embed_model_api_key"],
            embed_model_name=params["embed_model_name"],
            metadata=params["metadata"],
        )

        return {"status": "success", "message": "", "chunks_size": len(chunked_docs)}
