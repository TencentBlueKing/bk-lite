from typing import Any, Dict, List

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag
from apps.opspilot.metis.llm.rag.naive_rag_entity import (
    DocumentDeleteRequest,
    DocumentMetadataUpdateRequest,
    DocumentRetrieverRequest,
    IndexDeleteRequest,
)
from apps.opspilot.models import EmbedProvider, KnowledgeBase, KnowledgeGraph, RerankProvider


class KnowledgeSearchService:
    @staticmethod
    def set_graph_rag_request(knowledge_base_folder, kwargs, query):
        graph_rag_request = {}
        if kwargs["enable_graph_rag"]:
            graph_obj = KnowledgeGraph.objects.filter(knowledge_base_id=knowledge_base_folder.id).first()
            if not graph_obj:
                return {}
            graph_rag_request = {
                "embed_model_base_url": graph_obj.embed_model.base_url,
                "embed_model_api_key": graph_obj.embed_model.api_key or " ",
                "embed_model_name": graph_obj.embed_model.model_name,
                "rerank_model_base_url": graph_obj.rerank_model.base_url,
                "rerank_model_name": graph_obj.rerank_model.model_name,
                "rerank_model_api_key": graph_obj.rerank_model.api_key or " ",
                "size": knowledge_base_folder.graph_size,
                "group_ids": ["graph-{}".format(graph_obj.id)],
                "search_query": query,
            }
        return graph_rag_request

    @classmethod
    def search(
        cls,
        knowledge_base_folder: KnowledgeBase,
        query: str,
        kwargs: Dict[str, Any],
        score_threshold: float = 0,
        is_qa=False,
    ) -> List[Dict[str, Any]]:
        """执行知识库搜索

        Args:
            knowledge_base_folder: 知识库文件夹对象
            query: 搜索查询语句
            kwargs: 搜索配置参数
            score_threshold: 分数阈值，低于此分数的结果将被过滤
            is_qa: 是否为问答模式
        """
        docs = []
        rag_client = PgvectorRag()

        # 获取嵌入模型地址
        embed_mode = EmbedProvider.objects.get(id=kwargs["embed_model"])

        # 获取重排序模型地址
        rerank_model_address = rerank_model_api_key = rerank_model_name = ""
        if kwargs["enable_rerank"]:
            rerank_model = RerankProvider.objects.get(id=kwargs["rerank_model"])
            rerank_model_address = rerank_model.base_url
            rerank_model_api_key = rerank_model.api_key or " "
            rerank_model_name = rerank_model.model_name

        # 构建搜索请求
        request = DocumentRetrieverRequest(
            index_name=knowledge_base_folder.knowledge_index_name(),
            search_query=query,
            metadata_filter={"enabled": "true"},
            k=kwargs.get("rag_size", 50),
            qa_size=kwargs.get("qa_size", 50),
            search_type=kwargs["search_type"],
            score_threshold=score_threshold if score_threshold > 0 else 0.7,
            embed_model_base_url=embed_mode.base_url,
            embed_model_api_key=embed_mode.api_key or " ",
            embed_model_name=embed_mode.model_name,
            enable_rerank=kwargs["enable_rerank"],
            rerank_model_base_url=rerank_model_address,
            rerank_model_api_key=rerank_model_api_key,
            rerank_model_name=rerank_model_name,
            rerank_top_k=kwargs["rerank_top_k"],
            rag_recall_mode=kwargs.get("rag_recall_mode", "chunk"),
            enable_naive_rag=kwargs["enable_naive_rag"] and not is_qa,
            enable_qa_rag=kwargs["enable_qa_rag"] and is_qa,
        )

        # 执行搜索
        try:
            results = rag_client.search(request)
        except Exception as e:
            logger.exception(f"搜索失败: {e}")
            return []

        # 处理搜索结果
        for doc in results:
            meta_data = doc.metadata
            score = meta_data.get("similarity_score", 0)
            doc_info = {}

            if kwargs["enable_rerank"]:
                doc_info["rerank_score"] = meta_data.get("relevance_score", 0)

            if is_qa:
                doc_info.update(
                    {
                        "question": meta_data.get("qa_question", ""),
                        "answer": meta_data.get("qa_answer", ""),
                        "score": score,
                        "knowledge_id": meta_data.get("knowledge_id", ""),
                        "knowledge_title": meta_data.get("knowledge_title", ""),
                    }
                )
            else:
                doc_info.update(
                    {
                        "content": doc.page_content,
                        "score": score,
                        "knowledge_id": meta_data.get("knowledge_id", ""),
                        "knowledge_title": meta_data.get("knowledge_title", ""),
                    }
                )
            docs.append(doc_info)

        # 按分数降序排序
        docs.sort(key=lambda x: x["score"], reverse=True)
        return docs

    @staticmethod
    def change_chunk_enable(index_name, chunk_id, enabled):
        """修改 chunk 启用状态

        Args:
            index_name: 索引名称
            chunk_id: chunk ID
            enabled: 是否启用
        """
        rag_client = PgvectorRag()
        request = DocumentMetadataUpdateRequest(
            knowledge_ids=[],
            chunk_ids=[str(chunk_id)],
            metadata={"enabled": "true" if enabled else "false"},
        )
        try:
            rag_client.update_metadata(request)
        except Exception:
            logger.exception("Failed to update ES metadata: index_name=%s, chunk_id=%s", index_name, chunk_id)

    @staticmethod
    def delete_es_content(index_name, doc_id, doc_name="", is_chunk=False, keep_qa=False):
        """删除 ES 内容

        Args:
            index_name: 索引名称
            doc_id: 文档ID
            doc_name: 文档名称
            is_chunk: 是否为 chunk
            keep_qa: 是否保留问答对
        """
        rag_client = PgvectorRag()
        if isinstance(doc_id, str) or isinstance(doc_id, int):
            doc_ids = [str(doc_id)]
        else:
            doc_ids = [str(i) for i in doc_id]
        request = DocumentDeleteRequest(
            chunk_ids=doc_ids if is_chunk else [],
            knowledge_ids=doc_ids if not is_chunk else [],
            keep_qa=keep_qa,
        )
        try:
            rag_client.delete_document(request)
            if doc_name:
                logger.info("Document {} successfully deleted.".format(doc_name))
        except Exception:
            logger.exception("Failed to delete ES content: index_name=%s, doc_ids=%s", index_name, doc_ids)
            if doc_name:
                logger.info("Document {} not found, skipping deletion.".format(doc_name))

    @staticmethod
    def delete_es_index(index_name):
        """删除 ES 索引

        Args:
            index_name: 索引名称
        """
        rag_client = PgvectorRag()
        request = IndexDeleteRequest(index_name=index_name)
        try:
            rag_client.delete_index(request)
            logger.info("Index {} successfully deleted.".format(index_name))
        except Exception:
            logger.exception("Failed to delete ES index: index_name=%s", index_name)
