import base64
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from django.conf import settings

from apps.core.logger import opspilot_logger as logger
from apps.core.mixinx import EncryptMixin
from apps.core.utils.loader import LanguageLoader
from apps.opspilot.enum import SkillTypeChoices
from apps.opspilot.models import KnowledgeBase, KnowledgeDocument, LLMModel, SkillTools
from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService
from apps.opspilot.utils.chat_server_helper import ChatServerHelper


class LLMService:
    """服务类，用于处理与LLM模型交互的逻辑，包括聊天、知识检索等功能"""

    def __init__(self):
        self.knowledge_search_service = KnowledgeSearchService()

    def chat(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理聊天请求，并返回带引用知识的回复内容

        Args:
            kwargs: 包含聊天所需参数的字典

        Returns:
            包含回复内容和引用知识的字典
        """
        citing_knowledge = []
        data, doc_map, title_map = self.invoke_chat(kwargs)
        # 如果启用了知识源引用，构建引用信息
        if kwargs["enable_rag_knowledge_source"]:
            citing_knowledge = [
                {
                    "knowledge_title": doc_map.get(k, {}).get("name"),
                    "knowledge_id": k,
                    "knowledge_base_id": doc_map.get(k, {}).get("knowledge_base_id"),
                    "result": v,
                    "knowledge_source_type": doc_map.get(k, {}).get("knowledge_source_type"),
                    "citing_num": len(v),
                }
                for k, v in title_map.items()
            ]

        return {"content": data["message"], "citing_knowledge": citing_knowledge}

    @staticmethod
    def _process_user_message_and_images(user_message: Union[str, List[Dict[str, Any]]]) -> Tuple[str, List[str]]:
        """
        处理用户消息和图片数据

        Args:
            user_message: 用户消息，可能是字符串或包含文本和图片的列表

        Returns:
            处理后的文本消息和图片URL列表
        """
        image_data = []
        text_message = user_message

        if isinstance(user_message, list):
            for item in user_message:
                if item["type"] == "image_url":
                    image_url = item.get("image_url", {}).get("url") or item.get("url")
                    if image_url:
                        image_data.append(image_url)
                else:
                    text_message = item.get("message", item.get("text", ""))

        return text_message, image_data

    @staticmethod
    def process_chat_history(chat_history: List[Dict[str, Any]], window_size: int) -> List[Dict[str, Any]]:
        """
        处理聊天历史，处理窗口大小和图片数据

        Args:
            chat_history: 原始聊天历史
            window_size: 对话窗口大小

        Returns:
            处理后的聊天历史
        """
        num = window_size * -1
        processed_history = []
        role_map = {"assistant": "bot"}
        for user_msg in chat_history[num:]:
            message = user_msg.get("message", user_msg.get("text", ""))
            if user_msg["event"] == "user" and isinstance(message, list):
                image_list = []
                msg = ""
                for item in user_msg["message"]:
                    if item["type"] == "image_url":
                        image_url = item.get("image_url", {}).get("url") or item.get("url")
                        if image_url:
                            image_list.append(image_url)
                    else:
                        msg = item.get("text", "") or item.get("message", "")
                processed_history.append({"event": "user", "message": msg, "image_data": image_list})
            else:
                txt = user_msg.get("message", user_msg.get("text", ""))
                if isinstance(txt, list):
                    txt = "\n".join([i.get("message", i.get("text")) for i in txt])
                processed_history.append(
                    {
                        "event": role_map.get(user_msg["event"], user_msg["event"]),
                        "message": txt,
                    }
                )

        return processed_history

    def format_chat_server_kwargs(self, kwargs, llm_model):
        title_map = doc_map = {}
        naive_rag_request = []
        # 如果启用RAG，搜索文档
        extra_config = {}
        if kwargs["enable_rag"]:
            naive_rag_request, km_request, doc_map = self.format_naive_rag_kwargs(kwargs)
            extra_config.update(km_request)
        user_message, image_data = self._process_user_message_and_images(kwargs["user_message"])
        # 处理聊天历史
        chat_history = self.process_chat_history(kwargs["chat_history"], kwargs.get("conversation_window_size", 10))
        # 构建聊天参数
        chat_kwargs = {
            "openai_api_base": llm_model.decrypted_llm_config["openai_base_url"],
            "openai_api_key": llm_model.decrypted_llm_config["openai_api_key"],
            "model": llm_model.decrypted_llm_config["model"],
            "system_message_prompt": kwargs["skill_prompt"],
            "temperature": kwargs["temperature"],
            "user_message": user_message,
            "chat_history": chat_history,
            "image_data": image_data,
            "user_id": str(kwargs["user_id"]),
            "enable_naive_rag": kwargs["enable_rag"],
            "rag_stage": "string",
            "naive_rag_request": naive_rag_request,
            "enable_suggest": kwargs.get("enable_suggest", False),
            "enable_query_rewrite": kwargs.get("enable_query_rewrite", False),
        }
        if kwargs.get("thread_id"):
            chat_kwargs["thread_id"] = str(kwargs["thread_id"])
        if kwargs["enable_rag_knowledge_source"]:
            extra_config.update({"enable_rag_source": True})
        if kwargs.get("enable_rag_strict_mode"):
            extra_config.update({"enable_rag_strict_mode": kwargs["enable_rag_strict_mode"]})
        if kwargs["skill_type"] != SkillTypeChoices.KNOWLEDGE_TOOL:
            for tool in kwargs.get("tools", []):
                for i in tool.get("kwargs", []):
                    if i["type"] == "password":
                        EncryptMixin.decrypt_field("value", i)
            tool_map = {i["id"]: {u["key"]: u["value"] for u in i["kwargs"] if u["key"]} for i in kwargs.get("tools", [])}

            tools = list(SkillTools.objects.filter(id__in=list(tool_map.keys())).values_list("params", flat=True))
            for i in tools:
                i.pop("kwargs", None)
            for i in tool_map.values():
                extra_config.update(i)
            chat_kwargs.update({"tools_servers": tools})
            chat_kwargs.update({"extra_config": extra_config})
        elif extra_config:
            chat_kwargs.update({"extra_config": extra_config})
        return chat_kwargs, doc_map, title_map

    def invoke_chat(self, kwargs: Dict[str, Any]) -> Tuple[Dict, Dict, Dict]:
        """
        调用聊天服务并处理结果

        Args:
            kwargs: 包含聊天所需参数的字典

        Returns:
            处理后的数据、文档映射和标题映射
        """
        llm_model = LLMModel.objects.get(id=kwargs["llm_model"])
        show_think = kwargs.pop("show_think", True)
        kwargs.pop("group", 0)
        # 处理用户消息和图片
        chat_kwargs, doc_map, title_map = self.format_chat_server_kwargs(kwargs, llm_model)

        # 调用聊天服务
        url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_chatbot_workflow"
        if kwargs["skill_type"] == SkillTypeChoices.BASIC_TOOL:
            url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_react_agent"
        elif kwargs["skill_type"] == SkillTypeChoices.PLAN_EXECUTE:
            url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_plan_and_execute_agent"
        elif kwargs["skill_type"] == SkillTypeChoices.LATS:
            url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_lats_agent"
        result = ChatServerHelper.post_chat_server(chat_kwargs, url)
        if not result:
            loader = LanguageLoader(app="opspilot", default_lang="en")
            message = loader.get("error.url_request_failed") or "URL request failed"
            return {"message": message}, doc_map, title_map
        data = result["message"]

        # 更新团队令牌使用信息 (已移除TeamTokenUseInfo相关逻辑)

        # 处理内容（可选隐藏思考过程）
        if not show_think:
            content = re.sub(r"<think>.*?</think>", "", data, flags=re.DOTALL).strip()
            result["message"] = content
        return result, doc_map, title_map

    @staticmethod
    def image_to_base64(image_path: str, log_file: str = "base64.log") -> Optional[str]:
        """
        将图像文件转换为base64字符串并保存到日志文件

        Args:
            image_path: 图像文件路径
            log_file: 保存base64结果的日志文件路径

        Returns:
            图像的base64编码字符串，如果转换失败则返回None
        """
        try:
            image_path = Path(image_path)
            if not image_path.exists():
                raise FileNotFoundError(f"Image file not found: {image_path}")

            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

                # 保存到日志文件
                with open(log_file, "w") as log:
                    log.write(encoded_string)

                return encoded_string

        except Exception as e:
            logger.error(f"Error converting image to base64: {e}")
            return None

    @classmethod
    def format_naive_rag_kwargs(cls, kwargs: Dict[str, Any]) -> Tuple[List, Dict, Dict]:
        """
        搜索相关文档以提供上下文

        Args:
            kwargs: 包含搜索所需参数的字典

        Returns:
            请求参数、标题映射
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
        km_request = cls.set_km_request(knowledge_base_list, kwargs["enable_km_route"], kwargs["km_llm_model"])
        # 为每个知识库搜索相关文档
        for knowledge_base in knowledge_base_list:
            default_kwargs = cls.set_default_naive_rag_kwargs(knowledge_base, score_threshold_map)
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
            "search_type": knowledge_base.search_type,  # 0: similarity, mmr, similarity_score_threshold
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
llm_service = LLMService()
