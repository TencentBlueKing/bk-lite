import base64
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from django.conf import settings
from django.utils.translation import gettext as _

from apps.core.logger import logger
from apps.opspilot.enum import SkillTypeChoices
from apps.opspilot.knowledge_mgmt.services.knowledge_search_service import KnowledgeSearchService
from apps.opspilot.models import (
    KnowledgeBase,
    KnowledgeDocument,
    LLMModel,
    SkillTools,
    TeamTokenUseInfo,
    TokenConsumption,
)
from apps.opspilot.quota_rule_mgmt.quota_utils import QuotaUtils
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

        # 记录token消耗
        if "bot_id" in kwargs:
            TokenConsumption.objects.create(
                bot_id=kwargs["bot_id"],
                input_tokens=data["prompt_tokens"],
                output_tokens=data["completion_tokens"],
                username=kwargs["username"],
                user_id=kwargs["user_id"],
            )

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
                    text_message = item["text"]

        return text_message, image_data

    def _process_chat_history(self, chat_history: List[Dict[str, Any]], window_size: int) -> List[Dict[str, Any]]:
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

        for user_msg in chat_history[num:]:
            if user_msg["event"] == "user" and isinstance(user_msg["message"], list):
                image_list = []
                msg = ""
                for item in user_msg["message"]:
                    if item["type"] == "image_url":
                        image_url = item.get("image_url", {}).get("url") or item.get("url")
                        if image_url:
                            image_list.append(image_url)
                    else:
                        msg = item["message"]
                processed_history.append({"event": "user", "message": msg, "image_data": image_list})
            else:
                txt = user_msg["message"]
                if isinstance(txt, list):
                    txt = "\n".join([i["message"] for i in txt])
                processed_history.append({"event": user_msg["event"], "message": txt})

        return processed_history

    def format_stream_chat_params(self, kwargs: Dict[str, Any]) -> Tuple[Dict, Dict, TeamTokenUseInfo, Dict]:
        """
        格式化流式聊天所需的参数

        Args:
            kwargs: 包含聊天所需参数的字典

        Returns:
            文档映射、标题映射、团队令牌使用信息和聊天参数
        """
        llm_model = LLMModel.objects.get(id=kwargs["llm_model"])
        self.validate_remaining_token(llm_model)
        # 处理用户消息和图片
        chat_kwargs, doc_map, title_map = self.format_chat_server_kwargs(kwargs, llm_model)
        # 获取或创建团队令牌使用信息
        group = llm_model.consumer_team or llm_model.team[0]
        team_info, _ = TeamTokenUseInfo.objects.get_or_create(
            group=group, llm_model=llm_model.name, defaults={"used_token": 0}
        )

        return doc_map, title_map, team_info, chat_kwargs

    @staticmethod
    def validate_remaining_token(llm_model):
        try:
            current_team = llm_model.consumer_team
            if not current_team:
                current_team = llm_model.team[0] if llm_model.team else ""
            remaining_token = QuotaUtils.get_remaining_token(current_team, llm_model.name)
        except Exception as e:
            logger.exception(e)
            remaining_token = 1
        if remaining_token <= 0:
            raise Exception(_("Token used up"))

    def format_chat_server_kwargs(self, kwargs, llm_model):
        title_map = doc_map = {}
        naive_rag_request = []
        # 如果启用RAG，搜索文档
        if kwargs["enable_rag"]:
            naive_rag_request, doc_map = self.format_naive_rag_kwargs(kwargs)

        user_message, image_data = self._process_user_message_and_images(kwargs["user_message"])
        # 处理聊天历史
        chat_history = self._process_chat_history(kwargs["chat_history"], kwargs["conversation_window_size"])
        tools = SkillTools.objects.filter(name__in=kwargs.get("tools", [])).values_list("params", flat=True)
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
        }
        if kwargs.get("thread_id"):
            chat_kwargs["thread_id"] = str(kwargs["thread_id"])
        if kwargs["skill_type"] == SkillTypeChoices.BASIC_TOOL:
            chat_kwargs.update({"tools_servers": list(tools)})
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
        self.validate_remaining_token(llm_model)
        show_think = kwargs.pop("show_think", True)
        # 处理用户消息和图片
        chat_kwargs, doc_map, title_map = self.format_chat_server_kwargs(kwargs, llm_model)

        # 调用聊天服务
        url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_chatbot_workflow"
        if kwargs["skill_type"] == SkillTypeChoices.BASIC_TOOL:
            url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_react_agent"
        result = ChatServerHelper.post_chat_server(chat_kwargs, url)
        data = result["message"]

        # 更新团队令牌使用信息
        group = llm_model.consumer_team or llm_model.team[0]
        used_token = result["prompt_tokens"] + result["completion_tokens"]
        team_info, is_created = TeamTokenUseInfo.objects.get_or_create(
            group=group, llm_model=llm_model.name, defaults={"used_token": used_token}
        )
        if not is_created:
            team_info.used_token += used_token
            team_info.save()

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

    @staticmethod
    def format_naive_rag_kwargs(kwargs: Dict[str, Any]) -> Tuple[List, Dict]:
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
            KnowledgeDocument.objects.filter(knowledge_base_id__in=base_ids).values(
                "id", "knowledge_source_type", "name", "knowledge_base_id"
            )
        )
        doc_map = {i["id"]: i for i in doc_list}

        # 为每个知识库搜索相关文档
        for knowledge_base in knowledge_base_list:
            embed_model_base_url = knowledge_base.embed_model.embed_config["base_url"]
            embed_model_api_key = knowledge_base.embed_model.embed_config["api_key"]
            rerank_model_base_url = rerank_model_api_key = rerank_model_name = ""
            if knowledge_base.rerank_model:
                rerank_model_base_url = knowledge_base.rerank_model.rerank_config["base_url"]
                rerank_model_api_key = knowledge_base.rerank_model.rerank_config["api_key"]
                rerank_model_name = knowledge_base.rerank_model.name
            score_threshold = score_threshold_map.get(knowledge_base.id, 0.7)
            kwargs = {
                "index_name": knowledge_base.knowledge_index_name(),
                "metadata_filter": {"enabled": True},
                "size": knowledge_base.result_count,
                "threshold": score_threshold,
                "enable_term_search": knowledge_base.enable_text_search,  # TODO 确认是否这个参数
                "text_search_weight": knowledge_base.text_search_weight,
                "text_search_mode": knowledge_base.text_search_mode,
                "enable_vector_search": knowledge_base.enable_vector_search,
                "vector_search_weight": knowledge_base.vector_search_weight,
                "rag_k": knowledge_base.rag_k,
                "rag_num_candidates": knowledge_base.rag_num_candidates,
                "enable_rerank": knowledge_base.enable_rerank,
                "embed_model_base_url": embed_model_base_url,
                "embed_model_api_key": embed_model_api_key,
                "embed_model_name": knowledge_base.embed_model.name,
                "rerank_model_base_url": rerank_model_base_url,
                "rerank_model_api_key": rerank_model_api_key,
                "rerank_model_name": rerank_model_name,
                "rerank_top_k": knowledge_base.rerank_top_k,
            }
            naive_rag_request.append(kwargs)

        return naive_rag_request, doc_map


# 创建服务实例
llm_service = LLMService()
