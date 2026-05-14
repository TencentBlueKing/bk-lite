import asyncio
import re
import uuid
from typing import Any, Dict, Tuple

from apps.core.logger import opspilot_logger as logger
from apps.core.mixinx import EncryptMixin
from apps.core.utils.loader import LanguageLoader
from apps.opspilot.enum import SkillTypeChoices
from apps.opspilot.models import LLMModel, SkillTools
from apps.opspilot.services.builtin_tools import (
    BUILTIN_MSSQL_TOOL_NAME,
    BUILTIN_MYSQL_TOOL_NAME,
    BUILTIN_ORACLE_TOOL_NAME,
    BUILTIN_REDIS_TOOL_NAME,
    build_builtin_mssql_runtime_tool,
    build_builtin_mysql_runtime_tool,
    build_builtin_oracle_runtime_tool,
    build_builtin_redis_runtime_tool,
)
from apps.opspilot.services.history_service import history_service
from apps.opspilot.services.rag_service import rag_service
from apps.opspilot.utils.agent_factory import create_agent_instance
from apps.opspilot.utils.prompt_utils import resolve_skill_params


def _is_eventlet_environment() -> bool:
    """检测当前进程是否运行在 eventlet monkey patch 环境中。"""
    try:
        import eventlet.patcher

        return bool(eventlet.patcher.is_monkey_patched("socket"))
    except Exception:
        return False


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

        try:
            # 创建 agent 实例并直接执行
            graph, request = create_agent_instance(skill_type, chat_kwargs)

            if _is_eventlet_environment():
                raise RuntimeError("当前 Celery worker 使用 eventlet 池，不支持在任务中执行 asyncio.run(graph.execute(...))，请改用 --pool threads 或 solo")

            # 调用 agent 的 execute 方法（非流式同步执行）
            response = asyncio.run(graph.execute(request))

            # 构建返回结果
            result = {
                "message": response.message,
                "success": True,
                "total_tokens": response.total_tokens,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "browser_steps": response.browser_steps,
            }

            # 处理内容（可选隐藏思考过程）
            if not show_think:
                content = re.sub(r"<think>.*?</think>", "", result["message"], flags=re.DOTALL).strip()
                result["message"] = content

            return result, doc_map, title_map

        except Exception as e:
            # 记录详细的异常信息以便排查问题
            logger.exception(f"invoke_chat 执行失败: skill_type={skill_type}, error={str(e)}")

            loader = LanguageLoader(app="opspilot", default_lang="en")
            message = loader.get("error.agent_execution_failed") or f"Agent execution failed: {str(e)}"
            return (
                {
                    "message": message,
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "browser_steps": [],
                },
                doc_map,
                title_map,
            )

    @staticmethod
    def _process_tools_and_extra_config(kwargs, chat_kwargs, extra_config):  # noqa: C901
        """处理工具配置和 extra_config 构建"""
        selected_tools = kwargs.get("tools", [])
        selected_builtin_kwargs = {}
        builtin_tool_names = {
            BUILTIN_REDIS_TOOL_NAME: None,
            BUILTIN_MYSQL_TOOL_NAME: None,
            BUILTIN_ORACLE_TOOL_NAME: None,
            BUILTIN_MSSQL_TOOL_NAME: None,
        }
        builtin_builders = {
            BUILTIN_REDIS_TOOL_NAME: build_builtin_redis_runtime_tool,
            BUILTIN_MYSQL_TOOL_NAME: build_builtin_mysql_runtime_tool,
            BUILTIN_ORACLE_TOOL_NAME: build_builtin_oracle_runtime_tool,
            BUILTIN_MSSQL_TOOL_NAME: build_builtin_mssql_runtime_tool,
        }

        for tool in selected_tools:
            for i in tool.get("kwargs", []):
                if i.get("type") == "password":
                    EncryptMixin.decrypt_field("value", i)
            if tool.get("name") in builtin_tool_names:
                selected_builtin_kwargs[tool["name"]] = {u["key"]: u["value"] for u in tool.get("kwargs", []) if u.get("key")}

        tool_map = {i["id"]: {u["key"]: u["value"] for u in i["kwargs"] if u.get("key")} for i in selected_tools if "id" in i}

        skill_tools_queryset = SkillTools.objects.filter(id__in=list(tool_map.keys()))
        tools = []
        loaded_tool_names = set()

        for skill_tool in skill_tools_queryset:
            loaded_tool_names.add(skill_tool.name)
            tool_params = skill_tool.params.copy()
            tool_params.pop("kwargs", None)

            is_builtin = skill_tool.is_build_in or skill_tool.name in builtin_tool_names
            if is_builtin:
                tool_params["url"] = f"langchain:{skill_tool.name}"
                tool_kwargs_for_builtin = tool_map.get(skill_tool.id, {})
                builder = builtin_builders.get(skill_tool.name)
                if builder:
                    tool_params["extra_tools_prompt"] = builder(tool_kwargs_for_builtin)["extra_tools_prompt"]
            tools.append(tool_params)

        for name, builder in builtin_builders.items():
            if name in selected_builtin_kwargs and name not in loaded_tool_names:
                tools.append(builder(selected_builtin_kwargs[name]))

        for i in tool_map.values():
            extra_config.update(i)
        extra_config.update({"execution_id": chat_kwargs["execution_id"]})
        if kwargs.get("node_id"):
            extra_config["node_id"] = kwargs["node_id"]
        if kwargs.get("trigger_type"):
            extra_config["trigger_type"] = kwargs["trigger_type"]
        chat_kwargs.update({"tools_servers": tools})
        chat_kwargs.update({"extra_config": extra_config})

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
        show_think = kwargs.get("show_think", True)
        title_map = doc_map = {}
        naive_rag_request = []
        extra_config = {"show_think": show_think}

        # 如果启用RAG，搜索文档
        if kwargs["enable_rag"]:
            naive_rag_request, km_request, doc_map = rag_service.format_naive_rag_kwargs(kwargs)
            extra_config.update(km_request)

        user_message, image_data = history_service.process_user_message_and_images(kwargs["user_message"])

        # 处理聊天历史
        chat_history = history_service.process_chat_history(kwargs["chat_history"], kwargs.get("conversation_window_size", 10), image_data)

        # 处理 skill_params: 解密并替换 prompt 中的 {{key}} 占位符
        resolved_prompt = resolve_skill_params(kwargs["skill_prompt"], kwargs.get("skill_params", []))

        # 构建聊天参数
        chat_kwargs = {
            "openai_api_base": llm_model.openai_api_base,
            "openai_api_key": llm_model.openai_api_key,
            "model": llm_model.model_name,
            "protocol_type": llm_model.protocol_type,
            "system_message_prompt": resolved_prompt,
            "temperature": kwargs["temperature"],
            "user_message": user_message,
            "chat_history": chat_history,
            "user_id": str(kwargs["user_id"]),
            "enable_naive_rag": kwargs["enable_rag"],
            "rag_stage": "string",
            "naive_rag_request": naive_rag_request,
            "enable_suggest": kwargs.get("enable_suggest", False),
            "enable_query_rewrite": kwargs.get("enable_query_rewrite", False),
            "locale": kwargs.get("locale", "en"),
        }

        if kwargs.get("thread_id"):
            chat_kwargs["thread_id"] = str(kwargs["thread_id"])
        elif kwargs.get("execution_id"):
            chat_kwargs["thread_id"] = str(kwargs["execution_id"])
        else:
            chat_kwargs["thread_id"] = str(uuid.uuid4())

        chat_kwargs["execution_id"] = kwargs.get("execution_id") or chat_kwargs.get("thread_id")
        if kwargs["enable_rag_knowledge_source"]:
            extra_config.update({"enable_rag_source": True})
        if kwargs.get("enable_rag_strict_mode"):
            extra_config.update({"enable_rag_strict_mode": kwargs["enable_rag_strict_mode"]})

        if kwargs.get("browser_use_force_task"):
            extra_config.update(
                {
                    "browser_use_base_task": kwargs.get("skill_prompt", ""),
                    "browser_use_user_message": user_message,
                    "browser_use_force_task": True,
                }
            )

        if kwargs["skill_type"] != SkillTypeChoices.KNOWLEDGE_TOOL:
            ChatService._process_tools_and_extra_config(kwargs, chat_kwargs, extra_config)
        elif extra_config:
            extra_config.update({"execution_id": chat_kwargs["execution_id"]})
            if kwargs.get("node_id"):
                extra_config["node_id"] = kwargs["node_id"]
            if kwargs.get("trigger_type"):
                extra_config["trigger_type"] = kwargs["trigger_type"]
            chat_kwargs.update({"extra_config": extra_config})
        return chat_kwargs, doc_map, title_map


# 创建服务实例
chat_service = ChatService()
