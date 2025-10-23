from typing import Any, Dict, List

from django.conf import settings

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import EmbedProvider, KnowledgeBase, KnowledgeGraph, RerankProvider
from apps.opspilot.utils.chat_server_helper import ChatServerHelper


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
        # 获取嵌入模型地址
        embed_mode = EmbedProvider.objects.get(id=kwargs["embed_model"])
        embed_mode_config = embed_mode.decrypted_embed_config
        # 获取重排序模型地址
        rerank_model = None
        if kwargs["enable_rerank"]:
            rerank_model = RerankProvider.objects.get(id=kwargs["rerank_model"])
        if "model" not in embed_mode_config:
            embed_mode_config["model"] = embed_mode.name
        # 构建搜索参数
        params = cls.build_search_params(
            knowledge_base_folder,
            query,
            embed_mode_config,
            rerank_model,
            kwargs,
            score_threshold,
        )

        url = f"{settings.METIS_SERVER_URL}/api/rag/naive_rag_test"
        result = ChatServerHelper.post_chat_server(params, url)
        if not result:
            return []
        # 处理搜索结果
        for doc in result["documents"]:
            score = doc["metadata"].get("similarity_score", 0)
            meta_data = doc["metadata"]
            doc_info = {}
            if kwargs["enable_rerank"]:
                doc_info["rerank_score"] = doc["metadata"].get("relevance_score", 0)
            if is_qa:
                doc_info.update(
                    {
                        "question": meta_data["qa_question"],
                        "answer": meta_data["qa_answer"],
                        "score": score,
                        "knowledge_id": meta_data["knowledge_id"],
                        "knowledge_title": meta_data["knowledge_title"],
                    }
                )
                docs.append(doc_info)
            else:
                doc_info.update(
                    {
                        "content": doc["page_content"],
                        "score": score,
                        "knowledge_id": meta_data["knowledge_id"],
                        "knowledge_title": meta_data["knowledge_title"],
                    }
                )
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
            "metadata": {"enabled": "true" if enabled else "false"},
        }
        ChatServerHelper.post_chat_server(kwargs, url)

    @staticmethod
    def delete_es_content(index_name, doc_id, doc_name="", is_chunk=False, keep_qa=False):
        url = f"{settings.METIS_SERVER_URL}/api/rag/delete_doc"
        kwargs = {
            "chunk_ids": [str(doc_id)] if is_chunk else [],
            "knowledge_ids": [str(doc_id)] if not is_chunk else [],
            "keep_qa": keep_qa,
        }
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
