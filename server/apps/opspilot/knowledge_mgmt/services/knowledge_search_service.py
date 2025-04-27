from typing import Any, Dict, List

from django.conf import settings

from apps.core.logger import logger
from apps.opspilot.knowledge_mgmt.models import KnowledgeBase
from apps.opspilot.models import EmbedProvider, RerankProvider
from apps.opspilot.utils.chat_server_helper import ChatServerHelper


class KnowledgeSearchService:
    @staticmethod
    def _build_search_params(
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
            embed_model_address: 嵌入模型地址
            rerank_model_address: 重排序模型地址
            kwargs: 搜索配置参数

        Returns:
            Dict[str, Any]: 构建好的搜索参数字典
        """
        rerank_model_address = rerank_model_api_key = rerank_model_name = ""
        if kwargs["enable_rerank"]:
            rerank_model_address = rerank_model.rerank_config["base_url"]
            rerank_model_api_key = rerank_model.rerank_config["api_key"]
            rerank_model_name = rerank_model.rerank_config.get("model", rerank_model.name)
        params = {
            "index_name": knowledge_base_folder.knowledge_index_name(),
            "search_query": query,
            "metadata_filter": {"enabled": True},
            "size": knowledge_base_folder.result_count,
            "threshold": score_threshold,
            "enable_term_search": kwargs["enable_text_search"],
            "text_search_weight": kwargs["text_search_weight"],
            "text_search_mode": kwargs["text_search_mode"],
            "enable_vector_search": kwargs["enable_vector_search"],
            "vector_search_weight": kwargs["vector_search_weight"],
            "rag_k": kwargs["rag_k"],
            "rag_num_candidates": kwargs["rag_num_candidates"],
            "enable_rerank": kwargs["enable_rerank"],
            "embed_model_base_url": embed_mode_config["base_url"],
            "embed_model_api_key": embed_mode_config["api_key"],
            "embed_model_name": embed_mode_config["model"],
            "rerank_model_base_url": rerank_model_address,
            "rerank_model_api_key": rerank_model_api_key,
            "rerank_model_name": rerank_model_name,
            "rerank_top_k": kwargs["rerank_top_k"],
        }
        return params

    @classmethod
    def search(
        cls, knowledge_base_folder: KnowledgeBase, query: str, kwargs: Dict[str, Any], score_threshold: float = 0
    ) -> List[Dict[str, Any]]:
        """执行知识库搜索

        Args:
            knowledge_base_folder: 知识库文件夹对象
            query: 搜索查询语句
            kwargs: 搜索配置参数
            score_threshold: 分数阈值，低于此分数的结果将被过滤

        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        docs = []
        # 获取嵌入模型地址
        embed_mode = EmbedProvider.objects.get(id=kwargs["embed_model"])
        embed_mode_config = embed_mode.embed_config

        # 获取重排序模型地址
        rerank_model = None
        if kwargs["enable_rerank"]:
            rerank_model = RerankProvider.objects.get(id=kwargs["rerank_model"])
        if "model" not in embed_mode_config:
            embed_mode_config["model"] = embed_mode.name
        # 构建搜索参数
        params = cls._build_search_params(
            knowledge_base_folder, query, embed_mode_config, rerank_model, kwargs, score_threshold
        )

        url = f"{settings.METIS_SERVER_URL}/api/rag/naive_rag_test"
        result = ChatServerHelper.post_chat_server(params, url)

        # 处理搜索结果
        for doc in result["documents"]:
            score = doc["metadata"]["_score"]
            doc_info = {
                "content": doc["page_content"],
                "score": score,
                "knowledge_id": doc["metadata"]["_source"]["metadata"]["knowledge_id"],
                "knowledge_title": doc["metadata"]["_source"]["metadata"]["knowledge_title"],
            }

            if kwargs["enable_rerank"]:
                doc_info["rerank_score"] = doc["metadata"]["relevance_score"]

            docs.append(doc_info)

        # 按分数降序排序
        docs.sort(key=lambda x: x["score"], reverse=True)
        return docs

    @staticmethod
    def change_chunk_enable(index_name, chunk_id, enabled):
        url = f"{settings.METIS_SERVER_URL}/api/rag/update_rag_document_metadata"
        kwargs = {
            "index_name": index_name,
            "metadata_filter": {"chunk_id": str(chunk_id)},
            "metadata": {"enabled": enabled},
        }
        ChatServerHelper.post_chat_server(kwargs, url)

    @staticmethod
    def delete_es_content(index_name, doc_id, doc_name="", is_chunk=False):
        url = f"{settings.METIS_SERVER_URL}/api/rag/delete_doc"
        key = "knowledge_id" if not is_chunk else "chunk_id"
        kwargs = {"index_name": index_name, "metadata_filter": {key: str(doc_id)}}
        try:
            ChatServerHelper.post_chat_server(kwargs, url)
            if doc_name:
                logger.info("Document {} successfully deleted.".format(doc_name))
        except Exception as e:
            logger.exception(e)
            if doc_name:
                logger.info("Document {} not found, skipping deletion.".format(doc_name))

    @staticmethod
    def delete_es_index(index_name):
        url = f"{settings.METIS_SERVER_URL}/api/rag/delete_index"
        kwargs = {"index_name": index_name}
        try:
            ChatServerHelper.post_chat_server(kwargs, url)
            logger.info("Index {} successfully deleted.".format(index_name))
        except Exception as e:
            logger.exception(e)
