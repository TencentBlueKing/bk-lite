import asyncio
import concurrent.futures
import os
import re
import uuid
from typing import Any, Dict, Tuple

from apps.core.logger import opspilot_logger as logger
from apps.core.mixinx import EncryptMixin
from apps.core.utils.loader import LanguageLoader
from apps.opspilot.models import LLMModel, SkillTools, SkillTypeChoices
from apps.opspilot.metis.llm.chain.report_renderers import strip_phantom_tool_calls
from apps.opspilot.services.builtin_tools import (
    BUILTIN_ATTACHMENT_FILE_TOOL_NAME,
    BUILTIN_MONITOR_TOOL_NAME,
    BUILTIN_MSSQL_TOOL_NAME,
    BUILTIN_MYSQL_TOOL_NAME,
    BUILTIN_ORACLE_TOOL_NAME,
    BUILTIN_REDIS_TOOL_NAME,
    build_builtin_attachment_file_runtime_tool,
    build_builtin_monitor_runtime_tool,
    build_builtin_mssql_runtime_tool,
    build_builtin_mysql_runtime_tool,
    build_builtin_oracle_runtime_tool,
    build_builtin_redis_runtime_tool,
)
from apps.opspilot.services.chat_request import ChatRequest
from apps.opspilot.services.history_service import history_service
from apps.opspilot.services.wiki.wiki_context_service import augment_prompt
from apps.opspilot.utils.agent_factory import create_agent_instance
from apps.opspilot.utils.prompt_utils import resolve_skill_params


def _truncate_candidate_title(text, limit=60):
    """从回答文本截取候选页标题(首行/前 N 字符)。"""
    if not text:
        return ""
    first_line = (text.strip().splitlines() or [""])[0].strip()
    if not first_line:
        return ""
    return first_line[:limit]


def _maybe_save_answer_as_wiki_candidate(kwargs, chat_result, doc_map):
    """如果 kwargs.wiki_save_answer_as_candidate=True 且有 wiki_kb_ids 且回答引用了 wiki 文档,
    自动调用 save_answer_candidate_page 把回答保存为待审核候选页。

    用于"高价值回答沉淀"——避免 UI 漏触发。返回落库后的 KnowledgePage 或 None。
    """
    if not kwargs.get("wiki_save_answer_as_candidate"):
        return None
    if not chat_result.get("success"):
        return None
    wiki_kb_ids = kwargs.get("wiki_kb_ids") or []
    if not wiki_kb_ids:
        return None
    # 只在 doc_map 中存在 wiki 来源时才落候选——避免把非 wiki 回答存到 wiki
    wiki_doc_marker = kwargs.get("wiki_doc_marker", "wiki")
    has_wiki_doc = False
    if isinstance(doc_map, dict):
        for value in doc_map.values():
            if isinstance(value, dict) and value.get("source") == wiki_doc_marker:
                has_wiki_doc = True
                break
    if not has_wiki_doc:
        return None
    # 落候选(用第一个 wiki KB,实际 KB 由调用方按规则选)
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.page_service import save_answer_candidate_page

    kb = WikiKnowledgeBase.objects.filter(id=wiki_kb_ids[0]).first()
    if not kb:
        return None
    body = chat_result.get("message", "") or ""
    title = _truncate_candidate_title(body)
    if not title:
        return None
    try:
        return save_answer_candidate_page(
            knowledge_base=kb,
            page_type="qa",
            title=title,
            body=body,
            source_conversation_id=str(kwargs.get("chat_id") or ""),
            source_message_id=str(kwargs.get("message_id") or ""),
            source_channel="chat_service",
            created_by=str(kwargs.get("user") or kwargs.get("username") or ""),
        )
    except Exception:  # noqa: BLE001 - 自动落候选失败不应阻塞 chat 主流程
        logger.exception("chat_service 自动落候选失败")
        return None


def _optional_positive_int(value):
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _wiki_context_options(kwargs):
    options = {}
    if kwargs.get("wiki_retrieval_mode"):
        options["retrieval_mode"] = kwargs["wiki_retrieval_mode"]
    graph_hops = _optional_positive_int(kwargs.get("wiki_graph_hops"))
    if graph_hops is not None:
        options["graph_hops"] = graph_hops
    token_budget = _optional_positive_int(kwargs.get("wiki_token_budget"))
    if token_budget:
        options["token_budget"] = token_budget
    top_k = _optional_positive_int(kwargs.get("wiki_top_k"))
    if top_k:
        options["top_k"] = top_k
    return options


def _resolve_agent_execute_timeout() -> int:
    """整轮 agent 执行预算（秒）：覆盖一次 invoke_chat 内的全部多轮 LLM + 工具调用。

    优先 AGENT_EXECUTE_TIMEOUT；兼容旧的 LLM_INVOKE_TIMEOUT；默认 300。
    单次 LLM 调用超时仍由 LLM_INVOKE_TIMEOUT 控制（见 llm_client_factory），二者解耦。
    """
    return int(os.getenv("AGENT_EXECUTE_TIMEOUT") or os.getenv("LLM_INVOKE_TIMEOUT") or "300")


def _is_eventlet_environment() -> bool:
    """检测当前进程是否运行在 eventlet monkey patch 环境中。"""
    try:
        import eventlet.patcher

        return bool(eventlet.patcher.is_monkey_patched("socket"))
    except Exception:
        return False


def _cancel_all_tasks(loop: asyncio.AbstractEventLoop) -> None:
    """取消事件循环中所有待处理的任务，确保资源正确释放。"""
    to_cancel = asyncio.all_tasks(loop)
    if not to_cancel:
        return
    for task in to_cancel:
        task.cancel()
    loop.run_until_complete(asyncio.gather(*to_cancel, return_exceptions=True))


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
        data, _doc_map, _title_map = ChatService.invoke_chat(kwargs)
        return {"content": data["message"], "citing_knowledge": []}

    @staticmethod
    def invoke_chat(kwargs: Dict[str, Any]) -> Tuple[Dict, Dict, Dict]:
        """
        调用聊天服务并处理结果

        Args:
            kwargs: 包含聊天所需参数的字典

        Returns:
            处理后的数据、文档映射和标题映射
        """
        # 将原始 kwargs 一次性解析为类型化的 ChatRequest（容忍未知键），
        # 缺失的可选键使用其默认值，缺失的必需键给出清晰错误（仍为 KeyError 子类）。
        request = ChatRequest.from_kwargs(kwargs)

        llm_model = LLMModel.objects.get(id=request.llm_model)
        show_think = request.show_think
        skill_type = request.skill_type
        # 与历史行为一致：在转发给 format_chat_server_kwargs 之前从原始 dict 中移除这些键。
        kwargs.pop("show_think", True)
        kwargs.pop("group", 0)

        # 处理用户消息和图片
        chat_kwargs, doc_map, title_map = ChatService.format_chat_server_kwargs(kwargs, llm_model)

        try:
            # 创建 agent 实例并直接执行
            graph, request = create_agent_instance(skill_type, chat_kwargs)

            if _is_eventlet_environment():
                raise RuntimeError("当前 Celery worker 使用 eventlet 池，不支持异步执行，请改用 --pool threads 或 solo")

            # 调用 agent 的 execute 方法（非流式同步执行）
            # 在独立线程中创建全新事件循环来执行异步代码，避免与 ASGI 主事件循环交互导致死锁
            def _run_in_new_loop():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(graph.execute(request))
                finally:
                    # 清理所有待处理的异步资源（如 httpx 连接池）
                    try:
                        _cancel_all_tasks(loop)
                        loop.run_until_complete(loop.shutdown_asyncgens())
                        loop.run_until_complete(loop.shutdown_default_executor())
                    except Exception:
                        pass
                    loop.close()

            # 整轮 agent 执行预算（含多轮 LLM + 工具调用），独立于单次 LLM 调用超时
            _agent_timeout = _resolve_agent_execute_timeout()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_run_in_new_loop)
                response = future.result(timeout=_agent_timeout)

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

            # 抹掉 LLM 幻觉的 phantom <tool_call> 文本
            # 流式 agui_stream 路径已在 _handle_chat_model_stream_content /
            # _handle_chat_model_end_event 中 strip,这里是非流式 invoke_chat 路径
            # 的兜底,避免漏到 wiki 候选/调用方。
            if result.get("message"):
                result["message"] = strip_phantom_tool_calls(result["message"])

            # 自动落候选:在 chat 完成后,如果 kwargs 标记保存且有 wiki 引用,把回答落为待审核候选页
            saved_page = _maybe_save_answer_as_wiki_candidate(kwargs, result, doc_map)
            if saved_page is not None:
                result["saved_wiki_candidate_id"] = saved_page.id

            return result, doc_map, title_map

        except concurrent.futures.TimeoutError:
            # 整轮 agent 执行超时，worker 线程已放弃等待
            _agent_timeout = _resolve_agent_execute_timeout()
            logger.error(f"invoke_chat agent 执行超时（>{_agent_timeout}s）: skill_type={skill_type}")
            loader = LanguageLoader(app="opspilot", default_lang="en")
            message = loader.get("error.llm_timeout") or f"智能体执行超时（>{_agent_timeout}s），请稍后重试"
            return (
                {
                    "message": message,
                    "success": False,
                    "error_type": "TimeoutError",
                    "error": f"agent execute timeout after {_agent_timeout}s",
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "browser_steps": [],
                },
                doc_map,
                title_map,
            )

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
            BUILTIN_ATTACHMENT_FILE_TOOL_NAME: None,
            BUILTIN_MONITOR_TOOL_NAME: None,
            BUILTIN_REDIS_TOOL_NAME: None,
            BUILTIN_MYSQL_TOOL_NAME: None,
            BUILTIN_ORACLE_TOOL_NAME: None,
            BUILTIN_MSSQL_TOOL_NAME: None,
        }
        builtin_builders = {
            BUILTIN_ATTACHMENT_FILE_TOOL_NAME: build_builtin_attachment_file_runtime_tool,
            BUILTIN_MONITOR_TOOL_NAME: build_builtin_monitor_runtime_tool,
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

        tool_map = {
            i["id"]: {u["key"]: u["value"] for u in i["kwargs"] if u.get("key")}
            for i in selected_tools
            if isinstance(i.get("id"), int) and i["id"] > 0
        }

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
            else:
                pass

            # 多实例检测（不区分 builtin 与否）
            tool_kwargs = tool_map.get(skill_tool.id, {})
            k8s_instances_raw = tool_kwargs.get("kubernetes_instances")
            # 使用 parse_kubernetes_instances 正确解析（支持 JSON 字符串和 list）
            from apps.opspilot.metis.llm.tools.kubernetes.connection import parse_kubernetes_instances

            k8s_instances = parse_kubernetes_instances(k8s_instances_raw) if k8s_instances_raw else []
            if len(k8s_instances) == 1:
                instance = k8s_instances[0]
                if instance.get("name"):
                    extra_config["instance_name"] = instance["name"]
                if instance.get("id"):
                    extra_config["instance_id"] = instance["id"]
            elif len(k8s_instances) > 1:
                instance_names = [inst.get("name", "") for inst in k8s_instances if inst.get("name")]
                if instance_names:
                    options_json = ", ".join(f'"{name}"' for name in instance_names)
                    count = len(instance_names)
                    k8s_prompt = (
                        f"\n[多集群环境] 当前有 {count} 个可用集群: [{options_json}]。\n"
                        "【重要】如果用户只是打招呼（hello/你好/hi等）或闲聊，直接用纯文本回复问候，"
                        "不要调用任何工具，不要调用 request_user_choice，不要提及集群。\n\n"
                        "以下集群选择规则仅在用户明确要求执行 Kubernetes 操作时生效：\n"
                        "- 用户提到了某个具体工作负载名称（如 'payment-gateway'）→ 用 search_workload_across_namespaces 搜索它在哪些集群中存在。"
                        "如果只在一个集群找到则直接操作；如果多个集群都有则必须调用 request_user_choice 让用户选择目标集群后再执行。\n"
                        "- 用户要执行 K8s 操作但没有指定集群名 → 必须先调用 request_user_choice，让用户从真实集群名中选择一个目标集群后再执行\n"
                        "- 用户明确说了集群名 → 直接操作该集群\n"
                        "- 用户说 '所有工作负载/全部工作负载' 只是工作负载范围，不是全部集群范围；多集群时仍然必须先选择目标集群\n"
                        "【禁止】用户说'所有工作负载'时，不要调用 search_workload_across_namespaces，那是用于搜索特定名称的。\n"
                        "【禁止】用户已经指定了工作负载名称时，不允许跳过搜索直接问用户选集群。必须先搜索。"
                    )
                    tool_params["extra_tools_prompt"] = tool_params.get("extra_tools_prompt", "") + k8s_prompt
                    extra_config["_multi_instance_options"] = instance_names
            tools.append(tool_params)

        for name, builder in builtin_builders.items():
            if name in selected_builtin_kwargs and name not in loaded_tool_names:
                tools.append(builder(selected_builtin_kwargs[name]))

        for i in tool_map.values():
            extra_config.update(i)
        extra_config.update({"execution_id": chat_kwargs["execution_id"]})
        if kwargs.get("attachment_id"):
            extra_config["attachment_id"] = kwargs["attachment_id"]
        if kwargs.get("node_id"):
            extra_config["node_id"] = kwargs["node_id"]
        if kwargs.get("trigger_type"):
            extra_config["trigger_type"] = kwargs["trigger_type"]

        # 当 attachment_file 工具被启用时，向系统提示词末尾注入强制调用指令，
        # 防止用户 skill_prompt 中的"直接输出"类指令覆盖工具调用意图。
        if BUILTIN_ATTACHMENT_FILE_TOOL_NAME in selected_builtin_kwargs:
            attachment_override = (
                "\n\n【附件生成强制规则 - 最高优先级，不可违反】\n"
                "当前工作流已配置文件生成工具 generate_attachment_file。\n"
                "* 如果任务目标涉及生成、创建、导出任何文件、报告或文档，"
                "必须调用 generate_attachment_file 工具，绝对不允许将文件内容以纯文字直接输出。\n"
                "* 工具调用成功后，仅输出简短摘要与工具返回的下载链接，不要重复输出完整内容。\n"
                "* 以上规则覆盖所有其他'直接输出'类指令。"
            )
            chat_kwargs["system_message_prompt"] = chat_kwargs.get("system_message_prompt", "") + attachment_override

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
        extra_config = {"show_think": show_think}

        user_message, image_data = history_service.process_user_message_and_images(kwargs["user_message"])

        # 处理聊天历史
        chat_history = history_service.process_chat_history(kwargs["chat_history"], kwargs.get("conversation_window_size", 10), image_data)

        # 处理 skill_params: 解密并替换 prompt 中的 {{key}} 占位符
        resolved_prompt = resolve_skill_params(kwargs["skill_prompt"], kwargs.get("skill_params", []))

        # Wiki 知识库复用:若技能选择了 Wiki 知识库,则检索并把上下文注入系统提示词
        wiki_kb_ids = kwargs.get("wiki_kb_ids")
        if wiki_kb_ids:
            resolved_prompt, wiki_citations = augment_prompt(resolved_prompt, wiki_kb_ids, user_message, **_wiki_context_options(kwargs))
            if wiki_citations:
                extra_config["wiki_citations"] = wiki_citations

        # 构建聊天参数
        chat_kwargs = {
            "openai_api_base": llm_model.openai_api_base,
            "openai_api_key": llm_model.openai_api_key,
            "model": llm_model.model_name,
            "protocol_type": llm_model.protocol_type,
            "vendor_type": llm_model.vendor.vendor_type if llm_model.vendor_id else "",
            "system_message_prompt": resolved_prompt,
            "temperature": kwargs["temperature"],
            "user_message": user_message,
            "chat_history": chat_history,
            "user_id": str(kwargs["user_id"]),
            "enable_naive_rag": False,
            "rag_stage": "string",
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

        if kwargs.get("browser_use_force_task"):
            extra_config.update(
                {
                    "browser_use_base_task": kwargs.get("skill_prompt", ""),
                    "browser_use_user_message": user_message,
                    "browser_use_force_task": True,
                }
            )

        import logging as _dbg_log
        if kwargs.get("matched_skill_packages") is not None:
            _dbg_log.warning("DEBUG_CHAT: matched_skill_packages count=%s, capabilities=%s", len(kwargs.get("matched_skill_packages") or []), kwargs.get("skill_package_capabilities"))
            extra_config.update(
                {
                    "matched_skill_packages": kwargs.get("matched_skill_packages") or [],
                    "skill_package_capabilities": kwargs.get("skill_package_capabilities") or [],
                    "skill_package_reports": kwargs.get("skill_package_reports") or {},
                    "skill_package_workflows": kwargs.get("skill_package_workflows") or {},
                }
            )

        # 用户显式选中的技能包全集(独立于 matched_skill_packages),
        # 用于 backend 物化,绕开 substring 匹配丢包。
        if kwargs.get("enabled_skill_packages") is not None:
            extra_config["enabled_skill_packages"] = kwargs.get("enabled_skill_packages") or []

        if kwargs["skill_type"] != SkillTypeChoices.KNOWLEDGE_TOOL:
            ChatService._process_tools_and_extra_config(kwargs, chat_kwargs, extra_config)
        elif extra_config:
            extra_config.update({"execution_id": chat_kwargs["execution_id"]})
            if kwargs.get("attachment_id"):
                extra_config["attachment_id"] = kwargs["attachment_id"]
            if kwargs.get("node_id"):
                extra_config["node_id"] = kwargs["node_id"]
            if kwargs.get("trigger_type"):
                extra_config["trigger_type"] = kwargs["trigger_type"]
            chat_kwargs.update({"extra_config": extra_config})
        return chat_kwargs, doc_map, title_map


# 创建服务实例
chat_service = ChatService()
