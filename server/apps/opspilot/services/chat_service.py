import asyncio
import re
from typing import Any, Dict, Tuple

from apps.core.logger import opspilot_logger
from apps.core.mixinx import EncryptMixin
from apps.core.utils.loader import LanguageLoader
from apps.opspilot.enum import SkillTypeChoices
from apps.opspilot.models import LLMModel, SkillTools
from apps.opspilot.services.history_service import history_service
from apps.opspilot.services.rag_service import rag_service
from apps.opspilot.utils.agent_factory import create_agent_instance


class ChatService:
    """处理聊天核心功能的服务"""

    @staticmethod
    def chat(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理聊天请求，并返回带引用知识的回复内容

        Args:
            kwargs: 包含聊天所需参数的字典

        Returns:
            包含回复内容和引用知识的字典
        """
        citing_knowledge = []
        data, doc_map, title_map = ChatService.invoke_chat(kwargs)

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
    def invoke_chat(kwargs: Dict[str, Any]) -> Tuple[Dict, Dict, Dict]:
        """
        调用聊天服务并处理结果

        Args:
            kwargs: 包含聊天所需参数的字典

        Returns:
            处理后的数据、文档映射和标题映射
        """
        llm_model = LLMModel.objects.get(id=kwargs["llm_model"])
        show_think = kwargs.pop("show_think", True)
        skill_type = kwargs.get("skill_type")
        kwargs.pop("group", 0)

        # 处理用户消息和图片
        chat_kwargs, doc_map, title_map = ChatService.format_chat_server_kwargs(kwargs, llm_model)

        # 创建 agent 实例并直接执行
        graph, request = create_agent_instance(skill_type, chat_kwargs)

        try:
            # 调用 agent 的 execute 方法（非流式同步执行）
            response = asyncio.run(graph.execute(request))

            # 构建返回结果
            result = {
                "message": response.message,
                "total_tokens": response.total_tokens,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "thread_id": response.thread_id,
            }

            # 处理内容（可选隐藏思考过程）
            if not show_think:
                content = re.sub(r"<think>.*?</think>", "", result["message"], flags=re.DOTALL).strip()
                result["message"] = content

            return result, doc_map, title_map

        except Exception as e:
            # 记录详细的异常信息以便排查问题
            opspilot_logger.error(f"invoke_chat 执行失败: skill_type={skill_type}, error={str(e)}", exc_info=True)

            loader = LanguageLoader(app="opspilot", default_lang="en")
            message = loader.get("error.agent_execution_failed") or f"Agent execution failed: {str(e)}"
            return {"message": message}, doc_map, title_map

    @staticmethod
    def format_chat_server_kwargs(kwargs, llm_model):
        """
        格式化聊天服务器请求参数

        Args:
            kwargs: 包含聊天所需参数的字典
            llm_model: LLM模型对象

        Returns:
            chat_kwargs字典、doc_map字典、title_map字典
        """
        title_map = doc_map = {}
        naive_rag_request = []
        extra_config = {}

        # 如果启用RAG，搜索文档
        if kwargs["enable_rag"]:
            naive_rag_request, km_request, doc_map = rag_service.format_naive_rag_kwargs(kwargs)
            extra_config.update(km_request)

        user_message, image_data = history_service.process_user_message_and_images(kwargs["user_message"])

        # 处理聊天历史
        chat_history = history_service.process_chat_history(kwargs["chat_history"], kwargs.get("conversation_window_size", 10))

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

            # 查询工具对象，需要判断是否为内置工具
            skill_tools_queryset = SkillTools.objects.filter(id__in=list(tool_map.keys()))
            tools = []

            for skill_tool in skill_tools_queryset:
                tool_params = skill_tool.params.copy()
                # 移除 kwargs 字段
                tool_params.pop("kwargs", None)

                # 如果是内置工具，添加 langchain 前缀的 URL
                if skill_tool.is_build_in:
                    tool_params["url"] = f"langchain:{skill_tool.name}"

                tools.append(tool_params)

            for i in tool_map.values():
                extra_config.update(i)
            chat_kwargs.update({"tools_servers": tools})
            chat_kwargs.update({"extra_config": extra_config})
        elif extra_config:
            chat_kwargs.update({"extra_config": extra_config})

        return chat_kwargs, doc_map, title_map


# 创建服务实例
chat_service = ChatService()
