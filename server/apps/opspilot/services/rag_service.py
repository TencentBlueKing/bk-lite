from typing import Any, Dict, List, Tuple

from apps.opspilot.models import KnowledgeBase, KnowledgeDocument, LLMModel
from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService


class RAGService:
    """处理RAG(检索增强生成)相关的服务"""

    @staticmethod
    def format_naive_rag_kwargs(kwargs: Dict[str, Any]) -> Tuple[List, Dict, Dict]:
        """
        搜索相关文档以提供上下文

        Args:
            kwargs: 包含搜索所需参数的字典

        Returns:
            naive_rag_request列表、km_request字典、doc_map字典
        """
        naive_rag_request = []
        score_threshold_map = {i["knowledge_base"]: i["score"] for i in kwargs["rag_score_threshold"]}
        base_ids = list(score_threshold_map.keys())

        # 获取知识库和文档
        knowledge_base_list = KnowledgeBase.objects.filter(id__in=base_ids)
        doc_list = list(
            KnowledgeDocument.objects.filter(knowledge_base_id__in=base_ids).values("id", "knowledge_source_type", "name", "knowledge_base_id")
        )
        doc_map = {i["id"]: i for i in doc_list}
        km_request = RAGService.set_km_request(knowledge_base_list, kwargs["enable_km_route"], kwargs["km_llm_model"])

        # 为每个知识库搜索相关文档
        for knowledge_base in knowledge_base_list:
            default_kwargs = RAGService.set_default_naive_rag_kwargs(knowledge_base, score_threshold_map)
            if knowledge_base.enable_naive_rag:
                params = dict(
                    default_kwargs,
                    **{
                        "enable_naive_rag": True,
                        "enable_qa_rag": False,
                        "enable_graph_rag": False,
                    },
                )
                naive_rag_request.append(params)
            if knowledge_base.enable_qa_rag:
                params = dict(
                    default_kwargs,
                    **{
                        "enable_naive_rag": False,
                        "enable_qa_rag": True,
                        "enable_graph_rag": False,
                    },
                )
                naive_rag_request.append(params)
            if knowledge_base.enable_graph_rag:
                graph_rag_request = KnowledgeSearchService.set_graph_rag_request(knowledge_base, {"enable_graph_rag": 1}, "")
                params = dict(
                    default_kwargs,
                    **{
                        "size": knowledge_base.rag_size,
                        "graph_rag_request": graph_rag_request,
                        "enable_naive_rag": False,
                        "enable_qa_rag": False,
                        "enable_graph_rag": True,
                    },
                )
                naive_rag_request.append(params)
        return naive_rag_request, km_request, doc_map

    @staticmethod
    def set_km_request(knowledge_base_list, enable_km_route, km_llm_model):
        """
        设置知识管理路由请求参数

        Args:
            knowledge_base_list: 知识库列表
            enable_km_route: 是否启用知识管理路由
            km_llm_model: 知识管理LLM模型ID

        Returns:
            包含路由配置的字典
        """
        km_request = {}
        if enable_km_route:
            llm_model = LLMModel.objects.get(id=km_llm_model)
            openai_api_base = llm_model.decrypted_llm_config["openai_base_url"]
            openai_api_key = llm_model.decrypted_llm_config["openai_api_key"]
            model = llm_model.decrypted_llm_config["model"]
            km_request = {
                "km_route_llm_api_base": openai_api_base,
                "km_route_llm_api_key": openai_api_key,
                "km_route_llm_model": model,
                "km_info": [
                    {
                        "index_name": i.knowledge_index_name(),
                        "description": i.introduction,
                    }
                    for i in knowledge_base_list
                ],
            }
        return km_request

    @staticmethod
    def set_default_naive_rag_kwargs(knowledge_base, score_threshold_map):
        """
        设置默认的RAG搜索参数

        Args:
            knowledge_base: 知识库对象
            score_threshold_map: 分数阈值映射字典

        Returns:
            包含默认RAG参数的字典
        """
        embed_config = knowledge_base.embed_model.decrypted_embed_config
        embed_model_base_url = embed_config["base_url"]
        embed_model_api_key = embed_config["api_key"] or " "
        embed_model_name = embed_config.get("model", knowledge_base.embed_model.name)

        rerank_model_base_url = rerank_model_api_key = rerank_model_name = ""
        if knowledge_base.rerank_model:
            rerank_config = knowledge_base.rerank_model.decrypted_rerank_config_config
            rerank_model_base_url = rerank_config["base_url"]
            rerank_model_api_key = rerank_config["api_key"] or " "
            rerank_model_name = rerank_config.get("model", knowledge_base.rerank_model.name)

        score_threshold = score_threshold_map.get(knowledge_base.id, 0.7)
        kwargs = {
            "index_name": knowledge_base.knowledge_index_name(),
            "metadata_filter": {"enabled": "true"},
            "score_threshold": score_threshold,
            "k": knowledge_base.rag_size,
            "qa_size": knowledge_base.qa_size,
            "search_type": knowledge_base.search_type,
            "enable_rerank": knowledge_base.enable_rerank,
            "embed_model_base_url": embed_model_base_url,
            "embed_model_api_key": embed_model_api_key,
            "embed_model_name": embed_model_name,
            "rerank_model_base_url": rerank_model_base_url,
            "rerank_model_api_key": rerank_model_api_key,
            "rerank_model_name": rerank_model_name,
            "rerank_top_k": knowledge_base.rerank_top_k,
            "rag_recall_mode": knowledge_base.rag_recall_mode,
            "graph_rag_request": {},
        }
        return kwargs


# 创建服务实例
rag_service = RAGService()
