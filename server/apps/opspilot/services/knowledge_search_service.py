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
    @classmethod
    def build_search_params(
        cls,
        knowledge_base_folder: KnowledgeBase,
        query: str,
        embed_mode_config: Dict[str, Any],
        rerank_model,
        kwargs: Dict[str, Any],
        score_threshold: float,
    ) -> Dict[str, Any]:
        """构建搜索参数

        Args:
            knowledge_base_folder: 知识库文件夹对象
            query: 搜索查询
            embed_mode_config: 嵌入模型
            rerank_model: 重排序模型
            kwargs: 搜索配置参数
            score_threshold: 分数阈值，低于此分数的结果将被过滤
        Returns:
            Dict[str, Any]: 构建好的搜索参数字典
        """
        rerank_model_address = rerank_model_api_key = rerank_model_name = ""
        if kwargs["enable_rerank"]:
            rerank_config = rerank_model.decrypted_rerank_config_config
            rerank_model_address = rerank_config["base_url"]
            rerank_model_api_key = rerank_config["api_key"] or " "
            rerank_model_name = rerank_model.rerank_config.get("model", rerank_model.name)
        params = {
            "index_name": knowledge_base_folder.knowledge_index_name(),
            "search_query": query,
            "metadata_filter": {"enabled": "true"},
            "score_threshold": score_threshold,
            "k": kwargs.get("rag_size", 50),
            "qa_size": kwargs.get("qa_size", 50),
            "search_type": kwargs["search_type"],
            "enable_rerank": kwargs["enable_rerank"],
            "embed_model_base_url": embed_mode_config["base_url"],
            "embed_model_api_key": embed_mode_config["api_key"] or " ",
            "embed_model_name": embed_mode_config["model"],
            "rerank_model_base_url": rerank_model_address,
            "rerank_model_api_key": rerank_model_api_key,
            "rerank_model_name": rerank_model_name,
            "rerank_top_k": kwargs["rerank_top_k"],
            "rag_recall_mode": kwargs.get("rag_recall_mode", "chunk"),
            "enable_naive_rag": kwargs["enable_naive_rag"],
            "enable_graph_rag": False,
            "enable_qa_rag": kwargs["enable_qa_rag"],
            "graph_rag_request": {},
        }

        return params

    @staticmethod
    def set_graph_rag_request(knowledge_base_folder, kwargs, query):
        graph_rag_request = {}
        if kwargs["enable_graph_rag"]:
            graph_obj = KnowledgeGraph.objects.filter(knowledge_base_id=knowledge_base_folder.id).first()
            if not graph_obj:
                return {}
            embed_config = graph_obj.embed_model.decrypted_embed_config
            rerank_config = graph_obj.rerank_model.decrypted_rerank_config_config
            graph_rag_request = {
                "embed_model_base_url": embed_config["base_url"],
                "embed_model_api_key": embed_config["api_key"] or " ",
                "embed_model_name": embed_config.get("model", graph_obj.embed_model.name),
                "rerank_model_base_url": rerank_config["base_url"],
                "rerank_model_name": rerank_config.get("model", graph_obj.rerank_model.name),
                "rerank_model_api_key": rerank_config["api_key"] or " ",
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
        embed_mode_config = embed_mode.decrypted_embed_config
        if "model" not in embed_mode_config:
            embed_mode_config["model"] = embed_mode.name

        # 获取重排序模型地址
        rerank_model_address = rerank_model_api_key = rerank_model_name = ""
        if kwargs["enable_rerank"]:
            rerank_model = RerankProvider.objects.get(id=kwargs["rerank_model"])
            rerank_config = rerank_model.decrypted_rerank_config_config
            rerank_model_address = rerank_config["base_url"]
            rerank_model_api_key = rerank_config["api_key"] or " "
            rerank_model_name = rerank_config.get("model", rerank_model.name)

        # 构建搜索请求
        request = DocumentRetrieverRequest(
            index_name=knowledge_base_folder.knowledge_index_name(),
            search_query=query,
            metadata_filter={"enabled": "true"},
            k=kwargs.get("rag_size", 50),
            qa_size=kwargs.get("qa_size", 50),
            search_type=kwargs["search_type"],
            score_threshold=score_threshold if score_threshold > 0 else 0.7,
            embed_model_base_url=embed_mode_config["base_url"],
            embed_model_api_key=embed_mode_config["api_key"] or " ",
            embed_model_name=embed_mode_config["model"],
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
        except Exception as e:
            logger.exception(e)

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
        except Exception as e:
            logger.exception(e)
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
        except Exception as e:
            logger.exception(e)
